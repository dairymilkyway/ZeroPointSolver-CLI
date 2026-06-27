#!/usr/bin/env python3
import argparse
import os
import random
import re
import signal
import sys
import time

import requests

from config import load_zsolver_key, load_faceunlock_key
from api_client import ZeroSolverClient
from faceunlock_client import FaceUnlockClient

DEFAULT_ACCOUNTS_FILE = "accs.txt"


# ── helpers ──────────────────────────────────────────

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


def read_accounts(filepath):
    if not os.path.exists(filepath):
        warn(f"{filepath} not found")
        sys.exit(1)
    with open(filepath, encoding="utf-8") as f:
        content = f.read()
    lines = [l for l in content.strip().splitlines() if l.strip()]
    if not lines:
        warn(f"{filepath} is empty")
        sys.exit(1)
    return content, lines


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


# ── watchers ─────────────────────────────────────────

def watch_until_done(client, job_id, interval=3):
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


def watch_until_done_fu(client, job_id, interval=3):
    while True:
        d = client.get_status(job_id)
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


def download_results(client, job_id, filenames):
    for fn in filenames:
        c = client.download(job_id, fn)
        if c is not None:
            out = f"{job_id}_{fn}"
            with open(out, "w", encoding="utf-8") as f:
                f.write(c)
            cnt = len([l for l in c.splitlines() if l.strip()])
            ok(f"{out}  ({cnt} lines)")
        else:
            warn(f"{fn}: not found")


def _raw_submit(client, text, label, captcha_type="ingame"):
    while True:
        try:
            jd = client.submit(text, captcha_type)
            if jd is None:
                warn("Submit returned None — retrying...")
                time.sleep(random.randint(10, 30))
                continue
            return jd
        except SystemExit as e:
            msg = str(e)
            if "429" in msg.lower() or "rate" in msg.lower():
                m = re.search(r"(\d+)s", msg)
                w = int(m.group(1)) + random.randint(3, 10) if m else random.randint(60, 120)
                warn(f"Rate limited — waiting {w}s")
                time.sleep(w)
                continue
            raise


# ── commands ─────────────────────────────────────────

def cmd_credits(client, args):
    header("CREDITS")
    d = client.get_credits()
    field("Balance:", f"{d['balance']:.2f}")
    field("Reserved:", f"{d['reserved']:.2f}")
    field("Available:", f"{d['effective']:.2f}")
    sep()
    field("In-game solve:", f"{d['cost_per_success']} cr")
    field("Captcha-lock:", f"{d['captcha_lock_cost_per_success']} cr")


def cmd_submit(client, args):
    fp = args.file or DEFAULT_ACCOUNTS_FILE
    text, lines = read_accounts(fp)
    ctype = "captchalock" if args.captchalock else "ingame"
    rate = 0.005 if args.captchalock else 0.0025

    header("SUBMIT")
    field("File", fp)
    field("Accounts", len(lines))
    field("Mode", ctype)
    try:
        bal = client.get_credits()
        field("Available", f"{bal['effective']:.2f} cr")
        field("Max cost", f"{len(lines) * rate:.4f} cr")
    except Exception:
        pass
    sep()

    if args.faceunlock:
        header("STEP 1/2 - FACE UNLOCK")
        try:
            fuk = load_faceunlock_key()
        except SystemExit as e:
            warn(str(e))
            sys.exit(1)
        fuc = FaceUnlockClient(fuk)
        try:
            b = fuc.get_balance()
            field("Balance", f"${b['effective']:.2f}")
        except Exception:
            pass
        priority = args.priority if hasattr(args, "priority") else False
        log()
        log("    Submitting...")
        fd = fuc.submit(text, priority=priority)
        fid = fd["job_id"]
        field("Job ID", fid)
        if "total_accounts" in fd:
            field("Total", fd["total_accounts"])
            field("DB match", fd.get("db_accounts_count", 0))
            field("Paid", fd.get("paid_accounts_count", 0))
            field("Est. cost", f"${fd['estimated_cost']:.2f}")
        log()
        fr = watch_until_done_fu(fuc, fid)
        if fr["status"] == "completed" and fr.get("result_files"):
            log()
            ok("Face unlock done — downloading...")
            download_results(fuc, fid, [f["filename"] for f in fr["result_files"]])
        sep()

    header("STEP 2/2 - CAPTCHA SOLVE")
    log("    Submitting...")
    d = _raw_submit(client, text, "captcha")
    jid = d["job_id"]
    field("Job ID", jid)
    field("Accounts", d["total_accounts"])
    field("Est. cost", f"{d['estimated_cost']} cr")
    field("Per success", f"{d['cost_per_success']} cr")

    if args.watch:
        log()
        r = watch_until_done(client, jid)
        if r["status"] == "completed" and r.get("result_files"):
            log()
            ok("Captcha done — downloading...")
            try:
                download_results(client, jid, r["result_files"])
            except Exception:
                pass
        try:
            bal = client.get_credits()
            sep()
            field("Remaining", f"{bal['effective']:.2f} cr")
        except Exception:
            pass


