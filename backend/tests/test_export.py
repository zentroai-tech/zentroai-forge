"""Tests for v2 export functionality."""

import io
import json
import logging
import tempfile
import zipfile
from pathlib import Path

import pytest

from agent_compiler.models.ir import Edge, EngineType, Flow, Node, NodeType
from agent_compiler.models.ir import FallbackSpec
from agent_compiler.models.ir_v2 import AgentSpec, EntrypointSpec, FlowIRv2, GraphSpec
from agent_compiler.observability.logging import JSONFormatter, redact_secrets
from agent_compiler.services.export_config import (
    ExportConfig,
    ExportEngine,
    ExportPackaging,
    ExportSurface,
)
from agent_compiler.services.export_service import ExportService, ExportTarget
from agent_compiler.services.multiagent_generator import MultiAgentGenerator


@pytest.fixture
def sample_flow_ir() -> FlowIRv2:
    """Create a sample v2 flow IR for testing."""
    return FlowIRv2(
        ir_version="2",
        flow=Flow(
            id="test-rag-agent",
            name="Test RAG Agent",
            version="1.0.0",
            description="A test RAG agent for export testing",
            engine_preference=EngineType.LANGCHAIN,
        ),
        agents=[
            AgentSpec(
                id="main",
                name="Main",
                graph=GraphSpec(
                    nodes=[
                        Node(
                            id="retriever",
                            type=NodeType.RETRIEVER,
                            name="Document Retriever",
                            params={"query_template": "{input}", "top_k": 5, "is_start": True},
                        ),
                        Node(
                            id="llm",
                            type=NodeType.LLM,
                            name="Answer Generator",
                            params={"model": "gpt-4o-mini", "temperature": 0.7},
                        ),
                        Node(
                            id="output",
                            type=NodeType.OUTPUT,
                            name="Final Output",
                            params={"output_template": "{current}", "format": "text"},
                        ),
                    ],
                    edges=[
                        Edge(source="retriever", target="llm"),
                        Edge(source="llm", target="output"),
                    ],
                    root="retriever",
                ),
            )
        ],
        entrypoints=[EntrypointSpec(name="main", agent_id="main")],
        handoffs=[],
    )


