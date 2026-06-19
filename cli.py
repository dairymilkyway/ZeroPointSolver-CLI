#!/usr/bin/env python3
import argparse
import os
import sys
import time

from config import load_api_key
from api_client import ZeroSolverClient

DEFAULT_ACCOUNTS_FILE = "accs.txt"


def cmd_credits(client, args):
    data = client.get_credits()
    print(f"Balance:   {data['balance']:.2f} credits")
    print(f"Reserved:  {data['reserved']:.2f} credits")
    print(f"Effective: {data['effective']:.2f} credits")
    print(f"In-game solve:     {data['cost_per_success']} credits each")
    print(f"Captcha-lock solve: {data['captcha_lock_cost_per_success']} credits each")


def cmd_submit(client, args):
    filepath = args.file or DEFAULT_ACCOUNTS_FILE
    if not os.path.exists(filepath):
        print(f"Error: {filepath} not found")
        sys.exit(1)

    with open(filepath, encoding="utf-8") as f:
        accounts_text = f.read()

    acct_lines = [l for l in accounts_text.strip().splitlines() if l.strip()]
    if not acct_lines:
        print(f"Error: {filepath} is empty")
        sys.exit(1)

    try:
        bal = client.get_credits()
        print(f"Credits: {bal['effective']:.2f} available  (Reserved: {bal['reserved']:.2f})")
    except Exception:
        pass

    captcha_type = "captchalock" if args.captchalock else "ingame"
    rate = 0.005 if args.captchalock else 0.0025
    max_cost = len(acct_lines) * rate
    print(f"Max cost: {max_cost:.4f} credits  ({len(acct_lines)} accs \N{multiplication sign} {rate})")
    print()

    data = client.submit(accounts_text, captcha_type)

    job_id = data["job_id"]
    print(f"Job ID: {job_id}")
    print(f"  Accounts: {data['total_accounts']}")
    print(f"  Estimated cost: {data['estimated_cost']} credits")
    print(f"  Cost per success: {data['cost_per_success']} credits")
    print(f"  Solver: {captcha_type}")

    if args.watch:
        print()
        cmd_status(client, argparse.Namespace(job_id=job_id, watch=True))
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

        label = status.upper()
        print(f"[{label}] {processed}/{total}  "
              f"\N{check mark} {solved} solved  "
              f"\N{white circle} {already} already  "
              f"\N{ballot x} {failed} failed  "
              f"charged: {data['charged_credits']} credits")

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
              f"\N{check mark} {job['successful']}  "
              f"\N{white circle} {job['already_solved']}  "
              f"\N{ballot x} {job['failed']}")


def main():
    parser = argparse.ArgumentParser(
        prog="zpsolver",
        description="ZeroPoint ZeroSolver CLI — submit, track, and download captcha solving jobs."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("credits", help="Check Solver Credits balance")

    p_submit = subparsers.add_parser("submit", help="Submit accounts for solving")
    p_submit.add_argument(
        "-f", "--file",
        help=f"Account file path (default: {DEFAULT_ACCOUNTS_FILE})"
    )
    p_submit.add_argument(
        "--captchalock",
        action="store_true",
        help="Use captcha-lock (unlock) solver instead of default in-game solver"
    )
    p_submit.add_argument(
        "-w", "--watch",
        action="store_true",
        help="Watch job progress until completion"
    )

    p_status = subparsers.add_parser("status", help="Check job status")
    p_status.add_argument("job_id", help="Job ID")
    p_status.add_argument(
        "-w", "--watch",
        action="store_true",
        help="Poll every 3s until the job finishes"
    )

    p_download = subparsers.add_parser("download", help="Download result files")
    p_download.add_argument("job_id", help="Job ID")

    p_cancel = subparsers.add_parser("cancel", help="Cancel a job")
    p_cancel.add_argument("job_id", help="Job ID")

    subparsers.add_parser("active", help="List active jobs")

    args = parser.parse_args()

    api_key = load_api_key()
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
