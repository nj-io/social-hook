"""Multi-channel bot daemon."""

import logging
import signal
import time
from typing import Any

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


def _create_telegram_runner(
    token: str,
    allowed_chat_ids: set[str] | None,
    config: Any,
) -> "ChannelRunner":
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

    return TelegramRunner(
        token=token,
        allowed_chat_ids=allowed_chat_ids,
        on_command=on_command,
        on_callback=on_callback,
        on_message=on_message,
    )


def create_bot(
    config: Any,
    *,
    token: str | None = None,
    allowed_chat_ids: set[str] | None = None,
) -> BotDaemon:
    """Create a configured BotDaemon.

    If config.channels has enabled entries, uses those.
    Otherwise falls back to token param or config.env vars.
    """
    from social_hook.errors import ConfigError

    runners = []

    # Channel-aware path
    channels = getattr(config, "channels", None) or {}
    enabled_channels = {k: v for k, v in channels.items() if getattr(v, "enabled", False)}

    if enabled_channels:
        env = getattr(config, "env", {}) or {}
        for name, ch_cfg in enabled_channels.items():
            if name == "telegram":
                tg_token = env.get("TELEGRAM_BOT_TOKEN")
                if tg_token:
                    chat_ids = set(ch_cfg.allowed_chat_ids) if ch_cfg.allowed_chat_ids else set()
                    runners.append(_create_telegram_runner(tg_token, chat_ids, config))
                else:
                    logger.warning("Telegram channel enabled but TELEGRAM_BOT_TOKEN not set")
            elif name == "web":
                pass  # Handled by FastAPI server
            elif name == "slack":
                logger.warning("Slack channel not yet implemented, skipping")
            else:
                logger.warning(f"Unknown channel '{name}', skipping")
    else:
        # Legacy fallback
        if token is None:
            env = getattr(config, "env", {}) or {}
            token = env.get("TELEGRAM_BOT_TOKEN")
            if not token:
                raise ConfigError("No channels configured and TELEGRAM_BOT_TOKEN not set")
            allowed_str = env.get("TELEGRAM_ALLOWED_CHAT_IDS", "")
            if allowed_str:
                allowed_chat_ids = {s.strip() for s in allowed_str.split(",") if s.strip()}

        runners.append(_create_telegram_runner(token, allowed_chat_ids, config))

    if not runners:
        raise ConfigError("No channel runners could be created — check credentials")

    return BotDaemon(runners=runners)