class TestExportService:
    """Tests for ExportService with v2 export contract."""

    def test_export_creates_valid_zip(self, sample_flow_ir: FlowIRv2):
        service = ExportService()
        zip_bytes = service.export_flow(sample_flow_ir, target=ExportTarget.RUNTIME)
        assert len(zip_bytes) > 0
        assert zipfile.ZipFile(io.BytesIO(zip_bytes)).testzip() is None

    def test_export_contains_required_files(self, sample_flow_ir: FlowIRv2):
        service = ExportService()
        zip_bytes = service.export_flow(sample_flow_ir, target=ExportTarget.RUNTIME)
        names = set(zipfile.ZipFile(io.BytesIO(zip_bytes)).namelist())

        required = {
            ".env.example",
            ".dockerignore",
            "Dockerfile",
            "docker-compose.yml",
            "Makefile",
            "README.md",
            "main.py",
            "pyproject.toml",
            "agents/__init__.py",
            "agents/main.py",
            "agents/registry.py",
            "ir.json",
            "requirements.txt",
            "requirements.lock",
            "requirements-dev.txt",
            "runtime/__init__.py",
            "runtime/providers/__init__.py",
            "runtime/providers/mock.py",
            "runtime/tools/__init__.py",
            "runtime/tools/registry.py",
            "runtime/tools/policies.py",
            "runtime/tools/adapters/__init__.py",
            "runtime/tools/adapters/local.py",
            "runtime/tools/adapters/mcp.py",
            "runtime/tools/schemas/tools.echo.json",
            "runtime/tools/schemas/tools.safe_calculator.json",
            "runtime/tools/schemas/tools.http_get.json",
            "runtime/mcp/__init__.py",
            "runtime/mcp/config.py",
            "runtime/mcp/client.py",
            "runtime/approvals/__init__.py",
            "runtime/approvals/types.py",
            "runtime/approvals/policy.py",
            "runtime/approvals/store.py",
            "runtime/replay/__init__.py",
            "runtime/replay/formats.py",
            "runtime/replay/recorder.py",
            "runtime/replay/player.py",
            "runtime/replay/cli.py",
            "runtime/resilience/__init__.py",
            "runtime/resilience/rate_limit.py",
            "runtime/resilience/circuit_breaker.py",
            "runtime/resilience/policies.py",
            "runtime/state/__init__.py",
            "runtime/state/store.py",
            "runtime/state/factory.py",
            "runtime/state/stores/__init__.py",
            "runtime/state/stores/inmemory.py",
            "runtime/state/stores/redis.py",
            "runtime/loop/__init__.py",
            "runtime/loop/plan_act_loop.py",
            "runtime/memory_write_policy.py",
            "runtime/memory_summarizer.py",
            "runtime/memory_retrieval_iface.py",
            "runtime/budgets.py",
            "runtime/config.py",
            "runtime/dispatcher.py",
            "runtime/healthcheck.py",
            "runtime/memory.py",
            "runtime/node_runtime.py",
            "runtime/observability.py",
            "runtime/policy_guard.py",
            "runtime/retry.py",
            "runtime/server.py",
            "runtime/schema_registry.py",
            "runtime/schema_validation.py",
            "runtime/schemas/index.json",
            "runtime/supervisor.py",
            "settings.py",
            ".github/workflows/ci.yml",
            "tests/__init__.py",
            "tests/test_smoke_multiagent.py",
            "tests/test_tool_registry.py",
            "tests/test_tool_policy.py",
            "tests/test_mcp_adapter_mock.py",
            "tests/test_state_store.py",
            "tests/test_plan_act_loop_smoke.py",
            "tests/test_approvals_flow.py",
            "tests/test_replay_determinism.py",
            "tests/test_rate_limit_and_circuit.py",
            "tests/test_memory_write_policy.py",
            "evals/run.py",
            "evals/smoke.json",
            "evals/regression.json",
        }
        assert required.issubset(names)

    def test_langgraph_target_includes_langgraph_runner(self, sample_flow_ir: FlowIRv2):
        service = ExportService()
        zip_bytes = service.export_flow(sample_flow_ir, target=ExportTarget.LANGGRAPH)
        zf = zipfile.ZipFile(io.BytesIO(zip_bytes))
        names = set(zf.namelist())
        requirements = zf.read("requirements.txt").decode("utf-8")
        runner = zf.read("runtime/langgraph_runner.py").decode("utf-8")

        assert "runtime/langgraph_runner.py" in names
        assert "langgraph==" in requirements
        assert "run_agent_once" in runner
        assert "add_conditional_edges" in runner
        assert "execute_root" not in runner

    def test_api_server_target_includes_api_server_artifacts(self, sample_flow_ir: FlowIRv2):
        service = ExportService()
        zip_bytes = service.export_flow(sample_flow_ir, target=ExportTarget.API_SERVER)
        zf = zipfile.ZipFile(io.BytesIO(zip_bytes))
        names = set(zf.namelist())
        requirements = zf.read("requirements.txt").decode("utf-8")
        api_server = zf.read("api.py").decode("utf-8")

        assert "api.py" in names
        assert "fastapi==" in requirements
        assert "uvicorn[standard]==" in requirements
        assert "@app.get(\"/metrics\")" in api_server
        assert "@app.get(\"/metrics/prometheus\")" in api_server
        assert "@app.get(\"/ready\")" in api_server
        assert "@app.get(\"/healthz\")" in api_server
        assert "@app.get(\"/readyz\")" in api_server

    def test_export_runtime_hardening_signals_present(self, sample_flow_ir: FlowIRv2):
        service = ExportService()
        zip_bytes = service.export_flow(sample_flow_ir, target=ExportTarget.RUNTIME)
        zf = zipfile.ZipFile(io.BytesIO(zip_bytes))
        dispatcher = zf.read("runtime/dispatcher.py").decode("utf-8")
        observability = zf.read("runtime/observability.py").decode("utf-8")
        env_example = zf.read(".env.example").decode("utf-8")
        dockerfile = zf.read("Dockerfile").decode("utf-8")
        compose = zf.read("docker-compose.yml").decode("utf-8")
        ci_workflow = zf.read(".github/workflows/ci.yml").decode("utf-8")
        pyproject = zf.read("pyproject.toml").decode("utf-8")
        makefile = zf.read("Makefile").decode("utf-8")
        dev_requirements = zf.read("requirements-dev.txt").decode("utf-8")
        requirements = zf.read("requirements.txt").decode("utf-8")
        readme = zf.read("README.md").decode("utf-8")
        runtime_server = zf.read("runtime/server.py").decode("utf-8")

        assert "run_id =" in dispatcher
        assert "BUDGET_WARNING" in dispatcher
        assert "BUDGET_EXCEEDED" in dispatcher
        assert "NODE_SLOW" in dispatcher
        assert "FLOW_POLICIES.get(\"redaction\"" in observability
        assert "inc_counter(" in observability
        assert "snapshot_metrics_prometheus" in observability
        assert "build_log_record" in observability
        assert "runs_total" in observability
        assert "runs_failed_total" in observability
        assert "tool_calls_total" in observability
        assert "NODE_TIMEOUT" in dispatcher
        assert "record_timing_ms(" in dispatcher
        assert "FORGE_ENV=production" in env_example
        assert "DEV_MODE=0" in env_example
        assert "FORGE_SLOW_NODE_MS=1500" in env_example
        assert "FORGE_OBS_PORT=9090" in env_example
        assert "FORGE_ALLOW_SCHEMA_SOFT_FAIL=0" in env_example
        assert "STATE_BACKEND=inmemory" in env_example
        assert "REDIS_URL=redis://localhost:6379/0" in env_example
        assert "MCP_SERVERS=[]" in env_example
        assert "TOOL_ALLOWLIST=tools.*,mcp:*" in env_example
        assert "TOOL_DENYLIST=python_repl,shell,exec" in env_example
        assert "RUNTIME_API_TOKEN=" in env_example
        assert "RUNTIME_API_TOKEN=change-me" not in env_example
        assert "RUN_STORE_BACKEND=filesystem" in env_example
        assert "RUN_STORE_DIR=artifacts/runs" in env_example
        assert "HTTP_GET_ALLOW_DOMAINS=example.com,api.mycorp.com" in env_example
        assert "LOOP_MAX_ITERS=10" in env_example
        assert "REPLAY_MODE=off" in env_example
        assert "APPROVALS_BACKEND=inmemory" in env_example
        assert "TOOL_RATE_LIMIT_RPS_DEFAULT=2" in env_example
        assert "MEMORY_WRITE_CONFIDENCE_THRESHOLD=0.7" in env_example
        assert "USER appuser" in dockerfile
        assert "uv.lock" in dockerfile
        assert "PYTHONDONTWRITEBYTECODE=1" in dockerfile
        assert "/tmp/forge" in dockerfile
        assert "python -m runtime.healthcheck" in dockerfile
        assert ".mypy_cache/" in zf.read(".dockerignore").decode("utf-8")
        assert ".ruff_cache/" in zf.read(".dockerignore").decode("utf-8")
        assert "dockerfile: Dockerfile" in compose
        assert "healthcheck:" in compose
        assert "uv sync --frozen" in ci_workflow
        assert "pip-audit -r requirements.audit.txt" in ci_workflow
        assert "bandit -q -r runtime agents -x tests" in ci_workflow
        assert "ruff check ." in ci_workflow
        assert "ruff format --check ." in ci_workflow
        assert "mypy runtime agents" in ci_workflow
        assert "evals/run.py --suite smoke" in ci_workflow
        assert "evals/run.py --suite regression" in ci_workflow
        assert "gitleaks/gitleaks-action@v2" in ci_workflow
        assert "cyclonedx-json" in ci_workflow
        assert "-ll -ii" in ci_workflow
        assert "bandit==" in dev_requirements
        assert "pip-audit==" in dev_requirements
        assert "## Security" in readme
        assert "pip-audit -r requirements.lock" in readme
        assert "pytest==" not in requirements
        assert "pytest-asyncio==" not in requirements
        assert "[tool.ruff]" in pyproject
        assert "[tool.mypy]" in pyproject
        assert "[tool.pytest.ini_options]" in pyproject
        assert "check: lint type test" in makefile
        assert "if path == \"/tools\":" in runtime_server
        assert "if path == \"/tools/health\":" in runtime_server
        assert "require_auth(path, self.headers.get(\"Authorization\"))" in runtime_server
        assert "run_store = get_run_store()" in runtime_server
        assert "if path == \"/runs\":" in runtime_server
        assert "if path.startswith(\"/runs/\") and path.endswith(\"/steps\"):" in runtime_server
        assert "if path.startswith(\"/runs/\") and path.endswith(\"/artifacts\"):" in runtime_server
        assert "if \"/artifacts/\" in path and path.startswith(\"/runs/\"):" in runtime_server
        assert "if path == \"/replay\":" in runtime_server
        assert "if path.startswith(\"/state/\"):" in runtime_server
        assert "if path == \"/approvals\":" in runtime_server
        assert "if path.startswith(\"/approvals/\") and path.endswith(\"/approve\"):" in runtime_server
        assert "if path.startswith(\"/sessions/\") and path.endswith(\"/memory\"):" in runtime_server
        assert "if path.startswith(\"/sessions/\") and path.endswith(\"/summarize\"):" in runtime_server
        assert "dispatch(dict(input_payload), entrypoint=entrypoint)" in runtime_server

    def test_export_zip_excludes_transient_cache_files(self, sample_flow_ir: FlowIRv2):
        service = ExportService()
        zip_bytes = service.export_flow(sample_flow_ir, target=ExportTarget.RUNTIME)
        names = set(zipfile.ZipFile(io.BytesIO(zip_bytes)).namelist())
        assert not any("/__pycache__/" in f or f.endswith(".pyc") for f in names)
        assert not any(f.startswith(".pytest_cache/") for f in names)
        assert not any(f.startswith(".mypy_cache/") for f in names)
        assert not any(f.startswith(".ruff_cache/") for f in names)

    def test_export_schema_soft_fail_default_is_env_controlled(self, sample_flow_ir: FlowIRv2):
        service = ExportService()
        zip_bytes = service.export_flow(sample_flow_ir, target=ExportTarget.RUNTIME)
        zf = zipfile.ZipFile(io.BytesIO(zip_bytes))
        settings = zf.read("settings.py").decode("utf-8")
        assert "FORGE_ALLOW_SCHEMA_SOFT_FAIL" in settings

    def test_export_ir_snapshot_is_v2(self, sample_flow_ir: FlowIRv2):
        service = ExportService()
        zip_bytes = service.export_flow(sample_flow_ir, target=ExportTarget.RUNTIME)
        zf = zipfile.ZipFile(io.BytesIO(zip_bytes))
        ir_payload = json.loads(zf.read("ir.json").decode("utf-8"))
        assert ir_payload["ir_version"] == "2"
        assert ir_payload["flow"]["id"] == sample_flow_ir.flow.id
        assert len(ir_payload["agents"]) == 1

    def test_export_readme_has_flow_info(self, sample_flow_ir: FlowIRv2):
        service = ExportService()
        zip_bytes = service.export_flow(sample_flow_ir, target=ExportTarget.RUNTIME)
        zf = zipfile.ZipFile(io.BytesIO(zip_bytes))
        content = zf.read("README.md").decode("utf-8")
        assert sample_flow_ir.flow.name in content
        assert "multi-agent" in content.lower()

    def test_export_without_tests(self, sample_flow_ir: FlowIRv2):
        service = ExportService()
        zip_bytes = service.export_flow(
            sample_flow_ir,
            target=ExportTarget.RUNTIME,
            include_tests=False,
        )
        names = set(zipfile.ZipFile(io.BytesIO(zip_bytes)).namelist())
        assert "tests/test_smoke_multiagent.py" not in names

    def test_export_fails_fast_on_missing_schema_ref(self, sample_flow_ir: FlowIRv2):
        flow_ir = sample_flow_ir.model_copy(deep=True)
        flow_ir.agents[0].graph.nodes[0].params["input_schema"] = {
            "kind": "json_schema",
            "ref": "does-not-exist-schema.json",
        }

        service = ExportService()
        with pytest.raises(ValueError, match="Missing schema file"):
            service.export_flow(flow_ir, target=ExportTarget.RUNTIME)

    def test_export_fails_fast_on_unsupported_fallback_provider(self, sample_flow_ir: FlowIRv2):
        flow_ir = sample_flow_ir.model_copy(deep=True)
        flow_ir.agents[0].fallbacks = FallbackSpec(
            llm_chain=[{"provider": "unsupported_provider", "model": "x"}],
            tool_fallbacks={},
        )

        service = ExportService()
        with pytest.raises(ValueError, match="unsupported provider"):
            service.export_flow(flow_ir, target=ExportTarget.RUNTIME)

    def test_export_schema_index_includes_hash_metadata(self, sample_flow_ir: FlowIRv2, tmp_path: Path):
        flow_ir = sample_flow_ir.model_copy(deep=True)
        # Create a real schema file in a temp directory so the exporter can read it
        schema_file = tmp_path / "handoff_input.schema.json"
        schema_file.write_text(
            '{"type": "object", "required": ["input"], "properties": {"input": {"type": "string"}}}',
            encoding="utf-8",
        )
        flow_ir.agents[0].graph.nodes[0].params["input_schema"] = {
            "kind": "json_schema",
            "ref": str(schema_file),
        }

        service = ExportService()
        zip_bytes = service.export_flow(flow_ir, target=ExportTarget.RUNTIME)
        zf = zipfile.ZipFile(io.BytesIO(zip_bytes))
        index_payload = json.loads(zf.read("runtime/schemas/index.json").decode("utf-8"))
        runtime_ref = "runtime/schemas/schema_0_handoff_input.schema.json"
        assert runtime_ref in index_payload
        entry = index_payload[runtime_ref]
        assert "path" in entry and entry["path"].startswith("runtime/schemas/")
        assert "sha256" in entry and len(entry["sha256"]) == 64
        assert entry.get("kind") == "json_schema"

    def test_export_materializes_known_pydantic_refs(self, sample_flow_ir: FlowIRv2):
        flow_ir = sample_flow_ir.model_copy(deep=True)
        flow_ir.handoffs = [
            {
                "from_agent_id": "main",
                "to_agent_id": "main",
                "mode": "call",
                "input_schema": {"kind": "pydantic", "ref": "contracts.HandoffInput"},
                "output_schema": {"kind": "pydantic", "ref": "contracts.HandoffOutput"},
            }
        ]
        # self-handoff is invalid; use second dummy agent
        flow_ir.agents.append(
            flow_ir.agents[0].model_copy(update={"id": "worker", "name": "Worker"})
        )
        flow_ir.handoffs = [
            {
                "from_agent_id": "main",
                "to_agent_id": "worker",
                "mode": "call",
                "input_schema": {"kind": "pydantic", "ref": "contracts.HandoffInput"},
                "output_schema": {"kind": "pydantic", "ref": "contracts.HandoffOutput"},
            }
        ]

        service = ExportService()
        zip_bytes = service.export_flow(flow_ir, target=ExportTarget.RUNTIME)
        zf = zipfile.ZipFile(io.BytesIO(zip_bytes))
        index_payload = json.loads(zf.read("runtime/schemas/index.json").decode("utf-8"))
        assert len(index_payload) >= 1

    def test_export_materializes_schema_registry_refs(self, sample_flow_ir: FlowIRv2):
        flow_ir = sample_flow_ir.model_copy(deep=True)
        flow_ir.resources.schema_contracts = {
            "handoff_input": {
                "type": "object",
                "required": ["input"],
                "properties": {"input": {"type": "string"}},
            },
            "handoff_output": {
                "type": "object",
                "required": ["result"],
                "properties": {"result": {"type": "string"}},
            },
        }
        flow_ir.agents.append(
            flow_ir.agents[0].model_copy(update={"id": "worker", "name": "Worker"})
        )
        flow_ir.handoffs = [
            {
                "from_agent_id": "main",
                "to_agent_id": "worker",
                "mode": "call",
                "input_schema": {"kind": "json_schema", "ref": "schema://handoff_input"},
                "output_schema": {"kind": "json_schema", "ref": "schema://handoff_output"},
            }
        ]

        service = ExportService()
        zip_bytes = service.export_flow(flow_ir, target=ExportTarget.RUNTIME)
        zf = zipfile.ZipFile(io.BytesIO(zip_bytes))
        index_payload = json.loads(zf.read("runtime/schemas/index.json").decode("utf-8"))
        assert any("handoff_input.schema.json" in key for key in index_payload.keys())


