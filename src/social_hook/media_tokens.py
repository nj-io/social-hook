"""Media token parser for inline article positioning.

Articles carry inline markdown tokens ``![caption](media:ID)`` inside
``draft.content`` that name a media item by stable id. The drafter emits
these; the advisory page and article preview resolve them at render time.
Flat posts (``vehicle != "article"``) never carry tokens — images attach at
post time instead.

Stdlib-only; zero project imports. Candidate for REUSABILITY.md promotion
after a second subsystem adopts it.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# Intentionally permissive on the id portion: id format is ``media_<12hex>``
# but we match anything that could plausibly be an id. The
# ``broken_media_reference`` diagnostic surfaces mismatches at read time.
TOKEN_RE = re.compile(r"!\[([^\]]*)\]\(media:([a-zA-Z0-9_\-]+)\)")


@dataclass(frozen=True)
class MediaToken:
    """A single parsed ``![caption](media:ID)`` occurrence.

    ``start``/``end`` are byte offsets into the source content (via
    ``re.Match.start/end``), useful for resolvers that want to splice or
    edit tokens without a second regex pass.
    """

    caption: str
    media_id: str
    start: int
    end: int


def extract_tokens(content: str) -> list[MediaToken]:
    """Parse all media tokens from ``content`` in source order.

    Returns ``[]`` for empty input. Malformed tokens (e.g. missing closing
    paren) are ignored by the regex — diagnostics surface unresolved refs
    at read time.
    """
    if not content:
        return []
    return [
        MediaToken(
            caption=m.group(1),
            media_id=m.group(2),
            start=m.start(),
            end=m.end(),
        )
        for m in TOKEN_RE.finditer(content)
    ]


def resolve_tokens(content: str, specs_by_id: dict[str, str]) -> str:
    """Replace tokens with rendered image references.

    ``specs_by_id`` maps ``media_id`` to the resolved path or URL. Orphan
    tokens (id not present in ``specs_by_id``) are left verbatim — the
    ``broken_media_reference`` diagnostic surfaces them at read time rather
    than silently swallowing them.
    """
    if not content:
        return content

    def replace(m: re.Match[str]) -> str:
        path = specs_by_id.get(m.group(2))
        if not path:
            # Orphan token — preserve source text verbatim.
            return str(m.group(0))
        return f"![{m.group(1)}]({path})"

    return TOKEN_RE.sub(replace, content)
