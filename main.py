#!/usr/bin/env python3
import os
import random
import signal
import sys
import time

import requests
from config import load_zsolver_key, load_faceunlock_key
from api_client import ZeroSolverClient
from faceunlock_client import FaceUnlockClient

DEFAULT_ACCOUNTS_FILE = "accs.txt"

client = None
fu_client = None
_credits_cache = None
_fu_balance_cache = None


def refresh_balance():
    global _credits_cache
    try:
        _credits_cache = client.get_credits()
    except Exception:
        _credits_cache = None
    return _credits_cache


def refresh_fu_balance():
    global _fu_balance_cache
    try:
        _fu_balance_cache = fu_client.get_balance()
    except Exception:
        _fu_balance_cache = None
    return _fu_balance_cache


def clear():
    os.system("cls" if os.name == "nt" else "clear")


def pause():
    input("\nPress Enter to continue...")


# ── ASCII helpers (same style as cli.py) ─────────────

def log(msg=""):
    print(msg, flush=True)


def header(title, width=54):
    pad = (width - len(title) - 2) // 2
    sep = "-" * (width - 2)
    log()
    log(f"  .{sep}.")
    log(f"  |{' ' * pad} {title} {' ' * (width - pad - len(title) - 3)}|")
    log(f"  '{sep}'")


def field(key, val, w=20):
    log(f"    {key:<{w}} {val}")


def sep(width=54):
    log(f"  {'-' * width}")


def ok(msg):
    log(f"   [+] {msg}")


def warn(msg):
    log(f"   [!] {msg}")


def badge(status):
    m = {"pending": "[PENDING]", "processing": "[  ..  ]",
         "completed": "[ DONE  ]", "failed": "[ FAIL  ]",
         "cancelled": "[ STOP  ]"}
    return m.get(status, f"[{status.upper()}]")


def progress_bar(p, t, w=20):
    if t == 0:
        return "[" + " " * w + "]"
    filled = int(p / t * w)
    return "[" + "#" * filled + "." * (w - filled) + "]"


def watch_loop(job_id, interval=3):
    while True:
        d = client.get_status(job_id)
        s = d["status"]
        p, t = d["processed"], d["total_accounts"]
        ok_, already, fail = d.get("successful", 0), d.get("already_solved", 0), d.get("failed", 0)
        charged = d.get("charged_credits", "?")
        bar = progress_bar(p, t)
        line = f"    {badge(s)}  {bar}  {p:>4}/{t:<4}  +{ok_}  o{already}  x{fail}  ${charged}"
        if s in ("completed", "failed", "cancelled"):
            log(line)
            return d
        print(line, end="\r", flush=True)
        time.sleep(interval)


def watch_loop_fu(job_id, interval=3):
    while True:
        d = fu_client.get_status(job_id)
        s = d["status"]
        p, t = d["processed"], d["total_accounts"]
        ok_, fail, other = d.get("successful", 0), d.get("failed", 0), d.get("other_failed", 0)
        bar = progress_bar(p, t)
        line = f"    {badge(s)}  {bar}  {p:>4}/{t:<4}  +{ok_}  x{fail}  o{other}"
        if s in ("completed", "failed", "cancelled"):
            log(line)
            return d
        print(line, end="\r", flush=True)
        time.sleep(interval)


def cmd_credits():
    clear()
    header("CREDITS")
    data = client.get_credits()
    global _credits_cache
    _credits_cache = data
    field("Balance:", f"{data['balance']:.2f}")
    field("Reserved:", f"{data['reserved']:.2f}")
    field("Available:", f"{data['effective']:.2f}")
    sep()
    field("In-game solve:", f"{data['cost_per_success']} cr")
    field("Captcha-lock:", f"{data['captcha_lock_cost_per_success']} cr")
    log()
    pause()