class TestAWSECSExport:
    """Tests for the AWS ECS (Fargate) export target."""

    def test_aws_ecs_export_contains_infra_files(self, sample_flow_ir: FlowIRv2):
        service = ExportService()
        zb = service.export_flow(sample_flow_ir, target=ExportTarget.AWS_ECS)
        names = set(zipfile.ZipFile(io.BytesIO(zb)).namelist())
        required = {
            "infra/aws/ecs/main.tf",
            "infra/aws/ecs/variables.tf",
            "infra/aws/ecs/outputs.tf",
            "infra/aws/ecs/terraform.tfvars.example",
            "README_AWS_ECS.md",
        }
        assert required.issubset(names), f"Missing infra files: {required - names}"

    def test_aws_ecs_main_tf_has_fargate_config(self, sample_flow_ir: FlowIRv2):
        zb = ExportService().export_flow(sample_flow_ir, target=ExportTarget.AWS_ECS)
        tf = zipfile.ZipFile(io.BytesIO(zb)).read("infra/aws/ecs/main.tf").decode()
        assert "FARGATE" in tf
        assert "aws_ecs_cluster" in tf
        assert "aws_ecs_service" in tf
        assert "aws_ecs_task_definition" in tf

    def test_aws_ecs_has_secrets_manager_iam(self, sample_flow_ir: FlowIRv2):
        zb = ExportService().export_flow(sample_flow_ir, target=ExportTarget.AWS_ECS)
        tf = zipfile.ZipFile(io.BytesIO(zb)).read("infra/aws/ecs/main.tf").decode()
        assert "secretsmanager:GetSecretValue" in tf
        assert "aws_iam_role" in tf

    def test_aws_ecs_has_cloudwatch_log_group(self, sample_flow_ir: FlowIRv2):
        zb = ExportService().export_flow(sample_flow_ir, target=ExportTarget.AWS_ECS)
        tf = zipfile.ZipFile(io.BytesIO(zb)).read("infra/aws/ecs/main.tf").decode()
        assert "aws_cloudwatch_log_group" in tf
        assert "awslogs" in tf

    def test_aws_ecs_includes_api_py_with_healthz(self, sample_flow_ir: FlowIRv2):
        zb = ExportService().export_flow(sample_flow_ir, target=ExportTarget.AWS_ECS)
        names = set(zipfile.ZipFile(io.BytesIO(zb)).namelist())
        assert "api.py" in names
        api = zipfile.ZipFile(io.BytesIO(zb)).read("api.py").decode()
        assert "/healthz" in api

    def test_non_aws_exports_unchanged(self, sample_flow_ir: FlowIRv2):
        """Runtime target must contain infra/ skeleton but NOT the full AWS ECS IaC files."""
        zb = ExportService().export_flow(sample_flow_ir, target=ExportTarget.RUNTIME)
        names = set(zipfile.ZipFile(io.BytesIO(zb)).namelist())
        # Skeleton is always generated
        assert any(n.startswith("infra/") for n in names)
        # iam_policy.json is AWS ECS-only
        assert "infra/aws/ecs/iam_policy.json" not in names


# ---------------------------------------------------------------------------
# ExportConfig unit tests
# ---------------------------------------------------------------------------


class TestExportConfig:
    """Unit tests for the ExportConfig composition model."""

    def test_from_preset_all_valid(self):
        """All four standard presets must parse without error."""
        presets = {
            "langgraph":  (ExportEngine.LANGGRAPH,  ExportSurface.CLI,  ExportPackaging.LOCAL),
            "runtime":    (ExportEngine.DISPATCHER, ExportSurface.CLI,  ExportPackaging.LOCAL),
            "api_server": (ExportEngine.DISPATCHER, ExportSurface.HTTP, ExportPackaging.LOCAL),
            "aws-ecs":    (ExportEngine.DISPATCHER, ExportSurface.HTTP, ExportPackaging.AWS_ECS),
        }
        for name, (engine, surface, packaging) in presets.items():
            cfg = ExportConfig.from_preset(name)
            assert cfg.engine == engine, f"{name}: engine mismatch"
            assert cfg.surface == surface, f"{name}: surface mismatch"
            assert cfg.packaging == packaging, f"{name}: packaging mismatch"

    def test_from_preset_invalid_raises(self):
        with pytest.raises(ValueError, match="Unknown export preset"):
            ExportConfig.from_preset("invalid-target")

    def test_validate_composition_ecs_requires_http(self):
        """aws-ecs + cli is an invalid combo and must raise ValueError."""
        cfg = ExportConfig(
            engine=ExportEngine.DISPATCHER,
            surface=ExportSurface.CLI,
            packaging=ExportPackaging.AWS_ECS,
        )
        with pytest.raises(ValueError, match="HTTP surface"):
            cfg.validate_composition()

    def test_validate_composition_valid_combos(self):
        """All four standard preset configs must pass validate_composition()."""
        for preset in ("langgraph", "runtime", "api_server", "aws-ecs"):
            ExportConfig.from_preset(preset).validate_composition()  # must not raise

    def test_cache_key_maps_to_preset_names(self):
        """Standard preset combos round-trip back to their preset name."""
        assert ExportConfig.from_preset("langgraph").cache_key == "langgraph"
        assert ExportConfig.from_preset("runtime").cache_key == "runtime"
        assert ExportConfig.from_preset("api_server").cache_key == "api_server"
        assert ExportConfig.from_preset("aws-ecs").cache_key == "aws-ecs"

    def test_cache_key_advanced_combo_is_canonical(self):
        """An advanced combo that doesn't match any preset gets a canonical key."""
        cfg = ExportConfig(
            engine=ExportEngine.LANGGRAPH,
            surface=ExportSurface.HTTP,
            packaging=ExportPackaging.LOCAL,
        )
        assert cfg.cache_key == "langgraph-http-local"

    def test_label_all_presets(self):
        labels = {
            "langgraph":  "LangGraph",
            "runtime":    "Simple Runtime",
            "api_server": "API Server",
            "aws-ecs":    "AWS ECS (Fargate) + Dispatcher",
        }
        for preset, expected in labels.items():
            assert ExportConfig.from_preset(preset).label == expected, preset

    def test_label_advanced_langgraph_http(self):
        cfg = ExportConfig(
            engine=ExportEngine.LANGGRAPH,
            surface=ExportSurface.HTTP,
            packaging=ExportPackaging.LOCAL,
        )
        assert cfg.label == "LangGraph + API Server"

    def test_label_advanced_langgraph_ecs(self):
        cfg = ExportConfig(
            engine=ExportEngine.LANGGRAPH,
            surface=ExportSurface.HTTP,
            packaging=ExportPackaging.AWS_ECS,
        )
        assert cfg.label == "AWS ECS (Fargate) + LangGraph"


# ---------------------------------------------------------------------------
# Composition API integration tests
# ---------------------------------------------------------------------------


