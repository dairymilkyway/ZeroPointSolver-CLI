#!/usr/bin/env python3
"""
Shared visual theme for ZPCaptchaSolver CLI.

Centralises all ANSI styling, icon sets, spacing, and rendering primitives.
Terminal capabilities detected once at startup; all output functions consume the
global Style singleton.
"""

import os
import re
import sys
from dataclasses import dataclass
from typing import Optional


_ANSI_RE = re.compile(r"\033\[[0-9;]*m")

_UNICODE_TO_ASCII = {
    "\u2500": "-", "\u2502": "|",
    "\u250c": "+", "\u2510": "+", "\u2514": "+", "\u2518": "+",
    "\u251c": "+", "\u2524": "+",
    "\u2588": "#", "\u2591": ".",
    "\u2713": "[OK]", "\u2717": "[FAIL]", "\u26a0": "[WARN]",
    "\u25cf": "[..]", "\u25c6": ">>",
    "\u2192": "->", "\u2026": "...",
    "\u280b": "/", "\u2819": "-", "\u2839": "\\", "\u2838": "|",
    "\u2826": "/", "\u2834": "-", "\u282e": "\\", "\u2827": "|",
    "\u280f": "\\",
}


def _safe_print(msg: str) -> None:
    """Print with graceful fallback when the terminal can't render Unicode."""
    try:
        print(msg, flush=True)
    except UnicodeEncodeError:
        clean = _ANSI_RE.sub("", msg)
        for uni, ascii_ in _UNICODE_TO_ASCII.items():
            clean = clean.replace(uni, ascii_)
        clean = clean.encode("ascii", errors="replace").decode("ascii")
        try:
            print(clean, flush=True)
        except Exception:
            print("", flush=True)


# ── terminal capability detection ─────────────────────

@dataclass
class TermCaps:
    color: bool
    unicode: bool
    width: int

    @classmethod
    def detect(cls, no_unicode: bool = False, no_color: bool = False) -> "TermCaps":
        is_tty = sys.stdout.isatty()
        color = not no_color and (is_tty or os.environ.get("FORCE_COLOR"))

        locale_ok = any(
            "UTF-8" in (os.environ.get(k, "").upper())
            for k in ("LC_ALL", "LC_CTYPE", "LANG")
        )
        unicode = not no_unicode
        if unicode and not locale_ok:
            if is_tty:
                if sys.platform == "win32":
                    unicode = _windows_unicode_ok()
                    if unicode:
                        _try_enable_utf8()
                elif os.environ.get("TERM", "") in (
                    "xterm-256color", "xterm-kitty", "alacritty", "wezterm",
                    "tmux-256color", "screen-256color",
                ):
                    pass
                else:
                    enc = getattr(sys.stdout, "encoding", "").lower()
                    unicode = enc in ("utf-8", "utf8", "utf_8", "utf-16-le")
            else:
                unicode = locale_ok

        width = _detect_width()
        return cls(color=color, unicode=unicode, width=width)


def _try_enable_utf8() -> None:
    """Attempt to switch the Windows console to UTF-8 code page."""
    try:
        import ctypes
        ctypes.windll.kernel32.SetConsoleOutputCP(65001)
    except Exception:
        pass
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except AttributeError:
        pass
    except Exception:
        pass


def _test_unicode_encoding() -> bool:
    """Verify the current stdout encoding can actually encode a box-drawing char."""
    try:
        "\u2500".encode(sys.stdout.encoding or "ascii")
        return True
    except (UnicodeEncodeError, UnicodeDecodeError):
        return False


def _windows_unicode_ok() -> bool:
    """Check whether the Windows terminal can render Unicode box-drawing chars."""
    _try_enable_utf8()
    if _test_unicode_encoding():
        return True
    if os.environ.get("WT_SESSION"):
        return True
    try:
        import ctypes
        cp = ctypes.windll.kernel32.GetConsoleOutputCP()
        if cp == 65001:
            return True
    except Exception:
        pass
    return False


def _detect_width() -> int:
    try:
        import shutil
        return shutil.get_terminal_size((80, 24)).columns
    except Exception:
        return 80


# ── ANSI colour constants (muted / desaturated palette) ─
# Max 4 colours: accent, success, error/warn, info.

_ANSI = "\033["
_RESET = f"{_ANSI}0m"
_BOLD = f"{_ANSI}1m"
_DIM = f"{_ANSI}2m"

_COLORS = {
    "ACCENT": f"{_ANSI}38;5;68m",    # soft blue
    "SUCCESS": f"{_ANSI}38;5;71m",   # soft green
    "ERROR": f"{_ANSI}38;5;167m",    # muted red
    "WARN": f"{_ANSI}38;5;179m",     # muted amber
    "INFO": f"{_ANSI}38;5;74m",      # soft cyan
    "MUTED": f"{_ANSI}38;5;242m",    # gray
    "BOLD": _BOLD,
    "DIM": _DIM,
    "RESET": _RESET,
}

_NO_COLOR = {k: "" for k in _COLORS}


# ── icon sets ─────────────────────────────────────────

