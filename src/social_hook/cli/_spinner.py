"""Reusable CLI spinner for long-running operations."""

import threading
import time
from collections.abc import Generator
from contextlib import contextmanager

from rich.console import Console
from rich.text import Text

_console = Console()


class _ElapsedStatus:
    """Rich renderable that appends elapsed seconds to a message."""

    def __init__(self, message: str) -> None:
        self.message = message
        self.start = time.monotonic()

    def __rich__(self) -> Text:
        elapsed = int(time.monotonic() - self.start)
        return Text(f"{self.message} ({elapsed}s)")


@contextmanager
def spinner(message: str, quiet: bool = False) -> Generator[None, None, None]:
    if quiet:
        yield
        return
    status_obj = _ElapsedStatus(message)
    with _console.status(status_obj) as s:
        # Poke the status every second so the elapsed counter updates
        stop = threading.Event()

        def _tick() -> None:
            while not stop.wait(1.0):
                s.update(status_obj)

        t = threading.Thread(target=_tick, daemon=True)
        t.start()
        try:
            yield
        finally:
            stop.set()
            t.join(timeout=2)