class TestExportConfigComposition:
    """Integration tests: export_flow() called with ExportConfig instead of target string."""

    def _zip(self, zb: bytes) -> zipfile.ZipFile:
        return zipfile.ZipFile(io.BytesIO(zb))

    def test_dispatcher_cli_local_matches_runtime(self, sample_flow_ir: FlowIRv2):
        """dispatcher+cli+local is equivalent to the legacy 'runtime' target."""
        cfg = ExportConfig(ExportEngine.DISPATCHER, ExportSurface.CLI, ExportPackaging.LOCAL)
        zb = ExportService().export_flow(sample_flow_ir, config=cfg)
        names = set(self._zip(zb).namelist())
        assert "main.py" in names
        assert "api.py" not in names
        # Skeleton infra/ is always generated; full ECS IaC (iam_policy.json) is not
        assert any(n.startswith("infra/") for n in names)
        assert "infra/aws/ecs/iam_policy.json" not in names

    def test_langgraph_cli_local_includes_runner(self, sample_flow_ir: FlowIRv2):
        """langgraph+cli+local must include the langgraph runner."""
        cfg = ExportConfig(ExportEngine.LANGGRAPH, ExportSurface.CLI, ExportPackaging.LOCAL)
        zb = ExportService().export_flow(sample_flow_ir, config=cfg)
        names = set(self._zip(zb).namelist())
        assert "runtime/langgraph_runner.py" in names
        assert "api.py" not in names

    def test_dispatcher_http_local_includes_api_py(self, sample_flow_ir: FlowIRv2):
        """dispatcher+http+local is equivalent to the legacy 'api_server' target."""
        cfg = ExportConfig(ExportEngine.DISPATCHER, ExportSurface.HTTP, ExportPackaging.LOCAL)
        zb = ExportService().export_flow(sample_flow_ir, config=cfg)
        names = set(self._zip(zb).namelist())
        assert "api.py" in names
        # Skeleton infra/ is always generated; full ECS IaC (iam_policy.json) is not
        assert any(n.startswith("infra/") for n in names)
        assert "infra/aws/ecs/iam_policy.json" not in names
        reqs = self._zip(zb).read("requirements.txt").decode()
        assert "fastapi==" in reqs
        assert "uvicorn[standard]==" in reqs

    def test_dispatcher_http_ecs_includes_infra_and_api(self, sample_flow_ir: FlowIRv2):
        """dispatcher+http+aws-ecs is equivalent to the legacy 'aws-ecs' target."""
        cfg = ExportConfig(ExportEngine.DISPATCHER, ExportSurface.HTTP, ExportPackaging.AWS_ECS)
        zb = ExportService().export_flow(sample_flow_ir, config=cfg)
        names = set(self._zip(zb).namelist())
        assert "api.py" in names
        assert "infra/aws/ecs/main.tf" in names
        assert "infra/aws/ecs/variables.tf" in names
        assert "README_AWS_ECS.md" in names

    def test_invalid_ecs_cli_combo_raises_at_export(self, sample_flow_ir: FlowIRv2):
        """Attempting to export with ecs+cli must raise ValueError."""
        cfg = ExportConfig(ExportEngine.DISPATCHER, ExportSurface.CLI, ExportPackaging.AWS_ECS)
        with pytest.raises(ValueError, match="HTTP surface"):
            ExportService().export_flow(sample_flow_ir, config=cfg)

    def test_config_kwarg_overrides_target(self, sample_flow_ir: FlowIRv2):
        """When both target and config are provided, config takes priority."""
        cfg = ExportConfig.from_preset("api_server")
        # Passing target="runtime" but config="api_server" → api_server should win
        zb = ExportService().export_flow(
            sample_flow_ir, target=ExportTarget.RUNTIME, config=cfg
        )
        names = set(self._zip(zb).namelist())
        assert "api.py" in names  # api_server artifact present → config won

    def test_requirements_runtime_no_fastapi(self, sample_flow_ir: FlowIRv2):
        cfg = ExportConfig.from_preset("runtime")
        zb = ExportService().export_flow(sample_flow_ir, config=cfg)
        reqs = self._zip(zb).read("requirements.txt").decode()
        assert "fastapi==" not in reqs
        assert "uvicorn[standard]==" not in reqs

    def test_requirements_langgraph_has_langgraph(self, sample_flow_ir: FlowIRv2):
        cfg = ExportConfig.from_preset("langgraph")
        zb = ExportService().export_flow(sample_flow_ir, config=cfg)
        reqs = self._zip(zb).read("requirements.txt").decode()
        assert "langgraph==" in reqs


# ---------------------------------------------------------------------------
# Log redaction tests
# ---------------------------------------------------------------------------


class TestLogRedaction:
    """Unit tests for the redact_secrets() function and JSONFormatter integration."""

    def test_redact_anthropic_key(self):
        text = "Using sk-ant-api03-abc12345678901234567890 for this call"
        result = redact_secrets(text)
        assert "[REDACTED:anthropic]" in result
        assert "sk-ant-" not in result

    def test_redact_openai_key(self):
        text = "Using sk-abcdefghij1234567890XY in the Authorization header"
        result = redact_secrets(text)
        assert "[REDACTED:openai]" in result
        assert "sk-abcdefghij1234567890XY" not in result

    def test_redact_bearer_token(self):
        text = "Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.abc"
        result = redact_secrets(text)
        assert "Bearer [REDACTED:token]" in result
        assert "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9" not in result

    def test_redact_generic_api_key(self):
        text = "ANTHROPIC_API_KEY=sk-ant-tooshort is set"
        # The generic pattern matches "api_key=..." before the sk- pattern
        result = redact_secrets(text)
        assert "[REDACTED]" in result or "[REDACTED:anthropic]" in result

    def test_redact_generic_secret(self):
        text = "DB password=supersecretvalue123 is stored here"
        result = redact_secrets(text)
        assert "[REDACTED]" in result
        assert "supersecretvalue123" not in result

    def test_no_redaction_needed(self):
        text = "Normal log message without any secrets"
        assert redact_secrets(text) == text

    def test_empty_string(self):
        assert redact_secrets("") == ""

    def test_json_formatter_redacts_anthropic_key(self):
        """JSONFormatter.format() must call redact_secrets on record.msg."""
        formatter = JSONFormatter()
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg="Calling API with sk-ant-api03-secretkey1234567890",
            args=(),
            exc_info=None,
        )
        output = formatter.format(record)
        data = json.loads(output)
        assert "[REDACTED:anthropic]" in data["message"]
        assert "sk-ant-" not in data["message"]


# ---------------------------------------------------------------------------
# PR_001 — Security P0 tests
# ---------------------------------------------------------------------------


def _minimal_ir() -> FlowIRv2:
    """Minimal FlowIRv2 for generator-level tests."""
    return FlowIRv2(
        ir_version="2",
        flow=Flow(
            id="test-flow",
            name="Test Flow",
            version="0.1.0",
            engine_preference=EngineType.LANGCHAIN,
        ),
        agents=[
            AgentSpec(
                id="main",
                name="Main",
                graph=GraphSpec(
                    nodes=[
                        Node(
                            id="output",
                            type=NodeType.OUTPUT,
                            name="Output",
                            params={"output_template": "{input}", "is_start": True},
                        )
                    ],
                    edges=[],
                    root="output",
                ),
            )
        ],
        entrypoints=[EntrypointSpec(name="main", agent_id="main")],
        handoffs=[],
    )


class TestSecurityPR001:
    """PR_001 — Security P0: no weak token defaults, production validation."""

    def test_env_example_no_change_me(self):
        """Generated .env.example must not contain the weak 'change-me' default token."""
        gen = MultiAgentGenerator(ir=_minimal_ir())
        with tempfile.TemporaryDirectory() as d:
            gen.generate(Path(d))
            env_example = (Path(d) / ".env.example").read_text()
            assert "change-me" not in env_example

    def test_env_example_has_empty_runtime_token(self):
        """Generated .env.example must declare RUNTIME_API_TOKEN with an empty value."""
        gen = MultiAgentGenerator(ir=_minimal_ir())
        with tempfile.TemporaryDirectory() as d:
            gen.generate(Path(d))
            env_example = (Path(d) / ".env.example").read_text()
            assert "RUNTIME_API_TOKEN=" in env_example

    def test_settings_has_production_validation(self):
        """Generated settings.py must include _validate_production_config."""
        gen = MultiAgentGenerator(ir=_minimal_ir())
        with tempfile.TemporaryDirectory() as d:
            gen.generate(Path(d))
            settings_src = (Path(d) / "settings.py").read_text()
            assert "_validate_production_config" in settings_src
            assert "RUNTIME_API_TOKEN" in settings_src
            assert "FORGE_ENV" in settings_src

    def test_settings_production_validation_calls_on_import(self):
        """Generated settings.py must call _validate_production_config() at module level."""
        gen = MultiAgentGenerator(ir=_minimal_ir())
        with tempfile.TemporaryDirectory() as d:
            gen.generate(Path(d))
            settings_src = (Path(d) / "settings.py").read_text()
            # The call must appear outside any function body (last line of module)
            assert "_validate_production_config()" in settings_src


# ---------------------------------------------------------------------------
# PR_002 — GitOps P0 tests
# ---------------------------------------------------------------------------


