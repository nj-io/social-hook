"""Platform adapters for social media posting."""

from social_hook.adapters.platform.base import PlatformAdapter

# Lazy imports to avoid requiring all dependencies at import time
# Import XAdapter or LinkedInAdapter directly when needed:
#   from social_hook.adapters.platform.x import XAdapter
#   from social_hook.adapters.platform.linkedin import LinkedInAdapter

__all__ = [
    "PlatformAdapter",
]
