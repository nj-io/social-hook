"""Interactive terminal helpers — re-exported from social_hook.terminal.

Import from here in E2E scripts for convenience, or directly from
social_hook.terminal in application code.
"""

from social_hook.terminal import copy_to_clipboard, getch, pause_with_url

__all__ = ["copy_to_clipboard", "getch", "pause_with_url"]