class TestGitOpsPR002:
    """PR_002 — GitOps P0: evals __init__, CI path fix, CHANGELOG, release config."""

    def test_evals_init_generated(self):
        """evals/__init__.py must be generated to enable python -m evals.run."""
        gen = MultiAgentGenerator(ir=_minimal_ir())
        with tempfile.TemporaryDirectory() as d:
            gen.generate(Path(d))
            assert (Path(d) / "evals" / "__init__.py").exists()

    def test_ci_evals_step_uses_direct_script_path(self):
        """CI must reference evals/run.py directly (not python -m evals.run)."""
        gen = MultiAgentGenerator(ir=_minimal_ir())
        with tempfile.TemporaryDirectory() as d:
            gen.generate(Path(d))
            ci = (Path(d) / ".github" / "workflows" / "ci.yml").read_text()
            assert "evals/run.py" in ci
            assert "python -m evals.run" not in ci

    def test_ci_evals_step_references_valid_path(self):
        """If CI uses python -m evals.run, evals/__init__.py must exist."""
        gen = MultiAgentGenerator(ir=_minimal_ir())
        with tempfile.TemporaryDirectory() as d:
            gen.generate(Path(d))
            ci = (Path(d) / ".github" / "workflows" / "ci.yml").read_text()
            if "python -m evals.run" in ci:
                assert (Path(d) / "evals" / "__init__.py").exists()

    def test_ci_has_release_job(self):
        """Generated CI must contain a release job."""
        gen = MultiAgentGenerator(ir=_minimal_ir())
        with tempfile.TemporaryDirectory() as d:
            gen.generate(Path(d))
            ci = (Path(d) / ".github" / "workflows" / "ci.yml").read_text()
            assert "release:" in ci
            assert "refs/heads/main" in ci

    def test_ci_eval_results_uploaded_as_artifact(self):
        """Generated CI must upload eval results as artifact."""
        gen = MultiAgentGenerator(ir=_minimal_ir())
        with tempfile.TemporaryDirectory() as d:
            gen.generate(Path(d))
            ci = (Path(d) / ".github" / "workflows" / "ci.yml").read_text()
            assert "eval-results" in ci
            assert "evals/*_results.json" in ci

    def test_changelog_generated(self):
        """Generated project must contain CHANGELOG.md referencing the flow."""
        gen = MultiAgentGenerator(ir=_minimal_ir())
        with tempfile.TemporaryDirectory() as d:
            gen.generate(Path(d))
            changelog = (Path(d) / "CHANGELOG.md").read_text()
            assert "Unreleased" in changelog
            assert "Test Flow" in changelog

    def test_github_release_config_generated(self):
        """Generated project must contain .github/release.yml."""
        gen = MultiAgentGenerator(ir=_minimal_ir())
        with tempfile.TemporaryDirectory() as d:
            gen.generate(Path(d))
            release_yml = (Path(d) / ".github" / "release.yml").read_text()
            assert "changelog:" in release_yml
            assert "breaking" in release_yml

    def test_readme_has_branch_protection_section(self):
        """Generated README must include Branch Protection guidance."""
        gen = MultiAgentGenerator(ir=_minimal_ir())
        with tempfile.TemporaryDirectory() as d:
            gen.generate(Path(d))
            readme = (Path(d) / "README.md").read_text()
            assert "Branch Protection" in readme


class TestProductionHardeningPR003:
    """PR_003 — Production hardening: typed settings, SIGTERM, Redis fail-fast."""

    def test_settings_has_typed_class(self):
        """Generated settings.py must contain _RuntimeSettings and RUNTIME_SETTINGS."""
        gen = MultiAgentGenerator(ir=_minimal_ir())
        with tempfile.TemporaryDirectory() as d:
            gen.generate(Path(d))
            settings = (Path(d) / "settings.py").read_text()
            assert "_RuntimeSettings" in settings
            assert "RUNTIME_SETTINGS = _RuntimeSettings()" in settings

    def test_settings_production_validation_openai_key(self):
        """_RuntimeSettings must validate OPENAI_API_KEY and is_production flag."""
        gen = MultiAgentGenerator(ir=_minimal_ir())
        with tempfile.TemporaryDirectory() as d:
            gen.generate(Path(d))
            settings = (Path(d) / "settings.py").read_text()
            assert "OPENAI_API_KEY" in settings
            assert "is_production" in settings

    def test_runtime_server_has_sigterm_handler(self):
        """Generated runtime/server.py must register a SIGTERM handler."""
        gen = MultiAgentGenerator(ir=_minimal_ir())
        with tempfile.TemporaryDirectory() as d:
            gen.generate(Path(d))
            server = (Path(d) / "runtime" / "server.py").read_text()
            assert "signal.SIGTERM" in server
            assert "_shutdown_event" in server

    def test_run_store_factory_no_silent_failure(self):
        """Generated run store factory must not silently swallow Redis errors in production."""
        gen = MultiAgentGenerator(ir=_minimal_ir())
        with tempfile.TemporaryDirectory() as d:
            gen.generate(Path(d))
            factory = (Path(d) / "runtime" / "run_store" / "factory.py").read_text()
            assert "is_production" in factory
            assert "RuntimeError" in factory

    def test_env_example_state_backend_warning(self):
        """Generated .env.example must warn that STATE_BACKEND=inmemory is stateless."""
        gen = MultiAgentGenerator(ir=_minimal_ir())
        with tempfile.TemporaryDirectory() as d:
            gen.generate(Path(d))
            env_example = (Path(d) / ".env.example").read_text()
            assert "LOST ON RESTART" in env_example or "stateless" in env_example.lower() or "lost on restart" in env_example.lower()

    def test_ci_mypy_covers_settings_and_evals(self):
        """Generated CI workflow mypy step must cover settings and evals modules."""
        gen = MultiAgentGenerator(ir=_minimal_ir())
        with tempfile.TemporaryDirectory() as d:
            gen.generate(Path(d))
            ci = (Path(d) / ".github" / "workflows" / "ci.yml").read_text()
            assert "mypy" in ci
            assert "settings" in ci
            assert "evals" in ci
            assert "--ignore-missing-imports" in ci


class TestEvalsEndToEndPR004:
    """PR_004 — Evals end-to-end: dispatch integration + configurable loop."""

    def test_run_evals_calls_dispatch(self):
        """Generated run_evals.py must import and call dispatch(), support --dry-run."""
        gen = MultiAgentGenerator(ir=_minimal_ir())
        with tempfile.TemporaryDirectory() as d:
            gen.generate(Path(d))
            runner_src = (Path(d) / "evals" / "run_evals.py").read_text()
            assert "from runtime.dispatcher import dispatch" in runner_src
            assert "--dry-run" in runner_src
            assert "_results.json" in runner_src

    def test_loop_agent_ids_env_configurable(self):
        """Generated dispatcher.py must use LOOP_AGENT_IDS env var instead of hardcoded 'supervisor'."""
        gen = MultiAgentGenerator(ir=_minimal_ir())
        with tempfile.TemporaryDirectory() as d:
            gen.generate(Path(d))
            dispatcher_src = (Path(d) / "runtime" / "dispatcher.py").read_text()
            assert "LOOP_AGENT_IDS" in dispatcher_src
            assert "_loop_agent_ids" in dispatcher_src

    def test_smoke_dataset_has_3_cases(self):
        """Generated smoke.jsonl must contain at least 3 test cases."""
        gen = MultiAgentGenerator(ir=_minimal_ir())
        with tempfile.TemporaryDirectory() as d:
            gen.generate(Path(d))
            smoke_path = Path(d) / "evals" / "datasets" / "smoke.jsonl"
            cases = [json.loads(line) for line in smoke_path.read_text().splitlines() if line.strip()]
            assert len(cases) >= 3


class TestAWSOpsIaCPR005:
    """PR_005 — AWS Ops & IaC: Terraform universal + deploy guide + Docker publish."""

    def test_readme_deploy_generated_for_all_packagings(self):
        """README_DEPLOY.md must be generated for all packaging presets."""
        for preset in ["runtime", "aws-ecs"]:
            config = ExportConfig.from_preset(preset)
            gen = MultiAgentGenerator(ir=_minimal_ir(), config=config)
            with tempfile.TemporaryDirectory() as d:
                gen.generate(Path(d))
                deploy_path = Path(d) / "README_DEPLOY.md"
                assert deploy_path.exists(), f"README_DEPLOY.md missing for preset={preset}"
                content = deploy_path.read_text(encoding="utf-8")
                assert "ECS" in content
                assert "STATE_BACKEND" in content

    def test_iam_policy_generated_for_aws_ecs(self):
        """infra/aws/ecs/iam_policy.json must exist for aws-ecs packaging with all 3 statement Sids."""
        config = ExportConfig.from_preset("aws-ecs")
        gen = MultiAgentGenerator(ir=_minimal_ir(), config=config)
        with tempfile.TemporaryDirectory() as d:
            gen.generate(Path(d))
            iam_path = Path(d) / "infra" / "aws" / "ecs" / "iam_policy.json"
            assert iam_path.exists()
            policy = json.loads(iam_path.read_text())
            sids = [s["Sid"] for s in policy["Statement"]]
            assert "SSMParameters" in sids
            assert "CloudWatchLogs" in sids
            assert "ECRPull" in sids

    def test_ci_has_docker_push_job(self):
        """Generated CI workflow must contain a docker job that pushes to GHCR."""
        gen = MultiAgentGenerator(ir=_minimal_ir())
        with tempfile.TemporaryDirectory() as d:
            gen.generate(Path(d))
            ci = (Path(d) / ".github" / "workflows" / "ci.yml").read_text()
            assert "docker/build-push-action" in ci
            assert "ghcr.io" in ci

    def test_settings_has_ssm_loader(self):
        """Generated settings.py must contain _load_ssm_secrets and AWS_SECRETS_BACKEND guard."""
        gen = MultiAgentGenerator(ir=_minimal_ir())
        with tempfile.TemporaryDirectory() as d:
            gen.generate(Path(d))
            settings_src = (Path(d) / "settings.py").read_text()
            assert "_load_ssm_secrets" in settings_src
            assert "AWS_SECRETS_BACKEND" in settings_src