def cmd_status(client, args):
    header("STATUS")
    field("Job ID", args.job_id)
    sep()
    hit = False
    while True:
        if hit:
            sys.stdout.write("\033[8A\033[J")
        hit = True
        d = client.get_status(args.job_id)
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
                log(f"\n    Files: {', '.join(d['result_files'])}")
            return
        if not args.watch:
            return
        time.sleep(3)


def cmd_download(client, args):
    header("DOWNLOAD")
    field("Job ID", args.job_id)
    sep()
    d = client.get_status(args.job_id)
    if d["status"] != "completed":
        field("Status", f"{d['status']} — wait")
        return
    for fn in d.get("result_files", []):
        c = client.download(args.job_id, fn)
        if c is not None:
            with open(fn, "w", encoding="utf-8") as f:
                f.write(c)
            cnt = len([l for l in c.splitlines() if l.strip()])
            ok(f"{fn}  ({cnt} lines)")
        else:
            warn(f"{fn}: not found")


def cmd_cancel(client, args):
    header("CANCEL")
    client.cancel(args.job_id)
    ok(f"Cancelled {args.job_id}")


def cmd_active(client, args):
    header("ACTIVE JOBS")
    try:
        bal = client.get_credits()
        field("Balance", f"{bal['balance']:.2f}")
        field("Reserved", f"{bal['reserved']:.2f}")
        field("Available", f"{bal['effective']:.2f}")
        sep()
    except Exception:
        pass
    d = client.get_active()
    jobs = d.get("jobs", [])
    if not jobs:
        log("    (no active ZeroSolver jobs)")
    else:
        log(f"    {'Job ID':<38} {'Status':<12}  {'Prog':>6}   Results")
        sep(58)
        for j in jobs:
            prog = f"{j['processed']}/{j['total_accounts']}"
            res = f"+{j['successful']} o{j['already_solved']} x{j['failed']}"
            log(f"    {j['job_id']:<38} {j['status']:<12}  {prog:>6}   {res}")


def cmd_faceunlock(fuc, args):
    fp = args.file or DEFAULT_ACCOUNTS_FILE
    text, lines = read_accounts(fp)

    header("FACE UNLOCK")
    field("File", fp)
    field("Accounts", len(lines))
    try:
        b = fuc.get_balance()
        field("Balance", f"${b['effective']:.2f}")
    except Exception:
        pass
    rate = 0.10 if args.priority else 0.05
    field("Rate", f"${rate}/acc")
    field("Max", f"${len(lines) * rate:.2f}")
    sep()

    log("    Submitting...")
    d = fuc.submit(text, priority=args.priority)
    jid = d["job_id"]
    field("Job ID", jid)
    if "total_accounts" in d:
        field("Total", d["total_accounts"])
        field("DB match", d.get("db_accounts_count", 0))
        field("Paid", d.get("paid_accounts_count", 0))
        field("Est. cost", f"${d['estimated_cost']:.2f}")
    else:
        field("Status", "Reconnected to existing job")

    if args.watch:
        log()
        r = watch_until_done_fu(fuc, jid)
        if r["status"] == "completed" and r.get("result_files"):
            log()
            ok("Downloading results...")
            download_results(fuc, jid, [f["filename"] for f in r["result_files"]])
        try:
            b = fuc.get_balance()
            sep()
            field("Remaining", f"${b['effective']:.2f}")
        except Exception:
            pass


# ── autosolve ─────────────────────────────────────────

def sleep_range(lo=10, hi=60):
    t = random.randint(lo, hi)
    bar = progress_bar(0, t)
    log(f"    Sleeping {t}s  {bar}")
    for i in range(t):
        if i % 5 == 0 and i > 0:
            print(f"    Sleeping {t}s  {progress_bar(i, t)}", end="\r", flush=True)
        time.sleep(1)
    log(f"    Sleeping {t}s  {progress_bar(t, t)}")


def cmd_autosolve(client, args):
    fuk = load_faceunlock_key()
    fuc = FaceUnlockClient(fuk)
    fp = args.file or DEFAULT_ACCOUNTS_FILE
    cycle = 0

    def sigint(sig, frame):
        log("\n   [!] Stopped by user.")
        sys.exit(0)
    signal.signal(signal.SIGINT, sigint)

    while True:
        cycle += 1
        header(f"AUTOSOLVE  cycle {cycle}")

        if not os.path.exists(fp):
            warn(f"{fp} not found — waiting")
            sleep_range(30, 60)
            continue

        with open(fp, encoding="utf-8") as f:
            all_l = [l.strip() for l in f if l.strip()]
        if not all_l:
            warn(f"{fp} is empty — waiting")
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
            fd = _raw_submit(fuc, new_text, "FU")
            if not fd:
                warn("Face unlock submit failed — skipping cycle")
                sleep_range(30, 60)
                continue
            fid = fd["job_id"]
            log(f"      Job {fid}")
            fr = watch_until_done_fu(fuc, fid)
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
            if not zd:
                warn("Captcha submit failed — skipping cycle")
                sleep_range(30, 60)
                continue
            zid = zd["job_id"]
            log(f"      Job {zid}")
            zr = watch_until_done(client, zid)
            zs_ok = zr.get("successful", 0)
            zs_already = zr.get("already_solved", 0)
            if zr["status"] != "completed":
                warn(f"Captcha solve ended: {zr['status']}")

        except SystemExit as e:
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