def cmd_submit():
    clear()
    filepath = input(f"  Accounts file [{DEFAULT_ACCOUNTS_FILE}]: ").strip()
    if not filepath:
        filepath = DEFAULT_ACCOUNTS_FILE
    if not os.path.exists(filepath):
        warn(f"{filepath} not found")
        pause()
        return
    with open(filepath, encoding="utf-8") as f:
        accounts_text = f.read()
    acct_lines = [l for l in accounts_text.strip().splitlines() if l.strip()]
    if not acct_lines:
        warn(f"{filepath} is empty")
        pause()
        return

    header("SUBMIT")
    refresh_balance()
    if _credits_cache:
        field("Available", f"{_credits_cache['effective']:.2f} cr")
    field("Accounts", len(acct_lines))
    sep()

    fu_first = input("  Pre-process with Face Unlock first? [y/N]: ").strip().lower()

    if fu_first == "y":
        header("STEP 1/2 - FACE UNLOCK")
        try:
            refresh_fu_balance()
            if _fu_balance_cache:
                field("FU Balance", f"${_fu_balance_cache['effective']:.2f}")
        except Exception:
            pass
        est_fu = len(acct_lines) * 0.05
        field("Est. FU cost", f"${est_fu:.2f} max")
        sep()
        log("    Submitting...")
        fu_data = fu_client.submit(accounts_text)
        fu_job_id = fu_data["job_id"]
        field("Job ID", fu_job_id)
        field("Total", fu_data['total_accounts'])
        field("DB match", fu_data.get('db_accounts_count', 0))
        field("Paid", fu_data.get('paid_accounts_count', 0))
        field("Est. cost", f"${fu_data['estimated_cost']:.2f}")
        w = input("\n  Watch face unlock progress? [y/N]: ").strip().lower()
        if w == "y":
            log()
            fu_result = watch_loop_fu(fu_job_id)
            if fu_result["status"] == "completed" and fu_result.get("result_files"):
                dl = input("  Download face unlock results? [y/N]: ").strip().lower()
                if dl == "y":
                    log()
                    for f_info in fu_result["result_files"]:
                        content = fu_client.download(fu_job_id, f_info["filename"])
                        if content is not None:
                            out = f"{fu_job_id}_{f_info['filename']}"
                            with open(out, "w", encoding="utf-8") as f:
                                f.write(content)
                            ok(f"{out}")
        sep()

    header("STEP 2/2 - CAPTCHA SOLVE")
    log("  Solver type:")
    log("    1. In-game (default, 0.0025 credits each)")
    log("    2. Captcha-lock (0.005 credits each)")
    st = input("  Choice [1]: ").strip()
    captcha_type = "captchalock" if st == "2" else "ingame"
    rate = 0.005 if st == "2" else 0.0025
    max_cost = len(acct_lines) * rate
    if _credits_cache:
        log()
        field("Max cost", f"{max_cost:.4f} cr")
        field("Available", f"{_credits_cache['effective']:.2f} cr")
        if max_cost > _credits_cache["effective"]:
            warn("Not enough credits!")
    log()
    log("    Submitting...")
    data = client.submit(accounts_text, captcha_type)
    job_id = data["job_id"]
    field("Job ID", job_id)
    field("Accounts", data['total_accounts'])
    field("Est. cost", f"{data['estimated_cost']} cr")
    field("Per success", f"{data['cost_per_success']} cr")
    refresh_balance()
    if _credits_cache:
        field("Remaining", f"{_credits_cache['effective']:.2f} cr")
    w = input("\n  Watch progress? [y/N]: ").strip().lower()
    if w == "y":
        log()
        result = watch_loop(job_id)
        if result["status"] == "completed":
            refresh_balance()
            if _credits_cache:
                log()
                field("Charged", f"{result['charged_credits']} cr")
                field("Balance", f"{_credits_cache['effective']:.2f} cr")
            auto = input("  Download results now? [y/N]: ").strip().lower()
            if auto == "y":
                log()
                for filename in result.get("result_files", []):
                    content = client.download(job_id, filename)
                    if content is not None:
                        with open(filename, "w", encoding="utf-8") as f:
                            f.write(content)
                        cnt = len([l for l in content.splitlines() if l.strip()])
                        ok(f"{filename}  ({cnt} lines)")
    sep()
    pause()


