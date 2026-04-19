# rag_retriever_citations

RAG retrieval recipe that assigns deterministic **C1..Cn** citation IDs to returned
chunks, deduplicates citations by source, and enforces per-chunk size caps.

Companion shared helpers in `forge_integrations/shared/`:

- `citations_renderer.py` — formats a bibliography string and normalises loose
  citation marker variants (`C1`, `(C1)`, `[c1]` → `[C1]`).
- `citation_required_check.py` — enforcement check: every paragraph of ≥ 20 words
  must contain at least one `[Cn]` marker, and all markers must reference known
  citation IDs.

## Input

| Field     | Type    | Required | Default | Description                        |
|-----------|---------|----------|---------|------------------------------------|
| `query`   | string  | yes      | —       | Search query (max 2000 chars)      |
| `top_k`   | integer | no       | `8`     | Max chunks to retrieve (1–50)      |
| `filters` | object  | no       | `{}`    | Backend-specific filter object     |

## Output

```json
{
  "query": "What are the side effects of imatinib?",
  "chunks": [
    {
      "citation_id": "C1",
      "text": "Imatinib is associated with ...",
      "score": 0.94,
      "source": {
        "source_id": "pubmed-12345",
        "title": "Imatinib Mesylate: Clinical Review",
        "url": "https://pubmed.ncbi.nlm.nih.gov/12345",
        "span": { "start": 0, "end": 512 }
      }
    }
  ],
  "citations": [
    {
      "citation_id": "C1",
      "source_id": "pubmed-12345",
      "title": "Imatinib Mesylate: Clinical Review",
      "url": "https://pubmed.ncbi.nlm.nih.gov/12345"
    }
  ],
  "total_chunks": 1
}
```

## Citation ID assignment

1. Chunks are sorted by **score descending**, tiebreaker **source_id ascending**,
   tiebreaker **span.start ascending**.
2. The first unique source encountered receives **C1**, the second **C2**, etc.
3. Multiple chunks from the same source share one `citation_id`.
4. `citations[]` contains one entry per unique source in C1..Cn order.

## Env vars

| Variable                | Required | Default | Description                               |
|-------------------------|----------|---------|-------------------------------------------|
| `RAG_BACKEND_URL`       | yes      | —       | POST endpoint of your retrieval backend   |
| `RAG_REQUEST_TIMEOUT_S` | no       | `15`    | HTTP request timeout in seconds           |

## Security properties

- Chunk text hard-capped at **8 KB** (`_MAX_CHUNK_BYTES`) to protect the
  context window from oversized documents.
- No environment secrets are written into the tool output.
- `citation_required_check` can be run post-generation to enforce grounding.

## Copy into exported repo

- Tool: `tools/rag_retriever_citations.py`
- Shared helpers:
  - `tools/citations_renderer.py`
  - `tools/citation_required_check.py`
- Schemas:
  - `runtime/schemas/tools/rag_retriever_citations.input.json`
  - `runtime/schemas/tools/rag_retriever_citations.output.json`
- Register in: `runtime/tools/registry.py`
- Allowlist in: `settings.py` under `FLOW_POLICIES["tool_allowlist"]`
- Add to `.env.example`:
  ```
  RAG_BACKEND_URL=http://your-rag-service/retrieve
  RAG_REQUEST_TIMEOUT_S=15
  ```

## Running tests

From the repo root (requires `jsonschema` and `requests` installed):

```bash
py -3.11 -m pytest forge_integrations/recipes/rag_retriever_citations/tests/ -v
```

## Using citation enforcement in your flow

After calling `rag_retriever_citations`, pass the returned `citations` and the
generated text through `citation_required_check`:

```python
from forge_integrations.shared import citation_required_check, citations_renderer

# After LLM generation
result = citation_required_check.run({
    "text": llm_output,
    "citation_ids": [c["citation_id"] for c in rag_output["citations"]],
})
if not result["pass"]:
    # Handle missing / invalid citations
    print(result["issues"])

# Append bibliography
bibliography = citations_renderer.render_references(rag_output["citations"])
final_output = llm_output + "\n\n## References\n" + bibliography
```

## AbstainSpec integration

To enforce citations at the IR policy level, set `require_citations_for_rag: true`
in the agent's `AbstainSpec`:

```json
{
  "abstain": {
    "require_citations_for_rag": true
  }
}
```

The runtime will call `citation_required_check` automatically before returning
the agent's response.
