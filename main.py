#!/usr/bin/env python3
import os
import sys
import time
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


def print_header(title):
    clear()
    print("  ZeroPoint ZeroSolver")
    print(f"  {'─' * 30}")
    if title:
        print(f"  {title}")
        print()


def watch_loop(job_id, interval=3):
    while True:
        data = client.get_status(job_id)
        status = data["status"]
        processed = data["processed"]
        total = data["total_accounts"]
        solved = data["successful"]
        already = data["already_solved"]
        failed = data["failed"]
        print(f"  [{status.upper()}] {processed}/{total}"
              f"  + {solved}  o {already}  x {failed}"
              f"  charged: {data['charged_credits']}")
        if status in ("completed", "failed", "cancelled"):
            return data
        time.sleep(interval)


def watch_loop_fu(job_id, interval=3):
    while True:
        data = fu_client.get_status(job_id)
        status = data["status"]
        processed = data["processed"]
        total = data["total_accounts"]
        solved = data.get("successful", 0)
        failed = data.get("failed", 0)
        other_failed = data.get("other_failed", 0)
        print(f"  [{status.upper()}] {processed}/{total}"
              f"  + {solved} unlocked"
              f"  x {failed} face failed"
              f"  other: {other_failed}")
        if status in ("completed", "failed", "cancelled"):
            return data
        time.sleep(interval)


def cmd_credits():
    print_header("CREDIT BALANCE")
    data = client.get_credits()
    global _credits_cache
    _credits_cache = data
    print(f"  Balance:   {data['balance']:.2f} credits")
    print(f"  Reserved:  {data['reserved']:.2f} credits")
    print(f"  Effective: {data['effective']:.2f} credits")
    print()
    print(f"  In-game solve:       {data['cost_per_success']} credits each")
    print(f"  Captcha-lock solve:  {data['captcha_lock_cost_per_success']} credits each")
    pause()


def cmd_submit():
    print_header("SUBMIT ACCOUNTS")
    refresh_balance()
    b = _credits_cache
    if b:
        print(f"  Credits: {b['effective']:.2f} available  (Reserved: {b['reserved']:.2f})")
        print()
    filepath = input(f"  Accounts file [{DEFAULT_ACCOUNTS_FILE}]: ").strip()
    if not filepath:
        filepath = DEFAULT_ACCOUNTS_FILE
    if not os.path.exists(filepath):
        print(f"\n  Error: {filepath} not found")
        pause()
        return
    with open(filepath, encoding="utf-8") as f:
        accounts_text = f.read()
    acct_lines = [l for l in accounts_text.strip().splitlines() if l.strip()]
    if not acct_lines:
        print(f"\n  Error: {filepath} is empty")
        pause()
        return
    print(f"  {len(acct_lines)} accounts loaded")
    print()

    fu_first = input("  Pre-process with Face Unlock first? [y/N]: ").strip().lower()

    if fu_first == "y":
        print()
        print("  ── Face Unlock Step ──")
        try:
            refresh_fu_balance()
            if _fu_balance_cache:
                print(f"  Face Unlock balance: ${_fu_balance_cache['effective']:.2f}")
        except Exception:
            pass
        est_fu = len(acct_lines) * 0.05
        print(f"  Estimated FU cost: ${est_fu:.2f} max")
        print()
        fu_data = fu_client.submit(accounts_text)
        fu_job_id = fu_data["job_id"]
        print(f"  Face Unlock Job ID: {fu_job_id}")
        print(f"  Total: {fu_data['total_accounts']} | Free: {fu_data.get('db_accounts_count', 0)} | Paid: {fu_data.get('paid_accounts_count', 0)}")
        print(f"  Estimated cost: ${fu_data['estimated_cost']:.2f}")
        w = input("\n  Watch face unlock progress? [y/N]: ").strip().lower()
        if w == "y":
            print()
            fu_result = watch_loop_fu(fu_job_id)
            if fu_result["status"] == "completed" and fu_result.get("result_files"):
                dl = input("  Download face unlock results? [y/N]: ").strip().lower()
                if dl == "y":
                    for f_info in fu_result["result_files"]:
                        content = fu_client.download(fu_job_id, f_info["filename"])
                        if content is not None:
                            with open(f_info["filename"], "w", encoding="utf-8") as f:
                                f.write(content)
                            print(f"  Downloaded {f_info['filename']}")
        print()

    print("  ── Captcha Solve Step ──")
    print("  Solver type:")
    print("    1. In-game (default, 0.0025 credits each)")
    print("    2. Captcha-lock (0.005 credits each)")
    st = input("  Choice [1]: ").strip()
    captcha_type = "captchalock" if st == "2" else "ingame"
    rate = 0.005 if st == "2" else 0.0025
    max_cost = len(acct_lines) * rate
    if b:
        print(f"\n  Max cost: {max_cost:.4f} credits  |  Available: {b['effective']:.2f}")
        if max_cost > b["effective"]:
            print("  ! Not enough credits for this job!")
    print()
    data = client.submit(accounts_text, captcha_type)
    job_id = data["job_id"]
    print(f"  Job ID: {job_id}")
    print(f"  Accounts: {data['total_accounts']}")
    print(f"  Estimated cost: {data['estimated_cost']} credits")
    print(f"  Cost per success: {data['cost_per_success']} credits")
    refresh_balance()
    if _credits_cache:
        print(f"  Balance after reservation: {_credits_cache['effective']:.2f}")
    w = input("\n  Watch progress? [y/N]: ").strip().lower()
    if w == "y":
        print()
        result = watch_loop(job_id)
        if result["status"] == "completed":
            refresh_balance()
            if _credits_cache:
                print(f"  Charged: {result['charged_credits']} | New balance: {_credits_cache['effective']:.2f}")
            auto = input("  Download results now? [y/N]: ").strip().lower()
            if auto == "y":
                for filename in result.get("result_files", []):
                    content = client.download(job_id, filename)
                    if content is not None:
                        with open(filename, "w", encoding="utf-8") as f:
                            f.write(content)
                        print(f"  Downloaded {filename}")
        print()
    pause()