class TestObservabilityPR006:
    """PR_006 — OTel in export + Prometheus + dashboards."""

    def test_observability_has_otel_support(self):
        """Generated observability.py must have FORGE_OTEL_ENABLED guard and guarded import."""
        gen = MultiAgentGenerator(ir=_minimal_ir())
        with tempfile.TemporaryDirectory() as d:
            gen.generate(Path(d))
            obs_src = (Path(d) / "runtime" / "observability.py").read_text()
            assert "FORGE_OTEL_ENABLED" in obs_src
            assert "_otel_tracer" in obs_src
            # OTel import is guarded — no hard dependency
            assert "try:" in obs_src
            assert "ImportError" in obs_src

    def test_grafana_dashboard_generated(self):
        """docs/grafana-dashboard.json must exist with at least 5 panels."""
        gen = MultiAgentGenerator(ir=_minimal_ir())
        with tempfile.TemporaryDirectory() as d:
            gen.generate(Path(d))
            dashboard_path = Path(d) / "docs" / "grafana-dashboard.json"
            assert dashboard_path.exists()
            dashboard = json.loads(dashboard_path.read_text())
            assert "panels" in dashboard
            assert len(dashboard["panels"]) >= 5

    def test_alerts_yaml_generated(self):
        """docs/alerts.yaml must exist with the 3 required alert rules."""
        gen = MultiAgentGenerator(ir=_minimal_ir())
        with tempfile.TemporaryDirectory() as d:
            gen.generate(Path(d))
            alerts_path = Path(d) / "docs" / "alerts.yaml"
            assert alerts_path.exists()
            content = alerts_path.read_text(encoding="utf-8")
            assert "ForgeHighFailureRate" in content
            assert "ForgeGuardBlockSpike" in content
            assert "ForgeNoRuns" in content

    def test_pyproject_has_otel_extras(self):
        """Generated pyproject.toml must have [project.optional-dependencies] with otel extras."""
        gen = MultiAgentGenerator(ir=_minimal_ir())
        with tempfile.TemporaryDirectory() as d:
            gen.generate(Path(d))
            pyproject = (Path(d) / "pyproject.toml").read_text()
            assert "[project.optional-dependencies]" in pyproject
            assert "opentelemetry-api" in pyproject


class TestSecurityV2PR007:
    """PR_007 — Threat model, rate limiting HTTP, Sigstore, ir.json gitignore."""

    def test_security_md_generated(self):
        """SECURITY.md must exist with threat model content."""
        gen = MultiAgentGenerator(ir=_minimal_ir())
        with tempfile.TemporaryDirectory() as d:
            gen.generate(Path(d))
            security = (Path(d) / "SECURITY.md").read_text(encoding="utf-8")
            assert "Threat Model" in security
            assert "RUNTIME_API_TOKEN" in security
            assert "Attack Surfaces" in security

    def test_security_md_has_deployment_checklist(self):
        """SECURITY.md must contain a deployment checklist with ≥ 8 items."""
        gen = MultiAgentGenerator(ir=_minimal_ir())
        with tempfile.TemporaryDirectory() as d:
            gen.generate(Path(d))
            security = (Path(d) / "SECURITY.md").read_text(encoding="utf-8")
            checklist_items = [line for line in security.splitlines() if line.strip().startswith("- [ ]")]
            assert len(checklist_items) >= 8, f"Expected ≥ 8 checklist items, got {len(checklist_items)}"

    def test_gitignore_excludes_ir_json(self):
        """.gitignore must include ir.json."""
        gen = MultiAgentGenerator(ir=_minimal_ir())
        with tempfile.TemporaryDirectory() as d:
            gen.generate(Path(d))
            gitignore = (Path(d) / ".gitignore").read_text()
            assert "ir.json" in gitignore

    def test_gitignore_excludes_eval_results(self):
        """.gitignore must include eval results pattern."""
        gen = MultiAgentGenerator(ir=_minimal_ir())
        with tempfile.TemporaryDirectory() as d:
            gen.generate(Path(d))
            gitignore = (Path(d) / ".gitignore").read_text()
            assert "evals/*_results.json" in gitignore or "_results.json" in gitignore

    def test_server_has_ip_rate_limiter(self):
        """Generated runtime/server.py must contain _IPRateLimiter with 429 response."""
        gen = MultiAgentGenerator(ir=_minimal_ir())
        with tempfile.TemporaryDirectory() as d:
            gen.generate(Path(d))
            server_src = (Path(d) / "runtime" / "server.py").read_text()
            assert "_IPRateLimiter" in server_src
            assert "SERVER_RATE_LIMIT_RPS" in server_src
            assert "429" in server_src

    def test_ci_has_cosign_signing(self):
        """Generated CI workflow must include Sigstore cosign signing."""
        gen = MultiAgentGenerator(ir=_minimal_ir())
        with tempfile.TemporaryDirectory() as d:
            gen.generate(Path(d))
            ci = (Path(d) / ".github" / "workflows" / "ci.yml").read_text()
            assert "cosign" in ci or "sigstore" in ci.lower()


class TestDevExPR008:
    """PR_008 — devcontainer, pre-commit, profiling, model pinning."""

    def test_devcontainer_generated(self):
        """Export must include .devcontainer/devcontainer.json with Python 3.11 and forwarded ports."""
        gen = MultiAgentGenerator(ir=_minimal_ir())
        with tempfile.TemporaryDirectory() as d:
            gen.generate(Path(d))
            dc_path = Path(d) / ".devcontainer" / "devcontainer.json"
            assert dc_path.exists()
            dc = json.loads(dc_path.read_text())
            assert "python" in dc.get("image", "").lower()
            assert "forwardPorts" in dc
            assert 8080 in dc["forwardPorts"]

    def test_precommit_config_generated(self):
        """Export must include .pre-commit-config.yaml with ruff and detect-private-key hooks."""
        gen = MultiAgentGenerator(ir=_minimal_ir())
        with tempfile.TemporaryDirectory() as d:
            gen.generate(Path(d))
            pc_path = Path(d) / ".pre-commit-config.yaml"
            assert pc_path.exists()
            content = pc_path.read_text()
            assert "ruff" in content
            assert "detect-private-key" in content

    def test_makefile_has_docker_push(self):
        """Makefile must have docker-push target with REGISTRY variable."""
        gen = MultiAgentGenerator(ir=_minimal_ir())
        with tempfile.TemporaryDirectory() as d:
            gen.generate(Path(d))
            makefile = (Path(d) / "Makefile").read_text()
            assert "docker-push" in makefile
            assert "REGISTRY" in makefile

    def test_makefile_has_profile_target(self):
        """Makefile must have profile target using cProfile."""
        gen = MultiAgentGenerator(ir=_minimal_ir())
        with tempfile.TemporaryDirectory() as d:
            gen.generate(Path(d))
            makefile = (Path(d) / "Makefile").read_text()
            assert "profile" in makefile
            assert "cProfile" in makefile

    def test_agent_config_has_model_version(self):
        """Generated agent modules must include model_version in AGENT_CONFIG."""
        gen = MultiAgentGenerator(ir=_minimal_ir())
        with tempfile.TemporaryDirectory() as d:
            gen.generate(Path(d))
            for agent in gen.ir.agents:
                agent_src = (Path(d) / "agents" / f"{agent.id}.py").read_text()
                assert '"model_version"' in agent_src


class TestSecurityHardeningV3PR009:
    """PR_009 — metrics auth, CORS default, HTTP security headers, MCP validation."""

    def test_metrics_not_auth_exempt(self):
        """/metrics must require authentication (not in is_auth_exempt set)."""
        gen = MultiAgentGenerator(ir=_minimal_ir())
        with tempfile.TemporaryDirectory() as d:
            gen.generate(Path(d))
            auth_src = (Path(d) / "runtime" / "auth.py").read_text()
            # The return line of is_auth_exempt must NOT include /metrics
            # Find the line that contains the return set inside is_auth_exempt
            return_line = next(
                (l for l in auth_src.splitlines() if "return path in" in l),
                "",
            )
            assert '"/metrics"' not in return_line, \
                f"/metrics must not be in is_auth_exempt return set, got: {return_line!r}"
            assert '"/healthz"' in return_line, \
                f"/healthz must remain exempt, got: {return_line!r}"

    def test_cors_default_is_not_wildcard(self):
        """FORGE_RUNTIME_CORS_ORIGINS must default to empty string, not '*'."""
        gen = MultiAgentGenerator(ir=_minimal_ir())
        with tempfile.TemporaryDirectory() as d:
            gen.generate(Path(d))
            server_src = (Path(d) / "runtime" / "server.py").read_text()
            # The default must be "" not "*"
            assert 'FORGE_RUNTIME_CORS_ORIGINS", "")' in server_src or \
                   'FORGE_RUNTIME_CORS_ORIGINS\", \"\")' in server_src

    def test_http_security_headers_in_responses(self):
        """Generated server must send X-Content-Type-Options, X-Frame-Options, Cache-Control."""
        gen = MultiAgentGenerator(ir=_minimal_ir())
        with tempfile.TemporaryDirectory() as d:
            gen.generate(Path(d))
            server_src = (Path(d) / "runtime" / "server.py").read_text()
            assert "X-Content-Type-Options" in server_src
            assert "nosniff" in server_src
            assert "X-Frame-Options" in server_src
            assert "DENY" in server_src
            assert "Cache-Control" in server_src
            assert "no-store" in server_src

    def test_mcp_validation_in_settings(self):
        """settings.py must validate MCP_ALLOWED_COMMANDS when MCP_SERVERS is configured."""
        gen = MultiAgentGenerator(ir=_minimal_ir())
        with tempfile.TemporaryDirectory() as d:
            gen.generate(Path(d))
            settings_src = (Path(d) / "settings.py").read_text()
            assert "MCP_ALLOWED_COMMANDS" in settings_src
            assert "MCP_SERVERS" in settings_src

    def test_env_example_has_secure_cors_default(self):
        """Generated .env.example must have FORGE_RUNTIME_CORS_ORIGINS empty (not *)."""
        gen = MultiAgentGenerator(ir=_minimal_ir())
        with tempfile.TemporaryDirectory() as d:
            gen.generate(Path(d))
            env = (Path(d) / ".env.example").read_text()
            lines = {l.split("=")[0]: l for l in env.splitlines() if "=" in l and not l.startswith("#")}
            cors_line = lines.get("FORGE_RUNTIME_CORS_ORIGINS", "MISSING")
            assert cors_line != "MISSING", "FORGE_RUNTIME_CORS_ORIGINS not found in .env.example"
            assert cors_line == "FORGE_RUNTIME_CORS_ORIGINS=" or cors_line.endswith("="), \
                f"Expected FORGE_RUNTIME_CORS_ORIGINS= (empty), got: {cors_line!r}"

    def test_env_example_has_mcp_allowed_commands(self):
        """Generated .env.example must include MCP_ALLOWED_COMMANDS (empty default)."""
        gen = MultiAgentGenerator(ir=_minimal_ir())
        with tempfile.TemporaryDirectory() as d:
            gen.generate(Path(d))
            env = (Path(d) / ".env.example").read_text()
            assert "MCP_ALLOWED_COMMANDS" in env


