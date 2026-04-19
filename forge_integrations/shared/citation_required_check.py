"""Citation enforcement check for RAG-generated text.

Verifies that every paragraph of 20 or more words contains at least one
[Cn] citation marker, and that all markers reference known citation IDs.
"""

from __future__ import annotations

import re
from typing import Any

_CITATION_RE = re.compile(r"\[C(\d+)\]")
_MIN_PARAGRAPH_WORDS = 20


def _paragraphs(text: str) -> list[str]:
    """Split text into non-empty paragraphs on blank lines."""
    return [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]


def _word_count(text: str) -> int:
    return len(text.split())


def run(args: dict[str, Any]) -> dict[str, Any]:
    """Check citation requirements on generated text.

    Args:
        args: dict with keys:
            - ``text`` (str): the generated text to check.
            - ``citation_ids`` (list[str]): valid citation IDs, e.g. ``["C1", "C2"]``.

    Returns:
        dict:
            - ``pass`` (bool): ``True`` if all checks pass.
            - ``issues`` (list[str]): human-readable issue descriptions.
            - ``missing`` (list[str]): paragraph snippets (≥20 words) lacking any marker.
            - ``invalid`` (list[str]): markers found in text not present in ``citation_ids``.
    """
    text = str(args.get("text") or "")
    citation_ids_raw = args.get("citation_ids") or []
    valid_ids: set[str] = {str(c) for c in citation_ids_raw}

    issues: list[str] = []
    missing_paragraphs: list[str] = []
    invalid_markers: list[str] = []
    found_markers: set[str] = set()

    for para in _paragraphs(text):
        marker_nums = _CITATION_RE.findall(para)
        for n in marker_nums:
            found_markers.add(f"C{n}")

        if _word_count(para) >= _MIN_PARAGRAPH_WORDS and not marker_nums:
            snippet = para[:80] + ("..." if len(para) > 80 else "")
            missing_paragraphs.append(snippet)
            issues.append(f"Paragraph missing citation: '{snippet}'")

    if valid_ids:
        for marker in sorted(found_markers):
            if marker not in valid_ids:
                invalid_markers.append(f"[{marker}]")
                issues.append(f"Unknown citation marker: [{marker}]")

    return {
        "pass": len(issues) == 0,
        "issues": issues,
        "missing": missing_paragraphs,
        "invalid": invalid_markers,
    }