def cmd_status():
    print_header("JOB STATUS")
    job_id = input("  Job ID: ").strip()
    if not job_id:
        return
    w = input("  Watch progress? [y/N]: ").strip().lower()
    hit = False
    while True:
        if hit:
            clear()
            print(f"  Job ID: {job_id}\n")
        hit = False
        data = client.get_status(job_id)
        status = data["status"]
        processed = data["processed"]
        total = data["total_accounts"]
        solved = data["successful"]
        already = data["already_solved"]
        failed = data["failed"]
        print(f"  [{status.upper()}] {processed}/{total}"
              f"  + {solved}  o {already}  x {failed}"
              f"  charged: {data['charged_credits']}")
        if status in ("completed", "failed", "cancelled"):
            if status == "completed" and data.get("result_files"):
                print(f"  Files: {', '.join(data['result_files'])}")
            break
        if w != "y":
            break
        hit = True
        time.sleep(3)
    pause()


def cmd_download():
    print_header("DOWNLOAD RESULTS")
    job_id = input("  Job ID: ").strip()
    if not job_id:
        return
    print("  Source:")
    print("    1. ZeroSolver (captcha)")
    print("    2. Face Unlock")
    src = input("  Choice [1]: ").strip()
    if src == "2":
        data = fu_client.get_status(job_id)
        if data["status"] != "completed":
            print(f"\n  Job is {data['status']} — not completed yet.")
            pause()
            return
        for f_info in data.get("result_files", []):
            content = fu_client.download(job_id, f_info["filename"])
            if content is not None:
                with open(f_info["filename"], "w", encoding="utf-8") as f:
                    f.write(content)
                lines = len([l for l in content.splitlines() if l.strip()])
                print(f"\n  Downloaded {f_info['filename']} ({lines} lines)")
            else:
                print(f"\n  {f_info['filename']}: not found")
    else:
        data = client.get_status(job_id)
        if data["status"] != "completed":
            print(f"\n  Job is {data['status']} — not completed yet.")
            pause()
            return
        for filename in data.get("result_files", []):
            content = client.download(job_id, filename)
            if content is not None:
                with open(filename, "w", encoding="utf-8") as f:
                    f.write(content)
                lines = len([l for l in content.splitlines() if l.strip()])
                print(f"\n  Downloaded {filename} ({lines} lines)")
            else:
                print(f"\n  {filename}: not found")
        if not data.get("result_files"):
            print("  No result files available.")
    pause()


def cmd_cancel():
    print_header("CANCEL JOB")
    job_id = input("  Job ID: ").strip()
    if not job_id:
        return
    print("  Source:")
    print("    1. ZeroSolver (captcha)")
    print("    2. Face Unlock")
    src = input("  Choice [1]: ").strip()
    if src == "2":
        c = input(f"  Cancel Face Unlock job {job_id}? [y/N]: ").strip().lower()
        if c == "y":
            fu_client.cancel(job_id)
            print(f"\n  Face Unlock job {job_id} cancelled.")
            refresh_fu_balance()
            if _fu_balance_cache:
                print(f"  FU Balance: ${_fu_balance_cache['effective']:.2f}")
    else:
        c = input(f"  Cancel ZeroSolver job {job_id}? [y/N]: ").strip().lower()
        if c == "y":
            client.cancel(job_id)
            print(f"\n  Job {job_id} cancelled.")
            refresh_balance()
            if _credits_cache:
                print(f"  Balance: {_credits_cache['effective']:.2f} credits")
    pause()