class IconSet:
    def __init__(self, unicode: bool):
        # Status icons
        self.ok = "✓" if unicode else "[OK]"
        self.err = "✗" if unicode else "[FAIL]"
        self.warn = "⚠" if unicode else "[WARN]"
        self.progress = "●" if unicode else "[...]"
        self.bullet = "◆" if unicode else ">>"
        self.arrow = "→" if unicode else "->"
        self.ellipsis = "…" if unicode else "..."

        # Box drawing
        if unicode:
            self.H, self.V = "─", "│"
            self.TL, self.TR = "┌", "┐"
            self.BL, self.BR = "└", "┘"
            self.LT, self.RT = "├", "┤"
        else:
            self.H, self.V = "-", "|"
            self.TL, self.TR = ".", "."
            self.BL, self.BR = "'", "'"
            self.LT, self.RT = "|", "|"

        # Progress bar
        self.PB_FILL = "█" if unicode else "#"
        self.PB_EMPTY = "░" if unicode else "."

        # Spinner frames (braille for unicode, simple for ASCII)
        if unicode:
            self.spinner_frames = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
        else:
            self.spinner_frames = ["|", "/", "-", "\\"]


# ── global style singleton ────────────────────────────

class Style:
    _instance: Optional["Style"] = None

    def __init__(self, caps: TermCaps):
        self.caps = caps
        self.icons = IconSet(caps.unicode)
        self.c = _NO_COLOR if not caps.color else _COLORS
        self._spinner_idx = 0

    # ── colour helpers ────────────────────────────

    def cw(self, name: str, text: str) -> str:
        c = self.c.get(name.upper())
        if not c:
            return text
        return f"{c}{text}{_RESET}"

    def dim(self, text: str) -> str:
        c = self.c.get("DIM")
        if not c:
            return text
        return f"{c}{text}{_RESET}"

    def bold(self, text: str) -> str:
        c = self.c.get("BOLD")
        if not c:
            return text
        return f"{c}{text}{_RESET}"

    # ── spinner ───────────────────────────────────

    def next_spinner(self) -> str:
        frames = self.icons.spinner_frames
        self._spinner_idx = (self._spinner_idx + 1) % len(frames)
        return frames[self._spinner_idx]

    # ── lifecycle ─────────────────────────────────

    @classmethod
    def init(cls, caps: Optional[TermCaps] = None, **kwargs) -> "Style":
        if caps is None:
            caps = TermCaps.detect(**kwargs)
        cls._instance = cls(caps)
        return cls._instance

    @classmethod
    def current(cls) -> "Style":
        if cls._instance is None:
            cls.init()
        return cls._instance


# ── public rendering helpers ─────────────────────────

def _s() -> Style:
    return Style.current()


def log(msg: str = ""):
    _safe_print(msg)


def header(title: str, width: int = 0) -> None:
    s = _s()
    if width <= 0:
        width = min(s.caps.width - 4, 60)
    label = f" {title} "
    if len(label) > width:
        label = label[:width - 3] + s.icons.ellipsis + " "
    pad_l = (width - len(label)) // 2
    pad_r = width - pad_l - len(label)
    log()
    log(f"  {s.cw('ACCENT', s.icons.TL)}{s.cw('ACCENT', s.icons.H * width)}{s.cw('ACCENT', s.icons.TR)}")
    log(f"  {s.cw('ACCENT', s.icons.V)}{' ' * pad_l}{s.bold(label)}{' ' * pad_r}{s.cw('ACCENT', s.icons.V)}")
    log(f"  {s.cw('ACCENT', s.icons.BL)}{s.cw('ACCENT', s.icons.H * width)}{s.cw('ACCENT', s.icons.BR)}")


def field(key: str, val: str, w: int = 18) -> None:
    s = _s()
    log(f"    {s.dim(key)}  {val}")


def sep(width: Optional[int] = None, char: Optional[str] = None) -> None:
    s = _s()
    if width is None:
        width = min(s.caps.width - 4, 60)
    c = char or s.icons.H
    log(f"  {s.dim(c * width)}")


def ok(msg: str) -> None:
    s = _s()
    log(f"    {s.cw('SUCCESS', s.icons.ok)} {msg}")


def err(msg: str) -> None:
    s = _s()
    log(f"    {s.cw('ERROR', s.icons.err)} {msg}")


def warn(msg: str) -> None:
    s = _s()
    log(f"    {s.cw('WARN', s.icons.warn)} {msg}")


def info(msg: str) -> None:
    s = _s()
    log(f"    {s.cw('INFO', s.icons.bullet)} {msg}")


def badge(status: str) -> str:
    s = _s()
    m = {
        "pending": (s.icons.progress, "INFO"),
        "processing": (s.icons.progress, "ACCENT"),
        "completed": (s.icons.ok, "SUCCESS"),
        "failed": (s.icons.err, "ERROR"),
        "cancelled": (s.icons.warn, "WARN"),
    }
    icon, colour = m.get(status, ("?", "MUTED"))
    return s.cw(colour, icon)


def progress_bar(p: int, t: int, w: int = 20) -> str:
    s = _s()
    if t == 0:
        return s.dim(s.icons.PB_EMPTY * w)
    filled = int(p / t * w)
    bar = s.icons.PB_FILL * filled + s.icons.PB_EMPTY * (w - filled)
    pct = int(p / t * 100)
    return f"{s.cw('ACCENT', bar)} {s.dim(f'{pct:>2}%')}"


def truncate_path(path: str, max_len: int = 50) -> str:
    if len(path) <= max_len:
        return path
    parts = path.replace("\\", "/").split("/")
    tail = "/".join(parts[-3:])
    s = _s()
    if len(tail) + 3 <= max_len:
        return f"{s.dim(s.icons.ellipsis)}/{tail}"
    return f"{s.dim(s.icons.ellipsis)}{tail[-(max_len - 1):]}"