class TestProductionGradeV2PR010:
    """PR_010 — backends fail-fast + idempotency key."""

    def test_settings_validates_inmemory_state_backend_in_prod(self):
        """settings.py must reject STATE_BACKEND=inmemory in production."""
        gen = MultiAgentGenerator(ir=_minimal_ir())
        with tempfile.TemporaryDirectory() as d:
            gen.generate(Path(d))
            settings_src = (Path(d) / "settings.py").read_text()
            assert "STATE_BACKEND" in settings_src
            assert "inmemory" in settings_src
            assert "is not safe for production" in settings_src

    def test_settings_validates_filesystem_run_store_in_prod(self):
        """settings.py must reject RUN_STORE_BACKEND=filesystem in production."""
        gen = MultiAgentGenerator(ir=_minimal_ir())
        with tempfile.TemporaryDirectory() as d:
            gen.generate(Path(d))
            settings_src = (Path(d) / "settings.py").read_text()
            assert "RUN_STORE_BACKEND" in settings_src
            assert "filesystem" in settings_src
            assert "is not safe for production" in settings_src

    def test_server_has_idempotency_cache(self):
        """Generated server must include _IdempotencyCache class."""
        gen = MultiAgentGenerator(ir=_minimal_ir())
        with tempfile.TemporaryDirectory() as d:
            gen.generate(Path(d))
            server_src = (Path(d) / "runtime" / "server.py").read_text()
            assert "_IdempotencyCache" in server_src
            assert "X-Idempotency-Key" in server_src
            assert "IDEMPOTENCY_TTL_S" in server_src

    def test_server_idempotency_cache_has_eviction(self):
        """_IdempotencyCache must implement TTL eviction."""
        gen = MultiAgentGenerator(ir=_minimal_ir())
        with tempfile.TemporaryDirectory() as d:
            gen.generate(Path(d))
            server_src = (Path(d) / "runtime" / "server.py").read_text()
            assert "_evict" in server_src
            assert "time.monotonic" in server_src

    def test_env_example_has_backend_vars(self):
        """Generated .env.example must include STATE_BACKEND, RUN_STORE_BACKEND, IDEMPOTENCY_TTL_S."""
        gen = MultiAgentGenerator(ir=_minimal_ir())
        with tempfile.TemporaryDirectory() as d:
            gen.generate(Path(d))
            env = (Path(d) / ".env.example").read_text()
            assert "STATE_BACKEND" in env
            assert "RUN_STORE_BACKEND" in env
            assert "IDEMPOTENCY_TTL_S" in env


class TestGitOpsV2PR011:
    """PR_011 — GitHub Environments, multi-arch Docker, Dependabot, CODEOWNERS."""

    def test_ci_docker_job_has_production_environment(self):
        """CI workflow docker and sign jobs must declare environment: production."""
        gen = MultiAgentGenerator(ir=_minimal_ir())
        with tempfile.TemporaryDirectory() as d:
            gen.generate(Path(d))
            ci_src = (Path(d) / ".github" / "workflows" / "ci.yml").read_text()
            assert ci_src.count("environment: production") >= 2, \
                f"Expected at least 2 occurrences of 'environment: production', got: {ci_src.count('environment: production')}"

    def test_ci_docker_build_is_multiarch(self):
        """CI workflow must build for linux/amd64,linux/arm64 and include QEMU setup."""
        gen = MultiAgentGenerator(ir=_minimal_ir())
        with tempfile.TemporaryDirectory() as d:
            gen.generate(Path(d))
            ci_src = (Path(d) / ".github" / "workflows" / "ci.yml").read_text()
            assert "linux/amd64,linux/arm64" in ci_src
            assert "setup-qemu-action" in ci_src

    def test_dependabot_yml_generated(self):
        """Generated project must include .github/dependabot.yml with pip and github-actions."""
        gen = MultiAgentGenerator(ir=_minimal_ir())
        with tempfile.TemporaryDirectory() as d:
            gen.generate(Path(d))
            dep_path = Path(d) / ".github" / "dependabot.yml"
            assert dep_path.exists(), ".github/dependabot.yml not generated"
            dep_src = dep_path.read_text()
            assert "pip" in dep_src
            assert "github-actions" in dep_src
            assert "weekly" in dep_src

    def test_codeowners_generated(self):
        """Generated project must include .github/CODEOWNERS with runtime and terraform entries."""
        gen = MultiAgentGenerator(ir=_minimal_ir())
        with tempfile.TemporaryDirectory() as d:
            gen.generate(Path(d))
            co_path = Path(d) / ".github" / "CODEOWNERS"
            assert co_path.exists(), ".github/CODEOWNERS not generated"
            co_src = co_path.read_text()
            assert "/runtime/" in co_src
            assert "/terraform/" in co_src

    def test_security_md_has_environments_setup(self):
        """SECURITY.md must include GitHub Environments setup instructions."""
        gen = MultiAgentGenerator(ir=_minimal_ir())
        with tempfile.TemporaryDirectory() as d:
            gen.generate(Path(d))
            sec_src = (Path(d) / "SECURITY.md").read_text()
            assert "CI/CD Environment Setup" in sec_src
            assert "production" in sec_src


# ── Helper for AWS ECS packaging ──────────────────────────────────────────────

def _ecs_gen() -> MultiAgentGenerator:
    """Return a MultiAgentGenerator configured for AWS ECS packaging (triggers Terraform output)."""
    return MultiAgentGenerator(ir=_minimal_ir(), target="aws-ecs")


def _tf_src(d: str) -> str:
    """Read the generated Terraform main.tf; skip if not present."""
    tf_path = Path(d) / "infra" / "aws" / "ecs" / "main.tf"
    if not tf_path.exists():
        pytest.skip("No Terraform main.tf for this packaging")
    return tf_path.read_text()


def _tf_vars_src(d: str) -> str:
    """Read the generated Terraform variables.tf; skip if not present."""
    vars_path = Path(d) / "infra" / "aws" / "ecs" / "variables.tf"
    if not vars_path.exists():
        pytest.skip("No Terraform variables.tf for this packaging")
    return vars_path.read_text()


class TestAWSOpsV2PR012:
    """PR_012 — autoscaling, AWS Budgets, private VPC, ECS Exec."""

    def test_ecs_service_has_private_subnets_and_no_public_ip(self):
        """ECS service must use private_subnet_ids and assign_public_ip = DISABLED."""
        with tempfile.TemporaryDirectory() as d:
            _ecs_gen().generate(Path(d))
            tf = _tf_src(d)
            assert "private_subnet_ids" in tf
            assert '"DISABLED"' in tf

    def test_ecs_service_has_execute_command(self):
        """ECS service must have enable_execute_command = true."""
        with tempfile.TemporaryDirectory() as d:
            _ecs_gen().generate(Path(d))
            tf = _tf_src(d)
            assert "enable_execute_command" in tf
            assert "true" in tf

    def test_terraform_has_autoscaling(self):
        """Terraform must include aws_appautoscaling_target and cpu+memory policies."""
        with tempfile.TemporaryDirectory() as d:
            _ecs_gen().generate(Path(d))
            tf = _tf_src(d)
            assert "aws_appautoscaling_target" in tf
            assert "aws_appautoscaling_policy" in tf
            assert "ECSServiceAverageCPUUtilization" in tf
            assert "ECSServiceAverageMemoryUtilization" in tf

    def test_terraform_has_budgets(self):
        """Terraform must include aws_budgets_budget with two notification blocks."""
        with tempfile.TemporaryDirectory() as d:
            _ecs_gen().generate(Path(d))
            tf = _tf_src(d)
            assert "aws_budgets_budget" in tf
            assert tf.count("notification {") >= 2

    def test_terraform_variables_include_new_vars(self):
        """variables.tf must include private_subnet_ids, min/max_task_count, budget vars."""
        with tempfile.TemporaryDirectory() as d:
            _ecs_gen().generate(Path(d))
            vars_src = _tf_vars_src(d)
            assert "private_subnet_ids" in vars_src
            assert "min_task_count" in vars_src
            assert "max_task_count" in vars_src
            assert "monthly_budget_usd" in vars_src
            assert "budget_alert_email" in vars_src

    def test_iam_task_role_has_ssm_permissions(self):
        """Terraform must include IAM task role with ssmmessages permissions for ECS Exec."""
        with tempfile.TemporaryDirectory() as d:
            _ecs_gen().generate(Path(d))
            tf = _tf_src(d)
            assert "ecs_task_role" in tf
            assert "ssmmessages" in tf

    def test_readme_aws_ecs_has_ops_sections(self):
        """README_AWS_ECS.md must document Auto Scaling, Cost Control, and ECS Exec."""
        with tempfile.TemporaryDirectory() as d:
            _ecs_gen().generate(Path(d))
            readme = (Path(d) / "README_AWS_ECS.md").read_text()
            assert "Auto Scaling" in readme
            assert "Cost Control" in readme
            assert "ECS Exec" in readme


