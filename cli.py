#!/usr/bin/env python3
import argparse
import os
import sys
import time

from config import load_zsolver_key, load_faceunlock_key
from api_client import ZeroSolverClient
from faceunlock_client import FaceUnlockClient

DEFAULT_ACCOUNTS_FILE = "accs.txt"


def cmd_credits(client, args):
    data = client.get_credits()
    print(f"Balance:   {data['balance']:.2f} credits")
    print(f"Reserved:  {data['reserved']:.2f} credits")
    print(f"Effective: {data['effective']:.2f} credits")
    print(f"In-game solve:     {data['cost_per_success']} credits each")
    print(f"Captcha-lock solve: {data['captcha_lock_cost_per_success']} credits each")


def read_accounts(filepath):
    if not os.path.exists(filepath):
        print(f"Error: {filepath} not found")
        sys.exit(1)
    with open(filepath, encoding="utf-8") as f:
        content = f.read()
    lines = [l for l in content.strip().splitlines() if l.strip()]
    if not lines:
        print(f"Error: {filepath} is empty")
        sys.exit(1)
    return content, lines


def watch_until_done(client, job_id, interval=3):
    while True:
        data = client.get_status(job_id)
        status = data["status"]
        processed = data["processed"]
        total = data["total_accounts"]
        solved = data.get("successful", 0)
        already = data.get("already_solved", 0)
        failed = data.get("failed", 0)
        other_failed = data.get("other_failed", 0)
        print(f"  [{status.upper()}] {processed}/{total}"
              f"  +{solved} solved"
              f"  x{failed} failed"
              f"  other:{other_failed}"
              f"  charged:{data.get('charged_credits', '?')} credits")
        if status in ("completed", "failed", "cancelled"):
            return data
        time.sleep(interval)


def watch_until_done_fu(client, job_id, interval=3):
    while True:
        data = client.get_status(job_id)
        status = data["status"]
        processed = data["processed"]
        total = data["total_accounts"]
        solved = data.get("successful", 0)
        failed = data.get("failed", 0)
        other_failed = data.get("other_failed", 0)
        print(f"  [{status.upper()}] {processed}/{total}"
              f"  +{solved} unlocked"
              f"  x{failed} face failed"
              f"  other:{other_failed}")
        if status in ("completed", "failed", "cancelled"):
            return data
        time.sleep(interval)


def download_results(client, job_id, filenames):
    for filename in filenames:
        content = client.download(job_id, filename)
        if content is not None:
            out_name = f"{job_id}_{filename}"
            with open(out_name, "w", encoding="utf-8") as f:
                f.write(content)
            lines = len([l for l in content.splitlines() if l.strip()])
            print(f"  Downloaded {out_name} ({lines} lines)")
        else:
            print(f"  {filename}: not found (API)")


