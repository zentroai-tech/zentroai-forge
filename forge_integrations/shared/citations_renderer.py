"""Citation rendering helpers for RAG tool outputs."""

from __future__ import annotations

import re
from typing import Any


def render_references(citations: list[dict[str, Any]]) -> str:
    """Format a citations list as a numbered bibliography string.

    Each citation should have at minimum 'citation_id' and 'source_id'.
    'title' and 'url' are included when present.

    Returns a human-readable string like::

        [C1] Oncology Study — https://example.com/a
        [C2] doc-456
    """
    if not citations:
        return ""
    lines: list[str] = []
    for c in citations:
        cid = str(c.get("citation_id", ""))
        title = str(c.get("title", "")).strip()
        url = str(c.get("url", "")).strip()
        source_id = str(c.get("source_id", "")).strip()
        label = title or source_id
        if url:
            lines.append(f"[{cid}] {label} — {url}")
        else:
            lines.append(f"[{cid}] {label}")
    return "\n".join(lines)


_PAREN_CITATION_RE = re.compile(r"\(C(\d+)\)", re.IGNORECASE)
_BARE_CITATION_RE = re.compile(r"(?<!\[)\bC(\d+)\b(?!\])", re.IGNORECASE)
_LOWER_BRACKET_RE = re.compile(r"\[c(\d+)\]")


def normalize_citation_markers(text: str) -> str:
    """Normalize loose citation marker variants to the canonical [Cn] format.

    Handles common variants produced by language models:

    - ``(C1)``  → ``[C1]``
    - ``C1``    → ``[C1]``  (bare, not already bracketed)
    - ``[c1]``  → ``[C1]``  (lowercase)
    """
    # (Cn) → [Cn]
    text = _PAREN_CITATION_RE.sub(r"[C\1]", text)
    # bare Cn → [Cn]  (guard against double-bracketing)
    text = _BARE_CITATION_RE.sub(r"[C\1]", text)
    # [cn] → [Cn] (uppercase)
    text = _LOWER_BRACKET_RE.sub(r"[C\1]", text)
    return text
