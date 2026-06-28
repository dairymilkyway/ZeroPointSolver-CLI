# ZPCaptchaSolver

A Python CLI and interactive tool for the [ZeroPoint](https://zeropoint.to/) platform — submit Roblox accounts for **captcha solving** and **face unlock** processing, track job progress in real-time, and download results. Built on the ZeroSolver and Face Unlock REST APIs.

## Features

- **Dual API support** — ZeroSolver (captcha) + Face Unlock in one tool
- **Face Unlock pipeline** — detect & solve face lock, then captcha solve, all in one command
- **Interactive menu** (`python main.py`) — no commands to memorize
- **CLI mode** (`python cli.py <command>`) — for scripts and automation
- **Autosolve mode** — continuous cycles of face unlock + captcha solving on a timer
- **Live balance tracking** — credit and dollar balances shown before/after every job
- **Auto-watch** — poll job progress every 3 seconds with animated spinner and progress bar
- **Smart PR titles** — GitHub Action generates conventional-commit PR titles from git history
- **Rate-limit handling** — automatic retry with backoff on 429/503 errors
- **Priority queue** — opt into faster Face Unlock processing
- **Themed CLI output** — professional visual design with color, box-drawing, and ASCII fallback
- **Only one dependency** — `requests`

## Technology Stack

| Layer | Technology |
|---|---|
| Language | Python 3.7+ |
| HTTP | `requests` |
| APIs | ZeroPoint ZeroSolver REST API, ZeroPoint Face Unlock REST API |
| CI/CD | GitHub Actions (auto-PR with smart title generation) |

## Prerequisites

- Python 3.7+
- A [ZeroPoint](https://zeropoint.to/) account with Solver Credits and/or Face Unlock balance
- API keys (generate from the ZeroSolver and Face Unlock pages on zeropoint.to)

## Installation

```bash
git clone https://github.com/dairymilkyway/ZPCaptchaSolver.git
cd ZPCaptchaSolver
pip install -r requirements.txt
```

## Setup

Create a `.env` file in the project root with your API keys:

```
X-API-Key-Solver = ZP_ZeroSolver_YourKeyHere
X-API-Key-Face_Unlock = ZP_FaceUnlock_YourKeyHere
```

You can also set them as environment variables:

```bash
# Windows
set X-API-Key-Solver=ZP_ZeroSolver_YourKeyHere
set X-API-Key-Face_Unlock=ZP_FaceUnlock_YourKeyHere

# Linux/macOS
export X-API-Key-Solver=ZP_ZeroSolver_YourKeyHere
export X-API-Key-Face_Unlock=ZP_FaceUnlock_YourKeyHere
```

> **Security:** `.env` and `accs.txt` are gitignored. Never commit your API keys or account cookies.

## Quick Start

### Interactive Menu

```bash
python main.py
```

```
  ┌────────────────────────────────────────────┐
  │        ZeroPoint  ZeroSolver               │
  │                                            │
  │  ZS   100.00 cr     Res     0.00 cr        │
  │  FU   $100.00                              │
  ├────────────────────────────────────────────┤
  │  1. Credits                               │
  │  2. Submit Accounts                       │
  │  3. Job Status                            │
  │  4. Download Results                      │
  │  5. Cancel Job                            │
  │  6. Active Jobs                           │
  │  7. Face Unlock                           │
  │  8. Auto-Solve (FU + captcha-lock)        │
  │  9. Auto-Solve Captcha Only (in-game)     │
  ├────────────────────────────────────────────┤
  │  0. Exit                                  │
  └────────────────────────────────────────────┘
  Choice [0-9]:
```

### CLI Mode

```bash
python cli.py submit                      # submit accs.txt for captcha solving
python cli.py submit --captchalock        # use captcha-lock solver
python cli.py submit --faceunlock         # full pipeline: face unlock → captcha solve
python cli.py faceunlock                  # face unlock only
python cli.py faceunlock --priority       # face unlock with priority queue
python cli.py status <job_id> -w          # watch job progress
python cli.py download <job_id>           # download results
python cli.py cancel <job_id>             # cancel a job
python cli.py active                      # list active jobs
python cli.py credits                     # check ZeroSolver balance
python cli.py autosolve                   # continuous FU + captcha cycles
python cli.py autosolve-captcha           # continuous captcha-only cycles
```

## Project Architecture

```
User
  │
  ├── main.py (interactive menu)
  └── cli.py  (command-line)
       │
       ├── theme.py        → shared visual styling (colors, icons, progress bars)
       ├── config.py       → .env (API keys)
       ├── api_client.py   → ZeroPoint ZeroSolver API (captcha)
       └── faceunlock_client.py → ZeroPoint Face Unlock API
            │
            └── https://zeropoint.to/
                 ├── /api/zerosolver-api
                 └── /api/faceunlock-api
```

### Pipeline Flow

When `--faceunlock` is used, the tool runs a two-step pipeline:

```
accounts.txt
     │
     ▼
Step 1 ── Face Unlock API ──→ successful.txt (face-unlocked accounts)
     │
     ▼
Step 2 ── ZeroSolver API ───→ solved.txt, already_solved.txt, failed.txt
```

## Project Structure

```
ZPCaptchaSolver/
├── main.py                  # Interactive menu (both APIs)
├── cli.py                   # CLI entry point (both APIs)
├── theme.py                 # Shared visual theme module
├── api_client.py            # ZeroSolver API wrapper
├── faceunlock_client.py     # Face Unlock API wrapper
├── config.py                # API key loader (dual key support)
├── requirements.txt         # pip dependencies
├── .github/
│   └── workflows/
│       └── auto-pr.yml      # GitHub Action: auto-PR with smart title gen
├── .env                     # API keys (gitignored)
├── accs.txt                 # Account list (gitignored)
├── .gitignore
└── README.md
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
python cli.py faceunlock -f myaccounts.txt
```

## Commands

| Command | Menu | CLI | Description |
|---|---|---|---|
| Credits | `1` | `credits` | Check ZeroSolver Solver Credits balance |
| Submit | `2` | `submit` | Submit accounts for captcha solving (optionally with face unlock pre-processing) |
| Status | `3` | `status <id>` | Poll ZeroSolver job progress |
| Download | `4` | `download <id>` | Download result files from either API |
| Cancel | `5` | `cancel <id>` | Cancel a running job from either API |
| Active | `6` | `active` | List active jobs from both APIs |
| Face Unlock | `7` | `faceunlock` | Submit accounts for face unlock only |
| Auto-Solve | `8` | `autosolve` | Continuous FU + captcha-lock cycles |
| Auto Captcha | `9` | `autosolve-captcha` | Continuous in-game captcha cycles |

### CLI Flags

| Flag | Applies to | Description |
|---|---|---|
| `-f`, `--file` | `submit`, `faceunlock`, `autosolve*` | Account file path (default: `accs.txt`) |
| `--captchalock` | `submit` | Use captcha-lock solver (default: in-game) |
| `--faceunlock` | `submit` | Run full pipeline: face unlock first, then captcha solve |
| `--priority` | `faceunlock` | Use Priority queue for faster face unlock |
| `-w`, `--watch` | `submit`, `status`, `faceunlock` | Auto-poll until job finishes |

## Pricing

### ZeroSolver (Captcha Solving)

| Solver | Cost per success | CLI flag |
|---|---|---|
| In-game (default) | 0.0025 credits | *(none)* |
| Captcha-lock (unlock) | 0.005 credits | `--captchalock` |
| Already solved | FREE | — |
| Failed | FREE | — |

1 credit = $1 USD. You're only charged for successful solves.

### Face Unlock

| Queue | Cost per success | Notes |
|---|---|---|
| Standard (default) | $0.05/account | Database-matched accounts are FREE |
| Priority (`--priority`) | $0.10/account | Database-matched accounts: $0.05 flat |

### Result Files

#### ZeroSolver

| File | Contents |
|---|---|
| `solved.txt` | Accounts whose captcha was solved (billed) |
| `already_solved.txt` | Accounts with no captcha to solve (free) |
| `failed.txt` | Accounts that failed (free) |

#### Face Unlock

| File | Contents |
|---|---|
| `successful.txt` | Accounts successfully face unlocked |
| `failed.txt` | Accounts that failed face unlock |

Files are deleted after 24 hours — download promptly.

## Rate Limits

### ZeroSolver
- Submission cooldown: 0.8 seconds per account
- Max 10,000 accounts per submission
- Unlimited concurrent jobs

### Face Unlock
- Submission cooldown: 20 seconds per account
- Max 10,000 accounts per submission
- 1 active job at a time
- WebSocket real-time updates available via Socket.IO

## Development

```bash
# No build step required — pure Python
# Run syntax check on all files:
python -c "import py_compile; import glob; [py_compile.compile(f) for f in glob.glob('*.py')]"
```

### Workflow

1. Create a feature branch from `dev`
2. Make changes
3. Push to `dev` — the auto-PR action will suggest a title and create the PR

## License

MIT
