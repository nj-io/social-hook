"""Platform-agnostic channel runner abstraction."""

from abc import ABC, abstractmethod


class ChannelRunner(ABC):
    @abstractmethod
    def run(self) -> None:
        """Start the channel's listening loop. Blocks until stopped."""

    @abstractmethod
    def stop(self) -> None:
        """Signal the listening loop to stop gracefully."""

    @property
    @abstractmethod
    def platform(self) -> str:
        """Platform identifier (e.g., 'telegram', 'discord')."""
