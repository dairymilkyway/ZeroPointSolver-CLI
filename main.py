#!/usr/bin/env python3
import os
import sys
import time
from config import load_api_key
from api_client import ZeroSolverClient

DEFAULT_ACCOUNTS_FILE = "accs.txt"

client = None
_credits_cache = None


def refresh_balance():
    global _credits_cache
    try:
        _credits_cache = client.get_credits()
    except Exception:
        _credits_cache = None
    return _credits_cache


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
            print("  \N{warning sign} Not enough credits for this job!")
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
        while True:
            data = client.get_status(job_id)
            status = data["status"]
            processed = data["processed"]
            total = data["total_accounts"]
            solved = data["successful"]
            already = data["already_solved"]
            failed = data["failed"]
            print(f"  [{status.upper()}] {processed}/{total}"
                  f"  \N{check mark} {solved}  \N{white circle} {already}  \N{ballot x} {failed}"
                  f"  charged: {data['charged_credits']}")
            if status in ("completed", "failed", "cancelled"):
                break
            time.sleep(3)
        if status == "completed":
            refresh_balance()
            if _credits_cache:
                print(f"  Charged: {data['charged_credits']} | New balance: {_credits_cache['effective']:.2f}")
            auto = input("  Download results now? [y/N]: ").strip().lower()
            if auto == "y":
                for filename in data.get("result_files", []):
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
              f"  \N{check mark} {solved}  \N{white circle} {already}  \N{ballot x} {failed}"
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
    c = input(f"  Cancel job {job_id}? [y/N]: ").strip().lower()
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
        print("  No active jobs.")
    else:
        for job in jobs:
            print(f"  {job['job_id']}")
            print(f"    Status: {job['status']}")
            print(f"    Progress: {job['processed']}/{job['total_accounts']}"
                  f"  \N{check mark} {job['successful']}"
                  f"  \N{white circle} {job['already_solved']}"
                  f"  \N{ballot x} {job['failed']}")
            print()
    pause()


def main():
    global client
    api_key = load_api_key()
    client = ZeroSolverClient(api_key)
    refresh_balance()
    while True:
        clear()
        print("  ╔══════════════════════════════╗")
        print("  ║   ZeroPoint ZeroSolver       ║")
        if _credits_cache:
            b = _credits_cache
            print(f"  ║   Balance: {b['effective']:<6.2f}   Reserved: {b['reserved']:<6.2f} ║")
        print("  ╠══════════════════════════════╣")
        print("  ║  1. Check Credits            ║")
        print("  ║  2. Submit Accounts          ║")
        print("  ║  3. Job Status               ║")
        print("  ║  4. Download Results         ║")
        print("  ║  5. Cancel Job               ║")
        print("  ║  6. Active Jobs              ║")
        print("  ║                              ║")
        print("  ║  0. Exit                     ║")
        print("  ╚══════════════════════════════╝")
        choice = input("  Choice [0-6]: ").strip()
        dispatch = {
            "1": cmd_credits,
            "2": cmd_submit,
            "3": cmd_status,
            "4": cmd_download,
            "5": cmd_cancel,
            "6": cmd_active,
            "0": lambda: sys.exit(0),
        }
        fn = dispatch.get(choice)
        if fn:
            fn()
        else:
            print("  Invalid choice.")
            time.sleep(1)


if __name__ == "__main__":
    main()
