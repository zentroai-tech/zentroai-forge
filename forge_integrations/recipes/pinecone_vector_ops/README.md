# pinecone_vector_ops

Pinecone vector database operations recipe: ensure index, upsert, query, delete.

Exposes a single `run(args)` entry point that dispatches on `args["operation"]`.

## Operations

| Operation            | Description                                                 |
|----------------------|-------------------------------------------------------------|
| `ensure_collection`  | Create serverless index if it does not exist                |
| `upsert`             | Insert or update vectors                                    |
| `query`              | Nearest-neighbour search with optional metadata filter      |
| `delete`             | Delete vectors by ID                                        |

> **Note on `ensure_collection`:** Pinecone serverless indexes cannot be resized
> after creation and creation may take ~60 s.  For pod-based indexes, create the
> index manually via the Pinecone console and set `PINECONE_INDEX` + `PINECONE_HOST`.

## Input / output schemas

Shared provider-agnostic schemas live in `forge_integrations/shared/schemas/`.
Same schemas as `qdrant_vector_ops` — operations are interchangeable via
`vector_router`.

## Env vars

| Variable                 | Required                      | Default      | Description                             |
|--------------------------|-------------------------------|--------------|------------------------------------------|
| `PINECONE_API_KEY`       | yes                           | —            | Pinecone API key                         |
| `PINECONE_INDEX`         | yes (upsert/query/delete)     | —            | Default index name                       |
| `PINECONE_HOST`          | no                            | —            | Direct host URL (lower latency)          |
| `PINECONE_TIMEOUT_SECONDS`| no                           | `15`         | Request timeout in seconds               |
| `PINECONE_CLOUD`         | no (ensure_collection only)   | `aws`        | Cloud provider for serverless index      |
| `PINECONE_CLOUD_REGION`  | no (ensure_collection only)   | `us-east-1`  | Region for serverless index              |

## Security

- API key is never written into operation outputs.
- Pinecone SDK enforces HTTPS for all API calls.
- Upsert batches capped at **1 000 points** per call (schema-enforced).
- `score_threshold` filtering is applied in the tool layer after the provider
  returns results.

## Example calls

```python
from forge_integrations.recipes.pinecone_vector_ops.tool import run

# Ensure index (serverless)
run({
    "operation": "ensure_collection",
    "collection": "documents",
    "size": 1536,
    "distance": "cosine",
})

# Upsert
run({
    "operation": "upsert",
    "collection": "documents",
    "points": [
        {"id": "doc-1", "vector": [0.1, 0.2, ...], "payload": {"title": "AI Overview"}},
    ],
})

# Query
result = run({
    "operation": "query",
    "collection": "documents",
    "vector": [0.1, 0.2, ...],
    "top_k": 5,
    "score_threshold": 0.7,
    "filter": {"category": {"$eq": "oncology"}},
})
# result["matches"] → [{"id": "doc-1", "score": 0.92, "payload": {...}}, ...]

# Delete
run({
    "operation": "delete",
    "collection": "documents",
    "ids": ["doc-1", "doc-2"],
})
```

## Filter format

Pinecone filters use the Pinecone metadata filter syntax:

```python
{"category": {"$eq": "oncology"}}
{"$and": [{"year": {"$gte": 2020}}, {"status": {"$eq": "published"}}]}
```

See [Pinecone metadata filtering docs](https://docs.pinecone.io/guides/data/filter-with-metadata).

## Using via vector_router (provider-agnostic)

```python
from forge_integrations.shared.vector_router import vector_query

result = vector_query({
    "provider": "pinecone",
    "collection": "documents",
    "vector": [...],
    "top_k": 5,
})
```

## Smoke test (requires PINECONE_API_KEY and PINECONE_INDEX)

```bash
export PINECONE_API_KEY=your-api-key
export PINECONE_INDEX=smoke-test

python - <<'EOF'
from forge_integrations.recipes.pinecone_vector_ops.tool import run

# Upsert 3 points
run({"operation": "upsert", "collection": "smoke-test", "points": [
    {"id": "a", "vector": [1.0, 0.0, 0.0, 0.0], "payload": {"label": "A"}},
    {"id": "b", "vector": [0.0, 1.0, 0.0, 0.0], "payload": {"label": "B"}},
    {"id": "c", "vector": [0.0, 0.0, 1.0, 0.0], "payload": {"label": "C"}},
]})

import time; time.sleep(5)  # allow index to update

result = run({"operation": "query", "collection": "smoke-test",
              "vector": [1.0, 0.0, 0.0, 0.0], "top_k": 3})
print(result["matches"])
assert result["matches"][0]["id"] == "a"
assert result["matches"][0]["score"] > result["matches"][1]["score"]

run({"operation": "delete", "collection": "smoke-test", "ids": ["a", "b", "c"]})
print("Smoke test passed.")
EOF
```

## Copy into exported repo

- Tool: `tools/pinecone_vector_ops.py`
- Shared schemas: `runtime/schemas/tools/vector_*.json`
- Register in: `runtime/tools/registry.py`
- Add to `.env.example`:
  ```
  PINECONE_API_KEY=
  PINECONE_INDEX=my-index
  PINECONE_HOST=
  PINECONE_CLOUD=aws
  PINECONE_CLOUD_REGION=us-east-1
  ```

## Running tests

```bash
py -3.11 -m pytest forge_integrations/recipes/pinecone_vector_ops/tests/ -v
```
