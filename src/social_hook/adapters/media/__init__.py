"""Media adapters for generating visual assets."""

from social_hook.adapters.media.base import MediaAdapter

# Lazy imports to avoid requiring all dependencies at import time
# Import specific adapters directly when needed:
#   from social_hook.adapters.media.mermaid import MermaidAdapter
#   from social_hook.adapters.media.nanabananapro import NanaBananaAdapter
#   from social_hook.adapters.media.playwright import PlaywrightAdapter
#   from social_hook.adapters.media.rayso import RaySoAdapter

__all__ = [
    "MediaAdapter",
]
