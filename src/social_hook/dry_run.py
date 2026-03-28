"""Generic dry-run proxy for module-level function dispatch.

Wraps a target module so that read operations pass through while
write operations are silently skipped (returning sensible defaults).
Read vs write is determined by function name prefix.

REUSABILITY: This file has zero project-specific imports.
Only stdlib (logging). Copy-paste safe.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

# Default read prefixes — functions starting with these pass through
DEFAULT_READ_PREFIXES = ("get_",)


class DryRunProxy:
    """Wraps a module or object, skipping write operations in dry-run mode.

    Read operations (matching ``read_prefixes``) are forwarded to the
    target with ``first_arg`` prepended. All other operations return
    sensible defaults when ``dry_run=True``.

    Args:
        target: Module or object whose attributes are proxied.
        first_arg: Optional value prepended as the first positional
            argument on every forwarded call (e.g., a DB connection).
        dry_run: If True, skip write operations.
        read_prefixes: Tuple of name prefixes that identify read
            operations. Defaults to ``("get_",)``.

    Example::

        import my_db_ops

        proxy = DryRunProxy(my_db_ops, first_arg=conn, dry_run=True)
        proxy.get_user(42)         # passes through: my_db_ops.get_user(conn, 42)
        proxy.delete_user(42)      # skipped, returns None
        proxy.insert_record(rec)   # skipped, returns rec.id if available
    """

    def __init__(
        self,
        target: Any,
        first_arg: Any = None,
        *,
        dry_run: bool = False,
        read_prefixes: tuple[str, ...] = DEFAULT_READ_PREFIXES,
    ) -> None:
        # Use object.__setattr__ to avoid triggering __getattr__
        object.__setattr__(self, "_target", target)
        object.__setattr__(self, "_first_arg", first_arg)
        object.__setattr__(self, "dry_run", dry_run)
        object.__setattr__(self, "_read_prefixes", read_prefixes)

    def __getattr__(self, name: str) -> Any:
        """Delegate to target, intercepting writes in dry-run mode."""
        target = object.__getattribute__(self, "_target")
        func = getattr(target, name, None)
        if func is None:
            raise AttributeError(
                f"'{type(self).__name__}' has no attribute '{name}' "
                f"(not found in {target.__name__ if hasattr(target, '__name__') else target})"
            )

        dry_run = object.__getattribute__(self, "dry_run")
        read_prefixes = object.__getattribute__(self, "_read_prefixes")

        if dry_run and not name.startswith(read_prefixes):
            return _make_noop(name)

        first_arg = object.__getattribute__(self, "_first_arg")

        def wrapper(*args: Any, **kwargs: Any) -> Any:
            if first_arg is not None:
                return func(first_arg, *args, **kwargs)
            return func(*args, **kwargs)

        return wrapper


def _make_noop(name: str) -> Any:
    """Create a no-op wrapper for a write operation.

    Returns appropriate defaults based on the operation name prefix:
    - insert_*: returns the first arg's .id if available, else None
    - increment_*: returns 0
    - update_*/reset_*/set_*/supersede_*: returns False
    - Others: returns None
    """

    def noop(*args: Any, **kwargs: Any) -> Any:
        logger.debug("DryRun: skipping %s", name)
        if name.startswith("insert_"):
            if args and hasattr(args[0], "id"):
                return args[0].id
            if args and isinstance(args[0], dict):
                return args[0].get("id")
            return None
        elif name.startswith("increment_"):
            return 0
        elif (
            name.startswith("update_")
            or name.startswith("reset_")
            or name.startswith("set_")
            or name.startswith("supersede_")
        ):
            return False
        return None

    return noop
