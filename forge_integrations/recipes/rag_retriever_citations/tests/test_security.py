"""Security tests for rag_retriever_citations.

Validates:
- Chunk text is hard-capped at _MAX_CHUNK_BYTES.
- Environment secrets are not echoed into the tool output.
- citation_required_check enforces per-paragraph citation presence.
- citation_required_check detects invalid (unknown) citation IDs.
- Short paragraphs (< 20 words) are exempt from the citation requirement.
- citations_renderer produces correct bibliography strings.
- normalize_citation_markers canonicalises loose variants.
"""

from __future__ import annotations

from forge_integrations.recipes.rag_retriever_citations import tool
from forge_integrations.shared import citation_required_check, citations_renderer


def _make_chunk(source_id: str, score: float, text: str) -> dict:
    return {
        "text": text,
        "score": score,
        "source": {
            "source_id": source_id,
            "title": "Title",
            "url": "",
            "span": {"start": 0, "end": len(text)},
        },
    }


# ---------------------------------------------------------------------------
# Chunk size cap
# ---------------------------------------------------------------------------


def test_chunk_text_capped_at_8kb(monkeypatch):
    monkeypatch.setenv("RAG_BACKEND_URL", "http://localhost:9999/retrieve")
    large_text = "x" * 20_000  # 20 KB
    chunks = [_make_chunk("doc-1", 0.9, large_text)]
    monkeypatch.setattr(tool, "_retrieve", lambda q, tk, f: list(chunks))

    out = tool.run({"query": "cap test"})

    text_bytes = out["chunks"][0]["text"].encode("utf-8")
    assert len(text_bytes) <= tool._MAX_CHUNK_BYTES


def test_chunk_text_not_truncated_when_under_cap(monkeypatch):
    monkeypatch.setenv("RAG_BACKEND_URL", "http://localhost:9999/retrieve")
    normal_text = "short chunk"
    chunks = [_make_chunk("doc-1", 0.9, normal_text)]
    monkeypatch.setattr(tool, "_retrieve", lambda q, tk, f: list(chunks))

    out = tool.run({"query": "no truncation"})

    assert out["chunks"][0]["text"] == normal_text


# ---------------------------------------------------------------------------
# No secrets in output
# ---------------------------------------------------------------------------


def test_no_env_secrets_in_output(monkeypatch):
    """Tool must not echo environment secrets into its output."""
    monkeypatch.setenv("RAG_BACKEND_URL", "http://localhost:9999/retrieve")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-secret-key-12345")
    chunks = [_make_chunk("doc-1", 0.9, "Safe chunk text without secrets.")]
    monkeypatch.setattr(tool, "_retrieve", lambda q, tk, f: list(chunks))

    out = tool.run({"query": "no secrets"})

    assert "sk-test-secret-key-12345" not in str(out)


# ---------------------------------------------------------------------------
# citation_required_check
# ---------------------------------------------------------------------------


def test_citation_required_check_passes_with_short_paragraph():
    """Paragraphs under 20 words do not require citations."""
    result = citation_required_check.run({
        "text": "Short paragraph here.",
        "citation_ids": ["C1"],
    })
    assert result["pass"] is True
    assert result["issues"] == []


def test_citation_required_check_passes_long_paragraph_with_citation():
    text = ("This paragraph has more than twenty words and it properly "
            "references a source [C1] so the check should pass without any issues.")
    result = citation_required_check.run({
        "text": text,
        "citation_ids": ["C1"],
    })
    assert result["pass"] is True


def test_citation_required_check_fails_long_paragraph_no_citation():
    long_para = " ".join(["word"] * 25)  # 25 words, no citation marker
    result = citation_required_check.run({
        "text": long_para,
        "citation_ids": ["C1"],
    })
    assert result["pass"] is False
    assert len(result["missing"]) == 1


def test_citation_required_check_detects_invalid_ids():
    text = ("This paragraph has enough words to trigger the citation check "
            "and it references [C99] which is not in the provided list.")
    result = citation_required_check.run({
        "text": text,
        "citation_ids": ["C1", "C2"],
    })
    assert result["pass"] is False
    assert "[C99]" in result["invalid"]


def test_citation_required_check_allows_all_when_no_valid_ids_given():
    """When citation_ids is empty, unknown-marker check is skipped."""
    text = ("This paragraph has twenty words and references [C5] but no "
            "citation_ids list was provided so no invalid check runs here.")
    result = citation_required_check.run({
        "text": text,
        "citation_ids": [],
    })
    # Only the missing-citation check runs; [C5] is present so it passes.
    assert result["pass"] is True
    assert result["invalid"] == []


def test_citation_required_check_multi_paragraph(monkeypatch):
    """Each long paragraph is checked independently."""
    para_ok = ("First paragraph has enough words and has a citation [C1] "
               "so it passes the enforcement check without any problem at all.")
    para_bad = " ".join(["word"] * 22)  # no marker
    text = f"{para_ok}\n\n{para_bad}"

    result = citation_required_check.run({
        "text": text,
        "citation_ids": ["C1"],
    })
    assert result["pass"] is False
    assert len(result["missing"]) == 1


# ---------------------------------------------------------------------------
# citations_renderer
# ---------------------------------------------------------------------------


def test_citations_renderer_formats_bibliography():
    citations = [
        {
            "citation_id": "C1",
            "source_id": "doc-a",
            "title": "Oncology Study",
            "url": "https://example.com/a",
        },
        {
            "citation_id": "C2",
            "source_id": "doc-b",
            "title": "",
            "url": "",
        },
    ]
    rendered = citations_renderer.render_references(citations)
    assert "[C1] Oncology Study — https://example.com/a" in rendered
    assert "[C2] doc-b" in rendered


def test_citations_renderer_empty_list():
    assert citations_renderer.render_references([]) == ""


# ---------------------------------------------------------------------------
# normalize_citation_markers
# ---------------------------------------------------------------------------


def test_normalize_citation_markers_parenthesised():
    text = "See (C2) for details."
    result = citations_renderer.normalize_citation_markers(text)
    assert "[C2]" in result
    assert "(C2)" not in result


def test_normalize_citation_markers_bare():
    text = "As shown in C1 and C3."
    result = citations_renderer.normalize_citation_markers(text)
    assert "[C1]" in result
    assert "[C3]" in result


def test_normalize_citation_markers_lowercase_bracket():
    text = "Reference [c4] here."
    result = citations_renderer.normalize_citation_markers(text)
    assert "[C4]" in result
    assert "[c4]" not in result


def test_normalize_citation_markers_already_canonical():
    text = "Already [C1] canonical."
    result = citations_renderer.normalize_citation_markers(text)
    # Should not double-bracket
    assert result.count("[C1]") == 1
    assert "[[C1]]" not in result
