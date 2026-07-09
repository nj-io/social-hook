"""Operator-upload validation — single source of truth for size + format limits.

Reads ``adapters.models.SINGLE_IMAGE.max_size`` and the union of
``SINGLE_IMAGE.formats + GIF.formats`` so the 4 upload ingress points
(web POST /api/projects/{id}/uploads, web POST /api/drafts/{id}/media-upload,
bot /upload command, CLI `content create --uploads`/`--file`) all agree on
one cap and one allowlist.

Design notes:

* Stdlib-only (plus ``errors.ConfigError``) — matches Shared Utilities rule
  in CODING_PRACTICES §Shared Utilities: "Shared utilities live as top-level
  modules in src/social_hook/".
* Raises ``ConfigError`` with a structured message prefix so callers can
  translate to platform-appropriate responses (HTTP 413/415, Telegram reply,
  CLI stderr + exit 1).
* Error message prefix is one of: ``file_too_large`` or ``unsupported_format``.
  Callers parse the prefix to pick the HTTP status code when needed.
"""

from __future__ import annotations

from social_hook.adapters.models import GIF, SINGLE_IMAGE
from social_hook.errors import ConfigError

# Computed once at import so the helpers don't recompute on every call.
MAX_BYTES: int = SINGLE_IMAGE.max_size or 0
ALLOWED_FORMATS: frozenset[str] = frozenset(SINGLE_IMAGE.formats) | frozenset(GIF.formats)


def _extension_from_filename(filename: str | None) -> str:
    """Return the lowercase extension from ``filename`` (without dot), or ""."""
    if not filename or "." not in filename:
        return ""
    return filename.rsplit(".", 1)[-1].lower()


def _normalize_ext(ext: str) -> str:
    """Normalize ``jpeg`` → ``jpg`` so the allowlist check is canonical.

    SINGLE_IMAGE.formats is ("png", "jpg", "webp"); SINGLE_IMAGE never lists
    "jpeg" but the plan allows both spellings at ingress. This normalization
    is the single place where the jpg/jpeg equivalence lives.
    """
    return "jpg" if ext == "jpeg" else ext


def validate_upload(
    data: bytes | None = None,
    *,
    filename: str | None = None,
    size_bytes: int | None = None,
) -> None:
    """Validate a single operator upload against the shared size + format rules.

    Raises ``ConfigError`` on violation; returns ``None`` on accept.

    Parameters
    ----------
    data:
        The raw file bytes, when available (web multipart + bot file-download
        paths already hold them in memory).
    filename:
        The uploaded filename, used for the format allowlist check. Pass the
        original ``UploadFile.filename`` on the web side or ``basename(path)``
        on the CLI side.
    size_bytes:
        Pre-measured size in bytes — used by the CLI path which has a path on
        disk rather than bytes in memory. Mutually exclusive with ``data``.

    Raises
    ------
    ConfigError
        With message starting ``unsupported_format: ...`` for format
        rejections or ``file_too_large: ...`` for size rejections. Callers
        parse the prefix to pick the appropriate platform response.
    """
    ext = _normalize_ext(_extension_from_filename(filename))
    if ext not in ALLOWED_FORMATS:
        raise ConfigError(f"unsupported_format: .{ext!s} not in {sorted(ALLOWED_FORMATS)}")

    if size_bytes is None and data is not None:
        size_bytes = len(data)
    if size_bytes is None:
        # No size info provided — callers on the web path should always pass
        # either `data` or `size_bytes`. Refuse silently-passing validation.
        raise ConfigError("file_too_large: size unknown — cannot validate")
    if size_bytes > MAX_BYTES:
        raise ConfigError(f"file_too_large: {size_bytes} > {MAX_BYTES}")


def parse_violation(message: str) -> tuple[str, str]:
    """Split a ``ConfigError`` message into (kind, detail).

    Kind is one of ``"file_too_large"``, ``"unsupported_format"``, or
    ``"unknown"``. Callers use ``kind`` to pick a platform-appropriate
    response (HTTP 413 vs 415, Telegram error text, CLI exit).
    """
    for kind in ("file_too_large", "unsupported_format"):
        if message.startswith(kind):
            _, _, detail = message.partition(":")
            return kind, detail.strip()
    return "unknown", message
