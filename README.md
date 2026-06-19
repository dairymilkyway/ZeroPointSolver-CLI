# ZPCaptchaSolver

A Python CLI tool for the [ZeroPoint](https://zeropoint.to/zerosolver) ZeroSolver API — submit Roblox accounts for captcha solving, track job progress, and download results. Both an interactive menu and a one-liner CLI are included.

## Features

- **Interactive menu** (`python main.py`) — no commands to memorize
- **CLI mode** (`python cli.py <command>`) — for scripts and quick one-liners
- **Live credit tracking** — balance shown in menu, before/after every job
- **Auto-watch** — poll job progress every 3 seconds until completion
- **Rate-limit handling** — automatic retry with backoff on 429 errors
- **Dual solver support** — in-game captcha (default) and captcha-lock (account unlock)
- **Only one dependency** — `requests`

## Prerequisites

- Python 3.7+
- A [ZeroPoint](https://zeropoint.to/) account with Solver Credits
- An API key (generate from the ZeroSolver page)

## Installation

```bash
git clone https://github.com/dairymilkyway/ZPCaptchaSolver.git
cd ZPCaptchaSolver
pip install -r requirements.txt
```

## Setup

Create a `.env` file in the project root with your API key:

```
X-API-Key = ZP_ZeroSolver_YourKeyHere
```

You can also set it as an environment variable:
```bash
# Windows
set X-API-Key=ZP_ZeroSolver_YourKeyHere
# Linux/macOS
export X-API-Key=ZP_ZeroSolver_YourKeyHere
```

> **Security:** `.env` and `accs.txt` are gitignored. Never commit your API key or account cookies.

## Quick Start

### Interactive Menu

```bash
python main.py
```

```
╔══════════════════════════════╗
║   ZeroPoint ZeroSolver       ║
║   Balance: 2.25   Reserved: 0.00 ║
╠══════════════════════════════╣
║  1. Check Credits            ║
║  2. Submit Accounts          ║
║  3. Job Status               ║
║  4. Download Results         ║
║  5. Cancel Job               ║
║  6. Active Jobs              ║
║  0. Exit                     ║
╚══════════════════════════════╝
Choice [0-6]:
```

### CLI Mode

```bash
python cli.py submit                 # submit accs.txt
python cli.py submit --captchalock  # use captcha-lock solver
python cli.py status <job_id> -w    # watch progress
python cli.py download <job_id>     # download results
python cli.py cancel <job_id>       # cancel a job
python cli.py active                # list active jobs
python cli.py credits               # check balance
```

## Account File Format

Accounts go in `accs.txt` (one per line):

```
username:password:_|WARNING:-DO-NOT-SHARE-THIS...|_COOKIE...
```

The cookie must contain the `_|WARNING` marker. Lines without it are ignored.

Use `-f`/`--file` to use a different file:
```bash
python cli.py submit -f myaccounts.txt
```

## Commands

| Command | Menu | CLI | Description |
|---|---|---|---|
| Credits | `1` | `credits` | Check your Solver Credits balance |
| Submit | `2` | `submit` | Submit accounts for solving |
| Status | `3` | `status <id>` | Poll job progress |
| Download | `4` | `download <id>` | Download result files |
| Cancel | `5` | `cancel <id>` | Cancel a running job |
| Active | `6` | `active` | List active jobs |

### CLI Flags

| Flag | Applies to | Description |
|---|---|---|
| `-f`, `--file` | `submit` | Account file path (default: `accs.txt`) |
| `--captchalock` | `submit` | Use captcha-lock solver (default: in-game) |
| `-w`, `--watch` | `submit`, `status` | Auto-poll until job finishes |

## Pricing

| Solver | Cost per success | CLI flag |
|---|---|---|
| In-game (default) | 0.0025 credits | *(none)* |
| Captcha-lock (unlock) | 0.005 credits | `--captchalock` |
| Already solved | FREE | — |
| Failed | FREE | — |

1 credit = $1 USD. You're only charged for successful solves.

## Result Files

After a job completes, three files are available:

| File | Contents |
|---|---|
| `solved.txt` | Accounts whose captcha was solved (billed) |
| `already_solved.txt` | Accounts with no captcha to solve (free) |
| `failed.txt` | Accounts that failed (free) |

Files are deleted after 24 hours — download promptly.

## Project Structure

```
ZPCaptchaSolver/
├── main.py              # Interactive menu
├── cli.py               # CLI entry point
├── api_client.py        # ZeroSolver API wrapper
├── config.py            # API key loader
├── requirements.txt     # pip dependencies
├── .env                 # API key (gitignored)
├── accs.txt             # Account list (gitignored)
└── .gitignore
```

## Rate Limits

- Submission cooldown: 0.8 seconds per request
- Max 10,000 accounts per submission
- Unlimited concurrent jobs
- Automatic retry on 429/503 errors

## License

MIT
