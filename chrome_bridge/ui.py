"""Terminal UI, ANSI colors, badges, cards, and threaded Braille spinners for Chrome Bridge."""

import os
import sys
import threading
import time
from typing import Any, List, Optional, Tuple


class SpinnerContext:
    """Threaded ANSI animated Braille spinner context manager."""

    def __init__(self, ui: "TerminalUI", message: str):
        self.ui = ui
        self.message = message
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._completed = False

    def __enter__(self) -> "SpinnerContext":
        if self.ui.interactive:
            self._thread = threading.Thread(target=self._spin, daemon=True)
            self.ui._hide_cursor()
            self._thread.start()
        else:
            self.ui.stream.write(f"  ... {self.message}\n")
            self.ui.stream.flush()
        return self

    def _spin(self) -> None:
        idx = 0
        frames = self.ui.SPINNER_FRAMES
        while not self._stop_event.is_set():
            frame = frames[idx % len(frames)]
            self.ui.stream.write(f"\r  {self.ui.cyan(frame)} {self.message}\033[K")
            self.ui.stream.flush()
            idx += 1
            time.sleep(0.08)

    def ok(self, final_msg: Optional[str] = None) -> None:
        self._finish(self.ui.green("✓"), final_msg or self.message)

    def fail(self, final_msg: Optional[str] = None) -> None:
        self._finish(self.ui.red("✗"), final_msg or self.message)

    def warn(self, final_msg: Optional[str] = None) -> None:
        self._finish(self.ui.yellow("⚠️"), final_msg or self.message)

    def skip(self, final_msg: Optional[str] = None) -> None:
        self._finish(self.ui.dim("○"), final_msg or self.message)

    def _finish(self, symbol: str, text: str) -> None:
        if self._completed:
            return
        self._completed = True
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=0.2)
        if self.ui.interactive:
            self.ui.stream.write(f"\r  {symbol} {text}\033[K\n")
            self.ui._show_cursor()
        else:
            self.ui.stream.write(f"  {symbol} {text}\n")
        self.ui.stream.flush()

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        if not self._completed:
            if exc_type is not None:
                self.fail(f"{self.message} (failed: {exc_val})")
            else:
                self.ok()
        self.ui._show_cursor()


class TerminalUI:
    """Pure-Python zero-dependency live terminal UI and rendering engine."""

    SPINNER_FRAMES = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
    ASCII_SPINNER_FRAMES = ["|", "/", "-", "\\"]

    def __init__(
        self,
        force_color: Optional[bool] = None,
        interactive: Optional[bool] = None,
        stream: Optional[Any] = None,
    ):
        self.stream = stream or sys.stdout
        is_tty = hasattr(self.stream, "isatty") and self.stream.isatty()

        no_color_env = bool(os.environ.get("NO_COLOR"))
        ci_env = bool(os.environ.get("CI"))
        dumb_term = os.environ.get("TERM") == "dumb"

        if force_color is not None:
            self.supports_color = force_color
        else:
            self.supports_color = not no_color_env and (
                is_tty or os.environ.get("FORCE_COLOR") == "1"
            )

        if interactive is not None:
            self.interactive = interactive
        else:
            self.interactive = (
                is_tty
                and not no_color_env
                and not ci_env
                and not dumb_term
                and sys.platform != "win32"
            )

    def _hide_cursor(self) -> None:
        if self.interactive:
            self.stream.write("\033[?25l")
            self.stream.flush()

    def _show_cursor(self) -> None:
        if self.interactive:
            self.stream.write("\033[?25h")
            self.stream.flush()

    def colorize(self, code: str, text: str) -> str:
        if not self.supports_color:
            return text
        return f"\033[{code}m{text}\033[0m"

    def bold(self, text: str) -> str:
        return self.colorize("1", text)

    def dim(self, text: str) -> str:
        return self.colorize("2", text)

    def cyan(self, text: str) -> str:
        return self.colorize("36", text)

    def green(self, text: str) -> str:
        return self.colorize("32", text)

    def yellow(self, text: str) -> str:
        return self.colorize("33", text)

    def red(self, text: str) -> str:
        return self.colorize("31", text)

    def magenta(self, text: str) -> str:
        return self.colorize("35", text)

    def blue(self, text: str) -> str:
        return self.colorize("34", text)

    def badge_done(self, label: str = "DONE") -> str:
        return f"{self.green('✓')} {self.bold(label)}" if self.supports_color else f"[DONE] {label}"

    def badge_fail(self, label: str = "FAIL") -> str:
        return f"{self.red('✗')} {self.bold(label)}" if self.supports_color else f"[FAIL] {label}"

    def badge_warn(self, label: str = "WARN") -> str:
        return f"{self.yellow('⚠️')} {self.bold(label)}" if self.supports_color else f"[WARN] {label}"

    def spinner(self, message: str) -> SpinnerContext:
        return SpinnerContext(self, message)

    def card(self, title: str, items: List[Tuple[str, str]]) -> str:
        lines = [self.bold(f"┌─ {title} " + "─" * max(0, 50 - len(title)))]
        for label, val in items:
            lines.append(f"│  {self.dim(label.ljust(18))} : {val}")
        lines.append("└" + "─" * 54)
        return "\n".join(lines)

    def banner(self, title: str = "Chrome Bridge — Smart Live Assistant") -> None:
        if not self.supports_color:
            self.stream.write(f"\n=== {title} ===\n\n")
            self.stream.flush()
            return
        w = max(60, len(title) + 10)
        border = "═" * w
        pad = " " * ((w - len(title) - 2) // 2)
        self.stream.write(
            f"\n{self.cyan('╔' + border + '╗')}\n"
            f"{self.cyan('║')}{pad}{self.bold(title)}{pad}{' ' if (w - len(title) - 2) % 2 else ''}{self.cyan('║')}\n"
            f"{self.cyan('╚' + border + '╝')}\n\n"
        )
        self.stream.flush()


# Default singleton instance
ui = TerminalUI()

# Top-level functional helpers for backward-compatibility
colorize = ui.colorize
bold = ui.bold
dim = ui.dim
cyan = ui.cyan
green = ui.green
yellow = ui.yellow
red = ui.red
magenta = ui.magenta
blue = ui.blue
badge_done = ui.badge_done
badge_fail = ui.badge_fail
badge_warn = ui.badge_warn
spinner = ui.spinner
card = ui.card
banner = ui.banner

__all__ = [
    "SpinnerContext",
    "TerminalUI",
    "ui",
    "colorize",
    "bold",
    "dim",
    "cyan",
    "green",
    "yellow",
    "red",
    "magenta",
    "blue",
    "badge_done",
    "badge_fail",
    "badge_warn",
    "spinner",
    "card",
    "banner",
]