def cmd_autosolve_captcha(client, args):
    fp = args.file or DEFAULT_ACCOUNTS_FILE
    cycle = 0

    def sigint(sig, frame):
        log("\n   [!] Stopped by user.")
        sys.exit(0)
    signal.signal(signal.SIGINT, sigint)

    while True:
        cycle += 1
        header(f"AUTOSOLVE CAPTCHA  cycle {cycle}")

        if not os.path.exists(fp):
            warn(f"{fp} not found — waiting")
            sleep_range(30, 60)
            continue

        with open(fp, encoding="utf-8") as f:
            all_l = [l.strip() for l in f if l.strip()]
        if not all_l:
            warn(f"{fp} is empty — waiting")
            sleep_range(30, 60)
            continue

        new_text = "\n".join(all_l)
        field("Accounts", len(all_l))
        sep()

        zs_ok = 0
        zs_already = 0

        try:
            log("  Submitting (in-game)...")
            time.sleep(random.uniform(1, 3))
            zd = _raw_submit(client, new_text, "ZS", captcha_type="ingame")
            if not zd:
                warn("Captcha submit failed — skipping cycle")
                sleep_range(30, 60)
                continue
            zid = zd["job_id"]
            log(f"      Job {zid}")
            zr = watch_until_done(client, zid)
            zs_ok = zr.get("successful", 0)
            zs_already = zr.get("already_solved", 0)
            if zr["status"] != "completed":
                warn(f"Captcha solve ended: {zr['status']}")

        except SystemExit as e:
            warn(str(e))
            sleep_range(30, 60)
            continue
        except requests.exceptions.RequestException as e:
            warn(f"Network: {e}")
            sleep_range(30, 60)
            continue

        sep()
        ok(f"Cycle {cycle} complete")
        field("Solved", f"{zs_ok} solved + {zs_already} already")
        sep()
        log("    Waiting 350s before next cycle...")
        sleep_range(350, 350)


# ── main ──────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        prog="zpsolver",
        description="ZeroPoint CLI — captcha solving and face unlock for Roblox accounts.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("credits", help="Check Solver Credits balance")

    p = sub.add_parser("submit", help="Submit accounts for solving")
    p.add_argument("-f", "--file", help=f"Account file (default: {DEFAULT_ACCOUNTS_FILE})")
    p.add_argument("--captchalock", action="store_true", help="Use captcha-lock solver")
    p.add_argument("-w", "--watch", action="store_true", help="Watch progress")
    p.add_argument("--faceunlock", action="store_true", help="Pre-process with Face Unlock first")

    p = sub.add_parser("status", help="Check job status")
    p.add_argument("job_id")
    p.add_argument("-w", "--watch", action="store_true", help="Poll until done")

    sub.add_parser("download", help="Download result files").add_argument("job_id")
    sub.add_parser("cancel", help="Cancel a job").add_argument("job_id")
    sub.add_parser("active", help="List active jobs")

    p = sub.add_parser("autosolve", help="Continuous autopilot: FU + captcha")
    p.add_argument("-f", "--file", help=f"Account file (default: {DEFAULT_ACCOUNTS_FILE})")

    p = sub.add_parser("autosolve-captcha", help="Continuous captcha-only (in-game)")
    p.add_argument("-f", "--file", help=f"Account file (default: {DEFAULT_ACCOUNTS_FILE})")

    p = sub.add_parser("faceunlock", help="Face unlock only")
    p.add_argument("-f", "--file", help=f"Account file (default: {DEFAULT_ACCOUNTS_FILE})")
    p.add_argument("-w", "--watch", action="store_true")
    p.add_argument("--priority", action="store_true", help="Priority queue (2x)")

    args = parser.parse_args()

    if args.command == "autosolve":
        cmd_autosolve(ZeroSolverClient(load_zsolver_key()), args)
        return
    if args.command == "autosolve-captcha":
        cmd_autosolve_captcha(ZeroSolverClient(load_zsolver_key()), args)
        return
    if args.command == "faceunlock":
        cmd_faceunlock(FaceUnlockClient(load_faceunlock_key()), args)
        return
    if args.command == "submit" and args.faceunlock:
        cmd_submit(ZeroSolverClient(load_zsolver_key()), args)
        return

    c = ZeroSolverClient(load_zsolver_key())
    dispatch = {
        "credits": cmd_credits, "submit": cmd_submit,
        "status": cmd_status, "download": cmd_download,
        "cancel": cmd_cancel, "active": cmd_active,
    }
    dispatch[args.command](c, args)


if __name__ == "__main__":
    main()