def cmd_submit(client, args):
    filepath = args.file or DEFAULT_ACCOUNTS_FILE
    accounts_text, acct_lines = read_accounts(filepath)

    try:
        bal = client.get_credits()
        print(f"Credits: {bal['effective']:.2f} available  (Reserved: {bal['reserved']:.2f})")
    except Exception:
        pass

    captcha_type = "captchalock" if args.captchalock else "ingame"
    rate = 0.005 if args.captchalock else 0.0025
    max_cost = len(acct_lines) * rate
    print(f"Max cost: {max_cost:.4f} credits  ({len(acct_lines)} accs x {rate})")
    print()

    if args.faceunlock:
        print("=== Step 1: Face Unlock ===")
        try:
            fu_key = load_faceunlock_key()
        except SystemExit as e:
            print(e)
            sys.exit(1)
        fu_client = FaceUnlockClient(fu_key)
        try:
            bal_fu = fu_client.get_balance()
            print(f"Face Unlock balance: ${bal_fu['effective']:.2f}")
        except Exception:
            pass
        est_cost = len(acct_lines) * 0.05
        print(f"Estimated Face Unlock cost: ${est_cost:.2f} max")
        print()
        fu_data = fu_client.submit(accounts_text, priority=args.priority if hasattr(args, 'priority') else False)
        fu_job_id = fu_data["job_id"]
        print(f"Face Unlock Job ID: {fu_job_id}")
        if "total_accounts" in fu_data:
            print(f"  Total: {fu_data['total_accounts']} | Free: {fu_data.get('db_accounts_count', 0)} | Paid: {fu_data.get('paid_accounts_count', 0)}")
            print(f"  Estimated cost: ${fu_data['estimated_cost']:.2f}")
        else:
            print(f"  (reconnected to existing job)")
        print()
        print("  Watching face unlock...")
        fu_result = watch_until_done_fu(fu_client, fu_job_id)
        if fu_result["status"] == "completed":
            result_files = fu_result.get("result_files", [])
            if result_files:
                print("  Downloading face unlock results...")
                download_results(fu_client, fu_job_id, [f["filename"] for f in result_files])
        print()

    print("=== Step 2: Captcha Solve ===")
    data = client.submit(accounts_text, captcha_type)
    job_id = data["job_id"]
    print(f"Job ID: {job_id}")
    print(f"  Accounts: {data['total_accounts']}")
    print(f"  Estimated cost: {data['estimated_cost']} credits")
    print(f"  Cost per success: {data['cost_per_success']} credits")
    print(f"  Solver: {captcha_type}")

    if args.watch:
        print()
        result = watch_until_done(client, job_id)
        if result["status"] == "completed" and result.get("result_files"):
            print("  Downloading captcha results...")
            download_results(client, job_id, result["result_files"])
        try:
            bal = client.get_credits()
            print(f"Credits remaining: {bal['effective']:.2f}")
        except Exception:
            pass


def cmd_status(client, args):
    while True:
        data = client.get_status(args.job_id)
        status = data["status"]
        processed = data["processed"]
        total = data["total_accounts"]
        solved = data["successful"]
        already = data["already_solved"]
        failed = data["failed"]
        charged = data.get("charged_credits", "?")
        print(f"[{status.upper()}] {processed}/{total}  "
              f"+ {solved} solved  "
              f"o {already} already  "
              f"x {failed} failed  "
              f"charged: {charged} credits")
        if status in ("completed", "failed", "cancelled"):
            if status == "completed" and data.get("result_files"):
                print(f"  Result files: {', '.join(data['result_files'])}")
            return
        if not args.watch:
            return
        time.sleep(3)


def cmd_download(client, args):
    data = client.get_status(args.job_id)
    if data["status"] != "completed":
        print(f"Job is {data['status']} — wait for it to complete first.")
        return
    for filename in data.get("result_files", []):
        content = client.download(args.job_id, filename)
        if content is not None:
            with open(filename, "w", encoding="utf-8") as f:
                f.write(content)
            lines = len([l for l in content.splitlines() if l.strip()])
            print(f"Downloaded {filename} ({lines} lines)")
        else:
            print(f"  {filename}: not found")


def cmd_cancel(client, args):
    client.cancel(args.job_id)
    print(f"Job {args.job_id} cancelled.")


def cmd_active(client, args):
    try:
        bal = client.get_credits()
        print(f"Credits: {bal['balance']:.2f}  |  Reserved: {bal['reserved']:.2f}  |  Available: {bal['effective']:.2f}")
        print()
    except Exception:
        pass
    data = client.get_active()
    jobs = data.get("jobs", [])
    if not jobs:
        print("No active jobs.")
        return
    for job in jobs:
        print(f"  {job['job_id']}  [{job['status']}]  "
              f"{job['processed']}/{job['total_accounts']}  "
              f"+ {job['successful']}  "
              f"o {job['already_solved']}  "
              f"x {job['failed']}")


