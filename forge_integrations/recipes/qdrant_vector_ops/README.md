# qdrant_vector_ops

Qdrant vector database operations recipe: ensure collection, upsert, query, delete.

Exposes a single `run(args)` entry point that dispatches on `args["operation"]`.

## Operations

| Operation            | Description                              |
|----------------------|------------------------------------------|
| `ensure_collection`  | Create collection if it does not exist   |
| `upsert`             | Insert or update points                  |
| `query`              | Nearest-neighbour search (ANN)           |
| `delete`             | Delete points by ID                      |

## Input / output schemas

Shared provider-agnostic schemas live in `forge_integrations/shared/schemas/`:

| Schema file                             | Used by operation     |
|-----------------------------------------|-----------------------|
| `vector_ensure_collection.input.json`   | `ensure_collection`   |
| `vector_upsert.input.json`              | `upsert`              |
| `vector_query.input.json`               | `query`               |
| `vector_query.output.json`              | `query` (output)      |
| `vector_delete.input.json`              | `delete`              |

## Env vars

| Variable                | Required | Default | Description                            |
|-------------------------|----------|---------|----------------------------------------|
| `QDRANT_URL`            | yes      | —       | Qdrant instance URL                    |
| `QDRANT_API_KEY`        | no       | —       | Cloud API key (omit for local)         |
| `QDRANT_TIMEOUT_SECONDS`| no       | `15`    | Client timeout in seconds              |

## Security

- **HTTPS enforced** for non-localhost hosts. HTTP is only allowed for
  `localhost`, `127.0.0.1`, and `::1`.
- API key is never written into operation outputs.
- Upsert batches capped at **1 000 points** per call (schema-enforced).

## Example calls

```python
from forge_integrations.recipes.qdrant_vector_ops.tool import run

# Ensure collection
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
})
# result["matches"] → [{"id": "doc-1", "score": 0.95, "payload": {...}}, ...]

# Delete
run({
    "operation": "delete",
    "collection": "documents",
    "ids": ["doc-1", "doc-2"],
})
```

## Filter format

Qdrant filters follow the `qdrant-client` `Filter` model.
Pass `filter` as a dict matching `Filter` keyword arguments:

```python
run({
    "operation": "query",
    "collection": "documents",
    "vector": [...],
    "filter": {"must": [{"key": "category", "match": {"value": "oncology"}}]},
})
```

See [Qdrant filtering docs](https://qdrant.tech/documentation/concepts/filtering/).

## Using via vector_router (provider-agnostic)

```python
from forge_integrations.shared.vector_router import vector_query

result = vector_query({
    "provider": "qdrant",
    "collection": "documents",
    "vector": [...],
    "top_k": 5,
})
```

## Smoke test (requires running Qdrant)

```bash
# 1. Start Qdrant
docker run -p 6333:6333 qdrant/qdrant

# 2. Set env
export QDRANT_URL=http://localhost:6333

# 3. Run smoke
python - <<'EOF'
from forge_integrations.recipes.qdrant_vector_ops.tool import run

DIM = 4
run({"operation": "ensure_collection", "collection": "smoke", "size": DIM})

run({"operation": "upsert", "collection": "smoke", "points": [
    {"id": "a", "vector": [1.0, 0.0, 0.0, 0.0], "payload": {"label": "A"}},
    {"id": "b", "vector": [0.0, 1.0, 0.0, 0.0], "payload": {"label": "B"}},
    {"id": "c", "vector": [0.0, 0.0, 1.0, 0.0], "payload": {"label": "C"}},
]})

result = run({"operation": "query", "collection": "smoke", "vector": [1.0, 0.0, 0.0, 0.0], "top_k": 3})
print(result["matches"])
assert result["matches"][0]["id"] == "a"
assert result["matches"][0]["score"] > result["matches"][1]["score"]

run({"operation": "delete", "collection": "smoke", "ids": ["a", "b", "c"]})
print("Smoke test passed.")
EOF
```

## Copy into exported repo

- Tool: `tools/qdrant_vector_ops.py`
- Shared schemas: `runtime/schemas/tools/vector_*.json`
- Register in: `runtime/tools/registry.py`
- Add to `.env.example`:
  ```
  QDRANT_URL=http://localhost:6333
  QDRANT_API_KEY=
  QDRANT_TIMEOUT_SECONDS=15
  ```

## Running tests

```bash
py -3.11 -m pytest forge_integrations/recipes/qdrant_vector_ops/tests/ -v
```