def cmd_status():
    clear()
    header("STATUS")
    job_id = input("  Job ID: ").strip()
    if not job_id:
        return
    field("Job ID", job_id)
    sep()
    w = input("  Watch progress? [y/N]: ").strip().lower()
    while True:
        clear()
        header("STATUS")
        field("Job ID", job_id)
        sep()
        d = client.get_status(job_id)
        s = d["status"]
        p, t = d["processed"], d["total_accounts"]
        bar = progress_bar(p, t)
        field("Status", s.upper())
        field("Progress", f"{bar}  {p}/{t}")
        field("Solved", d["successful"])
        field("Already", d["already_solved"])
        field("Failed", d["failed"])
        field("Charged", f"{d.get('charged_credits', '?')} cr")
        if s in ("completed", "failed", "cancelled"):
            if s == "completed" and d.get("result_files"):
                log(f"    Files: {', '.join(d['result_files'])}")
            break
        if w != "y":
            break
        time.sleep(3)
    pause()


def cmd_download():
    clear()
    header("DOWNLOAD")
    job_id = input("  Job ID: ").strip()
    if not job_id:
        return
    field("Job ID", job_id)
    sep()
    log("  Source:")
    log("    1. ZeroSolver (captcha)")
    log("    2. Face Unlock")
    src = input("  Choice [1]: ").strip()
    if src == "2":
        data = fu_client.get_status(job_id)
        if data["status"] != "completed":
            field("Status", f"{data['status']} — wait")
            pause()
            return
        for f_info in data.get("result_files", []):
            content = fu_client.download(job_id, f_info["filename"])
            if content is not None:
                out = f"{job_id}_{f_info['filename']}"
                with open(out, "w", encoding="utf-8") as f:
                    f.write(content)
                lines = len([l for l in content.splitlines() if l.strip()])
                ok(f"{out}  ({lines} lines)")
            else:
                warn(f"{f_info['filename']}: not found")
    else:
        data = client.get_status(job_id)
        if data["status"] != "completed":
            field("Status", f"{data['status']} — wait")
            pause()
            return
        for filename in data.get("result_files", []):
            content = client.download(job_id, filename)
            if content is not None:
                with open(filename, "w", encoding="utf-8") as f:
                    f.write(content)
                lines = len([l for l in content.splitlines() if l.strip()])
                ok(f"{filename}  ({lines} lines)")
            else:
                warn(f"{filename}: not found")
        if not data.get("result_files"):
            warn("No result files available.")
    pause()


def cmd_cancel():
    clear()
    header("CANCEL")
    job_id = input("  Job ID: ").strip()
    if not job_id:
        return
    log("  Source:")
    log("    1. ZeroSolver (captcha)")
    log("    2. Face Unlock")
    src = input("  Choice [1]: ").strip()
    if src == "2":
        c = input(f"  Cancel Face Unlock job {job_id}? [y/N]: ").strip().lower()
        if c == "y":
            fu_client.cancel(job_id)
            ok(f"Job {job_id} cancelled.")
            refresh_fu_balance()
            if _fu_balance_cache:
                field("FU Balance", f"${_fu_balance_cache['effective']:.2f}")
    else:
        c = input(f"  Cancel ZeroSolver job {job_id}? [y/N]: ").strip().lower()
        if c == "y":
            client.cancel(job_id)
            ok(f"Job {job_id} cancelled.")
            refresh_balance()
            if _credits_cache:
                field("Balance", f"{_credits_cache['effective']:.2f} cr")
    pause()


def cmd_active():
    clear()
    header("ACTIVE JOBS")
    refresh_balance()
    if _credits_cache:
        b = _credits_cache
        field("Balance", f"{b['balance']:.2f}")
        field("Reserved", f"{b['reserved']:.2f}")
        field("Available", f"{b['effective']:.2f}")
        sep()

    data = client.get_active()
    jobs = data.get("jobs", [])
    if not jobs:
        log("    (no active ZeroSolver jobs)")
    else:
        log(f"    {'Job ID':<38} {'Status':<12}  {'Prog':>6}   Results")
        sep(58)
        for j in jobs:
            prog = f"{j['processed']}/{j['total_accounts']}"
            res = f"+{j['successful']} o{j['already_solved']} x{j['failed']}"
            log(f"    {j['job_id']:<38} {j['status']:<12}  {prog:>6}   {res}")

    try:
        fu_data = fu_client.get_active()
        fu_jobs = fu_data.get("jobs", [])
        if fu_jobs:
            log()
            log(f"    {'Job ID':<38} {'Status':<12}  {'Prog':>6}   Results")
            sep(58)
            for j in fu_jobs:
                q = "P" if j.get("priority") else "S"
                prog = f"{j['processed']}/{j['total_accounts']}"
                res = f"+{j['successful']} x{j.get('failed', 0)}"
                log(f"    {j['job_id']:<38} {q} {j['status']:<10}  {prog:>6}   {res}")
    except Exception:
        pass
    pause()