def cmd_faceunlock(fu_client, args):
    filepath = args.file or DEFAULT_ACCOUNTS_FILE
    accounts_text, acct_lines = read_accounts(filepath)

    try:
        bal = fu_client.get_balance()
        print(f"Face Unlock balance: ${bal['effective']:.2f}")
    except Exception:
        pass

    est_cost = len(acct_lines) * (0.10 if args.priority else 0.05)
    print(f"Max cost: ${est_cost:.2f}  ({len(acct_lines)} accs x {'$0.10' if args.priority else '$0.05'})")
    print()

    data = fu_client.submit(accounts_text, priority=args.priority)
    job_id = data["job_id"]
    print(f"Face Unlock Job ID: {job_id}")
    if "total_accounts" in data:
        print(f"  Total: {data['total_accounts']} | Free: {data.get('db_accounts_count', 0)} | Paid: {data.get('paid_accounts_count', 0)}")
        print(f"  Estimated cost: ${data['estimated_cost']:.2f}")
        print(f"  Queue: {'Priority' if data.get('priority') else 'Standard'}")
    else:
        print(f"  (reconnected to existing job)")

    if args.watch:
        print()
        result = watch_until_done_fu(fu_client, job_id)
        if result["status"] == "completed" and result.get("result_files"):
            print("  Downloading results...")
            download_results(fu_client, job_id, [f["filename"] for f in result["result_files"]])
        try:
            bal = fu_client.get_balance()
            print(f"Balance remaining: ${bal['effective']:.2f}")
        except Exception:
            pass


def main():
    parser = argparse.ArgumentParser(
        prog="zpsolver",
        description="ZeroPoint ZeroSolver CLI — submit, track, and download captcha solving jobs."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("credits", help="Check Solver Credits balance")

    p_submit = subparsers.add_parser("submit", help="Submit accounts for solving")
    p_submit.add_argument("-f", "--file", help=f"Account file path (default: {DEFAULT_ACCOUNTS_FILE})")
    p_submit.add_argument("--captchalock", action="store_true", help="Use captcha-lock (unlock) solver instead of default in-game solver")
    p_submit.add_argument("-w", "--watch", action="store_true", help="Watch job progress until completion")
    p_submit.add_argument("--faceunlock", action="store_true", help="Pre-process accounts with Face Unlock before captcha solving")

    p_status = subparsers.add_parser("status", help="Check job status")
    p_status.add_argument("job_id", help="Job ID")
    p_status.add_argument("-w", "--watch", action="store_true", help="Poll every 3s until the job finishes")

    p_download = subparsers.add_parser("download", help="Download result files")
    p_download.add_argument("job_id", help="Job ID")

    p_cancel = subparsers.add_parser("cancel", help="Cancel a job")
    p_cancel.add_argument("job_id", help="Job ID")

    subparsers.add_parser("active", help="List active jobs")

    p_fu = subparsers.add_parser("faceunlock", help="Submit accounts for face unlock only")
    p_fu.add_argument("-f", "--file", help=f"Account file path (default: {DEFAULT_ACCOUNTS_FILE})")
    p_fu.add_argument("-w", "--watch", action="store_true", help="Watch job progress until completion")
    p_fu.add_argument("--priority", action="store_true", help="Use Priority queue (2x pricing)")

    args = parser.parse_args()

    if args.command == "faceunlock":
        fu_key = load_faceunlock_key()
        fu_client = FaceUnlockClient(fu_key)
        cmd_faceunlock(fu_client, args)
        return

    if args.command == "submit" and args.faceunlock:
        api_key = load_zsolver_key()
        client = ZeroSolverClient(api_key)
        cmd_submit(client, args)
        return

    api_key = load_zsolver_key()
    client = ZeroSolverClient(api_key)

    dispatch = {
        "credits": cmd_credits,
        "submit": cmd_submit,
        "status": cmd_status,
        "download": cmd_download,
        "cancel": cmd_cancel,
        "active": cmd_active,
    }
    dispatch[args.command](client, args)


if __name__ == "__main__":
    main()