def cmd_active():
    print_header("ACTIVE JOBS")
    refresh_balance()
    if _credits_cache:
        b = _credits_cache
        print(f"  Balance: {b['balance']:.2f}  |  Reserved: {b['reserved']:.2f}  |  Available: {b['effective']:.2f}")
        print()
    data = client.get_active()
    jobs = data.get("jobs", [])
    if not jobs:
        print("  No active ZeroSolver jobs.")
    else:
        for job in jobs:
            print(f"  {job['job_id']}")
            print(f"    Status: {job['status']}")
            print(f"    Progress: {job['processed']}/{job['total_accounts']}"
                  f"  + {job['successful']}"
                  f"  o {job['already_solved']}"
                  f"  x {job['failed']}")
            print()

    try:
        fu_data = fu_client.get_active()
        fu_jobs = fu_data.get("jobs", [])
        if fu_jobs:
            print("  ── Face Unlock Active Jobs ──")
            for job in fu_jobs:
                print(f"  {job['job_id']}")
                print(f"    Status: {job['status']}  {'(Priority)' if job.get('priority') else '(Standard)'}")
                print(f"    Progress: {job['processed']}/{job['total_accounts']}"
                      f"  + {job['successful']}"
                      f"  x {job.get('failed', 0)}")
                print()
    except Exception:
        pass
    pause()


def cmd_faceunlock():
    print_header("FACE UNLOCK")
    refresh_fu_balance()
    if _fu_balance_cache:
        print(f"  Balance: ${_fu_balance_cache['effective']:.2f}  (Reserved: ${_fu_balance_cache['reserved']:.2f})")
        print()
    filepath = input(f"  Accounts file [{DEFAULT_ACCOUNTS_FILE}]: ").strip()
    if not filepath:
        filepath = DEFAULT_ACCOUNTS_FILE
    if not os.path.exists(filepath):
        print(f"\n  Error: {filepath} not found")
        pause()
        return
    with open(filepath, encoding="utf-8") as f:
        accounts_text = f.read()
    acct_lines = [l for l in accounts_text.strip().splitlines() if l.strip()]
    if not acct_lines:
        print(f"\n  Error: {filepath} is empty")
        pause()
        return
    print(f"  {len(acct_lines)} accounts loaded")
    print("  Queue:")
    print("    1. Standard ($0.05/acc)")
    print("    2. Priority ($0.10/acc)")
    q = input("  Choice [1]: ").strip()
    priority = q == "2"
    rate_str = "$0.10" if priority else "$0.05"
    max_cost = len(acct_lines) * (0.10 if priority else 0.05)
    if _fu_balance_cache:
        print(f"\n  Max cost: ${max_cost:.2f}  |  Available: ${_fu_balance_cache['effective']:.2f}")
        if max_cost > _fu_balance_cache["effective"]:
            print("  ! Not enough balance for this job!")
    print()
    data = fu_client.submit(accounts_text, priority=priority)
    job_id = data["job_id"]
    print(f"  Job ID: {job_id}")
    print(f"  Accounts: {data['total_accounts']}")
    print(f"  Free (DB): {data.get('db_accounts_count', 0)}")
    print(f"  Paid: {data.get('paid_accounts_count', 0)}")
    print(f"  Estimated cost: ${data['estimated_cost']:.2f}")
    print(f"  Queue: {'Priority' if priority else 'Standard'}")
    refresh_fu_balance()
    if _fu_balance_cache:
        print(f"  Balance after reservation: ${_fu_balance_cache['effective']:.2f}")
    w = input("\n  Watch progress? [y/N]: ").strip().lower()
    if w == "y":
        print()
        result = watch_loop_fu(job_id)
        if result["status"] == "completed":
            refresh_fu_balance()
            print(f"  Unlocked: {result.get('successful', 0)}")
            auto = input("  Download results now? [y/N]: ").strip().lower()
            if auto == "y":
                for f_info in result.get("result_files", []):
                    content = fu_client.download(job_id, f_info["filename"])
                    if content is not None:
                        with open(f_info["filename"], "w", encoding="utf-8") as f:
                            f.write(content)
                        print(f"  Downloaded {f_info['filename']}")
        print()
    pause()


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
        print("  =" * 35)
        print("  |   ZeroPoint ZeroSolver                |")
        if _credits_cache:
            b = _credits_cache
            print(f"  |   Balance: {b['effective']:<6.2f}   Reserved: {b['reserved']:<6.2f}        |")
        if _fu_balance_cache and fu_client:
            print(f"  |   FU Balance: ${_fu_balance_cache['effective']:<5.2f}                          |")
        print(f"  =" * 35)
        print(f"  |  1. Check Credits            |")
        print(f"  |  2. Submit Accounts          |")
        print(f"  |  3. Job Status               |")
        print(f"  |  4. Download Results         |")
        print(f"  |  5. Cancel Job               |")
        print(f"  |  6. Active Jobs              |")
        if fu_client:
            print(f"  |  7. Face Unlock              |")
        print(f"  =" * 35)
        print(f"  |  0. Exit                     |")
        print(f"  =" * 35)
        choice = input("  Choice [0-7]: ").strip()
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
        fn = dispatch.get(choice)
        if fn:
            fn()
        else:
            print("  Invalid choice.")
            time.sleep(1)


if __name__ == "__main__":
    main()
