"""Multi-channel bot daemon."""

import logging
import signal
import time
from typing import Any, Optional

from social_hook.bot.process import remove_pid, write_pid
from social_hook.bot.runner import ChannelRunner

logger = logging.getLogger(__name__)


class BotDaemon:
    """Multi-channel bot daemon. Manages ChannelRunner instances."""

    def __init__(self, runners: list[ChannelRunner]) -> None:
        self._runners = runners
        self._running = False

    def _handle_signal(self, signum, frame):
        logger.info(f"Received signal {signum}, shutting down")
        self.stop()

    def run(self, pid_file=None) -> None:
        self._running = True
        if pid_file:
            write_pid(pid_file)
        signal.signal(signal.SIGTERM, self._handle_signal)
        signal.signal(signal.SIGINT, self._handle_signal)
        try:
            if len(self._runners) == 1:
                self._runners[0].run()
            else:
                self._run_multi()
        finally:
            if pid_file:
                remove_pid(pid_file)
            logger.info("Bot daemon stopped")

    def _run_multi(self):
        import threading
        threads = []
        for runner in self._runners:
            t = threading.Thread(target=runner.run, daemon=True, name=f"runner-{runner.platform}")
            t.start()
            threads.append((t, runner))
        while self._running:
            time.sleep(1)
            for t, runner in threads:
                if not t.is_alive():
                    logger.error(f"Runner thread {runner.platform} died unexpectedly")
                    self.stop()
                    break

    def stop(self) -> None:
        self._running = False
        for runner in self._runners:
            runner.stop()


def create_bot(
    token: str,
    allowed_chat_ids: Optional[set[str]] = None,
    config: Optional[Any] = None,
) -> BotDaemon:
    """Create a configured BotDaemon with TelegramRunner."""
    from social_hook.bot.buttons import handle_callback
    from social_hook.bot.commands import handle_command, handle_message
    from social_hook.bot.runners.telegram import TelegramRunner
    from social_hook.messaging.telegram import TelegramAdapter

    adapter = TelegramAdapter(token=token)

    def on_command(message: dict) -> None:
        msg = TelegramAdapter.parse_message(message)
        handle_command(msg, adapter, config)

    def on_callback(callback: dict) -> None:
        event = TelegramAdapter.parse_callback(callback)
        handle_callback(event, adapter, config)

    def on_message(message: dict) -> None:
        msg = TelegramAdapter.parse_message(message)
        handle_message(msg, adapter, config)

    runner = TelegramRunner(
        token=token,
        allowed_chat_ids=allowed_chat_ids,
        on_command=on_command,
        on_callback=on_callback,
        on_message=on_message,
    )
    return BotDaemon(runners=[runner])