class TestDistributedHardeningPR013:
    """PR_013 — Redis rate limiter + idempotency + Pydantic BaseSettings."""

    def test_rate_limiter_supports_redis_backend(self):
        """Generated server must include Redis sliding window Lua script."""
        gen = MultiAgentGenerator(ir=_minimal_ir())
        with tempfile.TemporaryDirectory() as d:
            gen.generate(Path(d))
            server_src = (Path(d) / "runtime" / "server.py").read_text()
            assert "RATE_LIMITER_BACKEND" in server_src
            assert "redis" in server_src
            assert "ZREMRANGEBYSCORE" in server_src  # Lua script presence

    def test_idempotency_cache_supports_redis_backend(self):
        """Generated server must include Redis idempotency with setex."""
        gen = MultiAgentGenerator(ir=_minimal_ir())
        with tempfile.TemporaryDirectory() as d:
            gen.generate(Path(d))
            server_src = (Path(d) / "runtime" / "server.py").read_text()
            assert "IDEMPOTENCY_BACKEND" in server_src
            assert "setex" in server_src

    def test_redis_backend_fails_open(self):
        """Rate limiter must fall back to inmemory if redis package is missing."""
        gen = MultiAgentGenerator(ir=_minimal_ir())
        with tempfile.TemporaryDirectory() as d:
            gen.generate(Path(d))
            server_src = (Path(d) / "runtime" / "server.py").read_text()
            assert "RuntimeWarning" in server_src or "warnings.warn" in server_src
            assert "inmemory" in server_src

    def test_settings_uses_pydantic_base_settings(self):
        """Generated settings.py must use Pydantic BaseSettings."""
        gen = MultiAgentGenerator(ir=_minimal_ir())
        with tempfile.TemporaryDirectory() as d:
            gen.generate(Path(d))
            settings_src = (Path(d) / "settings.py").read_text()
            assert "BaseSettings" in settings_src
            assert "pydantic_settings" in settings_src
            assert "get_settings" in settings_src

    def test_settings_has_typed_fields(self):
        """ForgeSettings must define typed fields for key config."""
        gen = MultiAgentGenerator(ir=_minimal_ir())
        with tempfile.TemporaryDirectory() as d:
            gen.generate(Path(d))
            settings_src = (Path(d) / "settings.py").read_text()
            assert "server_port: int" in settings_src or "SERVER_PORT" in settings_src
            assert "Field(" in settings_src

    def test_pyproject_has_redis_optional_dep(self):
        """pyproject.toml must include redis as optional dependency."""
        gen = MultiAgentGenerator(ir=_minimal_ir())
        with tempfile.TemporaryDirectory() as d:
            gen.generate(Path(d))
            pyproject_src = (Path(d) / "pyproject.toml").read_text()
            assert "redis" in pyproject_src


class TestTFNetworkHardeningPR014:
    """PR_014 — SG scope + tfvars fix + ECR lifecycle."""

    def test_sg_ingress_uses_vpc_cidr_not_open(self):
        """Security group ingress must NOT use 0.0.0.0/0 (only egress may)."""
        with tempfile.TemporaryDirectory() as d:
            _ecs_gen().generate(Path(d))
            tf = _tf_src(d)
            assert "var.vpc_cidr" in tf
            # 0.0.0.0/0 must appear only once (egress rule), not in ingress
            ingress_block_start = tf.find("ingress {")
            ingress_block_end = tf.find("}", ingress_block_start)
            ingress_block = tf[ingress_block_start:ingress_block_end]
            assert "0.0.0.0/0" not in ingress_block

    def test_tf_variables_has_vpc_cidr(self):
        """variables.tf must declare vpc_cidr."""
        with tempfile.TemporaryDirectory() as d:
            _ecs_gen().generate(Path(d))
            vars_src = _tf_vars_src(d)
            assert "vpc_cidr" in vars_src

    def test_tf_has_ecr_lifecycle_policy(self):
        """Terraform must include aws_ecr_lifecycle_policy resource."""
        with tempfile.TemporaryDirectory() as d:
            _ecs_gen().generate(Path(d))
            tf = _tf_src(d)
            assert "aws_ecr_lifecycle_policy" in tf
            assert "imageCountMoreThan" in tf or "sinceImagePushed" in tf

    def test_tfvars_example_has_assign_public_ip_false(self):
        """terraform.tfvars.example must set assign_public_ip = false."""
        with tempfile.TemporaryDirectory() as d:
            _ecs_gen().generate(Path(d))
            tfvars_path = Path(d) / "infra" / "aws" / "ecs" / "terraform.tfvars.example"
            if not tfvars_path.exists():
                pytest.skip("No tfvars.example for this packaging")
            content = tfvars_path.read_text()
            assert "assign_public_ip   = false" in content or "assign_public_ip = false" in content
            assert "assign_public_ip   = true" not in content


class TestRateLimiterAndCIPR015:
    """PR_015 — Rate limiter eviction + CI tag immutability."""

    def test_rate_limiter_has_bucket_eviction(self):
        """Generated server must evict stale IP entries to bound memory."""
        gen = MultiAgentGenerator(ir=_minimal_ir())
        with tempfile.TemporaryDirectory() as d:
            gen.generate(Path(d))
            server_src = (Path(d) / "runtime" / "server.py").read_text()
            assert "_BUCKETS_MAXSIZE" in server_src
            assert "stale" in server_src

    def test_ci_release_no_force_push(self):
        """CI release job must not force-push git tags."""
        gen = MultiAgentGenerator(ir=_minimal_ir())
        with tempfile.TemporaryDirectory() as d:
            gen.generate(Path(d))
            ci_src = (Path(d) / ".github" / "workflows" / "ci.yml").read_text()
            assert "--force" not in ci_src


class TestDepsHardeningPR016:
    """PR_016 — pydantic-settings pinned + redis optional + SSM lazy init."""

    def test_requirements_pydantic_settings_pinned(self):
        """requirements.txt must pin pydantic-settings to an exact version."""
        gen = MultiAgentGenerator(ir=_minimal_ir())
        with tempfile.TemporaryDirectory() as d:
            gen.generate(Path(d))
            req = (Path(d) / "requirements.txt").read_text()
            assert "pydantic-settings==" in req
            assert "pydantic-settings>=" not in req

    def test_requirements_redis_is_optional(self):
        """requirements.txt must not have redis as a mandatory (uncommented) dep."""
        gen = MultiAgentGenerator(ir=_minimal_ir())
        with tempfile.TemporaryDirectory() as d:
            gen.generate(Path(d))
            req = (Path(d) / "requirements.txt").read_text()
            for line in req.splitlines():
                stripped = line.strip()
                if stripped.startswith("redis") and not stripped.startswith("#"):
                    assert False, f"redis is a mandatory dep in requirements.txt: {line!r}"

    def test_settings_has_init_secrets_not_top_level_call(self):
        """settings.py must define init_secrets() and not call _load_ssm_secrets at top level."""
        gen = MultiAgentGenerator(ir=_minimal_ir())
        with tempfile.TemporaryDirectory() as d:
            gen.generate(Path(d))
            settings_src = (Path(d) / "settings.py").read_text()
            assert "def init_secrets" in settings_src
            for line in settings_src.splitlines():
                assert not line.startswith("_load_ssm_secrets()"), (
                    "_load_ssm_secrets() called at module top-level"
                )


class TestInputHardeningPR017:
    """PR_017 — sanitize_input injection heuristics + tool schema enforcement."""

    def test_policy_guard_has_injection_patterns(self):
        """Generated policy_guard.py must include injection pattern detection."""
        gen = MultiAgentGenerator(ir=_minimal_ir())
        with tempfile.TemporaryDirectory() as d:
            gen.generate(Path(d))
            pg_src = (Path(d) / "runtime" / "policy_guard.py").read_text()
            assert "_DEFAULT_INJECTION_PATTERNS" in pg_src
            assert "check_injection" in pg_src

    def test_sanitize_input_raises_on_injection(self):
        """sanitize_input must raise ValueError on injection pattern detection."""
        gen = MultiAgentGenerator(ir=_minimal_ir())
        with tempfile.TemporaryDirectory() as d:
            gen.generate(Path(d))
            pg_src = (Path(d) / "runtime" / "policy_guard.py").read_text()
            assert "ValueError" in pg_src
            assert "injection" in pg_src.lower()

    def test_tool_adapter_has_schema_validation(self):
        """execute_local_tool must call _validate_tool_args before execution."""
        gen = MultiAgentGenerator(ir=_minimal_ir())
        with tempfile.TemporaryDirectory() as d:
            gen.generate(Path(d))
            local_src = (Path(d) / "runtime" / "tools" / "adapters" / "local.py").read_text()
            assert "_validate_tool_args" in local_src
            assert "jsonschema" in local_src

    def test_env_example_has_injection_patterns_var(self):
        """Generated .env.example must document FORGE_INJECTION_PATTERNS."""
        gen = MultiAgentGenerator(ir=_minimal_ir())
        with tempfile.TemporaryDirectory() as d:
            gen.generate(Path(d))
            env_src = (Path(d) / ".env.example").read_text()
            assert "FORGE_INJECTION_PATTERNS" in env_src
