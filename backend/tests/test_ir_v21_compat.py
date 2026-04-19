"""Compatibility tests for v2.1 schema coercions."""

from __future__ import annotations

from agent_compiler.models.ir import parse_ir


def test_parse_ir_normalizes_empty_handoff_schema_refs() -> None:
    payload = {
        "ir_version": "2",
        "flow": {
            "id": "compat_schema_refs",
            "name": "Compat",
            "version": "1.0.0",
            "engine_preference": "langchain",
            "description": "",
        },
        "agents": [
            {
                "id": "main",
                "name": "Main",
                "graph": {
                    "root": "out",
                    "nodes": [
                        {
                            "id": "out",
                            "type": "Output",
                            "name": "Output",
                            "params": {"is_start": True, "output_template": "{input}"},
                        }
                    ],
                    "edges": [],
                },
                "llm": {"provider": "auto", "model": "gpt-4o-mini", "temperature": 0.7},
                "tools_allowlist": [],
                "memory_namespace": "main",
                "budgets": {"max_depth": 5},
            }
        ],
        "entrypoints": [{"name": "main", "agent_id": "main", "description": ""}],
        "handoffs": [
            {
                "from_agent_id": "main",
                "to_agent_id": "main2",
                "mode": "call",
                "input_schema": {},
                "output_schema": {},
            }
        ],
        "resources": {"shared_memory_namespaces": [], "global_tools": []},
    }
    payload["agents"].append(
        {
            "id": "main2",
            "name": "Main2",
            "graph": {
                "root": "out2",
                "nodes": [
                    {
                        "id": "out2",
                        "type": "Output",
                        "name": "Output2",
                        "params": {"is_start": True, "output_template": "{input}"},
                    }
                ],
                "edges": [],
            },
            "llm": {"provider": "auto", "model": "gpt-4o-mini", "temperature": 0.7},
            "tools_allowlist": [],
            "memory_namespace": "main2",
            "budgets": {"max_depth": 5},
        }
    )

    ir = parse_ir(payload)
    assert ir.handoffs[0].input_schema is None
    assert ir.handoffs[0].output_schema is None