def cmd_faceunlock():
    clear()
    filepath = input(f"  Accounts file [{DEFAULT_ACCOUNTS_FILE}]: ").strip()
    if not filepath:
        filepath = DEFAULT_ACCOUNTS_FILE
    if not os.path.exists(filepath):
        warn(f"{filepath} not found")
        pause()
        return
    with open(filepath, encoding="utf-8") as f:
        accounts_text = f.read()
    acct_lines = [l for l in accounts_text.strip().splitlines() if l.strip()]
    if not acct_lines:
        warn(f"{filepath} is empty")
        pause()
        return

    header("FACE UNLOCK")
    refresh_fu_balance()
    if _fu_balance_cache:
        field("Balance", f"${_fu_balance_cache['effective']:.2f}")
    field("Accounts", len(acct_lines))
    log("  Queue:")
    log("    1. Standard ($0.05/acc)")
    log("    2. Priority ($0.10/acc)")
    q = input("  Choice [1]: ").strip()
    priority = q == "2"
    rate = 0.10 if priority else 0.05
    max_cost = len(acct_lines) * rate
    field("Rate", f"${rate}/acc")
    field("Max", f"${max_cost:.2f}")
    if _fu_balance_cache and max_cost > _fu_balance_cache["effective"]:
        warn("Not enough balance!")
    sep()

    log("    Submitting...")
    data = fu_client.submit(accounts_text, priority=priority)
    job_id = data["job_id"]
    field("Job ID", job_id)
    field("Total", data['total_accounts'])
    field("DB match", data.get('db_accounts_count', 0))
    field("Paid", data.get('paid_accounts_count', 0))
    field("Est. cost", f"${data['estimated_cost']:.2f}")
    field("Queue", "Priority" if priority else "Standard")
    refresh_fu_balance()
    if _fu_balance_cache:
        field("Remaining", f"${_fu_balance_cache['effective']:.2f}")
    w = input("\n  Watch progress? [y/N]: ").strip().lower()
    if w == "y":
        log()
        result = watch_loop_fu(job_id)
        if result["status"] == "completed":
            refresh_fu_balance()
            log()
            field("Unlocked", result.get('successful', 0))
            if _fu_balance_cache:
                field("Balance", f"${_fu_balance_cache['effective']:.2f}")
            auto = input("  Download results now? [y/N]: ").strip().lower()
            if auto == "y":
                log()
                for f_info in result.get("result_files", []):
                    content = fu_client.download(job_id, f_info["filename"])
                    if content is not None:
                        out = f"{job_id}_{f_info['filename']}"
                        with open(out, "w", encoding="utf-8") as f:
                            f.write(content)
                        cnt = len([l for l in content.splitlines() if l.strip()])
                        ok(f"{out}  ({cnt} lines)")
    sep()
    pause()



def sleep_range(lo=10, hi=60):
    t = random.randint(lo, hi)
    bar = progress_bar(0, t)
    log(f"    Sleeping {t}s  {bar}")
    for i in range(t):
        if i % 5 == 0 and i > 0:
            print(f"    Sleeping {t}s  {progress_bar(i, t)}", end="\r", flush=True)
        time.sleep(1)
    log(f"    Sleeping {t}s  {progress_bar(t, t)}")


def _raw_submit(client, text, label, captcha_type="ingame"):
    while True:
        try:
            jd = client.submit(text, captcha_type)
            return jd
        except SystemExit as e:
            msg = str(e)
            if "429" in msg.lower() or "rate" in msg.lower():
                import re
                m = re.search(r"(\d+)s", msg)
                w = int(m.group(1)) + random.randint(3, 10) if m else random.randint(60, 120)
                warn(f"Rate limited — waiting {w}s")
                time.sleep(w)
                continue
            raise


