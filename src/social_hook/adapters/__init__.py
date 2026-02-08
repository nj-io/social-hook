"""Adapters for external services: posting and media generation."""

from social_hook.adapters.media.base import MediaAdapter
from social_hook.adapters.models import MediaResult, PostResult, ThreadResult
from social_hook.adapters.platform.base import PlatformAdapter

# Concrete adapter imports are lazy to avoid requiring all dependencies at import time.
# Import specific adapters directly:
#   from social_hook.adapters.platform.x import XAdapter
#   from social_hook.adapters.platform.linkedin import LinkedInAdapter
#   from social_hook.adapters.media.mermaid import MermaidAdapter
# Or use the registry:
#   from social_hook.adapters.registry import get_media_adapter

__all__ = [
    "PostResult",
    "ThreadResult",
    "MediaResult",
    "PlatformAdapter",
    "MediaAdapter",
]
