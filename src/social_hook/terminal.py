"""Interactive terminal utilities.

Shared helpers for single-keypress input, clipboard copy, and interactive
pauses with URL copy support. Used by the CLI wizard, E2E test harness,
and any interactive terminal flow.
"""

import subprocess
import sys
import time


def getch():
    """Read a single keypress without requiring Enter."""
    import termios
    import tty

    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        return sys.stdin.read(1)
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)


def copy_to_clipboard(text):
    """Copy text to system clipboard (macOS/Linux).

    Tries pbcopy (macOS) then xclip (Linux). Silent on failure.
    Returns True if copied, False if clipboard not available.
    """
    try:
        subprocess.run(["pbcopy"], input=text.encode(), check=True)
        return True
    except FileNotFoundError:
        try:
            subprocess.run(["xclip", "-selection", "clipboard"], input=text.encode(), check=True)
            return True
        except FileNotFoundError:
            return False


def pause_with_url(url=None, action="continue", prefix="       "):
    """Pause for a single keypress, with optional [c] to copy URL.

    Use this whenever an interactive step displays a URL that the user
    might want to open or copy. The prompt stays on one line — pressing
    c briefly shows "Copied to clipboard!" then restores the prompt.

    Args:
        url: URL to offer for clipboard copy. If None, no copy option shown.
        action: Label for the default action (e.g., "delete", "continue").
        prefix: Indentation prefix for the prompt line.
    """
    prompt = f"{prefix}[Enter] {action}"
    if url:
        prompt += "  [c] copy URL"
    print(prompt, end="", flush=True)
    while True:
        ch = getch()
        if ch == "c" and url:
            if copy_to_clipboard(url):
                print(f"\r\033[2K{prefix}Copied to clipboard!", end="", flush=True)
            else:
                print(f"\r\033[2K{prefix}(clipboard not available)", end="", flush=True)
            time.sleep(0.8)
            print(f"\r\033[2K{prompt}", end="", flush=True)
        else:
            print("\r\033[2K", end="")  # clear the prompt line
            break