def cmd_autosolve():
    clear()
    header("AUTOSOLVE")
    log("    Press Ctrl+C to stop and return to menu.")
    log()
    filepath = input(f"  Accounts file [{DEFAULT_ACCOUNTS_FILE}]: ").strip()
    if not filepath:
        filepath = DEFAULT_ACCOUNTS_FILE
    cycle = 0

    def sigint(sig, frame):
        log("\n   [!] Returning to menu.")
        raise SystemExit(0)
    signal.signal(signal.SIGINT, sigint)

    while True:
        cycle += 1
        clear()
        header(f"AUTOSOLVE  cycle {cycle}")

        if not os.path.exists(filepath):
            warn(f"{filepath} not found — waiting")
            sleep_range(30, 60)
            continue

        with open(filepath, encoding="utf-8") as f:
            all_l = [l.strip() for l in f if l.strip()]
        if not all_l:
            warn(f"{filepath} is empty — waiting")
            sleep_range(30, 60)
            continue

        new_text = "\n".join(all_l)

        field("Accounts", len(all_l))
        sep()

        fu_ok = 0
        zs_ok = 0
        zs_already = 0

        try:
            log("  [1] Face Unlock")
            time.sleep(random.uniform(2, 4))
            fd = _raw_submit(fu_client, new_text, "FU")
            fid = fd["job_id"]
            log(f"      Job {fid}")
            fr = watch_loop_fu(fid)
            fu_ok = fr.get("successful", 0)
            if fr["status"] != "completed":
                warn(f"Face unlock failed ({fr['status']})")
                sleep_range(30, 60)
                continue

            log(f"    Waiting 350s before captcha solve...")
            sleep_range(350, 350)
            log("  [2] Captcha Solve (captcha-lock)")
            time.sleep(random.uniform(1, 3))
            zd = _raw_submit(client, new_text, "ZS", captcha_type="captchalock")
            zid = zd["job_id"]
            log(f"      Job {zid}")
            zr = watch_loop(zid)
            zs_ok = zr.get("successful", 0)
            zs_already = zr.get("already_solved", 0)
            if zr["status"] != "completed":
                warn(f"Captcha solve ended: {zr['status']}")

        except SystemExit as e:
            if "Returning to menu" in str(e):
                return
            warn(str(e))
            sleep_range(30, 60)
            continue
        except requests.exceptions.RequestException as e:
            warn(f"Network: {e}")
            sleep_range(30, 60)
            continue

        sep()
        ok(f"Cycle {cycle} complete")
        field("Unlocked", f"{fu_ok}/{len(all_l)}")
        field("Captcha'd", f"{zs_ok} solved + {zs_already} already")
        sep()
        sleep_range(10, 60)


def main():
    global client, fu_client
    api_key = load_zsolver_key()
    client = ZeroSolverClient(api_key)
    try:
        fu_key = load_faceunlock_key()
        fu_client = FaceUnlockClient(fu_key)
    except SystemExit:
        fu_client = None

    refresh_balance()
    if fu_client:
        refresh_fu_balance()

    while True:
        clear()
        log("  .------------------------------------------.")
        log("  |        ZeroPoint  ZeroSolver             |")
        if _credits_cache:
            b = _credits_cache
            log(f"  |  ZS  {b['effective']:>6.2f}  cr    Res  {b['reserved']:>5.2f}           |")
        if _fu_balance_cache and fu_client:
            log(f"  |  FU  ${_fu_balance_cache['effective']:>5.2f}                              |")
        log("  |------------------------------------------|")
        log("  |  1. Credits                              |")
        log("  |  2. Submit Accounts                      |")
        log("  |  3. Job Status                           |")
        log("  |  4. Download Results                     |")
        log("  |  5. Cancel Job                           |")
        log("  |  6. Active Jobs                          |")
        if fu_client:
            log("  |  7. Face Unlock                          |")
        log("  |  8. Auto-Solve (continuous)              |")
        log("  |------------------------------------------|")
        log("  |  0. Exit                                 |")
        log("  '------------------------------------------'")
        choice = input("  Choice [0-8]: ").strip()
        dispatch = {
            "1": cmd_credits,
            "2": cmd_submit,
            "3": cmd_status,
            "4": cmd_download,
            "5": cmd_cancel,
            "6": cmd_active,
            "0": lambda: sys.exit(0),
        }
        if fu_client:
            dispatch["7"] = cmd_faceunlock
        dispatch["8"] = cmd_autosolve
        fn = dispatch.get(choice)
        if fn:
            fn()
        else:
            print("  Invalid choice.")
            time.sleep(1)


if __name__ == "__main__":
    main()
