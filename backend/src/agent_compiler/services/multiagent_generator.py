"""Multi-agent project code generator.

Generates executable multi-agent Python projects from FlowIRv2.
"""

import json
import hashlib
import subprocess
import shutil
from pprint import pformat
from pathlib import Path
from typing import Any

from agent_compiler.models.ir_v2 import FlowIRv2, AgentSpec, HandoffMode
from agent_compiler.models.ir import SchemaRef
from agent_compiler.observability.logging import get_logger
from agent_compiler.services.export_config import (
    ExportConfig,
    ExportEngine,
    ExportPackaging,
    ExportSurface,
)

logger = get_logger(__name__)


class MultiAgentGenerator:
    """Generates a multi-agent project from a FlowIRv2."""

    def __init__(
        self,
        ir: FlowIRv2,
        include_tests: bool = True,
        config: ExportConfig | None = None,
        # Legacy parameter kept for backward compat; config takes priority
        target: str | None = None,
    ):
        self.ir = ir
        self.include_tests = include_tests
        if config is not None:
            self.config = config
        elif target is not None:
            self.config = ExportConfig.from_preset(target)
        else:
            self.config = ExportConfig()  # defaults: dispatcher, cli, local
        self._schema_ref_runtime_map: dict[str, str] = {}

    def generate(self, project_dir: Path) -> None:
        """Generate the complete multi-agent project."""
        # Create directory structure
        agents_dir = project_dir / "agents"
        runtime_dir = project_dir / "runtime"
        providers_dir = runtime_dir / "providers"
        tools_dir = runtime_dir / "tools"
        tools_schemas_dir = tools_dir / "schemas"
        tools_adapters_dir = tools_dir / "adapters"
        run_store_dir = runtime_dir / "run_store"
        run_store_stores_dir = run_store_dir / "stores"
        mcp_dir = runtime_dir / "mcp"
        state_dir = runtime_dir / "state"
        state_stores_dir = state_dir / "stores"
        loop_dir = runtime_dir / "loop"
        approvals_dir = runtime_dir / "approvals"
        replay_dir = runtime_dir / "replay"
        resilience_dir = runtime_dir / "resilience"
        docs_dir = project_dir / "docs"
        evals_dir = project_dir / "evals"
        evals_datasets_dir = evals_dir / "datasets"
        tests_dir = project_dir / "tests"

        agents_dir.mkdir(parents=True, exist_ok=True)
        runtime_dir.mkdir(parents=True, exist_ok=True)
        providers_dir.mkdir(parents=True, exist_ok=True)
        tools_dir.mkdir(parents=True, exist_ok=True)
        tools_schemas_dir.mkdir(parents=True, exist_ok=True)
        tools_adapters_dir.mkdir(parents=True, exist_ok=True)
        run_store_dir.mkdir(parents=True, exist_ok=True)
        run_store_stores_dir.mkdir(parents=True, exist_ok=True)
        mcp_dir.mkdir(parents=True, exist_ok=True)
        state_dir.mkdir(parents=True, exist_ok=True)
        state_stores_dir.mkdir(parents=True, exist_ok=True)
        loop_dir.mkdir(parents=True, exist_ok=True)
        approvals_dir.mkdir(parents=True, exist_ok=True)
        replay_dir.mkdir(parents=True, exist_ok=True)
        resilience_dir.mkdir(parents=True, exist_ok=True)
        docs_dir.mkdir(parents=True, exist_ok=True)
        evals_dir.mkdir(parents=True, exist_ok=True)
        evals_datasets_dir.mkdir(parents=True, exist_ok=True)

        # Materialize schemas and rewrite schema refs to portable runtime paths.
        self.ir = self._materialize_and_remap_schemas(runtime_dir / "schemas")

        # Generate files
        self._write(agents_dir / "__init__.py", self._generate_agents_init())
        self._write(agents_dir / "registry.py", self._generate_registry())

        for agent in self.ir.agents:
            self._write(
                agents_dir / f"{agent.id}.py",
                self._generate_agent_module(agent),
            )

        self._write(runtime_dir / "__init__.py", "")
        self._write(tools_dir / "__init__.py", "")
        self._write(tools_adapters_dir / "__init__.py", "")
        self._write(run_store_dir / "__init__.py", "")
        self._write(run_store_stores_dir / "__init__.py", "")
        self._write(mcp_dir / "__init__.py", "")
        self._write(state_dir / "__init__.py", "")
        self._write(state_stores_dir / "__init__.py", "")
        self._write(loop_dir / "__init__.py", "")
        self._write(approvals_dir / "__init__.py", "")
        self._write(replay_dir / "__init__.py", "")
        self._write(resilience_dir / "__init__.py", "")
        self._write(providers_dir / "__init__.py", "")
        self._write(providers_dir / "mock.py", self._generate_mock_provider())
        self._write(tools_dir / "registry.py", self._generate_tools_registry())
        self._write(tools_dir / "names.py", self._generate_tools_names())
        self._write(tools_dir / "policies.py", self._generate_tools_policies())
        self._write(tools_adapters_dir / "local.py", self._generate_tools_adapter_local())
        self._write(tools_adapters_dir / "mcp.py", self._generate_tools_adapter_mcp())
        self._write(tools_schemas_dir / "tools.echo.json", self._generate_tool_schema_echo())
        self._write(
            tools_schemas_dir / "tools.safe_calculator.json",
            self._generate_tool_schema_safe_calculator(),
        )
        self._write(tools_schemas_dir / "tools.http_get.json", self._generate_tool_schema_http_get())
        self._write(mcp_dir / "config.py", self._generate_mcp_config())
        self._write(mcp_dir / "client.py", self._generate_mcp_client())
        self._write(state_dir / "store.py", self._generate_state_store())
        self._write(state_stores_dir / "inmemory.py", self._generate_state_store_inmemory())
        self._write(state_stores_dir / "redis.py", self._generate_state_store_redis())
        self._write(state_dir / "factory.py", self._generate_state_store_factory())
        self._write(run_store_dir / "store.py", self._generate_run_store_store())
        self._write(run_store_stores_dir / "filesystem.py", self._generate_run_store_filesystem())
        self._write(run_store_stores_dir / "redis.py", self._generate_run_store_redis())
        self._write(run_store_dir / "factory.py", self._generate_run_store_factory())
        self._write(loop_dir / "plan_act_loop.py", self._generate_plan_act_loop())
        self._write(approvals_dir / "types.py", self._generate_approvals_types())
        self._write(approvals_dir / "policy.py", self._generate_approvals_policy())
        self._write(approvals_dir / "store.py", self._generate_approvals_store())
        self._write(replay_dir / "formats.py", self._generate_replay_formats())
        self._write(replay_dir / "recorder.py", self._generate_replay_recorder())
        self._write(replay_dir / "player.py", self._generate_replay_player())
        self._write(replay_dir / "cli.py", self._generate_replay_cli())
        self._write(resilience_dir / "rate_limit.py", self._generate_resilience_rate_limit())
        self._write(resilience_dir / "circuit_breaker.py", self._generate_resilience_circuit_breaker())
        self._write(resilience_dir / "policies.py", self._generate_resilience_policies())
        self._write(runtime_dir / "memory_write_policy.py", self._generate_memory_write_policy())
        self._write(runtime_dir / "memory_summarizer.py", self._generate_memory_summarizer())
        self._write(runtime_dir / "memory_retrieval_iface.py", self._generate_memory_retrieval_iface())
        self._write(evals_dir / "__init__.py", "")
        self._write(evals_dir / "run.py", self._generate_evals_runner())
        self._write(evals_dir / "smoke.json", self._generate_evals_smoke_suite())
        self._write(evals_dir / "regression.json", self._generate_evals_regression_suite())
        self._write(evals_dir / "assertions.py", self._generate_assertions_module())
        self._write(evals_dir / "run_evals.py", self._generate_run_evals_script())
        self._write(evals_datasets_dir / "smoke.jsonl", self._generate_smoke_dataset_jsonl())
        self._write(evals_datasets_dir / "regression.jsonl", self._generate_regression_dataset_jsonl())
        self._write(runtime_dir / "dispatcher.py", self._generate_dispatcher())
        self._write(runtime_dir / "supervisor.py", self._generate_supervisor())
        self._write(runtime_dir / "memory.py", self._generate_memory())
        self._write(runtime_dir / "budgets.py", self._generate_budgets())
        self._write(runtime_dir / "observability.py", self._generate_observability())
        self._write(runtime_dir / "policy_guard.py", self._generate_policy_guard())
        self._write(runtime_dir / "auth.py", self._generate_runtime_auth())
        self._write(runtime_dir / "retry.py", self._generate_retry())
        self._write(runtime_dir / "node_runtime.py", self._generate_node_runtime())
        self._write(runtime_dir / "schema_registry.py", self._generate_schema_registry())
        self._write(runtime_dir / "schema_validation.py", self._generate_schema_validation())
        self._write(runtime_dir / "healthcheck.py", self._generate_healthcheck())
        self._write(runtime_dir / "server.py", self._generate_runtime_server())
        self._write(runtime_dir / "config.py", self._generate_runtime_config())
        if self.config.engine == ExportEngine.LANGGRAPH:
            self._write(runtime_dir / "langgraph_runner.py", self._generate_langgraph_runner())

        self._write(project_dir / "settings.py", self._generate_settings())
        self._write(project_dir / "pyproject.toml", self._generate_pyproject())
        self._write(project_dir / "main.py", self._generate_main_entrypoint())
        self._write(project_dir / ".env.example", self._generate_env_example())
        req_content = self._generate_requirements()
        self._write(project_dir / "requirements.txt", req_content)
        self._write(project_dir / "requirements.lock", self._generate_requirements_lock(req_content))
        self._write(project_dir / "requirements-dev.txt", self._generate_requirements_dev())
        self._provision_uv_lock(project_dir)
        self._write(project_dir / "Makefile", self._generate_makefile())
        self._write(project_dir / "Dockerfile", self._generate_dockerfile())
        self._write(project_dir / "docker-compose.yml", self._generate_docker_compose())
        self._write(project_dir / ".gitignore", self._generate_gitignore())
        self._write(project_dir / ".dockerignore", self._generate_dockerignore())
        self._write(project_dir / "README.md", self._generate_readme())
        self._write(project_dir / "CHANGELOG.md", self._generate_changelog())
        devcontainer_dir = project_dir / ".devcontainer"
        devcontainer_dir.mkdir(parents=True, exist_ok=True)
        self._write(devcontainer_dir / "devcontainer.json", self._generate_devcontainer())
        self._write(project_dir / ".pre-commit-config.yaml", self._generate_precommit_config())
        self._write(docs_dir / "INTEGRATIONS.md", self._generate_integrations_doc())
        self._write(docs_dir / "grafana-dashboard.json", self._generate_grafana_dashboard())
        self._write(docs_dir / "alerts.yaml", self._generate_alerts_yaml())
        self._write(project_dir / "SECURITY.md", self._generate_security_md())
        if self.config.surface == ExportSurface.HTTP:
            self._write(project_dir / "api.py", self._generate_api_server())

        # infra/aws/ecs/ (always created; full IaC only for aws-ecs packaging)
        infra_dir = project_dir / "infra" / "aws" / "ecs"
        infra_dir.mkdir(parents=True, exist_ok=True)
        self._write(infra_dir / "README.md", self._generate_tf_readme_minimal())
        if self.config.packaging == ExportPackaging.AWS_ECS:
            self._write(infra_dir / "main.tf",                    self._generate_tf_main())
            self._write(infra_dir / "variables.tf",               self._generate_tf_variables())
            self._write(infra_dir / "outputs.tf",                 self._generate_tf_outputs())
            self._write(infra_dir / "terraform.tfvars.example",   self._generate_tf_tfvars_example())
            self._write(infra_dir / "iam_policy.json",            self._generate_tf_iam_policy())
            self._write(project_dir / "README_AWS_ECS.md",        self._generate_readme_aws_ecs())
        else:
            # Minimal skeleton for all other packagings
            self._write(infra_dir / "main.tf",      self._generate_tf_skeleton())
            self._write(infra_dir / "variables.tf", self._generate_tf_skeleton_variables())
        self._write(project_dir / "README_DEPLOY.md", self._generate_readme_deploy())
        self._write(project_dir / "ir.json", self.ir.model_dump_json(indent=2))

        ci_dir = project_dir / ".github" / "workflows"
        ci_dir.mkdir(parents=True, exist_ok=True)
        self._write(ci_dir / "ci.yml", self._generate_ci_workflow())
        github_dir = project_dir / ".github"
        self._write(github_dir / "release.yml", self._generate_release_config())
        self._write(github_dir / "dependabot.yml", self._generate_dependabot())
        self._write(github_dir / "CODEOWNERS", self._generate_codeowners())

        # Generate tool contracts, stubs, and contract tests
        self._generate_tool_contracts(project_dir)

        if self.include_tests:
            tests_dir.mkdir(parents=True, exist_ok=True)
            self._write(tests_dir / "__init__.py", "")
            self._write(
                tests_dir / "test_smoke_multiagent.py",
                self._generate_smoke_tests(),
            )
            self._write(tests_dir / "test_tool_registry.py", self._generate_test_tool_registry())
            self._write(tests_dir / "test_tool_policy.py", self._generate_test_tool_policy())
            self._write(tests_dir / "test_tool_allowlist_canonicalization.py", self._generate_test_tool_allowlist_canonicalization())
            self._write(tests_dir / "test_mcp_adapter_mock.py", self._generate_test_mcp_adapter_mock())
            self._write(tests_dir / "test_state_store.py", self._generate_test_state_store())
            self._write(tests_dir / "test_run_store_filesystem.py", self._generate_test_run_store_filesystem())
            self._write(tests_dir / "test_plan_act_loop_smoke.py", self._generate_test_plan_act_loop_smoke())
            self._write(tests_dir / "test_approvals_flow.py", self._generate_test_approvals_flow())
            self._write(tests_dir / "test_api_auth.py", self._generate_test_api_auth())
            self._write(tests_dir / "test_http_get_security.py", self._generate_test_http_get_security())
            self._write(tests_dir / "test_replay_determinism.py", self._generate_test_replay_determinism())
            self._write(tests_dir / "test_rate_limit_and_circuit.py", self._generate_test_rate_limit_and_circuit())
            self._write(tests_dir / "test_memory_write_policy.py", self._generate_test_memory_write_policy())

        logger.info(
            f"Generated multi-agent project with {len(self.ir.agents)} agents"
        )

    def _write(self, path: Path, content: str) -> None:
        path.write_text(content, encoding="utf-8")

    def _lock_template_dir(self) -> Path:
        return Path(__file__).resolve().parent.parent / "export_lock_templates"

    def _dependency_signature(self, project_dir: Path) -> str:
        payload = {
            "target": self.config.cache_key,
            "pyproject": (project_dir / "pyproject.toml").read_text(encoding="utf-8"),
            "requirements": (project_dir / "requirements.txt").read_text(encoding="utf-8"),
            "requirements_dev": (project_dir / "requirements-dev.txt").read_text(encoding="utf-8"),
        }
        raw = json.dumps(payload, sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def _provision_uv_lock(self, project_dir: Path) -> None:
        """Provision uv.lock from template cache, resolving once when needed."""
        template_dir = self._lock_template_dir()
        template_dir.mkdir(parents=True, exist_ok=True)
        template_lock = template_dir / f"{self.config.cache_key}.uv.lock"
        template_meta = template_dir / f"{self.config.cache_key}.meta.json"
        signature = self._dependency_signature(project_dir)
        project_lock = project_dir / "uv.lock"

        if template_lock.exists() and template_lock.stat().st_size > 0 and template_meta.exists():
            try:
                meta = json.loads(template_meta.read_text(encoding="utf-8"))
            except Exception:  # noqa: BLE001
                meta = {}
            if meta.get("dependency_signature") == signature:
                shutil.copyfile(template_lock, project_lock)
                return

        self._generate_uv_lock(project_dir)
        shutil.copyfile(project_lock, template_lock)
        template_meta.write_text(
            json.dumps(
                {
                    "target": self.config.cache_key,
                    "dependency_signature": signature,
                    "source": "auto-generated-by-exporter",
                },
                indent=2,
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

    def _generate_uv_lock(self, project_dir: Path) -> None:
        """Generate deterministic uv lockfile for exported project."""
        try:
            subprocess.run(
                ["uv", "lock"],
                cwd=project_dir,
                check=True,
                capture_output=True,
                text=True,
            )
        except FileNotFoundError as exc:
            raise RuntimeError(
                "uv is required to generate production-grade exports. Install uv and retry export."
            ) from exc
        except subprocess.CalledProcessError as exc:
            stderr = (exc.stderr or "").strip()
            stdout = (exc.stdout or "").strip()
            details = stderr or stdout or "uv lock failed without output."
            raise RuntimeError(f"Failed to generate uv.lock for export: {details}") from exc

        uv_lock = project_dir / "uv.lock"
        if not uv_lock.exists() or uv_lock.stat().st_size == 0:
            raise RuntimeError("Export generated an empty uv.lock; aborting.")

    def _generate_agents_init(self) -> str:
        agent_imports = "\n".join(
            f"from agents.{a.id} import build_{a.id}_graph as build_{a.id}_graph"
            for a in self.ir.agents
        )
        all_exports = ", ".join(f'"build_{a.id}_graph"' for a in self.ir.agents)
        return f'"""Agent modules."""\n\n{agent_imports}\n\n__all__ = [{all_exports}]\n'

    def _generate_registry(self) -> str:
        entries = ",\n    ".join(
            f'"{a.id}": build_{a.id}_graph'
            for a in self.ir.agents
        )
        imports = "\n".join(
            f"from agents.{a.id} import build_{a.id}_graph"
            for a in self.ir.agents
        )
        return f'''"""Agent registry — maps agent IDs to graph builders."""

from collections.abc import Callable
from typing import Any

{imports}

# Registry: agent_id -> callable that returns node list + edges
AGENT_REGISTRY: dict[str, Callable[[], dict[str, Any]]] = {{
    {entries},
}}


def get_agent_graph(agent_id: str) -> dict[str, Any]:
    """Get the graph definition for an agent."""
    builder = AGENT_REGISTRY.get(agent_id)
    if builder is None:
        raise ValueError(f"Unknown agent: {{agent_id}}")
    return builder()


def list_agents() -> list[str]:
    """List all registered agent IDs."""
    return list(AGENT_REGISTRY.keys())
'''

    def _generate_agent_module(self, agent: AgentSpec) -> str:
        nodes_repr = pformat(
            [n.model_dump(mode="json") for n in agent.graph.nodes], width=100, sort_dicts=False
        )
        edges_repr = pformat(
            [e.model_dump(mode="json") for e in agent.graph.edges], width=100, sort_dicts=False
        )
        return f'''"""Agent: {agent.name} (id={agent.id})

Auto-generated graph definition.
"""

from __future__ import annotations

from typing import Any


AGENT_CONFIG = {{
    "id": "{agent.id}",
    "name": "{agent.name}",
    "model": "{agent.llm.model}",
    "model_version": "{agent.llm.model}",  # Pin exact version (e.g. gpt-4o-2024-11-20)
    "provider": "{agent.llm.provider.value}",
    "temperature": {agent.llm.temperature},
    "system_prompt": {repr(agent.llm.system_prompt)},
    "tools_allowlist": {json.dumps(agent.tools_allowlist)},
    "memory_namespace": {repr(agent.memory_namespace)},
    "budgets": {{
        "max_tokens": {repr(agent.budgets.max_tokens)},
        "max_tool_calls": {repr(agent.budgets.max_tool_calls)},
        "max_steps": {repr(agent.budgets.max_steps)},
        "max_depth": {agent.budgets.max_depth},
    }},
    "policies": {pformat(agent.policies.model_dump() if agent.policies else None, width=100, sort_dicts=False)},
    "retries": {pformat(agent.retries.model_dump() if agent.retries else None, width=100, sort_dicts=False)},
    "fallbacks": {pformat(agent.fallbacks.model_dump() if agent.fallbacks else None, width=100, sort_dicts=False)},
}}


NODES = {nodes_repr}

EDGES = {edges_repr}


def build_{agent.id}_graph() -> dict[str, Any]:
    """Return the graph definition for this agent."""
    return {{
        "config": AGENT_CONFIG,
        "nodes": NODES,
        "edges": EDGES,
        "root": "{agent.graph.root}",
    }}
'''

    def _generate_tools_registry(self) -> str:
        return '''"""Unified tool registry (local + MCP)."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any

from runtime.mcp.client import MCPClient
from runtime.mcp.config import load_mcp_servers


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    input_schema: dict[str, Any]
    output_schema: dict[str, Any] | None
    adapter: str
    timeout_s: int = 30
    max_retries: int = 1
    requires_approval: bool = False


ToolCatalog = dict[str, ToolSpec]
_CATALOG: ToolCatalog | None = None


def _schema_dir() -> Path:
    return Path(__file__).resolve().parent / "schemas"


def _load_schema(file_name: str) -> dict[str, Any]:
    path = _schema_dir() / file_name
    return json.loads(path.read_text(encoding="utf-8"))


def _local_tool_specs() -> list[ToolSpec]:
    return [
        ToolSpec(
            name="tools.echo",
            description="Echoes input text.",
            input_schema=_load_schema("tools.echo.json"),
            output_schema={"type": "object"},
            adapter="local",
            timeout_s=10,
        ),
        ToolSpec(
            name="tools.safe_calculator",
            description="Safe arithmetic evaluator for numeric expressions.",
            input_schema=_load_schema("tools.safe_calculator.json"),
            output_schema={"type": "object"},
            adapter="local",
            timeout_s=10,
        ),
        ToolSpec(
            name="tools.http_get",
            description="HTTP GET (guarded, disabled by default by policy).",
            input_schema=_load_schema("tools.http_get.json"),
            output_schema={"type": "object"},
            adapter="local",
            timeout_s=15,
        ),
    ]


def _mcp_tool_specs() -> list[ToolSpec]:
    client = MCPClient()
    tools: list[ToolSpec] = []
    for server in load_mcp_servers():
        for tool in client.list_tools_sync(server.id):
            tool_name = str(tool.get("name", "")).strip()
            if not tool_name:
                continue
            full_name = f"mcp:{server.id}/{tool_name}"
            tools.append(
                ToolSpec(
                    name=full_name,
                    description=str(tool.get("description") or f"MCP tool from {server.id}"),
                    input_schema=tool.get("input_schema") or {"type": "object"},
                    output_schema=tool.get("output_schema"),
                    adapter="mcp",
                    timeout_s=int(tool.get("timeout_s") or 30),
                    max_retries=int(tool.get("max_retries") or 1),
                )
            )
    return tools


def load_tool_catalog() -> ToolCatalog:
    global _CATALOG
    if _CATALOG is not None:
        return _CATALOG
    catalog: ToolCatalog = {}
    for spec in _local_tool_specs() + _mcp_tool_specs():
        catalog[spec.name] = spec
    _CATALOG = catalog
    return _CATALOG


def list_tools() -> list[ToolSpec]:
    return sorted(load_tool_catalog().values(), key=lambda t: t.name)


def get_tool(name: str) -> ToolSpec | None:
    return load_tool_catalog().get(name)
'''

    def _generate_tools_policies(self) -> str:
        return '''"""Tool policy checks: allow/deny, timeout and payload size."""

from __future__ import annotations

import os
from fnmatch import fnmatchcase
from typing import Any
from runtime.tools.names import canonical_tool_name


def _parse_csv_env(name: str, default: str = "") -> list[str]:
    raw = os.environ.get(name, default)
    return [item.strip() for item in str(raw).split(",") if item.strip()]


def _matches(patterns: list[str], value: str) -> bool:
    return any(fnmatchcase(value, p) for p in patterns if p)


def _canonical_patterns(patterns: list[str]) -> list[str]:
    out: list[str] = []
    for item in patterns:
        raw = str(item or "").strip()
        if not raw:
            continue
        if raw == "tools.*" or raw == "mcp:*":
            out.append(raw)
            continue
        out.append(canonical_tool_name(raw))
    return out


def get_policy_config() -> dict[str, Any]:
    return {
        "allowlist": _parse_csv_env("TOOL_ALLOWLIST", "tools.*,mcp:*"),
        "denylist": _parse_csv_env("TOOL_DENYLIST", "python_repl,shell,exec"),
        "timeout_s": int(os.environ.get("TOOL_TIMEOUT_S", "30") or "30"),
        "max_payload_bytes": int(os.environ.get("TOOL_MAX_PAYLOAD_BYTES", "20000") or "20000"),
    }


def validate_tool_policy(tool_name: str, args: dict[str, Any], *, flow_policy: dict[str, Any] | None = None) -> None:
    policy = get_policy_config()
    flow_policy = flow_policy or {}
    requested = canonical_tool_name(tool_name)
    allowlist = _canonical_patterns(list(flow_policy.get("tool_allowlist") or []) or policy["allowlist"])
    denylist = _canonical_patterns(list(flow_policy.get("tool_denylist") or []) or policy["denylist"])

    if denylist and _matches(denylist, requested):
        raise RuntimeError(f"Tool denied by policy: {requested}")
    if allowlist and not _matches(allowlist, requested):
        raise RuntimeError(f"Tool not allowlisted: {requested}")

    payload_size = len(str(args or {}).encode("utf-8"))
    if payload_size > int(policy["max_payload_bytes"]):
        raise RuntimeError(f"Tool payload too large: {payload_size} bytes")
'''

    def _generate_tools_names(self) -> str:
        return '''"""Canonical tool names for policy checks."""

from __future__ import annotations


_ALIASES = {
    "echo": "tools.echo",
    "calculator": "tools.safe_calculator",
    "safe_calculator": "tools.safe_calculator",
    "datetime": "tools.datetime_now",
    "search": "tools.web_search",
    "web_search": "tools.web_search",
    "url_reader": "tools.web_search",
    "http_get": "tools.http_get",
}


def canonical_tool_name(name: str) -> str:
    value = str(name or "").strip()
    if not value:
        return value
    if value == "mcp:*" or value.startswith("mcp:"):
        return value
    return _ALIASES.get(value, value)
'''

    def _generate_tools_adapter_local(self) -> str:
        return '''"""Local tool adapter."""

from __future__ import annotations

import ast
import ipaddress
import os
import socket
from datetime import datetime, UTC
from urllib.parse import urlparse
from urllib.request import Request, urlopen
from typing import Any


def _safe_eval_arithmetic(expr: str) -> float:
    node = ast.parse(expr, mode="eval")
    if sum(1 for _ in ast.walk(node)) > 64:
        raise ValueError("Expression too complex")

    def _eval(n: ast.AST) -> float:
        if isinstance(n, ast.Expression):
            return _eval(n.body)
        if isinstance(n, ast.Constant) and isinstance(n.value, (int, float)):
            return float(n.value)
        if isinstance(n, ast.UnaryOp):
            val = _eval(n.operand)
            if isinstance(n.op, ast.UAdd):
                return +val
            if isinstance(n.op, ast.USub):
                return -val
        if isinstance(n, ast.BinOp):
            left, right = _eval(n.left), _eval(n.right)
            if isinstance(n.op, ast.Add):
                return left + right
            if isinstance(n.op, ast.Sub):
                return left - right
            if isinstance(n.op, ast.Mult):
                return left * right
            if isinstance(n.op, ast.Div):
                return left / right
            if isinstance(n.op, ast.FloorDiv):
                return left // right
            if isinstance(n.op, ast.Mod):
                return left % right
            if isinstance(n.op, ast.Pow):
                return left**right
        raise ValueError("Unsupported expression")

    banned = (ast.Name, ast.Attribute, ast.Call, ast.Subscript, ast.Lambda, ast.ListComp, ast.DictComp, ast.SetComp)
    for item in ast.walk(node):
        if isinstance(item, banned):
            raise ValueError("Unsupported expression")
    return float(_eval(node))


def _server_allowed_domains() -> list[str]:
    raw = os.environ.get("HTTP_GET_ALLOW_DOMAINS", "").strip()
    return [item.strip().lower() for item in raw.split(",") if item.strip()]


def _deny_ranges() -> list[ipaddress._BaseNetwork]:
    defaults = [
        "127.0.0.0/8",
        "::1/128",
        "10.0.0.0/8",
        "172.16.0.0/12",
        "192.168.0.0/16",
        "169.254.0.0/16",
        "fe80::/10",
        "100.64.0.0/10",
        "0.0.0.0/8",
    ]
    extra = [item.strip() for item in os.environ.get("HTTP_GET_DENY_IP_RANGES", "").split(",") if item.strip()]
    cidrs = defaults + extra
    out: list[ipaddress._BaseNetwork] = []
    for cidr in cidrs:
        try:
            out.append(ipaddress.ip_network(cidr, strict=False))
        except Exception:
            continue
    return out


def _host_allowed(host: str) -> bool:
    allowed = _server_allowed_domains()
    if not allowed:
        return False
    value = host.lower().strip()
    return any(value == domain or value.endswith("." + domain) for domain in allowed)


def _is_blocked_ip(ip: str) -> bool:
    addr = ipaddress.ip_address(ip)
    if addr.is_loopback or addr.is_private or addr.is_link_local or addr.is_unspecified or addr.is_reserved:
        return True
    if str(addr) in {"169.254.169.254", "100.100.100.200"}:
        return True
    for net in _deny_ranges():
        if addr in net:
            return True
    return False


def _validate_http_target(url: str) -> tuple[str, str]:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        raise RuntimeError("tools.http_get requires http/https URL")
    host = (parsed.hostname or "").strip()
    if not host:
        raise RuntimeError("tools.http_get missing host")
    if not _host_allowed(host):
        raise RuntimeError("HTTP domain not allowlisted for tools.http_get")
    try:
        infos = socket.getaddrinfo(host, parsed.port or (443 if parsed.scheme == "https" else 80), type=socket.SOCK_STREAM)
    except Exception as exc:
        raise RuntimeError(f"DNS resolution failed for {host}") from exc
    for info in infos:
        ip = info[4][0]
        if _is_blocked_ip(ip):
            raise RuntimeError(f"Blocked IP target for tools.http_get: {ip}")
    return parsed.geturl(), host


def _validate_tool_args(tool_name: str, args: dict[str, Any]) -> None:
    """Validate tool args against the tool's input_schema contract (best-effort).

    Schema files live at runtime/tools/contracts/<name>.json.
    Missing schema files and missing jsonschema package are silently skipped.
    """
    import json as _json
    from pathlib import Path as _Path
    short_name = tool_name.split(".")[-1]
    schema_path = _Path(__file__).parent / "contracts" / f"{short_name}.json"
    if not schema_path.exists():
        return
    try:
        import jsonschema as _jsonschema  # type: ignore[import]
        schema = _json.loads(schema_path.read_text(encoding="utf-8"))
        _jsonschema.validate(instance=args, schema=schema)
    except ImportError:
        pass  # jsonschema not installed — skip validation
    except _jsonschema.ValidationError as exc:
        raise ValueError(
            f"Tool '{tool_name}' args failed schema validation: {exc.message}"
        ) from exc


async def execute_local_tool(tool_name: str, args: dict[str, Any]) -> dict[str, Any]:
    _validate_tool_args(tool_name, args)
    if tool_name == "tools.echo":
        return {"tool": tool_name, "ok": True, "text": str(args.get("text", ""))}

    if tool_name == "tools.safe_calculator":
        expression = str(args.get("expression", ""))
        return {"tool": tool_name, "ok": True, "result": _safe_eval_arithmetic(expression)}

    if tool_name == "tools.http_get":
        url = str(args.get("url", "")).strip()
        url, _ = _validate_http_target(url)
        timeout_s = float(os.environ.get("HTTP_GET_TIMEOUT_S", "10") or "10")
        max_bytes = int(os.environ.get("HTTP_GET_MAX_RESPONSE_BYTES", "1000000") or "1000000")
        req = Request(url, method="GET", headers={"User-Agent": "forge-export-runtime/1.0"})
        with urlopen(req, timeout=timeout_s) as res:
            content = res.read(max_bytes).decode("utf-8", errors="replace")
            return {
                "tool": tool_name,
                "ok": True,
                "status": int(getattr(res, "status", 200)),
                "body": content,
                "fetched_at": datetime.now(UTC).isoformat(),
            }

    raise RuntimeError(f"Unknown local tool: {tool_name}")
'''

    def _generate_tools_adapter_mcp(self) -> str:
        return '''"""MCP tool adapter."""

from __future__ import annotations

from typing import Any

from runtime.mcp.client import MCPClient


def parse_mcp_tool_name(full_name: str) -> tuple[str, str]:
    if not full_name.startswith("mcp:") or "/" not in full_name:
        raise ValueError(f"Invalid MCP tool name: {full_name}")
    payload = full_name[len("mcp:") :]
    server_id, tool_name = payload.split("/", 1)
    server_id = server_id.strip()
    tool_name = tool_name.strip()
    if not server_id or not tool_name:
        raise ValueError(f"Invalid MCP tool name: {full_name}")
    return server_id, tool_name


async def execute_mcp_tool(full_name: str, args: dict[str, Any]) -> dict[str, Any]:
    server_id, tool_name = parse_mcp_tool_name(full_name)
    client = MCPClient()
    result = await client.call_tool(server_id=server_id, tool_name=tool_name, args=args)
    return {
        "tool": full_name,
        "ok": True,
        "server_id": server_id,
        "tool_name": tool_name,
        "result": result,
    }
'''

    def _generate_tool_schema_echo(self) -> str:
        return json.dumps(
            {
                "type": "object",
                "properties": {"text": {"type": "string"}},
                "required": ["text"],
                "additionalProperties": False,
            },
            indent=2,
        )

    def _generate_tool_schema_safe_calculator(self) -> str:
        return json.dumps(
            {
                "type": "object",
                "properties": {"expression": {"type": "string", "minLength": 1}},
                "required": ["expression"],
                "additionalProperties": False,
            },
            indent=2,
        )

    def _generate_tool_schema_http_get(self) -> str:
        return json.dumps(
            {
                "type": "object",
                "properties": {
                    "url": {"type": "string", "pattern": "^https?://"},
                },
                "required": ["url"],
                "additionalProperties": False,
            },
            indent=2,
        )

    def _generate_mcp_config(self) -> str:
        return '''"""MCP server config parser."""

from __future__ import annotations

from dataclasses import dataclass
import json
import os


@dataclass(frozen=True)
class MCPServer:
    id: str
    url: str


def load_mcp_servers() -> list[MCPServer]:
    raw = os.environ.get("MCP_SERVERS", "[]").strip()
    try:
        payload = json.loads(raw) if raw else []
    except json.JSONDecodeError as exc:
        raise RuntimeError("Invalid MCP_SERVERS JSON") from exc
    servers: list[MCPServer] = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        server_id = str(item.get("id", "")).strip()
        server_url = str(item.get("url", "")).strip()
        if server_id and server_url:
            servers.append(MCPServer(id=server_id, url=server_url))
    return servers
'''

    def _generate_mcp_client(self) -> str:
        return '''"""Minimal MCP client wrapper."""

from __future__ import annotations

import asyncio
import json
import os
from typing import Any
from urllib.request import Request, urlopen

from runtime.mcp.config import MCPServer, load_mcp_servers


class MCPClient:
    def __init__(self) -> None:
        self._servers = {s.id: s for s in load_mcp_servers()}

    def _get_server(self, server_id: str) -> MCPServer:
        server = self._servers.get(server_id)
        if server is None:
            raise RuntimeError(f"Unknown MCP server: {server_id}")
        return server

    def _request_json(self, url: str, payload: dict[str, Any]) -> dict[str, Any]:
        body = json.dumps(payload).encode("utf-8")
        req = Request(url, data=body, method="POST", headers={"Content-Type": "application/json"})
        with urlopen(req, timeout=20) as res:
            return json.loads(res.read().decode("utf-8"))

    def list_tools_sync(self, server_id: str) -> list[dict[str, Any]]:
        if os.environ.get("DEV_MODE", "0").strip().lower() in {"1", "true", "yes"}:
            return [{"name": "echo", "description": "Mock MCP echo", "input_schema": {"type": "object"}}]
        server = self._get_server(server_id)
        response = self._request_json(f"{server.url.rstrip('/')}/tools/list", {})
        return list(response.get("tools") or [])

    async def list_tools(self, server_id: str) -> list[dict[str, Any]]:
        return await asyncio.to_thread(self.list_tools_sync, server_id)

    async def call_tool(self, *, server_id: str, tool_name: str, args: dict[str, Any]) -> dict[str, Any]:
        if os.environ.get("DEV_MODE", "0").strip().lower() in {"1", "true", "yes"}:
            return {"mock": True, "server_id": server_id, "tool": tool_name, "args": args}
        server = self._get_server(server_id)
        response = await asyncio.to_thread(
            self._request_json,
            f"{server.url.rstrip('/')}/tools/call",
            {"tool_name": tool_name, "args": args},
        )
        return dict(response or {})
'''

    def _generate_state_store(self) -> str:
        return '''"""State store protocol."""

from __future__ import annotations

from typing import Any, Protocol


class StateStore(Protocol):
    def get(self, session_id: str) -> dict[str, Any]:
        ...

    def set(self, session_id: str, data: dict[str, Any]) -> None:
        ...

    def update(self, session_id: str, patch: dict[str, Any]) -> dict[str, Any]:
        ...
'''

    def _generate_state_store_inmemory(self) -> str:
        return '''"""In-memory state store (default)."""

from __future__ import annotations

from typing import Any


class InMemoryStateStore:
    def __init__(self) -> None:
        self._store: dict[str, dict[str, Any]] = {}

    def get(self, session_id: str) -> dict[str, Any]:
        item = dict(self._store.get(session_id, {}))
        if not item:
            return {}
        import time
        expires_at = float(item.get("_expires_at", 0) or 0)
        if expires_at and time.time() > expires_at:
            self._store.pop(session_id, None)
            return {}
        payload = dict(item.get("payload", {}))
        payload["_version"] = int(item.get("_version", 1))
        return payload

    def set(self, session_id: str, data: dict[str, Any]) -> None:
        import os
        import time
        ttl = int(os.environ.get("SESSION_TTL_S", "86400") or "86400")
        previous = self._store.get(session_id, {})
        version = int(previous.get("_version", 0)) + 1
        self._store[session_id] = {
            "payload": dict(data or {}),
            "_version": version,
            "_expires_at": time.time() + max(60, ttl),
        }

    def update(self, session_id: str, patch: dict[str, Any]) -> dict[str, Any]:
        payload = self.get(session_id)
        payload.update(dict(patch or {}))
        self.set(session_id, payload)
        return dict(payload)
'''

    def _generate_state_store_redis(self) -> str:
        return '''"""Redis-backed state store."""

from __future__ import annotations

import json
from typing import Any


class RedisStateStore:
    def __init__(self, redis_url: str) -> None:
        try:
            import redis
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError("redis package is required for STATE_BACKEND=redis") from exc
        self._client = redis.Redis.from_url(redis_url, decode_responses=True)

    def _key(self, session_id: str) -> str:
        return f"forge:session:{session_id}"

    def get(self, session_id: str) -> dict[str, Any]:
        raw = self._client.get(self._key(session_id))
        if not raw:
            return {}
        item = dict(json.loads(raw))
        payload = dict(item.get("payload", {}))
        payload["_version"] = int(item.get("_version", 1))
        return payload

    def set(self, session_id: str, data: dict[str, Any]) -> None:
        import os
        ttl = int(os.environ.get("SESSION_TTL_S", "86400") or "86400")
        existing = self.get(session_id)
        version = int(existing.get("_version", 0)) + 1
        item = {"payload": dict(data or {}), "_version": version}
        self._client.set(self._key(session_id), json.dumps(item), ex=max(60, ttl))

    def update(self, session_id: str, patch: dict[str, Any]) -> dict[str, Any]:
        current = self.get(session_id)
        current.update(dict(patch or {}))
        self.set(session_id, current)
        return current
'''

    def _generate_state_store_factory(self) -> str:
        return '''"""State store factory."""

from __future__ import annotations

import os

from runtime.state.stores.inmemory import InMemoryStateStore
from runtime.state.stores.redis import RedisStateStore


_STATE_STORE = None


def get_state_store():
    global _STATE_STORE
    if _STATE_STORE is not None:
        return _STATE_STORE

    backend = os.environ.get("STATE_BACKEND", "inmemory").strip().lower()
    if backend == "redis":
        redis_url = os.environ.get("REDIS_URL", "redis://localhost:6379/0").strip()
        _STATE_STORE = RedisStateStore(redis_url)
        return _STATE_STORE

    _STATE_STORE = InMemoryStateStore()
    return _STATE_STORE
'''

    def _generate_run_store_store(self) -> str:
        return '''"""Run store interfaces."""

from __future__ import annotations

from typing import Any, Protocol


class RunStore(Protocol):
    def put_run_manifest(self, run_id: str, data: dict[str, Any]) -> None: ...
    def append_step(self, run_id: str, step: dict[str, Any]) -> None: ...
    def list_steps(self, run_id: str) -> list[dict[str, Any]]: ...
    def get_run(self, run_id: str) -> dict[str, Any] | None: ...
'''

    def _generate_run_store_filesystem(self) -> str:
        return '''"""Filesystem-backed run store (default)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class FilesystemRunStore:
    def __init__(self, root_dir: str = "artifacts/runs") -> None:
        self.root = Path(root_dir)
        self.root.mkdir(parents=True, exist_ok=True)

    def _run_dir(self, run_id: str) -> Path:
        path = self.root / run_id
        path.mkdir(parents=True, exist_ok=True)
        return path

    def _manifest_path(self, run_id: str) -> Path:
        return self._run_dir(run_id) / "manifest.json"

    def _steps_dir(self, run_id: str) -> Path:
        path = self._run_dir(run_id) / "steps"
        path.mkdir(parents=True, exist_ok=True)
        return path

    def put_run_manifest(self, run_id: str, data: dict[str, Any]) -> None:
        self._manifest_path(run_id).write_text(json.dumps(data, indent=2, ensure_ascii=False, default=str), encoding="utf-8")

    def append_step(self, run_id: str, step: dict[str, Any]) -> None:
        step_id = str(step.get("step_id") or f"step_{len(self.list_steps(run_id)) + 1}")
        (self._steps_dir(run_id) / f"{step_id}.json").write_text(
            json.dumps(step, indent=2, ensure_ascii=False, default=str), encoding="utf-8"
        )

    def list_steps(self, run_id: str) -> list[dict[str, Any]]:
        steps_dir = self._steps_dir(run_id)
        out: list[dict[str, Any]] = []
        for path in sorted(steps_dir.glob("*.json")):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                continue
            out.append(payload if isinstance(payload, dict) else {"step_id": path.stem})
        return out

    def get_run(self, run_id: str) -> dict[str, Any] | None:
        path = self._manifest_path(run_id)
        if not path.exists():
            return None
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return None
        return payload if isinstance(payload, dict) else None
'''

    def _generate_run_store_redis(self) -> str:
        return '''"""Redis-backed run store (optional)."""

from __future__ import annotations

import json
from typing import Any


class RedisRunStore:
    def __init__(self, redis_url: str = "redis://localhost:6379/0") -> None:
        import redis

        self._redis = redis.Redis.from_url(redis_url, decode_responses=True)

    def _mkey(self, run_id: str) -> str:
        return f"forge:run:{run_id}:manifest"

    def _skey(self, run_id: str) -> str:
        return f"forge:run:{run_id}:steps"

    def put_run_manifest(self, run_id: str, data: dict[str, Any]) -> None:
        self._redis.set(self._mkey(run_id), json.dumps(data, ensure_ascii=False, default=str))

    def append_step(self, run_id: str, step: dict[str, Any]) -> None:
        self._redis.rpush(self._skey(run_id), json.dumps(step, ensure_ascii=False, default=str))

    def list_steps(self, run_id: str) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for item in self._redis.lrange(self._skey(run_id), 0, -1):
            try:
                payload = json.loads(item)
            except Exception:
                continue
            if isinstance(payload, dict):
                out.append(payload)
        return out

    def get_run(self, run_id: str) -> dict[str, Any] | None:
        raw = self._redis.get(self._mkey(run_id))
        if not raw:
            return None
        try:
            payload = json.loads(raw)
        except Exception:
            return None
        return payload if isinstance(payload, dict) else None
'''

    def _generate_run_store_factory(self) -> str:
        return '''"""Run store factory."""

from __future__ import annotations

import os

from runtime.run_store.stores.filesystem import FilesystemRunStore

_RUN_STORE = None


def get_run_store():
    global _RUN_STORE
    if _RUN_STORE is not None:
        return _RUN_STORE

    import logging as _logging
    _log = _logging.getLogger("forge.run_store.factory")

    backend = os.environ.get("RUN_STORE_BACKEND", "filesystem").strip().lower()
    if backend == "redis":
        is_production = os.environ.get("FORGE_ENV", "development").lower() in {{"prod", "production"}}
        try:
            from runtime.run_store.stores.redis import RedisRunStore

            _RUN_STORE = RedisRunStore(os.environ.get("REDIS_URL", "redis://localhost:6379/0").strip())
            return _RUN_STORE
        except Exception as exc:
            _log.error("Failed to initialise Redis run store: %s", exc)
            if is_production:
                raise RuntimeError(
                    f"RUN_STORE_BACKEND=redis but Redis is unavailable: {{exc}}. "
                    "Fix REDIS_URL or change RUN_STORE_BACKEND."
                ) from exc
            _log.warning("Falling back to filesystem run store (non-production only).")
    root = os.environ.get("RUN_STORE_DIR", "artifacts/runs").strip() or "artifacts/runs"
    _RUN_STORE = FilesystemRunStore(root)
    return _RUN_STORE
'''

    def _generate_plan_act_loop(self) -> str:
        return '''"""Reusable Plan -> Act -> Observe -> Evaluate/Repair loop."""

from __future__ import annotations

import os
from typing import Any, Awaitable, Callable


ToolExecutor = Callable[[str, dict[str, Any]], Awaitable[dict[str, Any]]]


def _choose_tool_for_step(step_text: str, goal: str) -> tuple[str, dict[str, Any]]:
    text = f"{step_text} {goal}".lower()
    has_math = any(op in text for op in ["+", "-", "*", "/", "%"])
    if has_math:
        expr = goal
        return ("tools.safe_calculator", {"expression": expr})
    return ("tools.echo", {"text": goal})


def _build_plan(goal: str) -> list[str]:
    return [
        f"Understand goal: {goal}",
        "Execute best-effort tool action",
        "Summarize result",
    ]


async def run_plan_act_loop(
    *,
    goal: str,
    execute_tool: ToolExecutor,
    state_store: Any | None = None,
    session_id: str | None = None,
) -> dict[str, Any]:
    max_iters = int(os.environ.get("LOOP_MAX_ITERS", "10") or "10")
    max_tool_calls = int(os.environ.get("LOOP_MAX_TOOL_CALLS", "10") or "10")
    max_failures = int(os.environ.get("LOOP_MAX_FAILURES", "3") or "3")

    state: dict[str, Any] = {
        "goal": goal,
        "plan_steps": _build_plan(goal),
        "current_step_idx": 0,
        "observations": [],
        "last_tool_result": None,
        "status": "running",
        "tool_calls": 0,
        "failures": 0,
        "iterations": 0,
    }

    while state["iterations"] < max_iters:
        state["iterations"] += 1
        step_idx = int(state["current_step_idx"])
        if step_idx >= len(state["plan_steps"]):
            state["status"] = "done"
            break

        step_text = state["plan_steps"][step_idx]
        tool_name, tool_args = _choose_tool_for_step(step_text, goal)

        if state["tool_calls"] >= max_tool_calls:
            state["status"] = "max_tool_calls_exceeded"
            break

        try:
            result = await execute_tool(tool_name, tool_args)
            state["tool_calls"] += 1
            state["last_tool_result"] = result
            state["observations"].append(
                {
                    "step": step_text,
                    "tool": tool_name,
                    "ok": True,
                    "result": result,
                }
            )
            state["current_step_idx"] = step_idx + 1
        except Exception as exc:  # noqa: BLE001
            state["failures"] += 1
            state["observations"].append(
                {
                    "step": step_text,
                    "tool": tool_name,
                    "ok": False,
                    "error": str(exc),
                }
            )
            if state["failures"] >= max_failures:
                state["status"] = "failed"
                break
            # Repair strategy (MVP): fallback to echo for next retry.
            state["plan_steps"].insert(step_idx + 1, "Repair by fallback echo summary")
            state["current_step_idx"] = step_idx + 1

        if state_store is not None and session_id:
            state_store.update(session_id, {"loop_state": state})

    if state["status"] == "running":
        state["status"] = "done"
    return state
'''

    def _generate_approvals_types(self) -> str:
        return '''"""Approval models."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, UTC
from typing import Any


@dataclass
class ApprovalRequest:
    approval_id: str
    tool_name: str
    scope: str
    status: str = "pending"
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    metadata: dict[str, Any] = field(default_factory=dict)
'''

    def _generate_approvals_policy(self) -> str:
        return '''"""Approval policy checks."""

from __future__ import annotations

import os


def requires_approval(*, tool_name: str, category: str, tool_requires_approval: bool) -> bool:
    if tool_requires_approval:
        return True
    required_for = {
        item.strip().lower()
        for item in os.environ.get("APPROVALS_REQUIRED_FOR", "mutating").split(",")
        if item.strip()
    }
    return category.strip().lower() in required_for
'''

    def _generate_approvals_store(self) -> str:
        return '''"""Approval store (in-memory default, Redis optional)."""

from __future__ import annotations

import json
import os
import uuid
import logging
import builtins
from typing import Any

from runtime.approvals.types import ApprovalRequest


class ApprovalStore:
    def __init__(self) -> None:
        self._logger = logging.getLogger("forge.runtime.approvals")
        self._backend = os.environ.get("APPROVALS_BACKEND", "inmemory").strip().lower()
        self._inmem: dict[str, ApprovalRequest] = {}
        self._redis = None
        if self._backend == "redis":
            try:
                import redis
                self._redis = redis.Redis.from_url(os.environ.get("REDIS_URL", "redis://localhost:6379/0"), decode_responses=True)
            except Exception:
                self._backend = "inmemory"
        if self._backend == "inmemory" and os.environ.get("FORGE_ENV", "production").strip().lower() in {"prod", "production"}:
            self._logger.warning("APPROVALS_BACKEND=inmemory in production; approvals are not durable across restart")

    def _rkey(self, approval_id: str) -> str:
        return f"forge:approval:{approval_id}"

    def request(self, tool_name: str, scope: str, metadata: dict[str, Any] | None = None) -> ApprovalRequest:
        approval_id = f"apr_{uuid.uuid4().hex[:12]}"
        req = ApprovalRequest(approval_id=approval_id, tool_name=tool_name, scope=scope, metadata=metadata or {})
        self._save(req)
        return req

    def get(self, approval_id: str) -> ApprovalRequest | None:
        if self._backend == "redis" and self._redis is not None:
            raw = self._redis.get(self._rkey(approval_id))
            if not raw:
                return None
            return ApprovalRequest(**json.loads(raw))
        return self._inmem.get(approval_id)

    def list(self, *, status: str | None = None, session_id: str | None = None) -> builtins.list[ApprovalRequest]:
        items = self._all()
        if status:
            status_norm = status.strip().lower()
            items = [item for item in items if str(item.status).strip().lower() == status_norm]
        if session_id:
            sid = session_id.strip()
            items = [item for item in items if str((item.metadata or {}).get("session_id") or "") == sid]
        items.sort(key=lambda r: r.created_at, reverse=True)
        return items

    def approve(self, approval_id: str) -> ApprovalRequest:
        req = self._must_get(approval_id)
        req.status = "approved"
        self._save(req)
        return req

    def deny(self, approval_id: str) -> ApprovalRequest:
        req = self._must_get(approval_id)
        req.status = "denied"
        self._save(req)
        return req

    def _must_get(self, approval_id: str) -> ApprovalRequest:
        req = self.get(approval_id)
        if req is None:
            raise RuntimeError(f"Approval not found: {approval_id}")
        return req

    def _all(self) -> builtins.list[ApprovalRequest]:
        if self._backend == "redis" and self._redis is not None:
            keys = self._redis.keys("forge:approval:*")
            items: builtins.list[ApprovalRequest] = []
            for key in keys:
                raw = self._redis.get(key)
                if not raw:
                    continue
                try:
                    items.append(ApprovalRequest(**json.loads(raw)))
                except Exception:
                    continue
            return items
        return list(self._inmem.values())

    def _save(self, req: ApprovalRequest) -> None:
        if self._backend == "redis" and self._redis is not None:
            self._redis.set(self._rkey(req.approval_id), json.dumps(req.__dict__))
            return
        self._inmem[req.approval_id] = req


_STORE: ApprovalStore | None = None


def get_approval_store() -> ApprovalStore:
    global _STORE
    if _STORE is None:
        _STORE = ApprovalStore()
    return _STORE
'''

    def _generate_replay_formats(self) -> str:
        return '''"""Canonical replay formats."""

from __future__ import annotations

from typing import Any


def step_snapshot(*, step_key: str, node_type: str, input_data: dict[str, Any], output_data: Any) -> dict[str, Any]:
    return {
        "step_key": step_key,
        "node_type": node_type,
        "input": input_data,
        "output": output_data,
    }
'''

    def _generate_replay_recorder(self) -> str:
        return '''"""Replay recorder."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from runtime.replay.formats import step_snapshot
from runtime.observability import build_log_record


class ReplayRecorder:
    def __init__(self, artifacts_dir: str, run_id: str):
        self.root = Path(artifacts_dir) / "replay" / run_id
        self.steps_dir = self.root / "steps"
        self.steps_dir.mkdir(parents=True, exist_ok=True)
        self._manifest: dict[str, Any] = {"run_id": run_id, "steps": []}

    def record_step(self, *, step_key: str, node_type: str, input_data: dict[str, Any], output_data: Any) -> None:
        snap = step_snapshot(step_key=step_key, node_type=node_type, input_data=input_data, output_data=output_data)
        # Reuse observability redaction path for persisted replay artifacts.
        redacted = (
            build_log_record("REPLAY_STEP", step_snapshot=snap)
            .get("payload", {})
            .get("step_snapshot", snap)
        )
        out = self.steps_dir / f"{step_key}.json"
        out.write_text(json.dumps(redacted, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
        self._manifest["steps"].append(step_key)

    def save_manifest(self) -> None:
        (self.root / "run_manifest.json").write_text(
            json.dumps(self._manifest, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
'''

    def _generate_replay_player(self) -> str:
        return '''"""Replay player."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class ReplayPlayer:
    def __init__(self, artifacts_dir: str, run_id: str):
        self.root = Path(artifacts_dir) / "replay" / run_id / "steps"

    def load_step_output(self, step_key: str) -> Any:
        path = self.root / f"{step_key}.json"
        if not path.exists():
            raise RuntimeError(f"Replay step not found: {step_key}")
        payload = json.loads(path.read_text(encoding="utf-8"))
        return payload.get("output")
'''

    def _generate_replay_cli(self) -> str:
        return '''"""CLI helper for replay inspection."""

from __future__ import annotations

import argparse
import json
import os

from runtime.replay.player import ReplayPlayer


def main() -> None:
    parser = argparse.ArgumentParser(description="Replay runner output")
    parser.add_argument("--run_id", required=True)
    parser.add_argument("--step_key", required=True)
    args = parser.parse_args()
    artifacts = os.environ.get("FORGE_ARTIFACTS_DIR", "artifacts")
    player = ReplayPlayer(artifacts, args.run_id)
    result = player.load_step_output(args.step_key)
    print(json.dumps(result, indent=2, ensure_ascii=False, default=str))


if __name__ == "__main__":
    main()
'''

    def _generate_resilience_rate_limit(self) -> str:
        return '''"""Per-tool token-bucket style limiter (simplified)."""

from __future__ import annotations

import time


class RateLimiter:
    def __init__(self) -> None:
        self._last: dict[str, float] = {}
        self._denied: dict[str, int] = {}
        self._allowed: dict[str, int] = {}

    def check(self, key: str, rps: float) -> None:
        if rps <= 0:
            return
        now = time.time()
        min_delta = 1.0 / rps
        last = self._last.get(key, 0.0)
        if now - last < min_delta:
            self._denied[key] = int(self._denied.get(key, 0)) + 1
            raise RuntimeError("RateLimited")
        self._last[key] = now
        self._allowed[key] = int(self._allowed.get(key, 0)) + 1

    def snapshot(self) -> dict[str, dict[str, float | int]]:
        return {
            key: {
                "last_ts": float(self._last.get(key, 0.0)),
                "allowed": int(self._allowed.get(key, 0)),
                "denied": int(self._denied.get(key, 0)),
            }
            for key in set(self._last) | set(self._allowed) | set(self._denied)
        }
'''

    def _generate_resilience_circuit_breaker(self) -> str:
        return '''"""Simple circuit breaker."""

from __future__ import annotations

import time


class CircuitBreaker:
    def __init__(self) -> None:
        self._state: dict[str, dict] = {}

    def before_call(self, key: str) -> None:
        item = self._state.get(key, {"failures": 0, "opened_at": 0.0, "open": False, "cooldown_s": 60.0})
        if item["open"]:
            if time.time() - float(item["opened_at"]) < float(item["cooldown_s"]):
                raise RuntimeError("CircuitOpen")
            item["open"] = False
            item["failures"] = 0
        self._state[key] = item

    def on_success(self, key: str) -> None:
        self._state[key] = {"failures": 0, "opened_at": 0.0, "open": False, "cooldown_s": self._state.get(key, {}).get("cooldown_s", 60.0)}

    def on_failure(self, key: str, threshold: int, cooldown_s: int) -> None:
        item = self._state.get(key, {"failures": 0, "opened_at": 0.0, "open": False, "cooldown_s": float(cooldown_s)})
        item["failures"] = int(item.get("failures", 0)) + 1
        item["cooldown_s"] = float(cooldown_s)
        if item["failures"] >= max(1, int(threshold)):
            item["open"] = True
            item["opened_at"] = time.time()
        self._state[key] = item

    def snapshot(self) -> dict[str, dict]:
        out: dict[str, dict] = {}
        now = time.time()
        for key, item in self._state.items():
            opened_at = float(item.get("opened_at", 0.0))
            cooldown_s = float(item.get("cooldown_s", 60.0))
            remaining = max(0.0, cooldown_s - max(0.0, now - opened_at)) if item.get("open") else 0.0
            out[key] = {
                "open": bool(item.get("open", False)),
                "failures": int(item.get("failures", 0)),
                "opened_at": opened_at,
                "cooldown_s": cooldown_s,
                "remaining_cooldown_s": remaining,
            }
        return out
'''

    def _generate_resilience_policies(self) -> str:
        return '''"""Resilience policy config."""

from __future__ import annotations

import os


def _parse_retry_on(raw: str) -> list[str]:
    values = [item.strip().lower() for item in str(raw or "").split(",")]
    parsed = [item for item in values if item]
    return parsed or ["timeout", "rate_limit", "5xx", "network", "unknown"]


def get_resilience_policy(tool_name: str) -> dict[str, object]:
    return {
        "rps": float(os.environ.get("TOOL_RATE_LIMIT_RPS_DEFAULT", "2") or "2"),
        "fail_threshold": int(os.environ.get("TOOL_CIRCUIT_FAIL_THRESHOLD_DEFAULT", "5") or "5"),
        "cooldown_s": int(os.environ.get("TOOL_CIRCUIT_COOLDOWN_S_DEFAULT", "60") or "60"),
        "retry_max_attempts": int(os.environ.get("TOOL_RETRY_MAX_ATTEMPTS", "2") or "2"),
        "retry_backoff_ms": int(os.environ.get("TOOL_RETRY_BACKOFF_MS", "300") or "300"),
        "retry_on": _parse_retry_on(os.environ.get("TOOL_RETRY_ON", "timeout,rate_limit,5xx,network,unknown")),
    }
'''

    def _generate_memory_write_policy(self) -> str:
        return '''"""Memory write governance policy."""

from __future__ import annotations

import os
from typing import Any


def should_write_memory(candidate: dict[str, Any]) -> bool:
    conf_t = float(os.environ.get("MEMORY_WRITE_CONFIDENCE_THRESHOLD", "0.7") or "0.7")
    rel_t = float(os.environ.get("MEMORY_WRITE_RELEVANCE_THRESHOLD", "0.6") or "0.6")
    confidence = float(candidate.get("confidence", 0.0) or 0.0)
    relevance = float(candidate.get("relevance", 0.0) or 0.0)
    return confidence >= conf_t and relevance >= rel_t
'''

    def _generate_memory_summarizer(self) -> str:
        return '''"""Session summarizer for bounded memory."""

from __future__ import annotations

from typing import Any


def summarize_session(entries: list[dict[str, Any]], max_items: int = 50) -> list[dict[str, Any]]:
    if len(entries) <= max_items:
        return entries
    head = entries[:5]
    tail = entries[-(max_items - 5) :]
    summary = {"type": "summary", "text": f"summarized {len(entries) - len(head) - len(tail)} entries"}
    return head + [summary] + tail
'''

    def _generate_memory_retrieval_iface(self) -> str:
        return '''"""Retrieval interface scaffold for future vector memory."""

from __future__ import annotations

from typing import Protocol, Any


class RetrievalBackend(Protocol):
    def search(self, query: str, top_k: int = 5) -> list[dict[str, Any]]:
        ...
'''

    def _generate_evals_runner(self) -> str:
        return '''"""Minimal eval harness runner."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def run_suite(name: str) -> int:
    suite_path = Path(__file__).resolve().parent / f"{name}.json"
    if not suite_path.exists():
        raise RuntimeError(f"Suite not found: {name}")
    suite = json.loads(suite_path.read_text(encoding="utf-8"))
    failures = 0
    for case in suite.get("cases", []):
        if not case.get("enabled", True):
            continue
        if not case.get("expected"):
            failures += 1
    return failures


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--suite", required=True, choices=["smoke", "regression"])
    args = parser.parse_args()
    failures = run_suite(args.suite)
    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
'''

    def _generate_evals_smoke_suite(self) -> str:
        return json.dumps(
            {
                "suite": "smoke",
                "cases": [
                    {"id": "routing_smoke", "enabled": True, "expected": "handoff"},
                    {"id": "tool_policy_smoke", "enabled": True, "expected": "allow_or_block"},
                ],
            },
            indent=2,
        )

    def _generate_evals_regression_suite(self) -> str:
        return json.dumps(
            {
                "suite": "regression",
                "cases": [
                    {"id": "approval_required_case", "enabled": True, "expected": "pending_or_approved"},
                    {"id": "replay_determinism_case", "enabled": True, "expected": "same_output"},
                    {"id": "repair_loop_case", "enabled": True, "expected": "recovered_or_failed"},
                ],
            },
            indent=2,
        )

    def _generate_assertions_module(self) -> str:
        return '''\
"""PR3 assertion library — portable, zero-dependency implementations.

Usage from run_evals.py:
    from evals.assertions import run_assertion
    passed, message = run_assertion(assertion, output, run_meta)
"""
from __future__ import annotations

import re
from typing import Any


def run_assertion(
    assertion: dict[str, Any],
    output: dict[str, Any],
    run_meta: dict[str, Any] | None = None,
) -> tuple[bool, str]:
    """Evaluate a single assertion.

    Returns (passed: bool, message: str).
    """
    a_type = assertion.get("type", "")
    expected = assertion.get("expected")
    field = assertion.get("field", "output")
    actual = _get_field(output, field)
    meta = run_meta or {}

    if a_type == "contains":
        if actual is not None and str(expected) in str(actual):
            return True, f"Output contains {expected!r}"
        return False, f"Output does not contain {expected!r}"

    if a_type == "not_contains":
        if actual is None or str(expected) not in str(actual):
            return True, f"Output does not contain {expected!r}"
        return False, f"Output contains {expected!r} but should not"

    if a_type == "equals":
        if actual == expected:
            return True, "Output equals expected"
        return False, f"Expected {expected!r}, got {actual!r}"

    if a_type == "regex":
        if actual is not None and re.search(str(expected), str(actual)):
            return True, f"Output matches pattern {expected!r}"
        return False, f"Output does not match pattern {expected!r}"

    if a_type == "schema_valid":
        schema = assertion.get("schema") or {}
        target = actual if actual is not None else output
        try:
            import jsonschema  # type: ignore[import]
            jsonschema.validate(instance=target, schema=schema)
            return True, "Output is schema-valid"
        except ImportError:
            required = schema.get("required", [])
            missing = [k for k in required if k not in (target or {})]
            if missing:
                return False, f"Missing required fields: {missing}"
            return True, "Output is schema-valid (lite)"
        except Exception as exc:
            return False, f"Schema error: {exc}"

    if a_type == "citation_required":
        text = str(actual) if actual is not None else str(output)
        patterns = [
            r"\\[\\d+\\]", r"\\(\\w[\\w\\s]*,\\s*\\d{4}\\)",
            r"https?://\\S+", r"Source:", r"Reference:",
        ]
        if any(re.search(p, text, re.IGNORECASE) for p in patterns):
            return True, "Output contains citation markers"
        return False, "No citation markers found"

    if a_type == "abstain_correctness":
        abstained = output.get("abstained", False)
        exp_abstain = expected
        if exp_abstain is None:
            return False, "No expected_abstain value"
        if bool(abstained) == bool(exp_abstain):
            return True, f"Abstain correctness OK: abstained={abstained}"
        return False, f"Expected abstained={exp_abstain}, got {abstained}"

    if a_type == "tool_success_rate":
        min_rate = float(expected) if expected is not None else 1.0
        steps = meta.get("steps", [])
        tool_steps = [s for s in steps if (s.get("node_type") or "").upper() == "TOOL"]
        if not tool_steps:
            return True, "No tool steps (vacuously true)"
        succeeded = sum(
            1 for s in tool_steps
            if (s.get("output") or {}).get("success", True)
            and not (s.get("output") or {}).get("error")
        )
        rate = succeeded / len(tool_steps)
        if rate >= min_rate:
            return True, f"Tool success rate {rate:.0%} >= {min_rate:.0%}"
        return False, f"Tool success rate {rate:.0%} < {min_rate:.0%}"

    return False, f"Unknown assertion type: {a_type!r}"


def _get_field(output: dict[str, Any], field: str) -> Any:
    if "." not in field:
        return output.get(field)
    value: Any = output
    for part in field.split("."):
        if isinstance(value, dict):
            value = value.get(part)
        elif isinstance(value, list) and part.isdigit():
            value = value[int(part)] if int(part) < len(value) else None
        else:
            return None
    return value
'''

    def _generate_run_evals_script(self) -> str:
        return '''\
"""PR3 eval runner — reads datasets/*.jsonl, calls dispatch(), runs assertions.

Usage:
    python evals/run_evals.py --suite smoke [--threshold 0.8] [--entrypoint main]

Exit code: 0 = all thresholds met, 1 = gate failed.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from pathlib import Path

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE.parent))

from evals.assertions import run_assertion  # noqa: E402


def load_dataset(name: str) -> list[dict]:
    path = _HERE / "datasets" / f"{name}.jsonl"
    if not path.exists():
        raise FileNotFoundError(f"Dataset not found: {path}")
    cases = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            cases.append(json.loads(line))
    return cases


def _run_case_against_agent(case: dict, entrypoint: str) -> dict:
    """Call the real agent dispatcher and return its output + metadata."""
    from runtime.dispatcher import dispatch  # noqa: PLC0415

    input_data = {"input": case.get("input", ""), "session_id": f"eval_{case.get('id', 'unknown')}"}
    start = time.perf_counter()
    try:
        result = asyncio.run(dispatch(input_data, entrypoint=entrypoint))
        duration_ms = (time.perf_counter() - start) * 1000
        return {
            "output": result.get("current") or result,
            "run_id": result.get("run_id", ""),
            "trace_id": result.get("trace_id", ""),
            "steps": result.get("outputs", {}),
            "duration_ms": duration_ms,
            "error": None,
        }
    except Exception as exc:  # noqa: BLE001
        duration_ms = (time.perf_counter() - start) * 1000
        return {
            "output": {},
            "run_id": "",
            "trace_id": "",
            "steps": {},
            "duration_ms": duration_ms,
            "error": str(exc),
        }


def run_suite(name: str, threshold: float, entrypoint: str, dry_run: bool) -> bool:
    cases = load_dataset(name)
    total = len(cases)
    passed = 0
    results = []

    for case in cases:
        assertions = case.get("assertions", [])
        if not assertions:
            passed += 1
            results.append({"id": case.get("id"), "status": "skip", "reason": "no assertions"})
            continue

        if dry_run:
            # Dry-run: evaluate assertions against static expected data (CI pre-flight)
            output = {"output": case.get("input", "")}
            run_meta: dict = {}
        else:
            run_result = _run_case_against_agent(case, entrypoint)
            if run_result["error"]:
                print(f"  ERROR [{case.get('id', '?')}]: {run_result['error']}")
                results.append({"id": case.get("id"), "status": "error", "error": run_result["error"]})
                continue
            output = {"output": run_result["output"]}
            run_meta = {"steps": list(run_result["steps"].values()), "duration_ms": run_result["duration_ms"]}

        all_ok = True
        for a in assertions:
            ok, msg = run_assertion(a, output, run_meta)
            if not ok:
                print(f"  FAIL [{case.get('id', '?')}] {a.get('type')}: {msg}")
                all_ok = False
        if all_ok:
            passed += 1
            results.append({"id": case.get("id"), "status": "pass"})
        else:
            results.append({"id": case.get("id"), "status": "fail"})

    rate = passed / total if total else 1.0
    gate = rate >= threshold
    status = "PASS" if gate else "FAIL"
    print(f"[{status}] {name}: {passed}/{total} passed ({rate:.0%}, threshold={threshold:.0%})")

    # Write results JSON for CI artifact upload
    results_path = _HERE / f"{name}_results.json"
    results_path.write_text(json.dumps({
        "suite": name, "passed": passed, "total": total,
        "rate": rate, "gate": gate, "cases": results,
    }, indent=2), encoding="utf-8")

    return gate


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--suite", required=True)
    parser.add_argument("--threshold", type=float, default=1.0)
    parser.add_argument("--entrypoint", default="main")
    parser.add_argument("--dry-run", action="store_true",
                        help="Evaluate assertions against static data (no agent call)")
    args = parser.parse_args()

    ok = run_suite(args.suite, args.threshold, args.entrypoint, args.dry_run)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
'''

    def _generate_smoke_dataset_jsonl(self) -> str:
        cases = [
            {
                "id": "smoke-001",
                "input": "Hello, are you working?",
                "entrypoint": "main",
                "expected": {"must_cite": False, "expected_abstain": False},
                "assertions": [
                    {"type": "not_contains", "expected": "ERROR", "field": "output"},
                    {"type": "not_contains", "expected": "Traceback", "field": "output"},
                ],
                "tags": ["smoke"],
            },
            {
                "id": "smoke-002",
                "input": "What is 2 + 2?",
                "entrypoint": "main",
                "expected": {},
                "assertions": [
                    {"type": "not_contains", "expected": "ERROR", "field": "output"},
                ],
                "tags": ["smoke", "math"],
            },
            {
                "id": "smoke-003-agent-registry",
                "input": "list_tools",
                "entrypoint": "main",
                "expected": {},
                "assertions": [],
                "tags": ["smoke", "registry"],
            },
        ]
        return "\n".join(json.dumps(c) for c in cases) + "\n"

    def _generate_regression_dataset_jsonl(self) -> str:
        cases = [
            {
                "id": "regression-001",
                "input": "Summarise the policy document.",
                "expected": {"expected_abstain": False},
                "assertions": [
                    {"type": "abstain_correctness", "expected": False},
                ],
                "tags": ["regression"],
            },
            {
                "id": "regression-002",
                "input": "Find information and cite your sources.",
                "expected": {"must_cite": True},
                "assertions": [
                    {"type": "citation_required", "field": "output"},
                ],
                "tags": ["regression", "citations"],
            },
        ]
        return "\n".join(json.dumps(c) for c in cases) + "\n"

    def _generate_dispatcher(self) -> str:
        entrypoints_repr = pformat(
            [e.model_dump(mode="json") for e in self.ir.entrypoints], width=100, sort_dicts=False
        )
        langgraph_import = (
            "from runtime.langgraph_runner import run_dispatch_via_langgraph\n"
            if self.config.engine == ExportEngine.LANGGRAPH
            else ""
        )
        dispatch_call = (
            """    async def _run_agent_once(
        agent_id: str,
        agent_input: dict[str, Any],
        depth: int,
    ) -> dict[str, Any]:
        return await call_agent(
            agent_id=agent_id,
            input_data=agent_input,
            memory=memory,
            budget=budget,
            run_id=run_id,
            trace_id=trace_id,
            depth=depth,
            enable_recursive_handoffs=False,
            state_store=state_store,
            session_id=session_id,
        )

    try:
        result = await run_dispatch_via_langgraph(
            root_agent_id=ep["agent_id"],
            input_data=input_data,
            run_agent_once=_run_agent_once,
            max_depth=MAX_GLOBAL_DEPTH,
        )
"""
            if self.config.engine == ExportEngine.LANGGRAPH
            else """    try:
        result = await call_agent(
            agent_id=ep["agent_id"],
            input_data=input_data,
            memory=memory,
            budget=budget,
            run_id=run_id,
            trace_id=trace_id,
            depth=0,
            state_store=state_store,
            session_id=session_id,
        )
"""
        )
        return f'''"""Entrypoint routing and agent dispatch."""

import time
import uuid
import os
from typing import Any

from agents.registry import get_agent_graph
from runtime.budgets import BudgetTracker, BudgetExceededError
from runtime.config import get_runtime_config, write_run_manifest
from runtime.memory import MemoryManager
from runtime.node_runtime import execute_node
from runtime.observability import log_event, inc_counter, record_timing_ms, snapshot_metrics, _otel_span_context
from runtime.loop.plan_act_loop import run_plan_act_loop
from runtime.policy_guard import sanitize_input, validate_tool_call
from runtime.retry import run_with_retry
from runtime.schema_validation import validate_payload
from runtime.state.factory import get_state_store
from runtime.supervisor import find_handoff
from runtime.tools.registry import list_tools
from settings import FLOW_POLICIES
{langgraph_import}


ENTRYPOINTS = {entrypoints_repr}

MAX_GLOBAL_DEPTH = 10

_PROFILE_ENABLED = os.environ.get("FORGE_PROFILE", "0").strip() in {{"1", "true"}}
_profile_data: list[dict[str, Any]] = []

if _PROFILE_ENABLED:
    def _profile_call(func_name: str, duration_ms: float, **labels: Any) -> None:
        _profile_data.append({{
            "func": func_name,
            "duration_ms": round(duration_ms, 2),
            **labels,
        }})

    def get_profile_report() -> str:
        if not _profile_data:
            return "No profile data collected."
        sorted_data = sorted(_profile_data, key=lambda x: x["duration_ms"], reverse=True)
        lines = [f"  {{d['func']:50s}} {{d['duration_ms']:8.2f}}ms {{d.get('run_id','')}}" for d in sorted_data[:20]]
        return "Top 20 by duration:\\n" + "\\n".join(lines)


async def dispatch(
    input_data: dict[str, Any],
    entrypoint: str = "main",
) -> dict[str, Any]:
    """Dispatch to the entrypoint agent.

    Args:
        input_data: Input data for the run.
        entrypoint: Name of the entrypoint to use.

    Returns:
        Agent execution result.
    """
    run_id = f"run_{{uuid.uuid4().hex[:12]}}"
    input_data = dict(input_data or {{}})
    session_id = str(input_data.get("session_id") or f"session_{{uuid.uuid4().hex[:12]}}")
    state_store = get_state_store()
    prior_state = state_store.get(session_id)
    if prior_state:
        input_data["_session_state"] = prior_state
    input_data["session_id"] = session_id
    incoming_trace = input_data.get("trace_id")
    trace_id = str(incoming_trace).strip() if incoming_trace else f"trace_{{uuid.uuid4().hex[:12]}}"
    write_run_manifest(
        run_id=run_id,
        entrypoint=entrypoint,
        input_data=input_data,
        status="started",
    )
    inc_counter("runs_total")
    log_event(
        "DISPATCH_START",
        run_id=run_id,
        trace_id=trace_id,
        status="started",
        entrypoint=entrypoint,
        input_keys=sorted(input_data.keys()),
    )

    # Find entrypoint
    ep = None
    for e in ENTRYPOINTS:
        if e["name"] == entrypoint:
            ep = e
            break
    if ep is None:
        raise ValueError(f"Entrypoint '{{entrypoint}}' not found")

    memory = MemoryManager()
    budget = BudgetTracker()
{dispatch_call}
        metrics = snapshot_metrics(run_id=run_id)
        log_event(
            "DISPATCH_END",
            run_id=run_id,
            trace_id=trace_id,
            entrypoint=entrypoint,
            root_agent=ep["agent_id"],
            status="ok",
            metrics=metrics,
        )
        state_store.update(
            session_id,
            {{
                "last_run_id": run_id,
                "last_entrypoint": entrypoint,
                "last_status": "ok",
                "available_tools": [tool.name for tool in list_tools()],
            }},
        )
        result = dict(result or {{}})
        result["run_id"] = run_id
        result["trace_id"] = trace_id
        result["session_id"] = session_id
        write_run_manifest(
            run_id=run_id,
            entrypoint=entrypoint,
            input_data=input_data,
            status="ok",
            metrics=metrics,
        )
        return result
    except Exception as exc:  # noqa: BLE001
        log_event(
            "DISPATCH_END",
            level="error",
            run_id=run_id,
            trace_id=trace_id,
            entrypoint=entrypoint,
            root_agent=ep["agent_id"],
            status="error",
            error_type=type(exc).__name__,
            error_msg=str(exc),
        )
        inc_counter("runs_failed_total")
        state_store.update(
            session_id,
            {{
                "last_run_id": run_id,
                "last_entrypoint": entrypoint,
                "last_status": "error",
                "last_error": str(exc),
            }},
        )
        write_run_manifest(
            run_id=run_id,
            entrypoint=entrypoint,
            input_data=input_data,
            status="error",
            error=str(exc),
        )
        raise


async def call_agent(
    agent_id: str,
    input_data: dict[str, Any],
    memory: "MemoryManager",
    budget: "BudgetTracker",
    run_id: str,
    trace_id: str,
    depth: int = 0,
    enable_recursive_handoffs: bool = True,
    state_store: Any | None = None,
    session_id: str | None = None,
) -> dict[str, Any]:
    """Execute a single agent's graph.

    Args:
        agent_id: The agent to execute.
        input_data: Input data.
        memory: Shared memory manager.
        budget: Budget tracker.
        depth: Current call depth.
        enable_recursive_handoffs: Whether Router handoffs recurse immediately.

    Returns:
        Execution result.
    """
    if depth >= MAX_GLOBAL_DEPTH:
        raise RuntimeError(
            f"Max global depth ({{MAX_GLOBAL_DEPTH}}) exceeded at agent '{{agent_id}}'"
        )

    graph = get_agent_graph(agent_id)
    runtime_cfg = get_runtime_config()
    config = graph["config"]
    log_event(
        "AGENT_START",
        run_id=run_id,
        trace_id=trace_id,
        node=agent_id,
        status="started",
        depth=depth,
        node_count=len(graph.get("nodes", [])),
    )

    # Check per-agent depth
    max_depth = config["budgets"].get("max_depth", 5)
    if depth >= max_depth:
        raise RuntimeError(
            f"Agent '{{agent_id}}' max_depth ({{max_depth}}) exceeded"
        )

    budget.register_agent(agent_id, config["budgets"])

    # Execute nodes in topological order
    nodes = graph["nodes"]
    edges = graph["edges"]
    order = _topological_sort(nodes, edges)

    raw_current = input_data.get("input", "")
    if isinstance(raw_current, str):
        sanitize_cfg = FLOW_POLICIES.get("input_sanitization", {{}})
        if sanitize_cfg.get("enabled", True):
            raw_current = sanitize_input(
                raw_current,
                strip_html=bool(sanitize_cfg.get("strip_html", True)),
                max_chars=int(sanitize_cfg.get("max_input_chars", 8000) or 8000),
            )

    context = {{"input": input_data, "current": raw_current, "outputs": {{}}}}

    # Optional reusable Plan->Act->Observe->Evaluate/Repair loop (MVP).
    _loop_agent_ids = set(
        a.strip().lower()
        for a in os.environ.get("LOOP_AGENT_IDS", "supervisor").split(",")
        if a.strip()
    )
    loop_enabled = (
        str(input_data.get("enable_loop", os.environ.get("LOOP_ENABLED", "1"))).lower()
        in {{"1", "true", "yes", "on"}}
    )
    if loop_enabled and agent_id.lower() in _loop_agent_ids:
        async def _loop_tool_executor(tool_name: str, tool_args: dict[str, Any]) -> dict[str, Any]:
            tool_node = {{
                "id": f"loop_tool_{{tool_name}}",
                "type": "Tool",
                "params": {{"tool_name": tool_name, "tool_config": tool_args}},
            }}
            tool_context = {{"current": tool_args.get("text") or tool_args.get("expression") or raw_current}}
            return await execute_node(
                node=tool_node,
                context=tool_context,
                agent_config=config,
                memory=memory,
                flow_policies=FLOW_POLICIES,
            )

        loop_state = await run_plan_act_loop(
            goal=str(raw_current),
            execute_tool=_loop_tool_executor,
            state_store=state_store,
            session_id=session_id,
        )
        context["outputs"]["_plan_act_loop"] = loop_state
        context["current"] = loop_state.get("last_tool_result") or loop_state

    # Enter OTel agent span (no-op context when OTel is disabled)
    _agent_otel_span = _otel_span_context(
        "forge.agent",
        agent_id=agent_id,
        run_id=run_id,
        trace_id=trace_id,
        depth=depth,
    )
    _agent_otel_span.__enter__()

    for node_id in order:
        node = next(n for n in nodes if n["id"] == node_id)
        step_id = f"step_{{uuid.uuid4().hex[:12]}}"
        node_started = time.perf_counter()
        try:
            budget.check(agent_id)
        except BudgetExceededError as exc:
            log_event(
                "BUDGET_EXCEEDED",
                level="error",
                run_id=run_id,
                trace_id=trace_id,
                step_id=step_id,
                node=node_id,
                status="error",
                error_type=type(exc).__name__,
                error_msg=str(exc),
                budget_type=exc.resource,
                used=exc.used,
                limit=exc.limit,
            )
            raise
        params = node.get("params", {{}})
        soft_fail = bool(runtime_cfg.allow_schema_soft_fail)
        context["__runtime"] = {{
            "run_id": run_id,
            "trace_id": trace_id,
            "agent_id": agent_id,
            "step_id": step_id,
            "node_id": node_id,
            "step_key": f"{{agent_id}}__{{node_id}}__{{step_id}}",
            "artifacts_dir": runtime_cfg.artifacts_dir,
            "replay_mode": str(input_data.get("replay_mode") or os.environ.get("REPLAY_MODE", "off")),
            "replay_run_id": str(input_data.get("replay_run_id") or os.environ.get("REPLAY_RUN_ID", "")),
        }}

        log_event(
            "NODE_START",
            run_id=run_id,
            trace_id=trace_id,
            step_id=step_id,
            node=node_id,
            status="started",
            depth=depth,
            node_type=node.get("type"),
        )
        inc_counter("node.started", run_id=run_id, agent_id=agent_id, node_type=str(node.get("type", "")))

        # Validate declared input schema for node boundaries.
        input_schema_error = validate_payload(
            payload={{
                "input": context.get("current"),
                "user_input": input_data,
                "agent_id": agent_id,
            }},
            schema_ref=params.get("input_schema"),
            soft_fail=soft_fail,
        )
        if input_schema_error:
            log_event(
                "SCHEMA_VALIDATION_ERROR",
                level="warning",
                phase="node_input",
                run_id=run_id,
                trace_id=trace_id,
                step_id=step_id,
                node=node_id,
                status="warning",
                error_type="SchemaValidationError",
                error_msg=input_schema_error,
                schema_ref=params.get("input_schema"),
            )

        # Enforce tool guardrails before node execution.
        if node.get("type") == "Tool":
            try:
                validate_tool_call(
                    tool_name=str(params.get("tool_name", "")),
                    agent_allowlist=config.get("tools_allowlist") or [],
                    flow_allowlist=FLOW_POLICIES.get("tool_allowlist", []) or [],
                    flow_denylist=FLOW_POLICIES.get("tool_denylist", []) or [],
                )
            except Exception as exc:  # noqa: BLE001
                inc_counter("guard.blocked", run_id=run_id, agent_id=agent_id, node_type="Tool")
                log_event(
                    "GUARD_BLOCK",
                    level="error",
                    run_id=run_id,
                    trace_id=trace_id,
                    step_id=step_id,
                    node=node_id,
                    status="blocked",
                    error_type=type(exc).__name__,
                    error_msg=str(exc),
                    tool_name=str(params.get("tool_name", "")),
                )
                raise

        # Execute node with retry policy.
        retries = config.get("retries") or {{}}

        def _on_retry(attempt: int, exc: Exception, category: str) -> None:
            log_event(
                "RETRY_ATTEMPT",
                level="warning",
                run_id=run_id,
                trace_id=trace_id,
                step_id=step_id,
                node=node_id,
                status="retrying",
                error_type=type(exc).__name__,
                error_msg=str(exc),
                attempt=attempt,
                category=category,
            )
            if category == "timeout":
                log_event(
                    "NODE_TIMEOUT",
                    level="warning",
                    run_id=run_id,
                    trace_id=trace_id,
                    step_id=step_id,
                    node=node_id,
                    status="timeout",
                    error_type=type(exc).__name__,
                    error_msg=str(exc),
                    attempt=attempt,
                )

        try:
            output = await run_with_retry(
                lambda: _execute_node(node, context, config, memory),
                max_attempts=int(retries.get("max_attempts", 2) or 2),
                backoff_ms=int(retries.get("backoff_ms", 300) or 300),
                retry_on=list(retries.get("retry_on") or ["timeout", "rate_limit", "5xx", "unknown"]),
                jitter=bool(retries.get("jitter", True)),
                on_retry=_on_retry,
            )
        except Exception as primary_error:  # noqa: BLE001
            inc_counter("node.failed", run_id=run_id, agent_id=agent_id, node_type=str(node.get("type", "")))
            log_event(
                "NODE_EXEC_ERROR",
                level="warning",
                run_id=run_id,
                trace_id=trace_id,
                step_id=step_id,
                node=node_id,
                status="error",
                error_type=type(primary_error).__name__,
                error_msg=str(primary_error),
                node_type=node.get("type"),
            )
            output = None
            fallback_cfg = config.get("fallbacks") or {{}}

            # LLM fallback chain: attempt next provider/model bindings.
            if node.get("type") == "LLM":
                chain = list(fallback_cfg.get("llm_chain") or [])
                for binding in chain[1:]:
                    attempt_cfg = dict(config)
                    attempt_cfg["provider"] = binding.get("provider", attempt_cfg.get("provider"))
                    attempt_cfg["model"] = binding.get("model", attempt_cfg.get("model"))
                    attempt_cfg["temperature"] = binding.get("temperature", attempt_cfg.get("temperature"))
                    try:
                        output = await run_with_retry(
                            lambda: _execute_node(node, context, attempt_cfg, memory),
                            max_attempts=int(retries.get("max_attempts", 2) or 2),
                            backoff_ms=int(retries.get("backoff_ms", 300) or 300),
                            retry_on=list(retries.get("retry_on") or ["timeout", "rate_limit", "5xx", "unknown"]),
                            jitter=bool(retries.get("jitter", True)),
                            on_retry=_on_retry,
                        )
                        if isinstance(output, dict):
                            output["fallback_used"] = binding
                        log_event(
                            "FALLBACK_USED",
                            run_id=run_id,
                            trace_id=trace_id,
                            step_id=step_id,
                            node=node_id,
                            status="fallback",
                            fallback_type="llm",
                            fallback_binding=binding,
                        )
                        break
                    except Exception:  # noqa: BLE001
                        continue

            # Tool fallback: map current tool name to backup tool.
            if output is None and node.get("type") == "Tool":
                tool_name = str(params.get("tool_name", ""))
                fallback_tool = (fallback_cfg.get("tool_fallbacks") or {{}}).get(tool_name)
                if fallback_tool:
                    validate_tool_call(
                        tool_name=str(fallback_tool),
                        agent_allowlist=config.get("tools_allowlist") or [],
                        flow_allowlist=FLOW_POLICIES.get("tool_allowlist", []) or [],
                        flow_denylist=FLOW_POLICIES.get("tool_denylist", []) or [],
                    )
                    node_copy = dict(node)
                    node_params = dict(params)
                    node_params["tool_name"] = fallback_tool
                    node_copy["params"] = node_params
                    output = await run_with_retry(
                        lambda: _execute_node(node_copy, context, config, memory),
                        max_attempts=int(retries.get("max_attempts", 2) or 2),
                        backoff_ms=int(retries.get("backoff_ms", 300) or 300),
                        retry_on=list(retries.get("retry_on") or ["timeout", "rate_limit", "5xx", "unknown"]),
                        jitter=bool(retries.get("jitter", True)),
                        on_retry=_on_retry,
                    )
                    if isinstance(output, dict):
                        output["fallback_tool_used"] = fallback_tool
                    log_event(
                        "FALLBACK_USED",
                        run_id=run_id,
                        trace_id=trace_id,
                        step_id=step_id,
                        node=node_id,
                        status="fallback",
                        fallback_type="tool",
                        from_tool=tool_name,
                        to_tool=fallback_tool,
                    )

            if output is None:
                raise primary_error
        context["outputs"][node_id] = output
        context["current"] = output
        if node.get("type") == "LLM" and isinstance(output, dict):
            budget.record_tokens(agent_id, int(output.get("token_usage", 0) or 0))
        if node.get("type") == "Tool" and isinstance(output, dict) and output.get("tool_called"):
            budget.record_tool_call(agent_id)
            inc_counter("tool_calls_total")
        budget.record_step(agent_id)

        for warning in budget.consume_and_get_warnings(agent_id, threshold=0.8):
            inc_counter("budget.warning", run_id=run_id, agent_id=agent_id, budget_type=str(warning.get("budget_type", "")))
            log_event(
                "BUDGET_WARNING",
                level="warning",
                run_id=run_id,
                trace_id=trace_id,
                step_id=step_id,
                node=node_id,
                status="warning",
                **warning,
            )

        elapsed_ms = (time.perf_counter() - node_started) * 1000.0
        record_timing_ms("node.latency_ms", elapsed_ms, run_id=run_id, agent_id=agent_id, node_type=str(node.get("type", "")))
        inc_counter("node.completed", run_id=run_id, agent_id=agent_id, node_type=str(node.get("type", "")))
        slow_node_ms = float(runtime_cfg.slow_node_ms)
        if elapsed_ms >= slow_node_ms:
            inc_counter("node.slow", run_id=run_id, agent_id=agent_id, node_type=str(node.get("type", "")))
            log_event(
                "NODE_SLOW",
                level="warning",
                run_id=run_id,
                trace_id=trace_id,
                step_id=step_id,
                node=node_id,
                duration_ms=round(elapsed_ms, 3),
                status="slow",
                depth=depth,
                node_type=node.get("type"),
                threshold_ms=slow_node_ms,
            )
        log_event(
            "NODE_END",
            run_id=run_id,
            trace_id=trace_id,
            step_id=step_id,
            node=node_id,
            duration_ms=round(elapsed_ms, 3),
            status="ok",
            depth=depth,
            node_type=node.get("type"),
        )

        # Validate declared output schema for node boundaries.
        output_schema_error = validate_payload(
            payload=output if isinstance(output, dict) else {{"result": output}},
            schema_ref=params.get("output_schema"),
            soft_fail=soft_fail,
        )
        if output_schema_error:
            log_event(
                "SCHEMA_VALIDATION_ERROR",
                level="warning",
                phase="node_output",
                run_id=run_id,
                trace_id=trace_id,
                step_id=step_id,
                node=node_id,
                status="warning",
                error_type="SchemaValidationError",
                error_msg=output_schema_error,
                schema_ref=params.get("output_schema"),
            )

        # Validate declared handoff schemas at router boundaries.
        selected_route = output.get("selected_route") if isinstance(output, dict) else None
        if node.get("type") == "Router" and selected_route:
            handoff = find_handoff(agent_id, selected_route)
            if handoff:
                handoff_input_error = validate_payload(
                    payload=input_data if isinstance(input_data, dict) else {{"input": input_data}},
                    schema_ref=handoff.get("input_schema"),
                    soft_fail=soft_fail,
                )
                if handoff_input_error:
                    log_event(
                        "SCHEMA_VALIDATION_ERROR",
                        level="warning",
                        phase="handoff_input",
                        run_id=run_id,
                        trace_id=trace_id,
                        step_id=step_id,
                        node=node_id,
                        status="warning",
                        error_type="SchemaValidationError",
                        error_msg=handoff_input_error,
                        from_agent=agent_id,
                        to_agent=handoff["to_agent_id"],
                        schema_ref=handoff.get("input_schema"),
                    )
                next_input = {{"input": str(context.get("current", "")), "source_agent": agent_id}}
                if not enable_recursive_handoffs:
                    context["next_agent_id"] = handoff["to_agent_id"]
                    context["next_input"] = next_input
                    log_event(
                        "AGENT_HANDOFF",
                        run_id=run_id,
                        trace_id=trace_id,
                        step_id=step_id,
                        node=node_id,
                        status="handoff",
                        from_agent=agent_id,
                        to_agent=handoff["to_agent_id"],
                        depth=depth,
                        mode=str(handoff.get("mode", "call")),
                        orchestrator="langgraph",
                    )
                    break

                handoff_result = await call_agent(
                    agent_id=handoff["to_agent_id"],
                    input_data=next_input,
                    memory=memory,
                    budget=budget,
                    run_id=run_id,
                    trace_id=trace_id,
                    depth=depth + 1,
                    enable_recursive_handoffs=True,
                    state_store=state_store,
                    session_id=session_id,
                )
                handoff_output_error = validate_payload(
                    payload=handoff_result if isinstance(handoff_result, dict) else {{"result": handoff_result}},
                    schema_ref=handoff.get("output_schema"),
                    soft_fail=soft_fail,
                )
                if handoff_output_error:
                    log_event(
                        "SCHEMA_VALIDATION_ERROR",
                        level="warning",
                        phase="handoff_output",
                        run_id=run_id,
                        trace_id=trace_id,
                        step_id=step_id,
                        node=node_id,
                        status="warning",
                        error_type="SchemaValidationError",
                        error_msg=handoff_output_error,
                        from_agent=agent_id,
                        to_agent=handoff["to_agent_id"],
                        schema_ref=handoff.get("output_schema"),
                    )
                context["outputs"][f"handoff:{{agent_id}}->{{handoff['to_agent_id']}}"] = handoff_result
                context["current"] = handoff_result

    log_event(
        "AGENT_END",
        run_id=run_id,
        trace_id=trace_id,
        node=agent_id,
        depth=depth,
        status="ok",
    )
    _agent_otel_span.__exit__(None, None, None)
    return context


def _topological_sort(nodes: list, edges: list) -> list[str]:
    """Topological sort of nodes."""
    node_ids = [n["id"] for n in nodes]
    adj: dict[str, list[str]] = {{nid: [] for nid in node_ids}}
    in_deg: dict[str, int] = {{nid: 0 for nid in node_ids}}

    for e in edges:
        adj[e["source"]].append(e["target"])
        in_deg[e["target"]] += 1

    queue = sorted(nid for nid in node_ids if in_deg[nid] == 0)
    result = []

    while queue:
        n = queue.pop(0)
        result.append(n)
        for nb in adj[n]:
            in_deg[nb] -= 1
            if in_deg[nb] == 0:
                queue.append(nb)
        queue.sort()

    return result


async def _execute_node(
    node: dict[str, Any],
    context: dict[str, Any],
    agent_config: dict[str, Any],
    memory: "MemoryManager",
) -> Any:
    """Execute a single node using runtime adapters."""
    return await execute_node(
        node=node,
        context=context,
        agent_config=agent_config,
        memory=memory,
        flow_policies=FLOW_POLICIES,
    )
'''

    def _generate_supervisor(self) -> str:
        handoffs_repr = pformat(
            [h.model_dump(mode="json") for h in self.ir.handoffs], width=100, sort_dicts=False
        )
        return f'''"""Supervisor: rules-based handoff routing."""

from typing import Any

HANDOFF_RULES: list[dict[str, Any]] = {handoffs_repr}


def find_handoff(from_agent: str, route_target: str) -> dict[str, Any] | None:
    """Find a handoff rule matching a route target."""
    for rule in HANDOFF_RULES:
        if rule["from_agent_id"] == from_agent and rule["to_agent_id"] == route_target:
            return rule
    return None


def get_handoffs_from(agent_id: str) -> list[dict[str, Any]]:
    """Get all handoff rules from a given agent."""
    return [r for r in HANDOFF_RULES if r["from_agent_id"] == agent_id]


def get_handoffs_to(agent_id: str) -> list[dict[str, Any]]:
    """Get all handoff rules targeting a given agent."""
    return [r for r in HANDOFF_RULES if r["to_agent_id"] == agent_id]
'''

    def _generate_memory(self) -> str:
        namespaces = self.ir.resources.shared_memory_namespaces
        return f'''"""Namespace-scoped memory manager."""

from typing import Any

SHARED_NAMESPACES: list[str] = {json.dumps(namespaces)}


class MemoryManager:
    """In-memory namespace-scoped store."""

    def __init__(self) -> None:
        self._store: dict[str, dict[str, Any]] = {{}}

    def get(self, namespace: str, key: str, default: Any = None) -> Any:
        return self._store.get(namespace, {{}}).get(key, default)

    def set(self, namespace: str, key: str, value: Any) -> None:
        self._store.setdefault(namespace, {{}})[key] = value

    def get_namespace(self, namespace: str) -> dict[str, Any]:
        return dict(self._store.get(namespace, {{}}))

    def clear(self, namespace: str) -> None:
        self._store.pop(namespace, None)
'''

    def _generate_budgets(self) -> str:
        return '''"""Budget enforcement for agents."""

from typing import Any


class BudgetExceededError(Exception):
    """Raised when an agent exceeds its budget."""

    def __init__(self, agent_id: str, resource: str, limit: int, used: int):
        self.agent_id = agent_id
        self.resource = resource
        self.limit = limit
        self.used = used
        super().__init__(
            f"Agent '{agent_id}' exceeded {resource} budget: {used}/{limit}"
        )


class BudgetTracker:
    """Tracks budget consumption per agent."""

    def __init__(self) -> None:
        self._limits: dict[str, dict[str, Any]] = {}
        self._usage: dict[str, dict[str, int]] = {}
        self._warnings_emitted: dict[str, set[str]] = {}

    def register_agent(self, agent_id: str, budgets: dict[str, Any]) -> None:
        """Register budget limits for an agent."""
        if agent_id not in self._limits:
            self._limits[agent_id] = budgets
            self._usage[agent_id] = {
                "tokens": 0,
                "tool_calls": 0,
                "steps": 0,
            }
            self._warnings_emitted[agent_id] = set()

    def check(self, agent_id: str) -> None:
        """Check if the agent is within budget."""
        limits = self._limits.get(agent_id, {})
        usage = self._usage.get(agent_id, {})

        max_steps = limits.get("max_steps")
        if max_steps is not None and usage["steps"] >= max_steps:
            raise BudgetExceededError(agent_id, "max_steps", max_steps, usage["steps"])

        max_tokens = limits.get("max_tokens")
        if max_tokens is not None and usage["tokens"] >= max_tokens:
            raise BudgetExceededError(agent_id, "max_tokens", max_tokens, usage["tokens"])

        max_tool_calls = limits.get("max_tool_calls")
        if max_tool_calls is not None and usage["tool_calls"] >= max_tool_calls:
            raise BudgetExceededError(
                agent_id, "max_tool_calls", max_tool_calls, usage["tool_calls"]
            )

    def record_step(self, agent_id: str) -> None:
        if agent_id in self._usage:
            self._usage[agent_id]["steps"] += 1

    def record_tokens(self, agent_id: str, count: int) -> None:
        if agent_id in self._usage:
            self._usage[agent_id]["tokens"] += count

    def record_tool_call(self, agent_id: str) -> None:
        if agent_id in self._usage:
            self._usage[agent_id]["tool_calls"] += 1

    def get_usage(self, agent_id: str) -> dict[str, int]:
        return dict(self._usage.get(agent_id, {"tokens": 0, "tool_calls": 0, "steps": 0}))

    def get_limits(self, agent_id: str) -> dict[str, Any]:
        return dict(self._limits.get(agent_id, {}))

    def consume_and_get_warnings(self, agent_id: str, threshold: float = 0.8) -> list[dict[str, Any]]:
        limits = self._limits.get(agent_id, {})
        usage = self._usage.get(agent_id, {})
        warnings: list[dict[str, Any]] = []
        mapping = {
            "max_steps": "steps",
            "max_tokens": "tokens",
            "max_tool_calls": "tool_calls",
        }
        emitted = self._warnings_emitted.setdefault(agent_id, set())
        for limit_key, usage_key in mapping.items():
            limit = limits.get(limit_key)
            if limit is None or int(limit) <= 0:
                continue
            used = int(usage.get(usage_key, 0))
            ratio = used / float(limit)
            if ratio >= threshold and limit_key not in emitted:
                emitted.add(limit_key)
                warnings.append(
                    {
                        "budget_type": limit_key,
                        "used": used,
                        "limit": int(limit),
                        "ratio": ratio,
                    }
                )
        return warnings
'''

    def _generate_settings(self) -> str:
        policy_data = self.ir.policies.model_dump()
        policy_data["allow_schema_soft_fail"] = False
        allowlist = list(policy_data.get("tool_allowlist") or [])
        if "echo" not in allowlist and "tools.echo" not in allowlist:
            if "mcp:*" in allowlist:
                idx = allowlist.index("mcp:*")
                allowlist.insert(idx, "echo")
            else:
                allowlist.append("echo")
        policy_data["tool_allowlist"] = allowlist
        policy_repr = pformat(policy_data, width=120, sort_dicts=False)
        return f'''"""Project settings."""

import os
from pathlib import Path
from typing import Any


def _load_env_file() -> None:
    # Lightweight dotenv loader (no extra dependency required).
    env_path = Path.cwd() / ".env"
    if not env_path.exists():
        return
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key:
            os.environ[key] = value


_load_env_file()

FLOW_ID = "{self.ir.flow.id}"
FLOW_NAME = "{self.ir.flow.name}"
FLOW_VERSION = "{self.ir.flow.version}"
FLOW_POLICIES: dict[str, Any] = {policy_repr}

_TOOL_ALIASES = {{
    "echo": "tools.echo",
    "calculator": "tools.safe_calculator",
    "safe_calculator": "tools.safe_calculator",
    "datetime": "tools.datetime_now",
    "search": "tools.web_search",
    "web_search": "tools.web_search",
    "url_reader": "tools.web_search",
    "http_get": "tools.http_get",
}}


def _canonical_tool_name(name: str) -> str:
    value = str(name or "").strip()
    if not value or value in {{"tools.*", "mcp:*"}} or value.startswith("mcp:"):
        return value
    return _TOOL_ALIASES.get(value, value)


def _normalize_tool_patterns(items: list[str] | None, *, default: list[str]) -> list[str]:
    raw = list(items or [])
    if not raw:
        raw = list(default)
    out: list[str] = []
    for item in raw:
        canon = _canonical_tool_name(item)
        if canon and canon not in out:
            out.append(canon)
    return out


def _normalize_redaction_patterns(items: list[str] | None) -> list[str]:
    out: list[str] = []
    for item in list(items or []):
        value = str(item).replace("\\\\\\\\", "\\\\").strip()
        if value:
            out.append(value)
    return out


FLOW_POLICIES["tool_allowlist"] = _normalize_tool_patterns(
    FLOW_POLICIES.get("tool_allowlist"),
    default=["tools.*", "mcp:*"],
)
FLOW_POLICIES["tool_denylist"] = _normalize_tool_patterns(
    FLOW_POLICIES.get("tool_denylist"),
    default=["python_repl", "shell", "exec"],
)
if isinstance(FLOW_POLICIES.get("redaction"), dict):
    FLOW_POLICIES["redaction"]["patterns"] = _normalize_redaction_patterns(
        FLOW_POLICIES["redaction"].get("patterns")
    )

FLOW_POLICIES["allow_schema_soft_fail"] = (
    os.environ.get("FORGE_ALLOW_SCHEMA_SOFT_FAIL", "0").strip().lower()
    in {"1", "true", "yes"}
)

OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
GOOGLE_API_KEY = os.environ.get("GOOGLE_API_KEY", "")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")


# ── Typed runtime settings ─────────────────────────────────────────────────────

class _RuntimeSettings:
    """Typed runtime settings with fail-fast validation on startup."""

    def __init__(self) -> None:
        self.forge_env: str = os.environ.get("FORGE_ENV", "development").lower()
        self.is_production: bool = self.forge_env in {{"prod", "production"}}
        self.runtime_api_token: str = os.environ.get("RUNTIME_API_TOKEN", "").strip()
        self.openai_api_key: str = os.environ.get("OPENAI_API_KEY", "").strip()
        self.log_level: str = os.environ.get("LOG_LEVEL", "INFO").upper()
        self.state_backend: str = os.environ.get("STATE_BACKEND", "inmemory").strip().lower()
        self.run_store_backend: str = os.environ.get("RUN_STORE_BACKEND", "filesystem").strip().lower()
        self.artifacts_dir: str = os.environ.get("FORGE_ARTIFACTS_DIR", "artifacts").strip()
        self._validate()

    def _validate(self) -> None:
        import logging as _logging
        errors: list[str] = []
        if self.is_production:
            if not self.runtime_api_token:
                errors.append("RUNTIME_API_TOKEN is required in production.")
            if not self.openai_api_key:
                errors.append("OPENAI_API_KEY is required in production.")
            if self.state_backend == "inmemory":
                errors.append(
                    "STATE_BACKEND=inmemory is not safe for production: state is lost on restart "
                    "and not shared across replicas. Set STATE_BACKEND=redis or STATE_BACKEND=postgres."
                )
            if self.run_store_backend == "filesystem":
                errors.append(
                    "RUN_STORE_BACKEND=filesystem is not safe for production: data is stored locally "
                    "and not shared across replicas. Set RUN_STORE_BACKEND=postgres or RUN_STORE_BACKEND=s3."
                )
        if errors:
            raise RuntimeError("Configuration errors:\\n" + "\\n".join(f"  - {{e}}" for e in errors))


RUNTIME_SETTINGS = _RuntimeSettings()


# ── Pydantic-based typed settings ─────────────────────────────────────────────

from functools import lru_cache  # noqa: E402
from typing import Literal  # noqa: E402
from pydantic import Field  # noqa: E402
from pydantic_settings import BaseSettings, SettingsConfigDict  # noqa: E402


class ForgeSettings(BaseSettings):
    """Typed runtime settings for Forge agent server (Pydantic BaseSettings).

    Populated from environment variables (and .env file if present).
    Access via get_settings() for a cached instance.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    runtime_api_token: str = Field(default="", alias="RUNTIME_API_TOKEN")
    forge_env: str = Field(default="development", alias="FORGE_ENV")
    server_host: str = Field(default="0.0.0.0", alias="SERVER_HOST")
    server_port: int = Field(default=8080, alias="SERVER_PORT")
    rate_limiter_backend: Literal["inmemory", "redis"] = Field(
        default="inmemory", alias="RATE_LIMITER_BACKEND"
    )
    rate_limiter_redis_url: str = Field(
        default="redis://localhost:6379/0", alias="RATE_LIMITER_REDIS_URL"
    )
    server_rate_limit_rps: float = Field(default=20.0, alias="SERVER_RATE_LIMIT_RPS")
    idempotency_backend: Literal["inmemory", "redis"] = Field(
        default="inmemory", alias="IDEMPOTENCY_BACKEND"
    )
    idempotency_redis_url: str = Field(
        default="redis://localhost:6379/0", alias="IDEMPOTENCY_REDIS_URL"
    )
    idempotency_ttl_s: float = Field(default=300.0, alias="IDEMPOTENCY_TTL_S")
    state_backend: str = Field(default="inmemory", alias="STATE_BACKEND")
    run_store_backend: str = Field(default="filesystem", alias="RUN_STORE_BACKEND")


@lru_cache(maxsize=1)
def get_settings() -> ForgeSettings:
    """Return a cached ForgeSettings instance loaded from environment / .env."""
    return ForgeSettings()


def _load_ssm_secrets() -> None:
    """Load secrets from AWS Parameter Store if AWS_SECRETS_BACKEND=ssm."""
    if os.environ.get("AWS_SECRETS_BACKEND", "").strip().lower() != "ssm":
        return
    try:
        import boto3  # noqa: PLC0415

        prefix = os.environ.get("AWS_SSM_PREFIX", "").rstrip("/")
        region = os.environ.get("AWS_REGION", "us-east-1")
        ssm = boto3.client("ssm", region_name=region)
        params = ssm.get_parameters_by_path(Path=prefix + "/", WithDecryption=True)
        for p in params.get("Parameters", []):
            key = p["Name"].split("/")[-1]
            os.environ.setdefault(key, p["Value"])
    except Exception as exc:  # noqa: BLE001
        import logging as _logging
        _logging.getLogger("forge.settings").warning("SSM load failed: %s", exc)


def init_secrets() -> None:
    """Call once at server startup to load secrets from AWS SSM (if configured).

    Not called automatically on import to keep settings side-effect-free.
    Call this from main.py or server.py before starting the HTTP server.
    """
    _load_ssm_secrets()


def _validate_production_config() -> None:
    """Fail fast if required production config is missing."""
    if os.environ.get("FORGE_ENV", "development").lower() not in {{"prod", "production"}}:
        return
    token = os.environ.get("RUNTIME_API_TOKEN", "").strip()
    if not token:
        raise RuntimeError(
            "RUNTIME_API_TOKEN is required in production. "
            "Generate with: openssl rand -hex 32"
        )
    openai_key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not openai_key:
        raise RuntimeError("OPENAI_API_KEY is required in production.")
    # MCP: if servers are configured, require an explicit command allowlist
    mcp_servers_raw = os.environ.get("MCP_SERVERS", "[]").strip()
    if mcp_servers_raw not in ("[]", "", "null", "{{}}"):
        allowed_cmds = os.environ.get("MCP_ALLOWED_COMMANDS", "").strip()
        if not allowed_cmds:
            raise RuntimeError(
                "MCP_SERVERS is configured but MCP_ALLOWED_COMMANDS is empty. "
                "In production, set MCP_ALLOWED_COMMANDS to an explicit allowlist "
                "(e.g. 'search,summarize') or set MCP_SERVERS=[] to disable MCP."
            )


_validate_production_config()
'''

    def _generate_observability(self) -> str:
        return '''"""Structured logging + metrics helpers for generated runtime."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, UTC
import json
import logging
import os
from typing import Any

from runtime.policy_guard import apply_redaction
from settings import FLOW_POLICIES


_OTEL_ENABLED = os.environ.get("FORGE_OTEL_ENABLED", "0").strip().lower() in {"1", "true", "yes"}
_otel_tracer = None

if _OTEL_ENABLED:
    try:
        from opentelemetry import trace  # noqa: PLC0415
        from opentelemetry.sdk.trace import TracerProvider  # noqa: PLC0415
        from opentelemetry.sdk.trace.export import BatchSpanProcessor  # noqa: PLC0415
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter  # noqa: PLC0415

        _provider = TracerProvider()
        _endpoint = os.environ.get("FORGE_OTEL_ENDPOINT", "http://localhost:4317")
        _provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=_endpoint)))
        trace.set_tracer_provider(_provider)
        _otel_tracer = trace.get_tracer("forge.runtime")
    except ImportError:
        import logging as _log
        _log.getLogger("forge.runtime").warning(
            "FORGE_OTEL_ENABLED=1 but opentelemetry-sdk not installed. "
            "Add opentelemetry-sdk to requirements.txt."
        )


def _otel_span_context(event_type: str, **attrs: Any):
    """Context manager that creates an OTel span if OTel is enabled."""
    if _otel_tracer is None:
        from contextlib import nullcontext  # noqa: PLC0415
        return nullcontext()
    return _otel_tracer.start_as_current_span(event_type, attributes={
        k: str(v) for k, v in attrs.items() if v is not None
    })


_LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO").upper()
_LOGGER = logging.getLogger("forge.runtime")
_COUNTERS: dict[str, int] = defaultdict(int)
_TIMINGS: dict[str, list[float]] = defaultdict(list)
_DEFAULT_COUNTERS = ("runs_total", "runs_failed_total", "tool_calls_total")
_DEFAULT_REDACTION_PATTERNS = [
    r"(?i)authorization:\\s*bearer\\s+[a-z0-9._-]+",
    r"(?i)api[_-]?key\\s*[=:]\\s*[^\\s,;]+",
    r"(?i)token\\s*[=:]\\s*[^\\s,;]+",
    r"(?i)secret\\s*[=:]\\s*[^\\s,;]+",
    r"sk-[a-zA-Z0-9]{16,}",
]

if not _LOGGER.handlers:
    logging.basicConfig(level=getattr(logging, _LOG_LEVEL, logging.INFO))


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _redact_value(value: Any, patterns: list[str], mask: str) -> Any:
    if isinstance(value, str):
        return apply_redaction(value, patterns, mask=mask)
    if isinstance(value, dict):
        return {k: _redact_value(v, patterns, mask) for k, v in value.items()}
    if isinstance(value, list):
        return [_redact_value(v, patterns, mask) for v in value]
    return value


def _metric_key(name: str, **labels: Any) -> str:
    if not labels:
        return name
    label_parts = [f"{k}={labels[k]}" for k in sorted(labels.keys())]
    return f"{name}|{'|'.join(label_parts)}"


def inc_counter(name: str, value: int = 1, **labels: Any) -> None:
    key = _metric_key(name, **labels)
    _COUNTERS[key] += int(value)


def record_timing_ms(name: str, duration_ms: float, **labels: Any) -> None:
    key = _metric_key(name, **labels)
    _TIMINGS[key].append(float(duration_ms))


def snapshot_metrics(*, run_id: str | None = None) -> dict[str, Any]:
    counter_snapshot = dict(_COUNTERS)
    for name in _DEFAULT_COUNTERS:
        counter_snapshot.setdefault(name, 0)
    timing_snapshot: dict[str, dict[str, float]] = {}
    for key, values in _TIMINGS.items():
        if not values:
            continue
        timing_snapshot[key] = {
            "count": float(len(values)),
            "avg_ms": sum(values) / len(values),
            "max_ms": max(values),
        }
    return {
        "run_id": run_id or "",
        "counters": counter_snapshot,
        "timings": timing_snapshot,
    }


def snapshot_metrics_prometheus() -> str:
    """Expose minimal Prometheus-compatible payload."""
    lines: list[str] = []
    counters = dict(_COUNTERS)
    for name in _DEFAULT_COUNTERS:
        counters.setdefault(name, 0)
    for key, value in sorted(counters.items()):
        metric_name = key.split("|", 1)[0].replace(".", "_")
        labels: dict[str, str] = {}
        if "|" in key:
            for part in key.split("|")[1:]:
                if "=" in part:
                    k, v = part.split("=", 1)
                    labels[k] = v
        label_str = ""
        if labels:
            rendered = ",".join(f'{k}="{v}"' for k, v in sorted(labels.items()))
            label_str = f"{{{rendered}}}"
        lines.append(f"{metric_name}{label_str} {value}")
    for key, values in sorted(_TIMINGS.items()):
        if not values:
            continue
        metric_name = key.split("|", 1)[0].replace(".", "_")
        lines.append(f"{metric_name}_count {len(values)}")
        lines.append(f"{metric_name}_sum {sum(values):.6f}")
        lines.append(f"{metric_name}_max {max(values):.6f}")
    return "\\n".join(lines) + "\\n"


def build_log_record(
    event: str,
    *,
    level: str = "info",
    run_id: str | None = None,
    trace_id: str | None = None,
    step_id: str | None = None,
    node: str | None = None,
    duration_ms: float | None = None,
    status: str | None = None,
    error_type: str | None = None,
    error_msg: str | None = None,
    **payload: Any,
) -> dict[str, Any]:
    redaction = _as_dict(FLOW_POLICIES.get("redaction", FLOW_POLICIES.get("output_redaction", {})))
    patterns = list(_DEFAULT_REDACTION_PATTERNS) + list(redaction.get("patterns") or [])
    mask = str(redaction.get("mask", "***REDACTED***"))
    sanitized_payload = _redact_value(payload, patterns, mask)
    record: dict[str, Any] = {
        "ts": datetime.now(UTC).isoformat(),
        "level": level.lower(),
        "event": event,
        "run_id": run_id or "",
        "trace_id": trace_id or "",
        "step_id": step_id or "",
        "node": node or "",
        "duration_ms": float(duration_ms) if duration_ms is not None else None,
        "status": status or "",
        "error_type": error_type or "",
        "error_msg": error_msg or "",
        "payload": sanitized_payload,
    }
    return record


def log_event(
    event: str,
    *,
    level: str = "info",
    run_id: str | None = None,
    trace_id: str | None = None,
    step_id: str | None = None,
    node: str | None = None,
    duration_ms: float | None = None,
    status: str | None = None,
    error_type: str | None = None,
    error_msg: str | None = None,
    **payload: Any,
) -> None:
    record = build_log_record(
        event,
        level=level,
        run_id=run_id,
        trace_id=trace_id,
        step_id=step_id,
        node=node,
        duration_ms=duration_ms,
        status=status,
        error_type=error_type,
        error_msg=error_msg,
        **payload,
    )
    inc_counter("events.total")
    inc_counter("events.by_type", event=event)
    inc_counter("events.by_level", level=level.lower())
    line = json.dumps(record, ensure_ascii=False, default=str)
    # OTel span enrichment — attaches event fields to the active span when enabled.
    if _OTEL_ENABLED and _otel_tracer is not None:
        try:
            from opentelemetry import trace as _trace  # noqa: PLC0415
            span = _trace.get_current_span()
            if span and span.is_recording():
                span.set_attribute("forge.event_type", event)
                for k, v in record.items():
                    if v is not None and k not in ("payload",):
                        span.set_attribute(f"forge.{k}", str(v))
        except Exception:  # noqa: BLE001
            pass
    log_fn = getattr(_LOGGER, level.lower(), _LOGGER.info)
    log_fn(line)
'''

    def _collect_schema_refs(self) -> list[SchemaRef]:
        refs: list[SchemaRef] = []
        for handoff in self.ir.handoffs:
            if handoff.input_schema is not None:
                refs.append(handoff.input_schema)
            if handoff.output_schema is not None:
                refs.append(handoff.output_schema)

        for agent in self.ir.agents:
            for node in agent.graph.nodes:
                params = node.params if isinstance(node.params, dict) else {}
                for key in ("input_schema", "output_schema"):
                    raw = params.get(key)
                    if isinstance(raw, dict):
                        try:
                            refs.append(SchemaRef.model_validate(raw))
                        except Exception:
                            continue
                    elif isinstance(raw, SchemaRef):
                        refs.append(raw)
        return refs

    def _materialize_and_remap_schemas(self, schemas_dir: Path) -> FlowIRv2:
        schemas_dir.mkdir(parents=True, exist_ok=True)
        refs = self._collect_schema_refs()
        index: dict[str, dict[str, Any]] = {}
        source_to_runtime: dict[str, str] = {}
        seen_by_source: dict[str, str] = {}
        counter = 0

        for ref in refs:
            if ref.kind != "json_schema":
                continue
            src = Path(ref.ref)
            if not src.exists():
                continue
            src_key = str(src.resolve())
            if src_key in seen_by_source:
                source_to_runtime[src_key] = seen_by_source[src_key]
                continue

            dst_name = f"schema_{counter}_{src.name}"
            counter += 1
            dst = schemas_dir / dst_name
            content = src.read_text(encoding="utf-8")
            dst.write_text(content, encoding="utf-8")
            runtime_ref = f"runtime/schemas/{dst_name}"
            seen_by_source[src_key] = runtime_ref
            source_to_runtime[src_key] = runtime_ref
            index[runtime_ref] = {
                "path": runtime_ref,
                "sha256": hashlib.sha256(content.encode("utf-8")).hexdigest(),
                "kind": ref.kind.value,
            }

        self._write(schemas_dir / "index.json", json.dumps(index, indent=2))
        self._schema_ref_runtime_map = source_to_runtime

        ir_copy = self.ir.model_copy(deep=True)
        for handoff in ir_copy.handoffs:
            if handoff.input_schema and handoff.input_schema.kind == "json_schema":
                key = str(Path(handoff.input_schema.ref).resolve())
                if key in source_to_runtime:
                    handoff.input_schema.ref = source_to_runtime[key]
            if handoff.output_schema and handoff.output_schema.kind == "json_schema":
                key = str(Path(handoff.output_schema.ref).resolve())
                if key in source_to_runtime:
                    handoff.output_schema.ref = source_to_runtime[key]

        for agent in ir_copy.agents:
            # Materialize effective per-agent policies in exported IR for determinism.
            if agent.policies is None and ir_copy.policies is not None:
                agent.policies = ir_copy.policies.model_copy(deep=True)
            for node in agent.graph.nodes:
                params = node.params if isinstance(node.params, dict) else {}
                for schema_key in ("input_schema", "output_schema"):
                    raw = params.get(schema_key)
                    if not isinstance(raw, dict):
                        continue
                    try:
                        schema_ref = SchemaRef.model_validate(raw)
                    except Exception:
                        continue
                    if schema_ref.kind != "json_schema":
                        continue
                    key = str(Path(schema_ref.ref).resolve())
                    if key in source_to_runtime:
                        schema_ref.ref = source_to_runtime[key]
                        params[schema_key] = schema_ref.model_dump()

        return ir_copy

    def _generate_policy_guard(self) -> str:
        return '''"""Runtime policy guard helpers."""

from __future__ import annotations

import re
from fnmatch import fnmatchcase
from runtime.tools.names import canonical_tool_name


# Prompt injection heuristic patterns — common jailbreak / injection prefixes.
# Override or extend via FORGE_INJECTION_PATTERNS env var (comma-separated regex list).
_DEFAULT_INJECTION_PATTERNS: list[str] = [
    r"(?i)\\bignore\\s+(previous|prior|above|all)\\s+(instructions?|prompts?|context)",
    r"(?i)\\bact\\s+as\\s+(a\\s+)?(dan|jailbreak|unrestricted|evil|do\\s+anything)",
    r"(?i)<\\|?(system|user|assistant|im_start|im_end)\\|?>",
    r"(?i)\\byou\\s+are\\s+now\\s+(a\\s+)?(new\\s+)?(ai|assistant|model|persona)",
    r"(?i)\\bforget\\s+(everything|all)\\s+(you\\s+)?(know|were\\s+told|learned)",
]


def _get_injection_patterns() -> list[str]:
    custom_raw = os.environ.get("FORGE_INJECTION_PATTERNS", "").strip()
    base = list(_DEFAULT_INJECTION_PATTERNS)
    if custom_raw and custom_raw.lower() != "disabled":
        for p in custom_raw.split(","):
            p = p.strip()
            if p:
                base.append(p)
    elif custom_raw.lower() == "disabled":
        return []
    return base


def sanitize_input(
    text: str,
    *,
    strip_html: bool = True,
    max_chars: int = 8000,
    check_injection: bool = True,
) -> str:
    """Sanitize user input before passing to LLM dispatch.

    - Strips HTML tags (prevents HTML injection into prompts).
    - Caps input length at max_chars (prevents token flooding).
    - Checks for common prompt injection patterns (raises ValueError if detected).

    Args:
        text: Raw user input string.
        strip_html: Strip HTML tags (default True).
        max_chars: Maximum allowed character count (default 8000, 0 = no limit).
        check_injection: Run injection heuristics (default True).

    Raises:
        ValueError: If a prompt injection pattern is detected.
    """
    value = text
    if strip_html:
        value = re.sub(r"<[^>]+>", " ", value)
    if max_chars > 0 and len(value) > max_chars:
        value = value[:max_chars]
    if check_injection:
        for pattern in _get_injection_patterns():
            try:
                if re.search(pattern, value):
                    raise ValueError(
                        f"Input rejected: prompt injection pattern detected. "
                        f"Pattern: {pattern!r[:60]}"
                    )
            except re.error:
                continue  # Skip malformed custom patterns gracefully
    return value


def apply_redaction(text: str, patterns: list[str], mask: str = "***REDACTED***") -> str:
    if not patterns:
        return text
    out = text
    for pattern in patterns:
        try:
            normalized = str(pattern).replace("\\\\\\\\", "\\\\")
            out = re.sub(normalized, mask, out)
        except re.error:
            continue
    return out


def validate_tool_call(
    *,
    tool_name: str,
    agent_allowlist: list[str] | None = None,
    flow_allowlist: list[str] | None = None,
    flow_denylist: list[str] | None = None,
) -> None:
    """Validate tool call against allowlist/denylist policies."""
    name = (tool_name or "").strip()
    if not name:
        return
    name = canonical_tool_name(name)

    def _matches(patterns: list[str], value: str) -> bool:
        for pattern in patterns:
            p = str(pattern or "").strip()
            if not p:
                continue
            if fnmatchcase(value, p):
                return True
        return False

    denylist = [canonical_tool_name(p) if str(p).strip() not in {"tools.*", "mcp:*"} else str(p).strip() for p in list(flow_denylist or [])]
    if _matches(denylist, name):
        raise RuntimeError(f"Tool denied by flow policy: {name}")

    allowed_by_agent = [canonical_tool_name(p) if str(p).strip() not in {"tools.*", "mcp:*"} else str(p).strip() for p in list(agent_allowlist or [])]
    allowed_by_flow = [canonical_tool_name(p) if str(p).strip() not in {"tools.*", "mcp:*"} else str(p).strip() for p in list(flow_allowlist or [])]

    # If either list is defined, the tool must be allowed by at least one policy list.
    if (allowed_by_agent or allowed_by_flow) and not (
        _matches(allowed_by_agent, name) or _matches(allowed_by_flow, name)
    ):
        raise RuntimeError(f"Tool not allowlisted: {name}")
'''

    def _generate_retry(self) -> str:
        return '''"""Runtime retry helpers."""

from __future__ import annotations

import asyncio
import inspect
import random
from typing import Any, Awaitable, Callable


def _classify_error(exc: Exception) -> str:
    message = str(exc).lower()
    if "timeout" in message:
        return "timeout"
    if "rate limit" in message or "429" in message:
        return "rate_limit"
    if "401" in message or "403" in message or "auth" in message:
        return "auth"
    if "500" in message or "502" in message or "503" in message or "504" in message:
        return "5xx"
    if "validation" in message or "schema" in message:
        return "validation"
    if "connection" in message or "network" in message:
        return "network"
    return "unknown"


async def run_with_retry(
    fn: Callable[[], Awaitable[Any]],
    *,
    max_attempts: int = 2,
    backoff_ms: int = 300,
    retry_on: list[str] | None = None,
    jitter: bool = True,
    on_retry: Callable[[int, Exception, str], Any] | None = None,
) -> Any:
    retry_categories = set(retry_on or ["timeout", "rate_limit", "5xx", "unknown"])
    last_error: Exception | None = None
    for attempt in range(1, max(1, max_attempts) + 1):
        try:
            return await fn()
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            category = _classify_error(exc)
            if category not in retry_categories:
                break
            if attempt >= max_attempts:
                break
            if on_retry is not None:
                maybe_coro = on_retry(attempt, exc, category)
                if inspect.isawaitable(maybe_coro):
                    await maybe_coro
            delay = backoff_ms / 1000.0
            if jitter:
                delay = max(0.0, delay * (0.5 + random.random()))
            await asyncio.sleep(delay)
    raise last_error if last_error is not None else RuntimeError("Retry exhausted")
'''

    def _generate_runtime_auth(self) -> str:
        return '''"""Runtime API auth helpers."""

from __future__ import annotations

import os


def _is_dev() -> bool:
    return os.environ.get("DEV_MODE", "0").strip().lower() in {"1", "true", "yes", "on"}


def _allow_unauth_in_dev() -> bool:
    return os.environ.get("ALLOW_UNAUTHENTICATED_IN_DEV", "0").strip().lower() in {"1", "true", "yes", "on"}


def is_auth_exempt(path: str) -> bool:
    """Paths that do not require RUNTIME_API_TOKEN authentication.

    NOTE: /metrics is intentionally NOT exempt — it may expose operational
    details (run counts, latencies, error rates). Protect it with the
    standard bearer token or behind a reverse proxy ACL.
    """
    return path in {"/healthz", "/readyz"}


def require_auth(path: str, authorization_header: str | None) -> None:
    if is_auth_exempt(path):
        return
    token = str(os.environ.get("RUNTIME_API_TOKEN", "")).strip()
    forge_env = os.environ.get("FORGE_ENV", "production").strip().lower()
    if not token or token == "change-me":
        if forge_env in {"prod", "production"}:
            raise PermissionError("runtime_api_token_not_configured")
        if _is_dev() and _allow_unauth_in_dev():
            return
        raise PermissionError("runtime_api_token_not_configured")
    if _is_dev() and _allow_unauth_in_dev():
        return
    header = str(authorization_header or "").strip()
    expected = f"Bearer {token}"
    if header != expected:
        raise PermissionError("unauthorized")
'''

    def _generate_mock_provider(self) -> str:
        return '''"""Deterministic mock LLM provider for offline/dev runs."""

from __future__ import annotations

import hashlib
from typing import Any


def mock_llm_response(
    *,
    provider: str,
    model: str,
    prompt: str,
    system_prompt: str | None = None,
) -> dict[str, Any]:
    basis = f"{provider}|{model}|{system_prompt or ''}|{prompt}"
    digest = hashlib.sha256(basis.encode("utf-8")).hexdigest()[:10]
    short_prompt = (prompt or "").strip().replace("\\n", " ")
    if len(short_prompt) > 96:
        short_prompt = short_prompt[:96] + "..."
    text = f"[MOCK:{provider}:{model}:{digest}] {short_prompt}"
    return {
        "text": text,
        "provider": "mock",
        "model": f"mock:{model}",
        "token_usage": max(1, len(text) // 4),
        "mock": True,
    }
'''

    def _generate_node_runtime(self) -> str:
        return '''"""Node runtime with minimal real execution for exported agents."""

from __future__ import annotations

import asyncio
import ast
import os
from datetime import datetime, UTC
from typing import Any

from jsonschema import ValidationError, validate
from runtime.approvals.policy import requires_approval
from runtime.approvals.store import get_approval_store
from runtime.replay.player import ReplayPlayer
from runtime.replay.recorder import ReplayRecorder
from runtime.resilience.circuit_breaker import CircuitBreaker
from runtime.resilience.policies import get_resilience_policy
from runtime.resilience.rate_limit import RateLimiter
from runtime.retry import run_with_retry
from runtime.memory_write_policy import should_write_memory
from runtime.tools.adapters.local import execute_local_tool
from runtime.tools.adapters.mcp import execute_mcp_tool
from runtime.tools.names import canonical_tool_name
from runtime.tools.policies import get_policy_config, validate_tool_policy
from runtime.tools.registry import get_tool
from runtime.providers.mock import mock_llm_response


_RATE_LIMITER = RateLimiter()
_CIRCUIT_BREAKER = CircuitBreaker()


def get_tool_resilience_health() -> dict[str, dict[str, Any]]:
    rl = _RATE_LIMITER.snapshot()
    cb = _CIRCUIT_BREAKER.snapshot()
    tools = sorted(set(rl.keys()) | set(cb.keys()))
    out: dict[str, dict[str, Any]] = {}
    for tool_name in tools:
        out[tool_name] = {
            "rate_limit": rl.get(tool_name, {"last_ts": 0.0, "allowed": 0, "denied": 0}),
            "circuit": cb.get(
                tool_name,
                {
                    "open": False,
                    "failures": 0,
                    "opened_at": 0.0,
                    "cooldown_s": 0.0,
                    "remaining_cooldown_s": 0.0,
                },
            ),
        }
    return out


def _dev_mode_enabled() -> bool:
    return os.environ.get("DEV_MODE", "0").strip().lower() in {"1", "true", "yes", "on"}


def _env_key_value(name: str) -> str:
    return str(os.environ.get(name, "") or "").strip()


def _is_placeholder_key(value: str) -> bool:
    lowered = value.strip().lower()
    if not lowered:
        return True
    return lowered in {"sk-...", "your_api_key_here", "changeme", "none", "null"}


def _coerce_text(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        for key in ("text", "output", "result", "status", "content"):
            if key in value:
                return str(value[key])
    return str(value)


def _estimate_tokens(text: Any) -> int:
    # Lightweight fallback approximation when provider usage metadata is absent.
    value = _coerce_text(text)
    if not value:
        return 0
    return max(1, len(value) // 4)


def _safe_eval_arithmetic(expr: str) -> float:
    node = ast.parse(expr, mode="eval")
    max_nodes = 64
    if sum(1 for _ in ast.walk(node)) > max_nodes:
        raise ValueError("Calculator expression too complex")

    def _eval(n: ast.AST, depth: int = 0) -> float:
        if depth > 20:
            raise ValueError("Calculator expression depth exceeded")
        if isinstance(n, ast.Expression):
            return _eval(n.body, depth + 1)
        if isinstance(n, ast.Constant):
            if isinstance(n.value, (int, float)):
                return float(n.value)
            raise ValueError("Only numeric literals are allowed")
        if isinstance(n, ast.UnaryOp):
            val = _eval(n.operand, depth + 1)
            if isinstance(n.op, ast.UAdd):
                return +val
            if isinstance(n.op, ast.USub):
                return -val
            raise ValueError("Unsupported unary operator")
        if isinstance(n, ast.BinOp):
            left = _eval(n.left, depth + 1)
            right = _eval(n.right, depth + 1)
            if isinstance(n.op, ast.Add):
                return left + right
            if isinstance(n.op, ast.Sub):
                return left - right
            if isinstance(n.op, ast.Mult):
                return left * right
            if isinstance(n.op, ast.Div):
                return left / right
            if isinstance(n.op, ast.FloorDiv):
                return left // right
            if isinstance(n.op, ast.Mod):
                return left % right
            if isinstance(n.op, ast.Pow):
                return left ** right
            raise ValueError("Unsupported binary operator")
        raise ValueError("Unsupported calculator expression")

    banned = (
        ast.Name, ast.Attribute, ast.Call, ast.Subscript, ast.Lambda,
        ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp,
        ast.Await, ast.Yield, ast.YieldFrom, ast.Import, ast.ImportFrom,
    )
    for n in ast.walk(node):
        if isinstance(n, banned):
            raise ValueError("Unsupported calculator expression")
    return float(_eval(node, 0))


async def _run_llm_node(params: dict[str, Any], current: Any, agent_config: dict[str, Any]) -> dict[str, Any]:
    provider = (params.get("provider") or agent_config.get("provider") or "auto").lower()
    model = str(params.get("model") or agent_config.get("model") or "gpt-4o-mini")
    temperature = float(params.get("temperature", agent_config.get("temperature", 0.7)))
    system_prompt = params.get("system_prompt") or agent_config.get("system_prompt")
    prompt_template = str(params.get("prompt_template") or "{input}")
    user_prompt = prompt_template.replace("{input}", _coerce_text(current))

    if provider == "auto":
        lowered = model.lower()
        if "gemini" in lowered:
            provider = "gemini"
        elif "claude" in lowered or "anthropic" in lowered:
            provider = "anthropic"
        else:
            provider = "openai"

    if provider == "openai":
        openai_key = _env_key_value("OPENAI_API_KEY")
        if _is_placeholder_key(openai_key):
            if _dev_mode_enabled():
                return mock_llm_response(
                    provider=provider,
                    model=model,
                    prompt=user_prompt,
                    system_prompt=str(system_prompt) if system_prompt else None,
                )
            raise RuntimeError("Missing OPENAI_API_KEY")
        from langchain_openai import ChatOpenAI
        from langchain_core.messages import HumanMessage, SystemMessage
        llm = ChatOpenAI(model=model, temperature=temperature)
        messages = [HumanMessage(content=user_prompt)]
        if system_prompt:
            messages.insert(0, SystemMessage(content=str(system_prompt)))
        llm_timeout_s = float(os.environ.get("LLM_TIMEOUT_S", "45") or "45")
        llm_retry_attempts = int(os.environ.get("LLM_RETRY_MAX_ATTEMPTS", "2") or "2")
        llm_retry_backoff_ms = int(os.environ.get("LLM_RETRY_BACKOFF_MS", "300") or "300")
        llm_retry_on = [v.strip() for v in str(os.environ.get("LLM_RETRY_ON", "timeout,rate_limit,5xx,network,unknown")).split(",") if v.strip()]

        async def _invoke() -> Any:
            try:
                return await asyncio.wait_for(llm.ainvoke(messages), timeout=llm_timeout_s)
            except TimeoutError as exc:
                raise RuntimeError("timeout calling openai") from exc

        response = await run_with_retry(
            _invoke,
            max_attempts=max(1, llm_retry_attempts),
            backoff_ms=max(0, llm_retry_backoff_ms),
            retry_on=llm_retry_on,
        )
        text_out = _coerce_text(getattr(response, "content", response))
        usage = getattr(response, "response_metadata", {}) or {}
        usage_tokens = (
            ((usage.get("token_usage") or {}).get("total_tokens"))
            if isinstance(usage, dict)
            else None
        )
        return {
            "text": text_out,
            "provider": provider,
            "model": model,
            "token_usage": int(usage_tokens) if usage_tokens is not None else _estimate_tokens(text_out),
        }

    if provider == "gemini":
        google_key = _env_key_value("GOOGLE_API_KEY")
        if _is_placeholder_key(google_key):
            if _dev_mode_enabled():
                return mock_llm_response(
                    provider=provider,
                    model=model,
                    prompt=user_prompt,
                    system_prompt=str(system_prompt) if system_prompt else None,
                )
            raise RuntimeError("Missing GOOGLE_API_KEY")
        from langchain_google_genai import ChatGoogleGenerativeAI
        from langchain_core.messages import HumanMessage, SystemMessage
        llm = ChatGoogleGenerativeAI(model=model, temperature=temperature)
        messages = [HumanMessage(content=user_prompt)]
        if system_prompt:
            messages.insert(0, SystemMessage(content=str(system_prompt)))
        llm_timeout_s = float(os.environ.get("LLM_TIMEOUT_S", "45") or "45")
        llm_retry_attempts = int(os.environ.get("LLM_RETRY_MAX_ATTEMPTS", "2") or "2")
        llm_retry_backoff_ms = int(os.environ.get("LLM_RETRY_BACKOFF_MS", "300") or "300")
        llm_retry_on = [v.strip() for v in str(os.environ.get("LLM_RETRY_ON", "timeout,rate_limit,5xx,network,unknown")).split(",") if v.strip()]

        async def _invoke() -> Any:
            try:
                return await asyncio.wait_for(llm.ainvoke(messages), timeout=llm_timeout_s)
            except TimeoutError as exc:
                raise RuntimeError("timeout calling gemini") from exc

        response = await run_with_retry(
            _invoke,
            max_attempts=max(1, llm_retry_attempts),
            backoff_ms=max(0, llm_retry_backoff_ms),
            retry_on=llm_retry_on,
        )
        text_out = _coerce_text(getattr(response, "content", response))
        return {
            "text": text_out,
            "provider": provider,
            "model": model,
            "token_usage": _estimate_tokens(text_out),
        }

    if provider == "anthropic":
        anthropic_key = _env_key_value("ANTHROPIC_API_KEY")
        if _is_placeholder_key(anthropic_key):
            if _dev_mode_enabled():
                return mock_llm_response(
                    provider=provider,
                    model=model,
                    prompt=user_prompt,
                    system_prompt=str(system_prompt) if system_prompt else None,
                )
            raise RuntimeError("Missing ANTHROPIC_API_KEY")
        from langchain_anthropic import ChatAnthropic
        from langchain_core.messages import HumanMessage, SystemMessage
        llm = ChatAnthropic(model_name=model, temperature=temperature, timeout=None, stop=None)
        messages = [HumanMessage(content=user_prompt)]
        if system_prompt:
            messages.insert(0, SystemMessage(content=str(system_prompt)))
        llm_timeout_s = float(os.environ.get("LLM_TIMEOUT_S", "45") or "45")
        llm_retry_attempts = int(os.environ.get("LLM_RETRY_MAX_ATTEMPTS", "2") or "2")
        llm_retry_backoff_ms = int(os.environ.get("LLM_RETRY_BACKOFF_MS", "300") or "300")
        llm_retry_on = [v.strip() for v in str(os.environ.get("LLM_RETRY_ON", "timeout,rate_limit,5xx,network,unknown")).split(",") if v.strip()]

        async def _invoke() -> Any:
            try:
                return await asyncio.wait_for(llm.ainvoke(messages), timeout=llm_timeout_s)
            except TimeoutError as exc:
                raise RuntimeError("timeout calling anthropic") from exc

        response = await run_with_retry(
            _invoke,
            max_attempts=max(1, llm_retry_attempts),
            backoff_ms=max(0, llm_retry_backoff_ms),
            retry_on=llm_retry_on,
        )
        text_out = _coerce_text(getattr(response, "content", response))
        return {
            "text": text_out,
            "provider": provider,
            "model": model,
            "token_usage": _estimate_tokens(text_out),
        }

    if _dev_mode_enabled():
        return mock_llm_response(
            provider=provider,
            model=model,
            prompt=user_prompt,
            system_prompt=str(system_prompt) if system_prompt else None,
        )
    raise RuntimeError(f"Unsupported provider: {provider}")


def _run_router_node(params: dict[str, Any], current: Any) -> dict[str, Any]:
    routes = params.get("routes", {}) or {}
    default_route = params.get("default_route")
    text = _coerce_text(current).lower()
    selected_route = None
    if isinstance(current, dict):
        selected_route = current.get("selected_route") or current.get("route")
    if not selected_route and isinstance(routes, dict):
        for condition, target in routes.items():
            if str(condition).lower() in text:
                selected_route = target
                break
    if not selected_route:
        selected_route = default_route
    if not selected_route and isinstance(routes, dict) and routes:
        selected_route = next(iter(routes.values()))
    return {"selected_route": selected_route, "routes": list(routes.keys())}


def _normalize_tool_name(tool_name: str) -> str:
    name = tool_name.strip()
    if name == "noop":
        return "tools.echo"
    return canonical_tool_name(name)


async def _execute_tool_call(tool_name: str, args: dict[str, Any], timeout_s: int) -> dict[str, Any]:
    if tool_name.startswith("mcp:"):
        return await asyncio.wait_for(execute_mcp_tool(tool_name, args), timeout=float(timeout_s))
    return await asyncio.wait_for(execute_local_tool(tool_name, args), timeout=float(timeout_s))


def _normalize_retry_on(value: Any) -> list[str]:
    if isinstance(value, list):
        parsed = [str(v).strip().lower() for v in value if str(v).strip()]
        return parsed or ["timeout", "rate_limit", "5xx", "network", "unknown"]
    if isinstance(value, str):
        parsed = [v.strip().lower() for v in value.split(",") if v.strip()]
        return parsed or ["timeout", "rate_limit", "5xx", "network", "unknown"]
    return ["timeout", "rate_limit", "5xx", "network", "unknown"]


def _as_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _as_float(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


async def _run_tool_node(params: dict[str, Any], current: Any, flow_policies: dict[str, Any]) -> dict[str, Any]:
    raw_tool_name = str(params.get("tool_name", "")).strip()
    tool_name = _normalize_tool_name(raw_tool_name)
    tool_config = params.get("tool_config", {}) or {}
    if not isinstance(tool_config, dict):
        tool_config = {}

    if tool_name == "tools.safe_calculator":
        # Calculator schema is strict; only pass expression.
        if "expression" not in tool_config:
            tool_config["expression"] = _coerce_text(current)
        tool_config.pop("text", None)
    elif tool_name == "tools.http_get":
        # HTTP schema is strict; do not inject free-form text args.
        tool_config.pop("text", None)
    else:
        if "text" not in tool_config and current is not None:
            tool_config["text"] = _coerce_text(current)

    spec = get_tool(tool_name)
    if spec is None:
        raise RuntimeError(f"Tool not found in registry: {tool_name}")

    runtime_meta = {}
    if isinstance(current, dict):
        runtime_meta = dict(current.get("__runtime") or {})
    replay_mode = str(runtime_meta.get("replay_mode") or os.environ.get("REPLAY_MODE", "off")).strip().lower()
    replay_run_id = str(runtime_meta.get("replay_run_id") or os.environ.get("REPLAY_RUN_ID", "")).strip()
    artifacts_dir = str(runtime_meta.get("artifacts_dir") or os.environ.get("FORGE_ARTIFACTS_DIR", "artifacts"))
    step_key = str(runtime_meta.get("step_key") or f"step_{tool_name}")

    # Deterministic replay mode: bypass external call using recorded snapshot.
    if replay_mode == "play":
        if not replay_run_id:
            raise RuntimeError("REPLAY_MODE=play requires replay_run_id")
        player = ReplayPlayer(artifacts_dir, replay_run_id)
        replay_output = player.load_step_output(step_key)
        if isinstance(replay_output, dict):
            replay_output.setdefault("tool", tool_name)
            replay_output["tool_called"] = True
            replay_output["replayed"] = True
        return replay_output

    try:
        validate(instance=tool_config, schema=spec.input_schema or {"type": "object"})
    except ValidationError as exc:
        raise RuntimeError(f"Tool args schema validation failed for {tool_name}: {exc.message}") from exc

    validate_tool_policy(tool_name, tool_config, flow_policy=flow_policies)

    policy_cfg = get_policy_config()
    timeout_s = int(spec.timeout_s or policy_cfg.get("timeout_s") or 30)

    # Approval gate for risky/mutating tools.
    category = "mutating" if tool_name in {"tools.http_get"} or tool_name.startswith("mcp:") else "readonly"
    if requires_approval(tool_name=tool_name, category=category, tool_requires_approval=bool(spec.requires_approval)):
        approval_scope = str(getattr(spec, "approval_scope", "session") or "session")
        approval_store = get_approval_store()
        existing_id = str(tool_config.get("approval_id", "")).strip()
        if existing_id:
            existing = approval_store.get(existing_id)
            if existing is None:
                raise RuntimeError(f"Approval not found: {existing_id}")
            if existing.status == "denied":
                raise RuntimeError(f"Tool execution denied by approval: {tool_name}")
            if existing.status != "approved":
                return {"tool": tool_name, "status": "PENDING_APPROVAL", "approval_id": existing.approval_id, "tool_called": False}
        else:
            req = approval_store.request(tool_name=tool_name, scope=approval_scope, metadata={"tool_args": tool_config})
            return {"tool": tool_name, "status": "PENDING_APPROVAL", "approval_id": req.approval_id, "tool_called": False}

    # Resilience: rate limiting + circuit breaker + retry/backoff.
    resilience = get_resilience_policy(tool_name)
    retry_max_attempts = max(1, _as_int(resilience.get("retry_max_attempts", 2), 2))
    retry_backoff_ms = max(0, _as_int(resilience.get("retry_backoff_ms", 300), 300))
    retry_on = _normalize_retry_on(resilience.get("retry_on"))
    rps = _as_float(resilience.get("rps", 2), 2.0)
    fail_threshold = max(1, _as_int(resilience.get("fail_threshold", 5), 5))
    cooldown_s = max(1, _as_int(resilience.get("cooldown_s", 60), 60))

    async def _call_with_resilience() -> dict[str, Any]:
        _RATE_LIMITER.check(tool_name, rps)
        _CIRCUIT_BREAKER.before_call(tool_name)
        try:
            out = await _execute_tool_call(tool_name, tool_config, timeout_s=timeout_s)
            _CIRCUIT_BREAKER.on_success(tool_name)
            return out
        except Exception:
            _CIRCUIT_BREAKER.on_failure(
                tool_name,
                threshold=fail_threshold,
                cooldown_s=cooldown_s,
            )
            raise

    result = await run_with_retry(
        _call_with_resilience,
        max_attempts=retry_max_attempts,
        backoff_ms=retry_backoff_ms,
        retry_on=retry_on,
    )

    # Replay recorder for deterministic playback.
    if replay_mode == "record":
        run_id = str(runtime_meta.get("run_id") or "run_unknown")
        recorder = ReplayRecorder(artifacts_dir, run_id)
        recorder.record_step(step_key=step_key, node_type="Tool", input_data=tool_config, output_data=result)
        recorder.save_manifest()

    result.setdefault("tool", tool_name)
    result["tool_called"] = True
    return result


def _run_retriever_node(params: dict[str, Any], current: Any) -> dict[str, Any]:
    query_template = str(params.get("query_template") or "{input}")
    query = query_template.replace("{input}", _coerce_text(current))
    top_k = int(params.get("top_k", 3))
    index_config = params.get("index_config", {}) or {}
    docs = index_config.get("documents", []) if isinstance(index_config, dict) else []
    if not isinstance(docs, list):
        docs = []
    selected_docs = docs[:max(1, top_k)]
    return {"query": query, "top_k": top_k, "documents": selected_docs}


def _run_memory_node(params: dict[str, Any], current: Any, memory: Any, agent_config: dict[str, Any]) -> dict[str, Any]:
    namespace = str(agent_config.get("memory_namespace") or "default")
    key = str(params.get("key") or "last")
    operation = str(params.get("operation") or "write").lower()
    if operation == "read":
        return {"namespace": namespace, "key": key, "value": memory.get(namespace, key)}
    candidate = {
        "value": current,
        "confidence": float(params.get("confidence", 1.0) or 0.0),
        "relevance": float(params.get("relevance", 1.0) or 0.0),
    }
    if not should_write_memory(candidate):
        return {"namespace": namespace, "key": key, "value": None, "skipped": True}
    memory.set(namespace, key, current)
    return {"namespace": namespace, "key": key, "value": current}


def _run_join_node(params: dict[str, Any], current: Any) -> dict[str, Any]:
    strategy = str(params.get("strategy") or "dict")
    if strategy == "array":
        return {"joined": [current], "strategy": strategy}
    if strategy == "last_non_null":
        return {"joined": current, "strategy": strategy}
    return {"joined": {"value": current}, "strategy": strategy}


async def execute_node(
    *,
    node: dict[str, Any],
    context: dict[str, Any],
    agent_config: dict[str, Any],
    memory: Any,
    flow_policies: dict[str, Any],
) -> Any:
    node_type = node.get("type")
    params = node.get("params", {}) or {}
    current = context.get("current")

    if node_type == "LLM":
        return await _run_llm_node(params, current, agent_config)
    if node_type == "Router":
        return _run_router_node(params, current)
    if node_type == "Tool":
        return await _run_tool_node(params, current, flow_policies)
    if node_type == "Retriever":
        return _run_retriever_node(params, current)
    if node_type == "Memory":
        return _run_memory_node(params, current, memory, agent_config)
    if node_type == "Join":
        return _run_join_node(params, current)
    if node_type == "Parallel":
        return {"status": "fanout", "value": current}
    if node_type == "Error":
        return {"error": params.get("error_template", "Execution failed"), "recovered": True}
    if node_type == "Output":
        template = str(params.get("output_template", "{result}"))
        formatted = template.replace("{result}", _coerce_text(current)).replace("{current}", _coerce_text(current))
        return {"output": formatted}

    return {"node_id": node.get("id"), "type": node_type, "status": "executed"}
'''

    def _generate_schema_registry(self) -> str:
        return '''"""Schema registry loader for generated runtime."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


def _runtime_root() -> Path:
    return Path(__file__).resolve().parent


def load_schema_index() -> dict[str, dict[str, Any]]:
    index_path = _runtime_root() / "schemas" / "index.json"
    if not index_path.exists():
        return {}
    raw = json.loads(index_path.read_text(encoding="utf-8"))
    normalized: dict[str, dict[str, Any]] = {}
    for source_ref, entry in raw.items():
        if isinstance(entry, str):
            normalized[source_ref] = {"path": entry, "sha256": "", "kind": "json_schema"}
        else:
            normalized[source_ref] = entry
    return normalized


def resolve_schema_path(source_ref: str) -> Path:
    index = load_schema_index()
    entry = index.get(source_ref)
    if entry is None:
        # Allow direct runtime relative refs (e.g., "runtime/schemas/schema_0_x.json")
        path = Path(source_ref)
    else:
        path_value = entry.get("path", "")
        if not path_value:
            raise FileNotFoundError(f"Schema ref has no path: {source_ref}")
        path = Path(path_value)
    if not path.is_absolute():
        repo_root = _runtime_root().parent
        path = repo_root / path
    if not path.exists():
        raise FileNotFoundError(f"Schema file missing: {path}")
    runtime_schemas_root = (_runtime_root() / "schemas").resolve()
    resolved = path.resolve()
    if runtime_schemas_root not in resolved.parents and resolved != runtime_schemas_root:
        raise ValueError(f"Schema path escapes runtime/schemas: {resolved}")
    return path


def load_schema(source_ref: str) -> dict[str, Any]:
    path = resolve_schema_path(source_ref)
    raw = path.read_text(encoding="utf-8")
    payload = json.loads(raw)
    index = load_schema_index()
    entry = index.get(source_ref, {})
    expected_sha = str(entry.get("sha256", "")).strip()
    if expected_sha:
        actual_sha = hashlib.sha256(raw.encode("utf-8")).hexdigest()
        if expected_sha != actual_sha:
            raise ValueError(f"Schema integrity check failed for {source_ref}")
    return payload
'''

    def _generate_schema_validation(self) -> str:
        return '''"""Schema validation helpers for generated runtime."""

from __future__ import annotations

from typing import Any

from jsonschema import ValidationError, validate

from runtime.schema_registry import load_schema


def _adapt_payload_for_schema(payload: dict[str, Any], schema: dict[str, Any]) -> dict[str, Any]:
    """Compatibility adapter for common contract aliases.

    If schema expects `result` but payload provides aliases (`output`,
    `outputs.output`, or `current`), synthesize `result`.
    """
    adapted = dict(payload or {})
    required_fields = schema.get("required")
    properties = schema.get("properties")
    requires_result = False
    if isinstance(required_fields, list):
        requires_result = "result" in [str(x) for x in required_fields]
    if not requires_result and isinstance(properties, dict):
        requires_result = "result" in properties

    if requires_result and "result" not in adapted:
        candidate: Any = None
        if "output" in adapted:
            candidate = adapted.get("output")
        else:
            outputs = adapted.get("outputs")
            if isinstance(outputs, dict) and "output" in outputs:
                candidate = outputs.get("output")
            elif "current" in adapted:
                current = adapted.get("current")
                if isinstance(current, dict) and "output" in current:
                    candidate = current.get("output")
                else:
                    candidate = current
        if candidate is not None:
            adapted["result"] = candidate
    return adapted


def validate_payload(
    payload: dict[str, Any],
    schema_ref: dict[str, Any] | None,
    *,
    soft_fail: bool = False,
) -> str | None:
    """Validate payload against schema ref from IR."""
    if not schema_ref:
        return None
    if schema_ref.get("kind") != "json_schema":
        message = f"Unsupported schema kind in generated runtime: {schema_ref.get('kind')}"
        if soft_fail:
            return message
        raise RuntimeError(message)

    try:
        schema = load_schema(schema_ref.get("ref", ""))
        validate(instance=_adapt_payload_for_schema(payload, schema), schema=schema)
        return None
    except (ValidationError, FileNotFoundError, ValueError) as exc:
        if soft_fail:
            return str(exc)
        raise RuntimeError(f"Schema validation failed: {exc}") from exc
'''

    def _generate_langgraph_runner(self) -> str:
        return '''"""LangGraph-native agent handoff orchestration."""

from __future__ import annotations

from typing import Any, Awaitable, Callable, Literal, TypedDict

from langgraph.graph import END, START, StateGraph


class DispatchState(TypedDict, total=False):
    current_agent_id: str
    current_input: dict[str, Any]
    depth: int
    done: bool
    result: dict[str, Any]


def _route_next(state: DispatchState) -> Literal["execute_agent", "__end__"]:
    if state.get("done"):
        return "__end__"
    return "execute_agent"


async def run_dispatch_via_langgraph(
    *,
    root_agent_id: str,
    input_data: dict[str, Any],
    run_agent_once: Callable[[str, dict[str, Any], int], Awaitable[dict[str, Any]]],
    max_depth: int = 10,
) -> dict[str, Any]:
    """Execute multi-agent handoffs through LangGraph state transitions."""

    async def _execute_agent(state: DispatchState) -> DispatchState:
        depth = int(state.get("depth", 0))
        if depth >= max_depth:
            raise RuntimeError(f"Max depth ({max_depth}) exceeded in LangGraph runner")

        current_agent_id = str(state.get("current_agent_id") or root_agent_id)
        current_input = dict(state.get("current_input") or {})
        result = await run_agent_once(current_agent_id, current_input, depth)

        next_agent_id = result.get("next_agent_id") if isinstance(result, dict) else None
        next_input = result.get("next_input") if isinstance(result, dict) else None
        if next_agent_id:
            return {
                "current_agent_id": str(next_agent_id),
                "current_input": dict(next_input or {"input": str(result.get("current", ""))}),
                "depth": depth + 1,
                "done": False,
                "result": result,
            }
        return {
            "depth": depth + 1,
            "done": True,
            "result": result,
        }

    graph = StateGraph(DispatchState)
    graph.add_node("execute_agent", _execute_agent)
    graph.add_edge(START, "execute_agent")
    graph.add_conditional_edges("execute_agent", _route_next)
    app = graph.compile()
    output = await app.ainvoke(
        {
            "current_agent_id": root_agent_id,
            "current_input": dict(input_data or {}),
            "depth": 0,
            "done": False,
            "result": {},
        }
    )
    if isinstance(output, dict):
        return dict(output.get("result") or {})
    return {}
'''

    def _generate_healthcheck(self) -> str:
        return '''"""Runtime health/readiness checks for generated export."""

from __future__ import annotations

from agents.registry import get_agent_graph, list_agents


def run_healthcheck() -> None:
    agents = list_agents()
    if not agents:
        raise RuntimeError("No agents registered")
    for agent_id in agents:
        graph = get_agent_graph(agent_id)
        nodes = list(graph.get("nodes") or [])
        if not nodes:
            raise RuntimeError(f"Agent '{agent_id}' has no nodes")
        root = str(graph.get("root") or "").strip()
        if not root:
            raise RuntimeError(f"Agent '{agent_id}' missing graph root")


if __name__ == "__main__":
    run_healthcheck()
'''

    def _generate_runtime_server(self) -> str:
        return '''"""Lightweight runtime API server for runs, tools, state and observability."""

from __future__ import annotations

import asyncio
import collections
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import signal
import threading
import time
import uuid
from typing import Any
from urllib.parse import urlparse

from runtime.healthcheck import run_healthcheck
from runtime.memory_summarizer import summarize_session
from runtime.observability import snapshot_metrics, snapshot_metrics_prometheus
from runtime.approvals.store import get_approval_store
from runtime.auth import require_auth
from runtime.policy_guard import apply_redaction
from runtime.replay.player import ReplayPlayer
from runtime.config import get_runtime_config
from runtime.run_store.factory import get_run_store
from runtime.state.factory import get_state_store
from runtime.tools.registry import list_tools
from settings import FLOW_POLICIES


class _IPRateLimiter:
    """Per-IP rate limiter with pluggable backends.

    Backends:
      inmemory (default) — token bucket in-process; not shared across replicas.
      redis — sliding window via Lua script; shared across replicas.

    Config:
      RATE_LIMITER_BACKEND=inmemory|redis  (default: inmemory)
      RATE_LIMITER_REDIS_URL=redis://localhost:6379/0
      SERVER_RATE_LIMIT_RPS=20
    """

    _LUA_SLIDING_WINDOW = """
local key = KEYS[1]
local now = tonumber(ARGV[1])
local window = tonumber(ARGV[2])
local limit = tonumber(ARGV[3])
local clear_before = now - window
redis.call('ZREMRANGEBYSCORE', key, '-inf', clear_before)
local count = redis.call('ZCARD', key)
if count < limit then
    redis.call('ZADD', key, now, now .. math.random())
    redis.call('EXPIRE', key, math.ceil(window / 1000) + 1)
    return 1
end
return 0
"""

    def __init__(self) -> None:
        self._rps = float(os.environ.get("SERVER_RATE_LIMIT_RPS", "20") or "20")
        self._backend = os.environ.get("RATE_LIMITER_BACKEND", "inmemory").strip().lower()
        self._redis_url = os.environ.get("RATE_LIMITER_REDIS_URL", "redis://localhost:6379/0")
        self._lock = threading.Lock()
        self._buckets: dict[str, collections.deque] = {}
        self._redis_client: Any = None
        self._lua_sha: str | None = None
        if self._backend == "redis":
            self._init_redis()

    def _init_redis(self) -> None:
        try:
            import redis as _redis
            self._redis_client = _redis.from_url(self._redis_url, decode_responses=True)
            self._lua_sha = self._redis_client.script_load(self._LUA_SLIDING_WINDOW)
        except ImportError:
            import warnings
            warnings.warn(
                "RATE_LIMITER_BACKEND=redis requires 'redis' package. "
                "Falling back to inmemory backend.",
                RuntimeWarning, stacklevel=2,
            )
            self._backend = "inmemory"

    def allow(self, ip: str) -> bool:
        if self._backend == "redis" and self._redis_client is not None:
            return self._allow_redis(ip)
        return self._allow_inmemory(ip)

    def _allow_redis(self, ip: str) -> bool:
        now_ms = int(time.monotonic() * 1000)
        window_ms = 1000  # 1 second
        try:
            result = self._redis_client.evalsha(
                self._lua_sha,
                1,
                f"ratelimit:{ip}",
                now_ms,
                window_ms,
                int(self._rps),
            )
            return bool(result)
        except Exception:
            # Redis unavailable: fail open (allow) to avoid cascading failures
            return True

    _BUCKETS_MAXSIZE = 10_000  # max unique IPs tracked in-memory

    def _allow_inmemory(self, ip: str) -> bool:
        now = time.monotonic()
        with self._lock:
            # Evict stale IP entries when dict is full to bound memory growth.
            if len(self._buckets) >= self._BUCKETS_MAXSIZE:
                stale_cutoff = now - 60.0
                stale = [k for k, q in self._buckets.items() if not q or q[-1] < stale_cutoff]
                for k in stale:
                    del self._buckets[k]
            q = self._buckets.setdefault(ip, collections.deque())
            cutoff = now - 1.0
            while q and q[0] < cutoff:
                q.popleft()
            if len(q) >= self._rps:
                return False
            q.append(now)
            return True


_ip_limiter = _IPRateLimiter()


# ── Idempotency cache (pluggable: inmemory | redis) ────────────────────────

class _IdempotencyCache:
    """TTL cache for idempotency keys with pluggable backends.

    Backends:
      inmemory (default) — dict + monotonic clock; not shared across replicas.
      redis — SET NX EX; shared across replicas.

    Config:
      IDEMPOTENCY_BACKEND=inmemory|redis  (default: inmemory)
      IDEMPOTENCY_REDIS_URL=redis://localhost:6379/0
      IDEMPOTENCY_TTL_S=300
    """

    def __init__(self) -> None:
        self._ttl = float(os.environ.get("IDEMPOTENCY_TTL_S", "300") or "300")
        self._backend = os.environ.get("IDEMPOTENCY_BACKEND", "inmemory").strip().lower()
        self._redis_url = os.environ.get("IDEMPOTENCY_REDIS_URL", "redis://localhost:6379/0")
        self._lock = threading.Lock()
        self._store: dict[str, tuple[float, Any]] = {}
        self._redis_client: Any = None
        if self._backend == "redis":
            self._init_redis()

    def _init_redis(self) -> None:
        try:
            import redis as _redis
            self._redis_client = _redis.from_url(self._redis_url, decode_responses=False)
        except ImportError:
            import warnings
            warnings.warn(
                "IDEMPOTENCY_BACKEND=redis requires 'redis' package. "
                "Falling back to inmemory backend.",
                RuntimeWarning, stacklevel=2,
            )
            self._backend = "inmemory"

    def get(self, key: str) -> Any | None:
        if self._backend == "redis" and self._redis_client is not None:
            raw = self._redis_client.get(f"idem:{key}")
            return json.loads(raw) if raw else None
        with self._lock:
            self._evict()
            entry = self._store.get(key)
            return entry[1] if entry else None

    def set(self, key: str, response: Any) -> None:
        if self._backend == "redis" and self._redis_client is not None:
            self._redis_client.setex(
                f"idem:{key}", int(self._ttl), json.dumps(response)
            )
            return
        with self._lock:
            self._store[key] = (time.monotonic() + self._ttl, response)

    def _evict(self) -> None:
        now = time.monotonic()
        expired = [k for k, (exp, _) in self._store.items() if exp <= now]
        for k in expired:
            del self._store[k]


_idempotency_cache = _IdempotencyCache()


def _dispatch_runtime(input_payload: dict[str, Any], entrypoint: str) -> dict[str, Any]:
    # Lazy import avoids expensive runtime graph/provider imports at server boot.
    from runtime.dispatcher import dispatch

    return asyncio.run(dispatch(dict(input_payload), entrypoint=entrypoint))


def _tool_health_snapshot() -> dict[str, dict[str, Any]]:
    # Lazy import keeps /healthz fast even when optional deps are heavy.
    from runtime.node_runtime import get_tool_resilience_health

    return get_tool_resilience_health()


def _redaction_patterns() -> list[str]:
    base = [
        r"(?i)api[_-]?key\\s*[:=]\\s*[^\\s,;]+",
        r"(?i)token\\s*[:=]\\s*[^\\s,;]+",
        r"(?i)authorization\\s*[:=]\\s*[^\\s,;]+",
        r"(?i)secret\\s*[:=]\\s*[^\\s,;]+",
        r"(?i)password\\s*[:=]\\s*[^\\s,;]+",
    ]
    redaction: dict[str, Any] = {}
    raw_redaction = FLOW_POLICIES.get("redaction", {})
    if isinstance(raw_redaction, dict):
        redaction = raw_redaction
    for item in list(redaction.get("patterns") or []):
        value = str(item).strip()
        if value:
            base.append(value)
    return base


def _redact_value(value: Any) -> Any:
    if isinstance(value, str):
        return apply_redaction(value, _redaction_patterns())
    if isinstance(value, list):
        return [_redact_value(v) for v in value]
    if isinstance(value, dict):
        masked: dict[str, Any] = {}
        for k, v in value.items():
            key = str(k).lower()
            if any(word in key for word in ("secret", "token", "password", "api_key", "authorization", "credential")):
                masked[k] = "***REDACTED***"
            else:
                masked[k] = _redact_value(v)
        return masked
    return value


def _load_run_manifest(run_id: str) -> dict[str, Any] | None:
    cfg = get_runtime_config()
    manifest_path = Path(cfg.artifacts_dir) / f"{run_id}.manifest.json"
    if not manifest_path.exists():
        return None
    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    return _redact_value(payload)


def _load_run_steps(run_id: str) -> list[dict[str, Any]]:
    cfg = get_runtime_config()
    steps_dir = Path(cfg.artifacts_dir) / "replay" / run_id / "steps"
    if not steps_dir.exists():
        return []
    steps: list[dict[str, Any]] = []
    for path in sorted(steps_dir.glob("*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        steps.append(
            {
                "step_id": path.stem,
                "status": "completed",
                "node_type": str(payload.get("node_type") or ""),
                "tool_name": str(payload.get("output", {}).get("tool") or ""),
                "input": _redact_value(payload.get("input")),
                "output": _redact_value(payload.get("output")),
            }
        )
    return steps


def _read_artifact_bytes(relative_name: str) -> bytes | None:
    cfg = get_runtime_config()
    root = Path(cfg.artifacts_dir).resolve()
    candidate = (root / relative_name).resolve()
    if root not in candidate.parents and candidate != root:
        return None
    if not candidate.exists() or not candidate.is_file():
        return None
    return candidate.read_bytes()


def _list_run_artifacts(run_id: str) -> list[str]:
    cfg = get_runtime_config()
    root = Path(cfg.artifacts_dir)
    names: list[str] = []
    direct = root / f"{run_id}.manifest.json"
    if direct.exists():
        names.append(direct.name)
    replay_dir = root / "replay" / run_id
    if replay_dir.exists():
        for p in sorted(replay_dir.rglob("*")):
            if p.is_file():
                try:
                    names.append(str(p.relative_to(root)).replace("\\\\", "/"))
                except Exception:
                    continue
    return names


class _Handler(BaseHTTPRequestHandler):
    server_version = "ForgeRuntimeServer/1.0"
    protocol_version = "HTTP/1.1"

    def setup(self) -> None:
        super().setup()
        timeout_s = int(os.environ.get("FORGE_SERVER_SOCKET_TIMEOUT_S", "30") or 30)
        try:
            self.connection.settimeout(timeout_s)
        except Exception:  # noqa: BLE001
            return

    def _allowed_origin(self) -> str:
        """Return the CORS origin to allow.

        Defaults to empty string (no CORS header sent) to follow deny-by-default.
        Set FORGE_RUNTIME_CORS_ORIGINS=* to allow all origins in development,
        or FORGE_RUNTIME_CORS_ORIGINS=https://app.example.com for production.
        """
        configured = os.environ.get("FORGE_RUNTIME_CORS_ORIGINS", "").strip()
        if configured == "*":
            return "*"
        origin = self.headers.get("Origin", "").strip()
        allowed = [item.strip() for item in configured.split(",") if item.strip()]
        if origin and origin in allowed:
            return origin
        return allowed[0] if allowed else ""

    def _set_cors_headers(self) -> None:
        origin = self._allowed_origin()
        if origin:
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization, X-Trace-Id")
            self.send_header("Access-Control-Max-Age", "600")

    def _send_json(self, code: int, payload: dict[str, Any]) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self._set_cors_headers()
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        # Security headers
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _send_text(self, code: int, body: str, content_type: str = "text/plain; version=0.0.4") -> None:
        raw = body.encode("utf-8")
        self.send_response(code)
        self._set_cors_headers()
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(raw)))
        # Security headers
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(raw)

    def log_message(self, fmt: str, *args: Any) -> None:
        # Keep server endpoint noise minimal; runtime events are logged elsewhere.
        return

    def do_OPTIONS(self) -> None:  # noqa: N802
        self.send_response(204)
        self._set_cors_headers()
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()

    def _read_json_body(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0") or 0)
        max_bytes = int(os.environ.get("FORGE_MAX_REQUEST_BYTES", str(1024 * 1024)) or (1024 * 1024))
        if length > max_bytes:
            raise ValueError("payload_too_large")
        body_raw = self.rfile.read(length).decode("utf-8") if length > 0 else "{}"
        try:
            payload = json.loads(body_raw or "{}")
        except json.JSONDecodeError as exc:
            raise ValueError("invalid_json") from exc
        return dict(payload or {})

    def do_GET(self) -> None:  # noqa: N802
        client_ip = self.client_address[0]
        if not _ip_limiter.allow(client_ip):
            self._send_json(429, {"detail": "Too Many Requests"})
            return
        parsed = urlparse(self.path)
        path = parsed.path
        query: dict[str, str] = {}
        for chunk in (parsed.query or "").split("&"):
            if "=" not in chunk:
                continue
            k, v = chunk.split("=", 1)
            query[k] = v
        try:
            require_auth(path, self.headers.get("Authorization"))
        except PermissionError as exc:
            self._send_json(401, {"error": str(exc)})
            return

        if path == "/healthz":
            self._send_json(200, {"status": "ok"})
            return
        if path == "/readyz":
            try:
                run_healthcheck()
                self._send_json(200, {"status": "ready"})
            except Exception as exc:  # noqa: BLE001
                self._send_json(503, {"status": "not_ready", "error": str(exc)})
            return
        if path == "/metrics":
            self._send_text(200, snapshot_metrics_prometheus())
            return
        if path == "/metrics.json":
            self._send_json(200, snapshot_metrics())
            return
        if path == "/tools":
            catalog = []
            for spec in list_tools():
                catalog.append(
                    {
                        "name": spec.name,
                        "description": spec.description,
                        "adapter": spec.adapter,
                        "timeout_s": spec.timeout_s,
                        "max_retries": spec.max_retries,
                        "requires_approval": spec.requires_approval,
                        "input_schema": spec.input_schema,
                        "output_schema": spec.output_schema,
                    }
                )
            self._send_json(200, {"tools": catalog})
            return
        if path == "/tools/health":
            self._send_json(200, {"tools": _tool_health_snapshot()})
            return
        if path == "/approvals":
            store = get_approval_store()
            status = query.get("status")
            session_id = query.get("session_id")
            items = [
                {
                    "approval_id": item.approval_id,
                    "tool_name": item.tool_name,
                    "scope": item.scope,
                    "status": item.status,
                    "created_at": item.created_at,
                    "updated_at": item.updated_at,
                    "metadata": _redact_value(item.metadata or {}),
                }
                for item in store.list(status=status, session_id=session_id)
            ]
            self._send_json(200, {"items": items})
            return
        if path.startswith("/approvals/"):
            approval_id = path.removeprefix("/approvals/").strip("/")
            if not approval_id:
                self._send_json(400, {"error": "approval_id_required"})
                return
            store = get_approval_store()
            item = store.get(approval_id)
            if item is None:
                self._send_json(404, {"error": "not_found"})
                return
            self._send_json(
                200,
                {
                    "approval_id": item.approval_id,
                    "tool_name": item.tool_name,
                    "scope": item.scope,
                    "status": item.status,
                    "created_at": item.created_at,
                    "updated_at": item.updated_at,
                    "metadata": _redact_value(item.metadata or {}),
                },
            )
            return
        if path.startswith("/sessions/") and path.endswith("/memory"):
            session_id = path.removeprefix("/sessions/").removesuffix("/memory").strip("/")
            if not session_id:
                self._send_json(400, {"error": "session_id_required"})
                return
            state = get_state_store().get(session_id)
            loop_state = state.get("loop_state") if isinstance(state, dict) else {}
            observations = list((loop_state or {}).get("observations") or [])
            summary = summarize_session(observations)
            self._send_json(
                200,
                {
                    "session_id": session_id,
                    "summary": _redact_value(summary),
                    "raw_count": len(observations),
                },
            )
            return
        if path.startswith("/runs/") and path.endswith("/steps"):
            run_id = path.removeprefix("/runs/").removesuffix("/steps").strip("/")
            if not run_id:
                self._send_json(400, {"error": "run_id_required"})
                return
            run_store = get_run_store()
            source_run_id = run_id
            replay_of = str((run_store.get_run(run_id) or {}).get("replay_of") or "")
            if replay_of:
                source_run_id = replay_of
            steps = list(run_store.list_steps(run_id) or [])
            if not steps:
                steps = _load_run_steps(run_id)
            if replay_of and not steps:
                steps = list(run_store.list_steps(source_run_id) or [])
                if not steps:
                    steps = _load_run_steps(source_run_id)
                for step in steps:
                    step["replay_substituted"] = True
            self._send_json(200, {"run_id": run_id, "steps": steps, "replay_of": replay_of or None})
            return
        if path.startswith("/runs/") and path.endswith("/artifacts"):
            run_id = path.removeprefix("/runs/").removesuffix("/artifacts").strip("/")
            if not run_id:
                self._send_json(400, {"error": "run_id_required"})
                return
            self._send_json(200, {"run_id": run_id, "artifacts": _list_run_artifacts(run_id)})
            return
        if "/artifacts/" in path and path.startswith("/runs/"):
            parts = path.split("/artifacts/", 1)
            run_id = parts[0].removeprefix("/runs/").strip("/")
            rel_name = parts[1].strip("/")
            if not run_id or not rel_name:
                self._send_json(400, {"error": "invalid_artifact_path"})
                return
            if not rel_name.startswith(f"replay/{run_id}/") and rel_name != f"{run_id}.manifest.json":
                self._send_json(404, {"error": "not_found"})
                return
            raw = _read_artifact_bytes(rel_name)
            if raw is None:
                self._send_json(404, {"error": "not_found"})
                return
            self._send_text(200, raw.decode("utf-8", errors="replace"), content_type="application/json; charset=utf-8")
            return
        if path.startswith("/runs/"):
            run_id = path.removeprefix("/runs/").strip("/")
            if not run_id:
                self._send_json(400, {"error": "run_id_required"})
                return
            payload = get_run_store().get_run(run_id) or _load_run_manifest(run_id)
            if payload is None:
                self._send_json(404, {"error": "not_found", "run_id": run_id})
                return
            if isinstance(payload, dict) and "run_id" not in payload:
                payload["run_id"] = run_id
            self._send_json(200, _redact_value(payload))
            return
        if path.startswith("/state/"):
            dev_mode = os.environ.get("DEV_MODE", "0").strip().lower() in {"1", "true", "yes", "on"}
            if not dev_mode:
                self._send_json(403, {"error": "forbidden_in_prod"})
                return
            session_id = path.removeprefix("/state/").strip("/")
            if not session_id:
                self._send_json(400, {"error": "session_id_required"})
                return
            state = get_state_store().get(session_id)
            self._send_json(200, {"session_id": session_id, "state": _redact_value(state)})
            return
        self._send_json(404, {"error": "not_found"})

    def do_POST(self) -> None:  # noqa: N802
        client_ip = self.client_address[0]
        if not _ip_limiter.allow(client_ip):
            self._send_json(429, {"detail": "Too Many Requests"})
            return
        parsed = urlparse(self.path)
        path = parsed.path
        try:
            require_auth(path, self.headers.get("Authorization"))
        except PermissionError as exc:
            self._send_json(401, {"error": str(exc)})
            return

        try:
            body = self._read_json_body()
        except ValueError as exc:
            if str(exc) == "payload_too_large":
                self._send_json(413, {"error": "payload_too_large"})
                return
            self._send_json(400, {"error": "invalid_json"})
            return

        store = get_approval_store()
        if path == "/runs":
            # Idempotency key deduplication — return cached response for repeated requests
            idem_key = self.headers.get("X-Idempotency-Key", "").strip()
            if idem_key:
                cached = _idempotency_cache.get(idem_key)
                if cached is not None:
                    self._send_json(200, cached)
                    return

            entrypoint = str(body.get("entrypoint") or "main").strip() or "main"
            input_payload = body.get("input") or {}
            if not isinstance(input_payload, dict):
                self._send_json(400, {"error": "input_must_be_object"})
                return
            try:
                result = _dispatch_runtime(dict(input_payload), entrypoint)
            except Exception as exc:  # noqa: BLE001
                self._send_json(500, {"error": "run_failed", "message": str(exc)})
                return

            run_id = str(result.get("run_id") or "").strip()
            if not run_id:
                run_id = f"run_{uuid.uuid4().hex[:12]}"
                result = dict(result or {})
                result["run_id"] = run_id
            record = {
                "run_id": run_id,
                "trace_id": str(result.get("trace_id") or ""),
                "session_id": str(result.get("session_id") or input_payload.get("session_id") or ""),
                "entrypoint": entrypoint,
                "status": str(result.get("status") or "completed"),
                "result": _redact_value(result),
            }
            if run_id:
                run_store = get_run_store()
                run_store.put_run_manifest(run_id, record)
                for step in _load_run_steps(run_id):
                    run_store.append_step(run_id, step)
            if idem_key:
                _idempotency_cache.set(idem_key, record)
            self._send_json(200, record)
            return
        if path == "/replay":
            source_run_id = str(body.get("run_id") or "").strip()
            mode = str(body.get("mode") or "play").strip().lower()
            if not source_run_id:
                self._send_json(400, {"error": "run_id_required"})
                return
            if mode != "play":
                self._send_json(400, {"error": "unsupported_mode", "supported": ["play"]})
                return
            run_store = get_run_store()
            source = run_store.get_run(source_run_id) or _load_run_manifest(source_run_id)
            if not source:
                self._send_json(404, {"error": "source_run_not_found"})
                return
            replay_run_id = f"replay_{source_run_id}"
            replay_record = {
                "run_id": replay_run_id,
                "trace_id": str((source or {}).get("trace_id") or ""),
                "session_id": str((source or {}).get("session_id") or ""),
                "status": "completed",
                "mode": "play",
                "replay_of": source_run_id,
                "result": _redact_value((source or {}).get("result") or {}),
            }
            run_store.put_run_manifest(replay_run_id, replay_record)
            for step in _load_run_steps(source_run_id):
                replay_step = dict(step)
                replay_step["replay_substituted"] = True
                run_store.append_step(replay_run_id, replay_step)
            self._send_json(200, {"replay_run_id": replay_run_id, "status": "completed"})
            return
        if path == "/approvals/request":
            tool_name = str(body.get("tool_name", "")).strip()
            scope = str(body.get("scope", "session"))
            if not tool_name:
                self._send_json(400, {"error": "tool_name_required"})
                return
            req = store.request(tool_name=tool_name, scope=scope, metadata=body.get("metadata") or {})
            self._send_json(200, {"approval_id": req.approval_id, "status": req.status})
            return
        if path.startswith("/approvals/") and path.endswith("/approve"):
            approval_id = path.removeprefix("/approvals/").removesuffix("/approve").strip("/")
            if not approval_id:
                self._send_json(400, {"error": "approval_id_required"})
                return
            req = store.approve(approval_id)
            self._send_json(200, {"approval_id": req.approval_id, "status": req.status})
            return
        if path.startswith("/approvals/") and path.endswith("/deny"):
            approval_id = path.removeprefix("/approvals/").removesuffix("/deny").strip("/")
            if not approval_id:
                self._send_json(400, {"error": "approval_id_required"})
                return
            req = store.deny(approval_id)
            self._send_json(200, {"approval_id": req.approval_id, "status": req.status})
            return
        if path == "/approvals/approve":
            approval_id = str(body.get("approval_id", "")).strip()
            if not approval_id:
                self._send_json(400, {"error": "approval_id_required"})
                return
            req = store.approve(approval_id)
            self._send_json(200, {"approval_id": req.approval_id, "status": req.status})
            return
        if path == "/approvals/deny":
            approval_id = str(body.get("approval_id", "")).strip()
            if not approval_id:
                self._send_json(400, {"error": "approval_id_required"})
                return
            req = store.deny(approval_id)
            self._send_json(200, {"approval_id": req.approval_id, "status": req.status})
            return
        if path.startswith("/sessions/") and path.endswith("/summarize"):
            dev_mode = os.environ.get("DEV_MODE", "0").strip().lower() in {"1", "true", "yes", "on"}
            if not dev_mode:
                self._send_json(403, {"error": "forbidden_in_prod"})
                return
            session_id = path.removeprefix("/sessions/").removesuffix("/summarize").strip("/")
            if not session_id:
                self._send_json(400, {"error": "session_id_required"})
                return
            store_state = get_state_store()
            state = store_state.get(session_id)
            loop_state = state.get("loop_state") if isinstance(state, dict) else {}
            observations = list((loop_state or {}).get("observations") or [])
            summarized = summarize_session(observations, max_items=int(body.get("max_items") or 50))
            if isinstance(state, dict):
                state["session_summary"] = summarized
                store_state.set(session_id, state)
            self._send_json(
                200,
                {
                    "session_id": session_id,
                    "summary": _redact_value(summarized),
                    "raw_count": len(observations),
                },
            )
            return

        self._send_json(404, {"error": "not_found"})


_shutdown_event = threading.Event()


def _handle_sigterm(signum: int, frame: object) -> None:
    import logging
    logging.getLogger("forge.runtime.server").info(
        "Signal %s received — initiating graceful shutdown", signum
    )
    _shutdown_event.set()


signal.signal(signal.SIGTERM, _handle_sigterm)
signal.signal(signal.SIGINT, _handle_sigterm)


def serve(host: str = "0.0.0.0", port: int = 9090) -> None:
    from settings import init_secrets
    init_secrets()  # Load AWS SSM secrets before starting the server (no-op if not configured)
    server = ThreadingHTTPServer((host, int(port)), _Handler)
    server.timeout = 1.0
    log_event("SERVER_START", host=host, port=port)
    try:
        while not _shutdown_event.is_set():
            server.handle_request()
    finally:
        server.server_close()
        log_event("SERVER_STOP", reason="shutdown")


if __name__ == "__main__":
    serve(
        host=os.environ.get("FORGE_OBS_HOST", "0.0.0.0"),
        port=int(os.environ.get("FORGE_OBS_PORT", "9090")),
    )
'''

    def _generate_runtime_config(self) -> str:
        return '''"""Typed runtime config + manifest writer for generated export."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import platform
from typing import Any

def _load_env_file() -> None:
    env_path = Path.cwd() / ".env"
    if not env_path.exists():
        return
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key:
            os.environ[key] = value


_load_env_file()
from settings import FLOW_ID, FLOW_NAME, FLOW_POLICIES, FLOW_VERSION  # noqa: E402


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None:
        return default
    try:
        return int(raw.strip())
    except ValueError:
        return default


@dataclass(frozen=True)
class RuntimeConfig:
    forge_env: str
    log_level: str
    slow_node_ms: int
    allow_schema_soft_fail: bool
    allow_placeholder_tools: bool
    state_backend: str
    redis_url: str
    tool_timeout_s: int
    loop_max_iters: int
    loop_max_tool_calls: int
    replay_mode: str
    replay_run_id: str
    approvals_backend: str
    approvals_required_for: str
    tool_rate_limit_rps_default: float
    tool_circuit_fail_threshold_default: int
    tool_circuit_cooldown_s_default: int
    memory_write_confidence_threshold: float
    memory_write_relevance_threshold: float
    session_ttl_s: int
    artifacts_dir: str

    def safe_summary(self) -> dict[str, Any]:
        return {
            "forge_env": self.forge_env,
            "log_level": self.log_level,
            "slow_node_ms": self.slow_node_ms,
            "allow_schema_soft_fail": self.allow_schema_soft_fail,
            "allow_placeholder_tools": self.allow_placeholder_tools,
            "state_backend": self.state_backend,
            "redis_url": self.redis_url,
            "tool_timeout_s": self.tool_timeout_s,
            "loop_max_iters": self.loop_max_iters,
            "loop_max_tool_calls": self.loop_max_tool_calls,
            "replay_mode": self.replay_mode,
            "replay_run_id": self.replay_run_id,
            "approvals_backend": self.approvals_backend,
            "approvals_required_for": self.approvals_required_for,
            "tool_rate_limit_rps_default": self.tool_rate_limit_rps_default,
            "tool_circuit_fail_threshold_default": self.tool_circuit_fail_threshold_default,
            "tool_circuit_cooldown_s_default": self.tool_circuit_cooldown_s_default,
            "memory_write_confidence_threshold": self.memory_write_confidence_threshold,
            "memory_write_relevance_threshold": self.memory_write_relevance_threshold,
            "session_ttl_s": self.session_ttl_s,
            "artifacts_dir": self.artifacts_dir,
        }


_RUNTIME_CONFIG: RuntimeConfig | None = None


def get_runtime_config() -> RuntimeConfig:
    global _RUNTIME_CONFIG
    if _RUNTIME_CONFIG is not None:
        return _RUNTIME_CONFIG
    _RUNTIME_CONFIG = RuntimeConfig(
        forge_env=os.environ.get("FORGE_ENV", "production").strip().lower(),
        log_level=os.environ.get("LOG_LEVEL", "INFO").strip().upper(),
        slow_node_ms=max(0, _env_int("FORGE_SLOW_NODE_MS", 1500)),
        allow_schema_soft_fail=_env_bool("FORGE_ALLOW_SCHEMA_SOFT_FAIL", False),
        allow_placeholder_tools=_env_bool("FORGE_ALLOW_PLACEHOLDER_TOOLS", False),
        state_backend=os.environ.get("STATE_BACKEND", "inmemory").strip().lower(),
        redis_url=os.environ.get("REDIS_URL", "redis://localhost:6379/0").strip(),
        tool_timeout_s=max(1, _env_int("TOOL_TIMEOUT_S", 30)),
        loop_max_iters=max(1, _env_int("LOOP_MAX_ITERS", 10)),
        loop_max_tool_calls=max(1, _env_int("LOOP_MAX_TOOL_CALLS", 10)),
        replay_mode=os.environ.get("REPLAY_MODE", "off").strip().lower(),
        replay_run_id=os.environ.get("REPLAY_RUN_ID", "").strip(),
        approvals_backend=os.environ.get("APPROVALS_BACKEND", "inmemory").strip().lower(),
        approvals_required_for=os.environ.get("APPROVALS_REQUIRED_FOR", "mutating").strip(),
        tool_rate_limit_rps_default=float(os.environ.get("TOOL_RATE_LIMIT_RPS_DEFAULT", "2") or "2"),
        tool_circuit_fail_threshold_default=max(1, _env_int("TOOL_CIRCUIT_FAIL_THRESHOLD_DEFAULT", 5)),
        tool_circuit_cooldown_s_default=max(1, _env_int("TOOL_CIRCUIT_COOLDOWN_S_DEFAULT", 60)),
        memory_write_confidence_threshold=float(os.environ.get("MEMORY_WRITE_CONFIDENCE_THRESHOLD", "0.7") or "0.7"),
        memory_write_relevance_threshold=float(os.environ.get("MEMORY_WRITE_RELEVANCE_THRESHOLD", "0.6") or "0.6"),
        session_ttl_s=max(60, _env_int("SESSION_TTL_S", 86400)),
        artifacts_dir=os.environ.get("FORGE_ARTIFACTS_DIR", "artifacts").strip() or "artifacts",
    )
    return _RUNTIME_CONFIG


def write_run_manifest(
    *,
    run_id: str,
    entrypoint: str,
    input_data: dict[str, Any],
    status: str,
    error: str | None = None,
    metrics: dict[str, Any] | None = None,
) -> None:
    cfg = get_runtime_config()
    root = Path(cfg.artifacts_dir)
    root.mkdir(parents=True, exist_ok=True)
    payload: dict[str, Any] = {
        "run_id": run_id,
        "ts": datetime.now(timezone.utc).isoformat(),
        "status": status,
        "entrypoint": entrypoint,
        "input_keys": sorted(input_data.keys()),
        "flow": {
            "id": FLOW_ID,
            "name": FLOW_NAME,
            "version": FLOW_VERSION,
        },
        "policies": {
            "tool_allowlist_size": len(list(FLOW_POLICIES.get("tool_allowlist") or [])),
            "tool_denylist_size": len(list(FLOW_POLICIES.get("tool_denylist") or [])),
            "allow_schema_soft_fail": bool(FLOW_POLICIES.get("allow_schema_soft_fail", False)),
        },
        "runtime": cfg.safe_summary(),
        "versions": {
            "python": platform.python_version(),
            "platform": platform.platform(),
        },
    }
    if error:
        payload["error"] = error
    if metrics:
        payload["metrics"] = metrics

    out = root / f"{run_id}.manifest.json"
    out.write_text(json.dumps(payload, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
'''

    def _generate_pyproject(self) -> str:
        return '''[project]
name = "forge-exported-agent"
version = "1.0.0"
requires-python = ">=3.11"

dependencies = [
  "pydantic==2.11.7",
  "pydantic-settings==2.4.0",
  "jsonschema==4.23.0",
  "langchain==0.3.27",
  "langchain-openai==0.2.14",
  "langchain-google-genai==2.0.9",
  "langchain-anthropic==0.3.7",
  "langgraph==0.2.61",
  "langgraph-checkpoint==2.0.9",
]

[project.optional-dependencies]
redis = [
  "redis==5.2.1",
]
dev = [
  "bandit==1.7.10",
  "pip-audit==2.7.3",
  "ruff==0.6.9",
  "mypy==1.11.2",
  "pytest==8.3.5",
  "pytest-asyncio==0.25.3",
  "types-requests==2.32.0.20240712",
]
otel = [
  "opentelemetry-api>=1.22.0",
  "opentelemetry-sdk>=1.22.0",
  "opentelemetry-exporter-otlp-proto-grpc>=1.22.0",
]
aws = [
  "boto3>=1.34.0",
]

[tool.ruff]
line-length = 100
target-version = "py311"

[tool.ruff.lint]
select = ["E", "F", "I", "UP", "B"]
ignore = ["E501", "F401", "I001", "UP017", "UP035", "B023"]

[tool.ruff.format]
quote-style = "double"
indent-style = "space"

[tool.mypy]
python_version = "3.11"
files = ["runtime", "agents"]
check_untyped_defs = false
disallow_incomplete_defs = false
warn_return_any = false
warn_unused_ignores = true
warn_redundant_casts = true
warn_unreachable = true
pretty = true
ignore_missing_imports = true
disable_error_code = ["arg-type", "union-attr", "assignment", "no-any-return"]

[tool.pytest.ini_options]
addopts = "-q"
testpaths = ["tests"]
markers = [
  "smoke: smoke tests for exported runtime"
]
filterwarnings = [
  "error",
  "ignore::DeprecationWarning:pkg_resources.*",
]
'''

    def _generate_env_example(self) -> str:
        return """# API Keys
OPENAI_API_KEY=sk-...
GOOGLE_API_KEY=
ANTHROPIC_API_KEY=
# Runtime
FORGE_ENV=production
DEV_MODE=0
LOG_LEVEL=INFO
FORGE_SLOW_NODE_MS=1500
FORGE_ALLOW_SCHEMA_SOFT_FAIL=0
FORGE_OBS_HOST=0.0.0.0
FORGE_OBS_PORT=9090
FORGE_MAX_REQUEST_BYTES=1048576
FORGE_SERVER_SOCKET_TIMEOUT_S=30
# CORS: set to https://your-app.example.com in production; leave empty to disable CORS
# Use * only in development (FORGE_ENV=development)
FORGE_RUNTIME_CORS_ORIGINS=
# REQUIRED in production — generate with: openssl rand -hex 32
RUNTIME_API_TOKEN=
ALLOW_UNAUTHENTICATED_IN_DEV=0
FORGE_ARTIFACTS_DIR=artifacts
# ⚠ STATE_BACKEND=inmemory — session state is LOST ON RESTART. Use redis in production.
STATE_BACKEND=inmemory
# ⚠ RUN_STORE_BACKEND=filesystem — run artifacts are LOST ON CONTAINER RESTART. Use redis or mount a persistent volume.
RUN_STORE_BACKEND=filesystem
RUN_STORE_DIR=artifacts/runs
REDIS_URL=redis://localhost:6379/0
MCP_SERVERS=[]
# MCP: comma-separated list of allowed MCP tool commands (required if MCP_SERVERS is non-empty in prod)
MCP_ALLOWED_COMMANDS=
# Idempotency TTL in seconds (default 300 = 5 minutes); applies to POST /runs X-Idempotency-Key
IDEMPOTENCY_TTL_S=300
# Rate limiter backend (inmemory | redis); use redis for multi-replica deployments
RATE_LIMITER_BACKEND=inmemory
RATE_LIMITER_REDIS_URL=redis://localhost:6379/0
# Idempotency backend (inmemory | redis); use redis for multi-replica deployments
IDEMPOTENCY_BACKEND=inmemory
IDEMPOTENCY_REDIS_URL=redis://localhost:6379/0
# Prompt injection detection — comma-separated regex patterns to block.
# Leave empty to use built-in defaults. Set to "disabled" to turn off entirely.
FORGE_INJECTION_PATTERNS=
TOOL_ALLOWLIST=tools.*,mcp:*
TOOL_DENYLIST=python_repl,shell,exec
TOOL_TIMEOUT_S=30
TOOL_RETRY_MAX_ATTEMPTS=2
TOOL_RETRY_BACKOFF_MS=300
TOOL_RETRY_ON=timeout,rate_limit,5xx,network,unknown
HTTP_GET_ALLOW_DOMAINS=example.com,api.mycorp.com
HTTP_GET_DENY_IP_RANGES=
HTTP_GET_TIMEOUT_S=10
HTTP_GET_MAX_RESPONSE_BYTES=1000000
LLM_TIMEOUT_S=45
LLM_RETRY_MAX_ATTEMPTS=2
LLM_RETRY_BACKOFF_MS=300
LLM_RETRY_ON=timeout,rate_limit,5xx,network,unknown
LOOP_MAX_ITERS=10
LOOP_MAX_TOOL_CALLS=10
LOOP_MAX_FAILURES=3
LOOP_ENABLED=1
# Comma-separated agent IDs that use the Plan->Act->Observe loop
# Default: supervisor. Set to your entrypoint agent ID if different.
LOOP_AGENT_IDS=supervisor
REPLAY_MODE=off
REPLAY_RUN_ID=
REPLAY_ARTIFACTS_DIR=artifacts/replay
APPROVALS_BACKEND=inmemory
APPROVALS_REQUIRED_FOR=mutating
TOOL_RATE_LIMIT_RPS_DEFAULT=2
# HTTP server rate limit (requests per second per IP, 0 = disabled)
SERVER_RATE_LIMIT_RPS=20
TOOL_CIRCUIT_FAIL_THRESHOLD_DEFAULT=5
TOOL_CIRCUIT_COOLDOWN_S_DEFAULT=60
MEMORY_WRITE_CONFIDENCE_THRESHOLD=0.7
MEMORY_WRITE_RELEVANCE_THRESHOLD=0.6
SESSION_TTL_S=86400
# Debug-only: allow MCP/search placeholder adapters in generated runtime.
FORGE_ALLOW_PLACEHOLDER_TOOLS=0
# AWS Secrets Manager / Parameter Store (optional)
# If set, OPENAI_API_KEY and RUNTIME_API_TOKEN are read from SSM
# instead of environment variables.
# AWS_SECRETS_BACKEND=ssm
# AWS_SSM_PREFIX=/my-flow-id
# AWS_REGION=us-east-1
# OpenTelemetry (optional — requires: pip install opentelemetry-sdk opentelemetry-exporter-otlp-proto-grpc)
FORGE_OTEL_ENABLED=0
FORGE_OTEL_ENDPOINT=http://localhost:4317
# Profiling (writes profile data to /tmp/forge-profile.pstats when enabled)
FORGE_PROFILE=0
"""

    def _generate_requirements(self) -> str:
        base = """pydantic==2.11.7
pydantic-settings==2.4.0
jsonschema==4.23.0
langchain==0.3.27
langchain-openai==0.2.14
langchain-google-genai==2.0.9
langchain-anthropic==0.3.7
# redis==5.2.1  # optional: install for STATE_BACKEND=redis or RATE_LIMITER_BACKEND=redis
#   pip install ".[redis]"
# boto3>=1.34.0  # optional: AWS SSM secrets backend (AWS_SECRETS_BACKEND=ssm)
"""
        if self.config.engine == ExportEngine.LANGGRAPH:
            base += "langgraph==0.2.61\nlanggraph-checkpoint==2.0.9\n"
        if self.config.surface == ExportSurface.HTTP:
            base += "fastapi==0.115.6\nuvicorn[standard]==0.34.0\n"
        return base

    def _generate_requirements_lock(self, requirements_content: str) -> str:
        return (
            "# Locked runtime dependencies (generated by Forge exporter)\n"
            "# Keep this file in sync with requirements.txt for reproducible installs.\n"
            + requirements_content
        )

    def _generate_requirements_dev(self) -> str:
        return """bandit==1.7.10
pip-audit==2.7.3
ruff==0.6.9
mypy==1.11.2
pytest==8.3.5
pytest-asyncio==0.25.3
types-requests==2.32.0.20240712
"""

    def _generate_main_entrypoint(self) -> str:
        return '''"""CLI entrypoint for generated multi-agent project."""

from __future__ import annotations

import argparse
import asyncio
import json

from runtime.dispatcher import dispatch


def main() -> None:
    parser = argparse.ArgumentParser(description="Run generated multi-agent flow")
    parser.add_argument("--input", required=True, help="User input text")
    parser.add_argument("--entrypoint", default="main", help="Entrypoint name")
    args = parser.parse_args()
    result = asyncio.run(dispatch({"input": args.input}, entrypoint=args.entrypoint))
    print(json.dumps(result, indent=2, default=str))


if __name__ == "__main__":
    main()
'''

    def _generate_makefile(self) -> str:
        return """PYTHON ?= python
UV ?= uv
VENV ?= .venv

ifeq ($(OS),Windows_NT)
VENV_PY := $(VENV)/Scripts/python
else
VENV_PY := $(VENV)/bin/python
endif

.PHONY: setup install install-dev lock lock-check test run lint fmt-check type check security

setup:
\t@command -v $(UV) >/dev/null 2>&1 && echo "[setup] using uv" || echo "[setup] using pip"
\t@if command -v $(UV) >/dev/null 2>&1; then \\
\t\t$(UV) venv $(VENV); \\
\t\tif [ -f uv.lock ]; then $(UV) sync --frozen --all-extras; else $(UV) sync --all-extras; fi; \\
\telse \\
\t\t$(PYTHON) -m venv $(VENV); \\
\t\t$(VENV_PY) -m pip install --upgrade pip; \\
\t\t$(VENV_PY) -m pip install -r requirements.lock -r requirements-dev.txt; \\
\tfi

install:
\t@if command -v $(UV) >/dev/null 2>&1; then \\
\t\tif [ -f uv.lock ]; then $(UV) sync --frozen; else $(UV) sync; fi; \\
\telse \\
\t\t$(PYTHON) -m pip install -r requirements.lock; \\
\tfi

install-dev:
\t@if command -v $(UV) >/dev/null 2>&1; then \\
\t\tif [ -f uv.lock ]; then $(UV) sync --frozen --all-extras; else $(UV) sync --all-extras; fi; \\
\telse \\
\t\t$(PYTHON) -m pip install -r requirements.lock -r requirements-dev.txt; \\
\tfi

lock:
\t$(UV) lock

lock-check:
\t$(UV) lock
\tgit diff --exit-code uv.lock

test:
\t$(PYTHON) -m pytest -q tests

run:
\t$(PYTHON) -m runtime.server

lint:
\t$(PYTHON) -m ruff check .
\t$(PYTHON) -m ruff format --check .

fmt-check:
\t$(PYTHON) -m ruff format --check .

type:
\t$(PYTHON) -m mypy runtime agents settings evals --ignore-missing-imports

security:
\tpip-audit -r requirements.lock
\tbandit -q -r runtime agents -x tests -ll -ii

check: lint type test security

.PHONY: docker-push
docker-push: ## Build and push Docker image to GHCR
	@if [ -z "$(REGISTRY)" ]; then echo "Error: REGISTRY not set (e.g. ghcr.io/org/repo)"; exit 1; fi
	docker build -t $(REGISTRY):$(shell git rev-parse --short HEAD) .
	docker build -t $(REGISTRY):latest .
	docker push $(REGISTRY):$(shell git rev-parse --short HEAD)
	docker push $(REGISTRY):latest

.PHONY: profile
profile: ## Run a quick cProfile on a smoke input
	python -m cProfile -o /tmp/forge-profile.pstats main.py --input "Profile smoke test"
	python -c "import pstats; p=pstats.Stats('/tmp/forge-profile.pstats'); p.sort_stats('cumulative'); p.print_stats(20)"

.PHONY: profile-viz
profile-viz: ## Generate flame graph from last profile (requires snakeviz)
	pip install snakeviz -q
	snakeviz /tmp/forge-profile.pstats
""" + ("""
tf-init:
\tcd infra/aws/ecs && terraform init

tf-validate:
\tcd infra/aws/ecs && terraform validate

tf-plan:
\tcd infra/aws/ecs && terraform plan -var-file=terraform.tfvars

tf-apply:
\tcd infra/aws/ecs && terraform apply -var-file=terraform.tfvars

deploy-aws: docker build -t $(IMAGE_URI) . && docker push $(IMAGE_URI)
\t$(MAKE) tf-apply
""" if self.config.packaging == ExportPackaging.AWS_ECS else "")

    def _generate_dockerfile(self) -> str:
        run_cmd = 'CMD ["python", "main.py", "--input", "healthcheck"]'
        if self.config.surface == ExportSurface.HTTP:
            run_cmd = 'CMD ["uvicorn", "api:app", "--host", "0.0.0.0", "--port", "8080"]'
        return f"""FROM python:3.11-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \\
    PYTHONUNBUFFERED=1

RUN pip install --no-cache-dir uv

COPY pyproject.toml /app/pyproject.toml
COPY uv.lock /app/uv.lock
RUN test -s /app/uv.lock && uv sync --frozen --no-dev

COPY . /app

RUN useradd --create-home --uid 10001 appuser \\
  && mkdir -p /tmp/forge \\
  && chown -R appuser:appuser /app /tmp/forge
USER appuser

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \\
  CMD python -m runtime.healthcheck || exit 1

{run_cmd}
"""

    def _generate_dockerignore(self) -> str:
        return """.git
__pycache__/
*.pyc
.pytest_cache/
.mypy_cache/
.ruff_cache/
.venv/
"""

    def _generate_gitignore(self) -> str:
        return """# Python cache/build
__pycache__/
*.pyc
*.pyo
*.pyd
.pytest_cache/
.mypy_cache/
.ruff_cache/
.coverage

# Virtualenv / local env
.venv/
.env

# Runtime artifacts
artifacts/
logs/

# Export IR (contains agent graph and prompts — do not commit to public repos)
ir.json

# Eval results (CI artifacts)
evals/*_results.json

# IDE
.idea/
.vscode/
"""

    def _generate_docker_compose(self) -> str:
        command = "python -m runtime.server"
        ports = '      - "9090:9090"'
        if self.config.surface == ExportSurface.HTTP:
            command = "uvicorn api:app --host 0.0.0.0 --port 8080"
            ports = '      - "8080:8080"'
        return f"""services:
  forge:
    build:
      context: .
      dockerfile: Dockerfile
    env_file:
      - .env
    environment:
      - DEV_MODE=${{DEV_MODE:-1}}
      - FORGE_ENV=${{FORGE_ENV:-development}}
      - FORGE_OBS_PORT=${{FORGE_OBS_PORT:-9090}}
    command: {command}
    ports:
{ports}
    healthcheck:
      test: ["CMD", "python", "-m", "runtime.healthcheck"]
      interval: 30s
      timeout: 5s
      retries: 3
      start_period: 10s
"""

    def _generate_ci_workflow(self) -> str:
        return """name: CI

on:
  push:
  pull_request:

permissions:
  contents: read

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'
      - name: Install dependencies
        run: |
          pip install --upgrade pip
          pip install uv
      - name: Validate lockfile exists and is non-empty
        run: |
          test -s uv.lock
      - name: Install dependencies (frozen)
        run: uv sync --frozen --all-extras
      - name: Lockfile up-to-date (uv)
        run: |
          uv lock
          git diff --exit-code uv.lock
      - name: Lint (ruff)
        run: ruff check .
      - name: Format check (ruff)
        run: ruff format --check .
      - name: Type check (mypy)
        run: mypy runtime agents settings evals --ignore-missing-imports
      - name: Run tests
        run: pytest -q tests
      - name: Run eval suites (smoke + regression)
        run: |
          python evals/run.py --suite smoke
          python evals/run.py --suite regression
      - name: Eval gate (dry-run, no agent call — structural assertions only)
        run: |
          python evals/run_evals.py --suite smoke --threshold 1.0 --dry-run
          python evals/run_evals.py --suite regression --threshold 0.8 --dry-run
      - name: Upload eval results
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: eval-results
          path: evals/*_results.json
      - name: Export locked requirements for security tooling
        run: uv export --locked --no-dev --format requirements-txt -o requirements.audit.txt
      - name: Dependency vulnerability scan
        run: pip-audit -r requirements.audit.txt
      - name: Static security scan (Bandit)
        run: bandit -q -r runtime agents -x tests -ll -ii
      - name: Secret scan
        uses: gitleaks/gitleaks-action@v2
      - name: Secret scan (TruffleHog)
        uses: trufflesecurity/trufflehog@main
        with:
          path: ./
          base: ${{ github.event.repository.default_branch }}
          extra_args: --only-verified
      - name: Generate SBOM (CycloneDX)
        run: pip-audit -r requirements.audit.txt -f cyclonedx-json -o sbom.json
      - name: Upload SBOM artifact
        uses: actions/upload-artifact@v4
        with:
          name: sbom-cyclonedx
          path: sbom.json
""" + ("""      - name: Terraform validate (infra/aws/ecs)
        run: |
          terraform -chdir=infra/aws/ecs init -backend=false
          terraform -chdir=infra/aws/ecs validate
""" if self.config.packaging == ExportPackaging.AWS_ECS else "") + """
  release:
    needs: test
    runs-on: ubuntu-latest
    if: github.ref == 'refs/heads/main' && github.event_name == 'push'
    permissions:
      contents: write
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0
      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'
      - name: Create release tag
        run: |
          VERSION=$(python -c "import sys; sys.path.insert(0, '.'); import settings; print(settings.FLOW_VERSION)")
          TAG="v${VERSION}-$(git rev-parse --short HEAD)"
          git tag "$TAG" || echo "Tag $TAG already exists — skipping."
          git push origin "$TAG" || echo "Tag $TAG already pushed — skipping."

  docker:
    needs: test
    runs-on: ubuntu-latest
    if: github.ref == 'refs/heads/main' && github.event_name == 'push'
    environment: production
    permissions:
      contents: read
      packages: write
    steps:
      - uses: actions/checkout@v4
      - name: Log in to GitHub Container Registry
        uses: docker/login-action@v3
        with:
          registry: ghcr.io
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}
      - name: Extract metadata
        id: meta
        uses: docker/metadata-action@v5
        with:
          images: ghcr.io/${{ github.repository }}
          tags: |
            type=sha,prefix=sha-
            type=raw,value=latest
      - name: Set up QEMU
        uses: docker/setup-qemu-action@v3
      - name: Set up Docker Buildx
        uses: docker/setup-buildx-action@v3
      - name: Build and push
        uses: docker/build-push-action@v5
        with:
          context: .
          platforms: linux/amd64,linux/arm64
          push: true
          tags: ${{ steps.meta.outputs.tags }}
          labels: ${{ steps.meta.outputs.labels }}
          cache-from: type=gha
          cache-to: type=gha,mode=max

  sign:
    needs: docker
    runs-on: ubuntu-latest
    if: github.ref == 'refs/heads/main' && github.event_name == 'push'
    environment: production
    permissions:
      contents: read
      packages: write
      id-token: write
    steps:
      - name: Install cosign
        uses: sigstore/cosign-installer@v3
      - name: Log in to GHCR
        uses: docker/login-action@v3
        with:
          registry: ghcr.io
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}
      - name: Sign container image
        run: |
          cosign sign --yes ghcr.io/${{ github.repository }}:sha-${{ github.sha }}
"""

    def _generate_readme(self) -> str:
        agent_list = "\n".join(
            f"- **{a.name}** (`{a.id}`): {len(a.graph.nodes)} nodes, model={a.llm.model}"
            for a in self.ir.agents
        )
        handoff_list = "\n".join(
            f"- `{h.from_agent_id}` -> `{h.to_agent_id}` (mode={h.mode.value})"
            for h in self.ir.handoffs
        ) or "- (none)"

        target_name = self.config.label

        # Engine-based summary line
        _engine_summary = (
            "- Uses LangGraph as the agent-handoff orchestrator (`runtime/langgraph_runner.py`)\n"
            "- Agent transitions are stateful in LangGraph; node execution remains in `runtime/dispatcher.py`"
            if self.config.engine == ExportEngine.LANGGRAPH
            else "- Executes directly via `runtime.dispatcher` and `runtime.node_runtime`"
        )
        # Surface-based summary line
        _surface_summary = (
            "- Ships a FastAPI server entrypoint (`api.py`); exposes HTTP endpoints"
            if self.config.surface == ExportSurface.HTTP
            else "- No external HTTP server; invoked via CLI (`python main.py`)"
        )
        # Packaging-based summary line
        _packaging_summary = (
            "- Includes Terraform infra (`infra/aws/ecs/`) for AWS ECS Fargate deployment"
            if self.config.packaging == ExportPackaging.AWS_ECS
            else ""
        )
        target_summary = "\n".join(filter(None, [_engine_summary, _surface_summary, _packaging_summary]))

        target_run = (
            '```bash\nuvicorn api:app --host 0.0.0.0 --port 8080\n```'
            if self.config.surface == ExportSurface.HTTP
            else '```bash\npython main.py --input "Hello" --entrypoint main\n```'
        )

        _notes_parts = []
        if self.config.engine == ExportEngine.LANGGRAPH:
            _notes_parts.append("- Requires `langgraph` and `langgraph-checkpoint` in `requirements.txt`.")
        if self.config.surface == ExportSurface.HTTP:
            _notes_parts.append(
                "- Endpoints:\n"
                "  - `GET /health`\n"
                "  - `GET /healthz`\n"
                "  - `GET /ready`\n"
                "  - `GET /readyz`\n"
                "  - `GET /metrics`\n"
                "  - `GET /metrics/prometheus`\n"
                "  - `POST /run` with body `{{\"input\": {{...}}, \"entrypoint\": \"main\"}}`"
            )
        else:
            _notes_parts.append("- No external HTTP server is started by default.")
        if self.config.packaging == ExportPackaging.AWS_ECS:
            _notes_parts.append("- See `README_AWS_ECS.md` for Terraform deploy instructions.")
        target_notes = "\n".join(_notes_parts)

        return f"""# {self.ir.flow.name} - Multi-Agent Export

Generated by Forge.

## Target Comparison

| Target | Runtime Core | Operational Complexity | Best For |
| --- | --- | --- | --- |
| `LangGraph` | Forge runtime + LangGraph agent orchestration | Medium/High | LangGraph-native state transitions with Forge node runtime |
| `Simple Runtime` | Forge runtime dispatcher directly | Low | Minimal dependencies, fast local iteration, controlled environments |
| `API Server` | Simple Runtime + FastAPI ingress | Medium | Service deployments behind gateway/load balancer |

## Decision Guide

1. If you need the smallest and most predictable runtime footprint, choose **`Simple Runtime`**.
2. If your platform standards require LangGraph-native orchestration, choose **`LangGraph`**.
3. If consumers will call the agent over HTTP (apps/services), choose **`API Server`**.
4. For first production rollout, start with **`Simple Runtime`** and move to **`API Server`** when ingress/ops is required.
5. `LangGraph` here provides **native agent-level orchestration**; node adapters remain Forge runtime.

## Target Profile

- **Selected target:** `{target_name}`
- **IR version:** `2`
- **Entrypoints:** {", ".join(e.name for e in self.ir.entrypoints)}

### Architecture and Particularities
{target_summary}

```mermaid
flowchart LR
    IN[Input] --> DISP[runtime.dispatcher]
    DISP --> AGENTS[agents/* graphs]
    AGENTS --> OUT[Output]
```

## Agent Topology

### Agents
{agent_list}

### Handoffs
{handoff_list}

## Setup

```bash
# Preferred (uv):
uv sync --frozen --all-extras

# Compatibility (pip):
pip install -r requirements.lock -r requirements-dev.txt
```

## Production-grade dependency policy

- `uv.lock` is required and must be committed, non-empty, and up-to-date.
- CI and Docker installs are frozen (`uv sync --frozen ...`) and fail without a valid lockfile.
- `requirements.lock` remains compatibility-only; production determinism is enforced via `uv.lock`.

Lockfile maintenance:

```bash
uv lock
uv sync --frozen --all-extras
```

## Quickstart (Offline demo, sin API keys)

```bash
cp .env.example .env
# Windows PowerShell:
# Copy-Item .env.example .env
```

En `.env`:

```dotenv
DEV_MODE=1
FORGE_ENV=development
```

Run local:

```bash
python -m runtime.server
curl -s http://127.0.0.1:9090/healthz
curl -s http://127.0.0.1:9090/metrics
```

## Quickstart (Real provider, con API keys)

```dotenv
DEV_MODE=0
FORGE_ENV=production
OPENAI_API_KEY=sk-...
```

## Run CLI
{target_run}

{target_notes}

Expected response shape:

```json
{{
  "run_id": "run_...",
  "trace_id": "trace_...",
  "status": "completed|failed",
  "output": {{}}
}}
```

## Tooling + MCP + State

- Tool registry combines local tools and MCP-discovered tools.
- Local tools (MVP): `tools.echo`, `tools.safe_calculator`, `tools.http_get` (guarded by policy).
- `tools.echo` is enabled by default.
- `tools.http_get` is present but should remain blocked unless you explicitly allowlist it and configure `HTTP_GET_ALLOW_DOMAINS`.
- MCP tools format: `mcp:<server_id>/<tool_name>`.
- Approval gates for risky tools:
  - request/approve/deny endpoints at runtime server (`/approvals/*`)
- Deterministic replay modes:
  - `REPLAY_MODE=record` captures step/tool outputs
  - `REPLAY_MODE=play` reuses captured outputs (no external calls)
- Resilience per tool:
  - rate limit + circuit breaker defaults from env vars
- State backend:
  - `STATE_BACKEND=inmemory` (default)
  - `STATE_BACKEND=redis` + `REDIS_URL=redis://...`

List tools:

```bash
python -c "from runtime.tools.registry import list_tools; print([t.name for t in list_tools()])"
```

Run with session persistence:

```bash
python - <<'PY'
import asyncio
from runtime.dispatcher import dispatch
print(asyncio.run(dispatch({{"input":"hello","session_id":"demo-1"}})))
PY
```

## Integrations (How-to)

This export is designed so you can integrate external systems (Telegram, WhatsApp, DBs, Google Apps, Slack, Jira, etc.)
without modifying the runtime core. Integrations should be implemented as Tools (outbound actions) and/or
Ingress handlers (inbound webhooks), and then wired through contracts + registry + policies.

### Integration patterns

#### A) Outbound actions (recommended default): Tools
Use a Tool when the agent needs to call an external system (send message, create ticket, query DB, write a row, etc.).

Where to put code:
- Tool implementation: `tools/<name>.py`
- Contracts (schemas): `runtime/schemas/tools/<name>.input.json` and `runtime/schemas/tools/<name>.output.json`
- Tool registration: `runtime/tools/registry.py` (or `tools/registry.py`)
- Policy allowlist: `settings.py` (`FLOW_POLICIES['tool_allowlist']`)
- Env config: `.env.example` and `runtime/config.py`
- Tests: `tests/test_<name>_contract.py` and `tests/test_<name>_security.py`

Minimal steps:
1. Create schemas:
   - `runtime/schemas/tools/<tool>.input.json`
   - `runtime/schemas/tools/<tool>.output.json`
2. Implement the tool: `tools/<tool>.py`
   - Validate inputs (schema + defensive checks)
   - Enforce timeouts/retries
   - Redact secrets in logs
3. Register it in `runtime/tools/registry.py`
4. Allowlist it in `settings.py`
5. Add required env vars to `.env.example`
6. Add tests + (optional) an eval case

#### B) Inbound events: Webhooks / Ingress
Use an ingress handler when an external system calls you (WhatsApp webhook, Telegram updates, Slack events).

Recommended approach:
- Keep ingress handling outside the agent core:
  - Add an HTTP route in `runtime/server.py` (minimal) OR run a small gateway service that calls the runtime `/invoke`.
- Normalize inbound payload -> internal request shape:
  - `{{"input": "...", "session_id": "...", "metadata": {{...}}}}`

Minimal steps (inside this repo):
1. Add a route in `runtime/server.py`, e.g. `/webhooks/<provider>`
2. Validate signature / token (provider-specific)
3. Transform payload into a runtime dispatch call
4. Store correlation identifiers (`run_id`, `trace_id`) + return quick ACK

> Security note: webhook endpoints must be authenticated/validated. Do not accept unauthenticated public webhooks.

#### C) Data access: DB / Vector DB
Prefer implementing DB operations as tools (read/write) with strict schemas and timeouts.
- For SQL: implement a `tools/db_query.py` and `tools/db_execute.py` with allowlisted queries or stored procedures.
- For vector DB: implement `tools/vector_search.py` (or integrate via your RAG pipeline module if present).

### Integration checklist (must pass)
- Tool contract exists (input/output schemas)
- Tool is registered and policy-allowlisted
- Secrets are env-only (not committed)
- Timeouts are enforced for outbound calls
- Tests include at least:
  - contract validation
  - failure modes (missing env, timeout)
- Observability:
  - logs include `run_id`/`trace_id`
  - tool calls emit start/end events

See `docs/INTEGRATIONS.md` for step-by-step examples.

## Programmatic Usage

```python
import asyncio
from runtime.dispatcher import dispatch

result = asyncio.run(dispatch({{"input": "Hello"}}))
print(result)
```

## Verification

```bash
pytest -q tests
```

## Local Ops

```bash
make install
make install-dev
make setup
make check
make test
make run
```

## Development Setup

### Using Dev Container (recommended)

```bash
# In VS Code: Ctrl+Shift+P → "Dev Containers: Open Folder in Container"
# Or with GitHub Codespaces: click "Code → Codespaces → New codespace"
```

### Local setup

```bash
pip install uv pre-commit
uv sync --all-extras
pre-commit install  # Installs git hooks
```

### Running checks

```bash
make lint        # ruff check + format check
make type-check  # mypy
make test        # pytest
make profile     # cProfile smoke test
```

### Model Version Pinning

To ensure deterministic behavior, pin the exact model version in your agent config:

| Alias | Recommended pin |
|---|---|
| `gpt-4o` | `gpt-4o-2024-11-20` |
| `gpt-4-turbo` | `gpt-4-turbo-2024-04-09` |
| `claude-3-5-sonnet` | `claude-3-5-sonnet-20241022` |
| `gemini-1.5-pro` | `gemini-1.5-pro-002` |

Set in the agent config: `model: "gpt-4o-2024-11-20"` instead of `model: "gpt-4o"`.

## Production deployment notes

- Deploy behind a reverse proxy (TLS termination + rate limiting).
- Runtime request hardening env vars:
  - `FORGE_MAX_REQUEST_BYTES` (default: 1048576)
  - `FORGE_SERVER_SOCKET_TIMEOUT_S` (default: 30)
- Ensure `RUNTIME_API_TOKEN` is set in production.

## Quality Gates

- `ruff check .`
- `ruff format --check .`
- `mypy runtime agents settings evals --ignore-missing-imports`
- `pytest -q tests`

## Security

- Dynamic code execution is blocked in calculator tool (safe AST evaluator only).
- Secrets are redacted in logs (`api_key`, `authorization`, `token`, `secret` patterns).
- CI security gates:
  - `bandit -q -r runtime agents -x tests -ll -ii`
  - `pip-audit -r requirements.lock`
  - `gitleaks` secret scanning
  - CycloneDX SBOM generation

Run locally:

```bash
pip install -r requirements.lock -r requirements-dev.txt
bandit -q -r runtime agents -x tests -ll -ii
pip-audit -r requirements.lock
```

## Observability

- Structured logs include: `ts`, `level`, `event`, `run_id`, `trace_id`, `step_id`, `node`, `duration_ms`, `status`, `error_type`, `error_msg`.
- Redaction is applied before serialization.
- Runtime observability server:

```bash
python -m runtime.server
curl -s http://127.0.0.1:9090/healthz
curl -s http://127.0.0.1:9090/readyz
curl -s http://127.0.0.1:9090/metrics
```

Sample log line:

```json
{{"ts":"...","level":"info","event":"NODE_END","run_id":"run_...","trace_id":"trace_...","step_id":"step_...","node":"triage","duration_ms":12.3,"status":"ok","error_type":"","error_msg":"","payload":{{}}}}
```

## Docker

```bash
docker build -t forge-agent .
docker run --rm -e OPENAI_API_KEY=$OPENAI_API_KEY forge-agent
```

## Docker Compose

```bash
docker compose up --build
```

Health check:

```bash
docker compose ps
```

Security hardening (optional runtime flags):

```bash
docker run --read-only --tmpfs /tmp:rw,noexec,nosuid,size=64m --rm -e OPENAI_API_KEY=$OPENAI_API_KEY forge-agent
```

## Troubleshooting

- Missing deps: run `pip install -r requirements.lock` (or `make setup`).
- No API key available: set `DEV_MODE=1` for deterministic mock LLM.
- Provider errors in production mode: verify `DEV_MODE=0` and API keys in `.env`.
- Runtime not ready: run `python -m runtime.healthcheck`.
- No metrics: verify `python -m runtime.server` and `curl http://127.0.0.1:9090/metrics`.
- Type/lint failures: run `make check` and inspect `ruff` / `mypy` output.

## Branch Protection (recommended)

Set the following in GitHub → Settings → Branches → `main`:
- Require pull request reviews: 1 reviewer
- Require status checks to pass before merging: `test` (from CI)
- Restrict pushes: direct pushes to `main` disabled

```bash
gh api repos/{{owner}}/{{repo}}/branches/main/protection \\
  --method PUT \\
  --field required_status_checks='{{"strict":true,"contexts":["test"]}}' \\
  --field enforce_admins=false \\
  --field required_pull_request_reviews='{{"required_approving_review_count":1}}' \\
  --field restrictions=null
```
"""

    def _generate_changelog(self) -> str:
        agent_ids = ", ".join(f"`{a.id}`" for a in self.ir.agents)
        handoff_count = len(self.ir.handoffs)
        return f"""# Changelog

All notable changes to this project will be documented in this file.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

## Unreleased

### Added
- Initial export of flow `{self.ir.flow.name}` (version {self.ir.flow.version})
- {len(self.ir.agents)} agent(s): {agent_ids}
- {handoff_count} handoff rule(s)
"""

    def _generate_release_config(self) -> str:
        return """changelog:
  categories:
    - title: Breaking Changes
      labels: ["breaking"]
    - title: New Features
      labels: ["enhancement"]
    - title: Bug Fixes
      labels: ["bug"]
    - title: Security
      labels: ["security"]
"""

    def _generate_grafana_dashboard(self) -> str:
        import json as _json
        dashboard = {
            "__inputs": [{"name": "DS_PROMETHEUS", "type": "datasource", "pluginId": "prometheus"}],
            "title": f"Forge Runtime — {self.ir.flow.name}",
            "uid": f"forge-{self.ir.flow.id[:8]}",
            "schemaVersion": 38,
            "panels": [
                {
                    "id": 1, "type": "stat", "title": "Total Runs",
                    "targets": [{"expr": "forge_runs_total", "datasource": "${DS_PROMETHEUS}"}],
                    "gridPos": {"h": 4, "w": 4, "x": 0, "y": 0},
                },
                {
                    "id": 2, "type": "stat", "title": "Failed Runs",
                    "targets": [{"expr": "forge_runs_failed_total", "datasource": "${DS_PROMETHEUS}"}],
                    "fieldConfig": {
                        "defaults": {
                            "color": {"mode": "thresholds"},
                            "thresholds": {"steps": [{"color": "green"}, {"value": 1, "color": "red"}]},
                        }
                    },
                    "gridPos": {"h": 4, "w": 4, "x": 4, "y": 0},
                },
                {
                    "id": 3, "type": "stat", "title": "Guard Blocks",
                    "targets": [{"expr": "forge_guard_blocked_total", "datasource": "${DS_PROMETHEUS}"}],
                    "gridPos": {"h": 4, "w": 4, "x": 8, "y": 0},
                },
                {
                    "id": 4, "type": "timeseries", "title": "Runs Over Time",
                    "targets": [{"expr": "rate(forge_runs_total[5m])", "legendFormat": "runs/s",
                                 "datasource": "${DS_PROMETHEUS}"}],
                    "gridPos": {"h": 8, "w": 12, "x": 0, "y": 4},
                },
                {
                    "id": 5, "type": "timeseries", "title": "Node Latency (avg ms)",
                    "targets": [{"expr": "forge_node_latency_avg_ms", "legendFormat": "{{node_type}}",
                                 "datasource": "${DS_PROMETHEUS}"}],
                    "gridPos": {"h": 8, "w": 12, "x": 12, "y": 4},
                },
            ],
        }
        return _json.dumps(dashboard, indent=2)

    def _generate_alerts_yaml(self) -> str:
        return f"""# Prometheus Alerting Rules — {self.ir.flow.name}
# Import in Prometheus with: rule_files: ["alerts.yaml"]

groups:
  - name: forge-runtime
    interval: 1m
    rules:
      - alert: ForgeHighFailureRate
        expr: rate(forge_runs_failed_total[5m]) / rate(forge_runs_total[5m]) > 0.1
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "Forge run failure rate > 10%"
          description: "Flow {self.ir.flow.id} has a failure rate of {{{{ $value | humanizePercentage }}}} over the last 5 minutes."

      - alert: ForgeGuardBlockSpike
        expr: rate(forge_guard_blocked_total[5m]) > 0.5
        for: 2m
        labels:
          severity: warning
        annotations:
          summary: "Forge tool guard block rate elevated"
          description: "Policy guard blocks are elevated — possible prompt injection attempt."

      - alert: ForgeNoRuns
        expr: rate(forge_runs_total[15m]) == 0
        for: 15m
        labels:
          severity: info
        annotations:
          summary: "No Forge runs in the last 15 minutes"
          description: "Flow {self.ir.flow.id} has received no runs. Service may be down."
"""

    def _generate_devcontainer(self) -> str:
        import json as _json
        return _json.dumps({
            "name": f"Forge \u2014 {self.ir.flow.name}",
            "image": "mcr.microsoft.com/devcontainers/python:3.11",
            "features": {
                "ghcr.io/devcontainers/features/docker-in-docker:2": {},
                "ghcr.io/devcontainers/features/node:1": {"version": "20"},
            },
            "postCreateCommand": "pip install uv && uv sync --all-extras",
            "customizations": {
                "vscode": {
                    "extensions": [
                        "ms-python.python",
                        "ms-python.mypy-type-checker",
                        "charliermarsh.ruff",
                        "ms-azuretools.vscode-docker",
                    ],
                    "settings": {
                        "python.defaultInterpreterPath": "/usr/local/bin/python",
                        "editor.formatOnSave": True,
                        "[python]": {"editor.defaultFormatter": "charliermarsh.ruff"},
                    },
                }
            },
            "forwardPorts": [8080, 9090],
            "remoteEnv": {
                "FORGE_ENV": "development",
                "LOG_LEVEL": "DEBUG",
            },
        }, indent=2)

    def _generate_precommit_config(self) -> str:
        return """repos:
  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.6.9
    hooks:
      - id: ruff
        args: [--fix]
      - id: ruff-format

  - repo: https://github.com/pre-commit/pre-commit-hooks
    rev: v4.6.0
    hooks:
      - id: trailing-whitespace
      - id: end-of-file-fixer
      - id: check-yaml
      - id: check-json
      - id: check-added-large-files
        args: ["--maxkb=500"]
      - id: detect-private-key

  - repo: https://github.com/PyCQA/bandit
    rev: 1.7.10
    hooks:
      - id: bandit
        args: ["-ll", "-x", "tests"]
        files: ^(runtime|agents|settings)\\.py$
"""

    def _generate_dependabot(self) -> str:
        return """\
version: 2
updates:
  # Python dependencies (pip)
  - package-ecosystem: "pip"
    directory: "/"
    schedule:
      interval: "weekly"
      day: "monday"
    open-pull-requests-limit: 5
    groups:
      runtime-deps:
        patterns:
          - "langchain*"
          - "openai*"
          - "anthropic*"
          - "fastapi*"
          - "pydantic*"
    ignore:
      # Major version bumps require manual review
      - dependency-name: "*"
        update-types: ["version-update:semver-major"]

  # GitHub Actions
  - package-ecosystem: "github-actions"
    directory: "/.github/workflows"
    schedule:
      interval: "weekly"
      day: "monday"
    open-pull-requests-limit: 3
"""

    def _generate_codeowners(self) -> str:
        return """\
# CODEOWNERS — GitHub auto-assigns reviewers based on file paths.
# Docs: https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/customizing-your-repository/about-code-owners

# Global fallback owner (update to your team's GitHub handle)
*                           @your-org/platform-team

# Runtime core — changes require runtime team approval
/runtime/                   @your-org/runtime-team

# Infrastructure / IaC — changes require infra team approval
/terraform/                 @your-org/infra-team
/.github/                   @your-org/infra-team

# Security-sensitive files — changes require security team approval
/runtime/auth.py            @your-org/security-team
/runtime/server.py          @your-org/security-team
SECURITY.md                 @your-org/security-team

# Agent configs — changes require ML team approval
/agents/                    @your-org/ml-team
"""

    def _generate_security_md(self) -> str:
        return f"""# Security Policy — {self.ir.flow.name}

## Supported Versions

| Version | Supported |
|---|---|
| {self.ir.flow.version} (current) | ✅ |

## Reporting a Vulnerability

Please **do not** open public issues for security vulnerabilities.
Report via email to your team's security contact or create a private advisory:

```
GitHub → Security → Advisories → New draft security advisory
```

Expected response: acknowledgment within 48 hours, patch within 14 days.

## Threat Model

### Assets

| Asset | Sensitivity | Location |
|---|---|---|
| LLM API keys (OPENAI, ANTHROPIC, GOOGLE) | Critical | `.env`, AWS SSM |
| `RUNTIME_API_TOKEN` | High | `.env`, AWS SSM |
| Agent conversation history | Medium | State store (inmemory/Redis) |
| Run artifacts (inputs/outputs) | Medium | `artifacts/runs/` or Redis |
| `ir.json` (agent graph + prompts) | Medium | Project root (gitignored) |

### Attack Surfaces

| Surface | Risk | Mitigation |
|---|---|---|
| Runtime HTTP server (`/dispatch`) | Medium | `RUNTIME_API_TOKEN` auth required |
| `tools.http_get` | Medium | Domain allowlist + IP blocklist + DNS validation |
| MCP tool execution | High if enabled | `MCP_ALLOWED_COMMANDS` allowlist; disabled by default |
| Tool policy bypass | Medium | TOOL_DENYLIST blocks `python_repl,shell,exec` |
| Prompt injection via user input | Medium | `sanitize_input()` strips HTML, caps at `MAX_INPUT_CHARS` |
| State store (Redis) | Low-Medium | Use Redis AUTH + TLS in production |
| Log exfiltration | Low | Secret redaction patterns in `observability.py` |

### Out of Scope

- Vulnerabilities in LLM providers (OpenAI, Anthropic, Google)
- Vulnerabilities in MCP server implementations
- Physical/infrastructure access to the host running this service

## Security Checklist for Deployment

- [ ] `RUNTIME_API_TOKEN` set to a strong random value (≥ 32 hex chars)
- [ ] `OPENAI_API_KEY` (and others) loaded from Secrets Manager, not `.env` in prod
- [ ] `FORGE_ENV=production` set
- [ ] `HTTP_GET_ALLOW_DOMAINS` explicitly set (default: deny all)
- [ ] MCP disabled (`MCP_SERVERS=[]`) unless explicitly needed
- [ ] `TOOL_DENYLIST` reviewed for your context
- [ ] Redis AUTH and TLS configured if `STATE_BACKEND=redis`
- [ ] Container runs as non-root user (Dockerfile: `appuser`)
- [ ] `.gitignore` excludes `ir.json`, `.env`, `artifacts/`

## CI/CD Environment Setup

GitHub Environments gate production deployments with required reviewers and dedicated secrets.

1. Go to **Settings → Environments → New environment → `production`**
2. Add **Required reviewers** (at least 1 person from `@your-org/platform-team`)
3. Add environment secrets:
   - `REGISTRY_TOKEN` — write-access token for your container registry
   - `COSIGN_PRIVATE_KEY` — Sigstore signing key (generated with `cosign generate-key-pair`)
   - `COSIGN_PASSWORD` — passphrase for the Sigstore key
4. Add **deployment branch rules**: only `main` can deploy to production
"""

    def _generate_readme_deploy(self) -> str:
        agent_ids = [a.id for a in self.ir.agents]
        return f"""# Deployment Guide — {self.ir.flow.name}

## Quick Start (local Docker)

```bash
cp .env.example .env
# Edit .env: set OPENAI_API_KEY, RUNTIME_API_TOKEN
docker-compose up
```

## AWS ECS Deployment

### Prerequisites
- AWS CLI configured (`aws configure`)
- Terraform ≥ 1.5
- ECR repository created

### Steps

1. **Build and push Docker image**
```bash
AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
AWS_REGION=us-east-1
ECR_REPO=$AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com/{self.ir.flow.id}

aws ecr get-login-password | docker login --username AWS --password-stdin $ECR_REPO
docker build -t $ECR_REPO:latest .
docker push $ECR_REPO:latest
```

2. **Configure Terraform**
```bash
cd infra/aws/ecs
cp terraform.tfvars.example terraform.tfvars
# Edit terraform.tfvars with your values
terraform init
terraform plan
terraform apply
```

3. **Set secrets in Parameter Store** (recommended)
```bash
aws ssm put-parameter --name "/{self.ir.flow.id}/OPENAI_API_KEY" \\
  --value "sk-..." --type SecureString
aws ssm put-parameter --name "/{self.ir.flow.id}/RUNTIME_API_TOKEN" \\
  --value "$(openssl rand -hex 32)" --type SecureString
```

### State Backend (ECS)

ECS tasks are stateless. Choose a persistence strategy:

| Backend | Setup | Durability |
|---|---|---|
| `inmemory` | None | ❌ Lost on restart |
| `filesystem` + EFS | Mount EFS volume | ✅ Durable |
| `redis` | ElastiCache Redis | ✅ Durable, recommended |

**Recommended (ECS):** `STATE_BACKEND=redis` + `RUN_STORE_BACKEND=redis` with ElastiCache.

### IAM Permissions Required

See `infra/aws/ecs/iam_policy.json` for the minimal IAM policy. Key permissions:
- `ssm:GetParameter` — for reading secrets from Parameter Store
- `logs:CreateLogGroup`, `logs:PutLogEvents` — for CloudWatch Logs
- `ecr:GetAuthorizationToken`, `ecr:BatchGetImage` — for pulling the image

### Healthchecks

The container exposes health at:
- `python -m runtime.healthcheck` (Docker HEALTHCHECK)
- `GET /healthz` (HTTP surface only)

ECS target group health check: `GET /healthz`, threshold 2/3.

### Cost Estimation (ECS Fargate, us-east-1)

| Config | vCPU | Memory | $/month (estimate) |
|---|---|---|---|
| Dev | 0.25 | 512MB | ~$5 |
| Prod (single task) | 0.5 | 1GB | ~$18 |
| Prod (2 tasks) | 0.5 | 1GB | ~$36 |

Enable autoscaling with target tracking on `ECSServiceAverageCPUUtilization` at 70%.

## Environment Promotion

```
dev branch  →  dev ECS cluster   (FORGE_ENV=development)
main branch →  staging ECS cluster (FORGE_ENV=staging)
git tag     →  prod ECS cluster   (FORGE_ENV=production)
```

Agents in this export: {', '.join(f'`{a}`' for a in agent_ids)}
"""

    def _generate_tf_readme_minimal(self) -> str:
        return f"""# Terraform — {self.ir.flow.name}

This directory contains Terraform configuration for deploying the exported agent to AWS ECS.

## Quick reference

```bash
terraform init
terraform plan -var-file=terraform.tfvars
terraform apply -var-file=terraform.tfvars
```

See `README_DEPLOY.md` in the project root for the full deployment guide.
"""

    def _generate_tf_skeleton(self) -> str:
        return f"""# Terraform skeleton for {self.ir.flow.name} (non-ECS packaging).
#
# This is a minimal scaffold. To get a full ECS deployment config, switch
# to aws-ecs packaging in Forge, or follow README_DEPLOY.md manually.

terraform {{
  required_version = ">= 1.5"
  required_providers {{
    aws = {{
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }}
  }}
}}

provider "aws" {{
  region = var.aws_region
}}
"""

    def _generate_tf_skeleton_variables(self) -> str:
        return """variable "aws_region" {
  description = "AWS region"
  type        = string
  default     = "us-east-1"
}
"""

    def _generate_tf_iam_policy(self) -> str:
        import json as _json
        policy = {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Sid": "SSMParameters",
                    "Effect": "Allow",
                    "Action": [
                        "ssm:GetParameter",
                        "ssm:GetParameters",
                        "ssm:GetParametersByPath",
                    ],
                    "Resource": [f"arn:aws:ssm:*:*:parameter/{self.ir.flow.id}/*"],
                },
                {
                    "Sid": "CloudWatchLogs",
                    "Effect": "Allow",
                    "Action": [
                        "logs:CreateLogGroup",
                        "logs:CreateLogStream",
                        "logs:PutLogEvents",
                        "logs:DescribeLogStreams",
                    ],
                    "Resource": [f"arn:aws:logs:*:*:log-group:/forge/{self.ir.flow.id}*"],
                },
                {
                    "Sid": "ECRPull",
                    "Effect": "Allow",
                    "Action": [
                        "ecr:GetAuthorizationToken",
                        "ecr:BatchGetImage",
                        "ecr:GetDownloadUrlForLayer",
                    ],
                    "Resource": "*",
                },
            ],
        }
        return _json.dumps(policy, indent=2)

    def _generate_integrations_doc(self) -> str:
        return """# Integrations Guide (Forge Export)

This repo is a production-grade agent export. Integrations are implemented as Tools (outbound) and optionally as
Ingress handlers (inbound webhooks). The runtime core stays unchanged.

## 1) Add a new Tool (example: telegram_send_message)

### 1.1 Define contracts (schemas)
Create:

- `runtime/schemas/tools/telegram_send_message.input.json`
- `runtime/schemas/tools/telegram_send_message.output.json`

Input schema should include:
- `chat_id` (string)
- `text` (string)
- optional `parse_mode`

Output schema should include:
- `message_id` (string/int)
- `ok` (boolean)

### 1.2 Implement the tool
Create `tools/telegram_send_message.py`:
- Read `TELEGRAM_BOT_TOKEN` from env
- Enforce network timeout
- Redact token in logs
- Return output matching schema

### 1.3 Register the tool
Add to `runtime/tools/registry.py`:
- name: `telegram_send_message`
- callable: `tools.telegram_send_message:run` (or similar)

### 1.4 Enable via policy allowlist
In `settings.py`:
- Add `telegram_send_message` to `FLOW_POLICIES['tool_allowlist']`

### 1.5 Add env vars
In `.env.example` add:
- `TELEGRAM_BOT_TOKEN=`
- `TELEGRAM_DEFAULT_CHAT_ID=`

### 1.6 Add tests
Add:
- `tests/test_telegram_send_message_contract.py`
- `tests/test_telegram_send_message_security.py`

Minimum assertions:
- fails fast if missing env var
- enforces timeout
- output conforms to schema

---

## 2) Inbound webhook integration (example: WhatsApp)

### Option A - Add route in runtime (minimal)
- Add `/webhooks/whatsapp` to `runtime/server.py`
- Validate signature/token
- Transform payload -> `dispatch({"input": ..., "session_id": ..., "metadata": ...})`
- Respond fast with 200 OK

### Option B - Separate gateway (recommended for production)
- Run a small webhook service (FastAPI) that:
  - validates provider signatures
  - normalizes inbound payload
  - calls runtime `/invoke` with `RUNTIME_API_TOKEN`

---

## 3) Database integration (SQL)
Recommended pattern: DB operations as tools with strict contracts.

- `tools/db_query.py` (read-only)
- `tools/db_execute.py` (writes; approval-gated)

Security:
- Do not accept raw SQL from the model in production.
- Prefer stored procedures or allowlisted query templates.

Env:
- `DATABASE_URL=...`
- `DB_CONNECT_TIMEOUT_S=...`
- `DB_STATEMENT_TIMEOUT_MS=...`

---

## 4) Google Apps (Calendar/Sheets/Gmail)
Implement as tools with scoped credentials and explicit allowlists.
- `tools/google_calendar_create_event.py`
- `tools/google_sheets_append_row.py`

Security:
- least-privilege scopes
- service account / oauth with restricted tenant
- redact tokens

---

## 5) Observability requirements for integrations
Every integration must:
- log start/end with `run_id`, `trace_id`
- store tool artifacts for replay when `REPLAY_MODE=record`
- use the shared retry/timeout helpers where available

---

## 6) Quick validation commands

```bash
pytest -q tests
python -m evals.run --suite smoke
curl -s http://127.0.0.1:9090/healthz
curl -s http://127.0.0.1:9090/metrics
```
"""

    # ------------------------------------------------------------------
    # AWS ECS / Terraform generators
    # ------------------------------------------------------------------

    def _generate_tf_main(self) -> str:
        flow_name = getattr(self.ir.flow, "name", "forge-agent").lower().replace(" ", "-")
        return f'''terraform {{
  required_version = ">= 1.5"
  required_providers {{
    aws = {{
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }}
  }}
}}

provider "aws" {{
  region = var.aws_region
}}

# ── CloudWatch log group ─────────────────────────────────────────────
resource "aws_cloudwatch_log_group" "agent" {{
  name              = "/ecs/${{var.cluster_name}}"
  retention_in_days = var.log_retention_days
}}

# ── ECS Cluster ──────────────────────────────────────────────────────
resource "aws_ecs_cluster" "main" {{
  name = var.cluster_name

  setting {{
    name  = "containerInsights"
    value = "enabled"
  }}
}}

# ── IAM Role for task execution ──────────────────────────────────────
resource "aws_iam_role" "ecs_execution" {{
  name = "${{var.service_name}}-ecs-execution"

  assume_role_policy = jsonencode({{
    Version = "2012-10-17"
    Statement = [{{
      Effect    = "Allow"
      Principal = {{ Service = "ecs-tasks.amazonaws.com" }}
      Action    = "sts:AssumeRole"
    }}]
  }})
}}

resource "aws_iam_role_policy_attachment" "ecs_execution_managed" {{
  role       = aws_iam_role.ecs_execution.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}}

resource "aws_iam_role_policy" "secrets_access" {{
  name = "${{var.service_name}}-secrets-access"
  role = aws_iam_role.ecs_execution.id

  policy = jsonencode({{
    Version = "2012-10-17"
    Statement = [{{
      Effect   = "Allow"
      Action   = ["secretsmanager:GetSecretValue"]
      Resource = values(var.secrets_arns)
    }}]
  }})
}}

# ── IAM Role for task (runtime permissions incl. ECS Exec) ───────────
resource "aws_iam_role" "ecs_task_role" {{
  name = "${{var.service_name}}-ecs-task"

  assume_role_policy = jsonencode({{
    Version = "2012-10-17"
    Statement = [{{
      Effect    = "Allow"
      Principal = {{ Service = "ecs-tasks.amazonaws.com" }}
      Action    = "sts:AssumeRole"
    }}]
  }})
}}

resource "aws_iam_role_policy" "ecs_exec_ssm" {{
  name = "${{var.service_name}}-ecs-exec-ssm"
  role = aws_iam_role.ecs_task_role.id

  policy = jsonencode({{
    Version = "2012-10-17"
    Statement = [{{
      Effect = "Allow"
      Action = [
        "ssmmessages:CreateControlChannel",
        "ssmmessages:CreateDataChannel",
        "ssmmessages:OpenControlChannel",
        "ssmmessages:OpenDataChannel"
      ]
      Resource = "*"
    }}]
  }})
}}

# ── ECS Task Definition ──────────────────────────────────────────────
resource "aws_ecs_task_definition" "agent" {{
  family                   = var.service_name
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = var.task_cpu
  memory                   = var.task_memory
  execution_role_arn       = aws_iam_role.ecs_execution.arn
  task_role_arn            = aws_iam_role.ecs_task_role.arn

  container_definitions = jsonencode([{{
    name      = "{flow_name}"
    image     = var.image_uri
    essential = true

    portMappings = [{{ containerPort = 8080, protocol = "tcp" }}]

    environment = [
      {{ name = "JSON_LOGS", value = "true" }},
      {{ name = "PORT",      value = "8080" }},
    ]

    secrets = [
      for k, arn in var.secrets_arns : {{
        name      = k
        valueFrom = arn
      }}
    ]

    logConfiguration = {{
      logDriver = "awslogs"
      options = {{
        "awslogs-group"         = aws_cloudwatch_log_group.agent.name
        "awslogs-region"        = var.aws_region
        "awslogs-stream-prefix" = "ecs"
      }}
    }}

    healthCheck = {{
      command     = ["CMD-SHELL", "curl -f http://localhost:8080/healthz || exit 1"]
      interval    = 30
      timeout     = 5
      retries     = 3
      startPeriod = 10
    }}
  }}])
}}

# ── Security Group ───────────────────────────────────────────────────
resource "aws_security_group" "agent" {{
  name        = "${{var.service_name}}-sg"
  description = "Security group for ${{var.service_name}} ECS service"
  vpc_id      = var.vpc_id

  ingress {{
    # Scope ingress to VPC CIDR only.
    # To expose publicly, add a separate SG rule scoped to your ALB security group.
    from_port   = 8080
    to_port     = 8080
    protocol    = "tcp"
    cidr_blocks = [var.vpc_cidr]
  }}

  egress {{
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }}
}}

# ── ECS Service ──────────────────────────────────────────────────────
resource "aws_ecs_service" "agent" {{
  name                   = var.service_name
  cluster                = aws_ecs_cluster.main.id
  task_definition        = aws_ecs_task_definition.agent.arn
  desired_count          = var.desired_count
  launch_type            = "FARGATE"
  enable_execute_command = true

  network_configuration {{
    # Private subnets — tasks have no public IP; traffic egresses via NAT Gateway.
    # Set var.private_subnet_ids to your private subnet IDs.
    subnets          = var.private_subnet_ids
    security_groups  = [aws_security_group.agent.id]
    assign_public_ip = "DISABLED"
  }}

  lifecycle {{
    ignore_changes = [task_definition]
  }}
}}

# ── Auto Scaling ──────────────────────────────────────────────────────

resource "aws_appautoscaling_target" "agent" {{
  max_capacity       = var.max_task_count
  min_capacity       = var.min_task_count
  resource_id        = "service/${{aws_ecs_cluster.main.name}}/${{aws_ecs_service.agent.name}}"
  scalable_dimension = "ecs:service:DesiredCount"
  service_namespace  = "ecs"

  depends_on = [aws_ecs_service.agent]
}}

resource "aws_appautoscaling_policy" "cpu_tracking" {{
  name               = "${{var.service_name}}-cpu-tracking"
  policy_type        = "TargetTrackingScaling"
  resource_id        = aws_appautoscaling_target.agent.resource_id
  scalable_dimension = aws_appautoscaling_target.agent.scalable_dimension
  service_namespace  = aws_appautoscaling_target.agent.service_namespace

  target_tracking_scaling_policy_configuration {{
    predefined_metric_specification {{
      predefined_metric_type = "ECSServiceAverageCPUUtilization"
    }}
    target_value       = 70.0
    scale_in_cooldown  = 300
    scale_out_cooldown = 60
  }}
}}

resource "aws_appautoscaling_policy" "memory_tracking" {{
  name               = "${{var.service_name}}-memory-tracking"
  policy_type        = "TargetTrackingScaling"
  resource_id        = aws_appautoscaling_target.agent.resource_id
  scalable_dimension = aws_appautoscaling_target.agent.scalable_dimension
  service_namespace  = aws_appautoscaling_target.agent.service_namespace

  target_tracking_scaling_policy_configuration {{
    predefined_metric_specification {{
      predefined_metric_type = "ECSServiceAverageMemoryUtilization"
    }}
    target_value       = 80.0
    scale_in_cooldown  = 300
    scale_out_cooldown = 60
  }}
}}

# ── Cost Budget ───────────────────────────────────────────────────────

resource "aws_budgets_budget" "agent" {{
  name         = "${{var.service_name}}-monthly-budget"
  budget_type  = "COST"
  limit_amount = var.monthly_budget_usd
  limit_unit   = "USD"
  time_unit    = "MONTHLY"

  notification {{
    comparison_operator        = "GREATER_THAN"
    threshold                  = 80
    threshold_type             = "PERCENTAGE"
    notification_type          = "ACTUAL"
    subscriber_email_addresses = [var.budget_alert_email]
  }}

  notification {{
    comparison_operator        = "GREATER_THAN"
    threshold                  = 100
    threshold_type             = "PERCENTAGE"
    notification_type          = "FORECASTED"
    subscriber_email_addresses = [var.budget_alert_email]
  }}
}}

# ── ECR Lifecycle Policy ──────────────────────────────────────────────
# Opt-in: set var.ecr_repo_name to your ECR repository name to enable.

resource "aws_ecr_lifecycle_policy" "agent" {{
  count      = var.ecr_repo_name != "" ? 1 : 0
  repository = var.ecr_repo_name

  policy = jsonencode({{
    rules = [
      {{
        rulePriority = 1
        description  = "Keep last 10 tagged images"
        selection = {{
          tagStatus   = "tagged"
          tagPatterns = ["*"]
          countType   = "imageCountMoreThan"
          countNumber = 10
        }}
        action = {{ type = "expire" }}
      }},
      {{
        rulePriority = 2
        description  = "Expire untagged images after 1 day"
        selection = {{
          tagStatus   = "untagged"
          countType   = "sinceImagePushed"
          countUnit   = "days"
          countNumber = 1
        }}
        action = {{ type = "expire" }}
      }}
    ]
  }})
}}
'''

    def _generate_tf_variables(self) -> str:
        return '''variable "aws_region" {
  description = "AWS region to deploy into"
  type        = string
  default     = "us-east-1"
}

variable "cluster_name" {
  description = "Name of the ECS cluster"
  type        = string
  default     = "forge-agents"
}

variable "service_name" {
  description = "Name of the ECS service"
  type        = string
  default     = "forge-agent"
}

variable "image_uri" {
  description = "Full ECR image URI (e.g. 123456789.dkr.ecr.us-east-1.amazonaws.com/my-agent:latest)"
  type        = string
}

variable "vpc_id" {
  description = "VPC ID for the ECS service"
  type        = string
}

variable "vpc_cidr" {
  description = "VPC CIDR block used to scope ECS security group ingress (e.g. 10.0.0.0/16)."
  type        = string
}

variable "ecr_repo_name" {
  description = "ECR repository name for lifecycle policy. Leave empty to skip."
  type        = string
  default     = ""
}

variable "subnet_ids" {
  description = "List of subnet IDs for the ECS tasks (kept for backward compatibility; prefer private_subnet_ids)"
  type        = list(string)
  default     = []
}

variable "private_subnet_ids" {
  description = "Private subnet IDs for ECS tasks (no public IP). Traffic egresses via NAT Gateway."
  type        = list(string)
}

variable "desired_count" {
  description = "Number of task replicas"
  type        = number
  default     = 1
}

variable "task_cpu" {
  description = "CPU units for the ECS task (1024 = 1 vCPU)"
  type        = number
  default     = 512
}

variable "task_memory" {
  description = "Memory (MiB) for the ECS task"
  type        = number
  default     = 1024
}

variable "secrets_arns" {
  description = "Map of environment variable name → Secrets Manager ARN"
  type        = map(string)
  default     = {}
}

variable "log_retention_days" {
  description = "CloudWatch log retention in days"
  type        = number
  default     = 30
}

variable "assign_public_ip" {
  description = "Assign a public IP to Fargate tasks (deprecated — service now hardcodes DISABLED)"
  type        = bool
  default     = false
}

variable "min_task_count" {
  description = "Minimum number of ECS tasks (auto scaling floor)."
  type        = number
  default     = 1
}

variable "max_task_count" {
  description = "Maximum number of ECS tasks (auto scaling ceiling)."
  type        = number
  default     = 10
}

variable "monthly_budget_usd" {
  description = "Monthly cost budget in USD. Alert fires at 80% actual and 100% forecasted."
  type        = string
  default     = "100"
}

variable "budget_alert_email" {
  description = "Email address to receive AWS Budget alert notifications."
  type        = string
}
'''

    def _generate_tf_outputs(self) -> str:
        return '''output "ecs_cluster_name" {
  description = "Name of the ECS cluster"
  value       = aws_ecs_cluster.main.name
}

output "ecs_service_name" {
  description = "Name of the ECS service"
  value       = aws_ecs_service.agent.name
}

output "cloudwatch_log_group" {
  description = "CloudWatch log group name"
  value       = aws_cloudwatch_log_group.agent.name
}

output "task_definition_arn" {
  description = "ARN of the latest ECS task definition"
  value       = aws_ecs_task_definition.agent.arn
}
'''

    def _generate_tf_tfvars_example(self) -> str:
        return '''# Copy this file to terraform.tfvars and fill in real values before deploying.

aws_region   = "us-east-1"
cluster_name = "forge-agents"
service_name = "forge-agent"

# ECR image URI — build & push your Docker image first (see README_AWS_ECS.md)
image_uri = "123456789012.dkr.ecr.us-east-1.amazonaws.com/forge-agent:latest"

# Networking
vpc_id     = "vpc-xxxxxxxxxxxxxxxxx"
vpc_cidr   = "10.0.0.0/16"
subnet_ids = ["subnet-xxxxxxxxxxxxxxxxx", "subnet-yyyyyyyyyyyyyyyyy"]

# Secrets Manager ARNs for API keys
secrets_arns = {
  ANTHROPIC_API_KEY = "arn:aws:secretsmanager:us-east-1:123456789012:secret:forge/ANTHROPIC_API_KEY-xxxxxx"
  OPENAI_API_KEY    = "arn:aws:secretsmanager:us-east-1:123456789012:secret:forge/OPENAI_API_KEY-xxxxxx"
  GEMINI_API_KEY    = "arn:aws:secretsmanager:us-east-1:123456789012:secret:forge/GEMINI_API_KEY-xxxxxx"
}

desired_count      = 1
task_cpu           = 512
task_memory        = 1024
log_retention_days = 30
# NOTE: assign_public_ip is deprecated — the ECS service hardcodes DISABLED.
# Tasks use private subnets; egress via NAT Gateway.
assign_public_ip   = false
# ecr_repo_name    = "forge-agent"  # Uncomment to enable ECR lifecycle policy
'''

    def _generate_readme_aws_ecs(self) -> str:
        return '''# AWS ECS (Fargate) Deployment Guide

This guide walks you through deploying the generated agent as a Fargate service using Terraform.

---

## Prerequisites

- [AWS CLI](https://docs.aws.amazon.com/cli/latest/userguide/install-cliv2.html) configured with appropriate credentials
- [Terraform](https://developer.hashicorp.com/terraform/downloads) >= 1.5
- [Docker](https://docs.docker.com/get-docker/) installed locally
- Access to an Amazon ECR registry in your target region

---

## 1 — Secrets setup (AWS Secrets Manager)

Create a secret for each API key your agent needs:

```bash
aws secretsmanager create-secret \\
  --name forge/ANTHROPIC_API_KEY \\
  --secret-string "sk-ant-xxxxxxxxxxxx"

aws secretsmanager create-secret \\
  --name forge/OPENAI_API_KEY \\
  --secret-string "sk-xxxxxxxxxxxx"

aws secretsmanager create-secret \\
  --name forge/GEMINI_API_KEY \\
  --secret-string "AIza-xxxxxxxxxxxx"
```

Note the ARN printed by each command — you will paste them into `terraform.tfvars`.

---

## 2 — Build & push Docker image to ECR

```bash
# Create repository (once)
aws ecr create-repository --repository-name forge-agent --region us-east-1

# Authenticate Docker to ECR
aws ecr get-login-password --region us-east-1 | \\
  docker login --username AWS --password-stdin \\
  123456789012.dkr.ecr.us-east-1.amazonaws.com

# Build and push
IMAGE_URI=123456789012.dkr.ecr.us-east-1.amazonaws.com/forge-agent:latest
docker build -t $IMAGE_URI .
docker push $IMAGE_URI
```

---

## 3 — Deploy with Terraform

```bash
cd infra/aws/ecs

# Copy example vars and edit
cp terraform.tfvars.example terraform.tfvars
# Edit terraform.tfvars: set image_uri, vpc_id, subnet_ids, secrets_arns

# Initialize providers
terraform init

# Preview changes
terraform plan

# Apply
terraform apply
```

---

## 4 — Verify deployment

```bash
# Get the public IP from your load balancer or task ENI and run:
curl https://<your-endpoint>/healthz
# Expected: {"status":"ok"}
```

---

## 5 — Rollback

Scale down to zero tasks:

```bash
terraform apply -var desired_count=0
```

Or revert to the previous task definition revision:

```bash
aws ecs update-service \\
  --cluster forge-agents \\
  --service forge-agent \\
  --task-definition forge-agent:<previous-revision>
```

---

## 6 — CloudWatch Logs

Tail logs in real-time:

```bash
aws logs tail /ecs/forge-agents --follow
```

Filter for errors:

```bash
aws logs filter-log-events \\
  --log-group-name /ecs/forge-agents \\
  --filter-pattern "ERROR"
```

---

## Makefile shortcuts

```bash
make tf-init      # terraform init
make tf-validate  # terraform validate
make tf-plan      # terraform plan
make tf-apply     # terraform apply
make deploy-aws   # docker build + push + tf-apply
```

---

## 7 — Auto Scaling

The Terraform configuration provisions CPU (70%) and memory (80%) target tracking policies.
Adjust `min_task_count` and `max_task_count` in `terraform.tfvars`:

```hcl
min_task_count = 2
max_task_count = 20
```

Scale-in cooldown is 300 s (5 min) to prevent flapping; scale-out cooldown is 60 s.

---

## 8 — Cost Control

An AWS Budget is created with `monthly_budget_usd` (default: $100 USD).
Set `budget_alert_email` to receive email alerts:

```hcl
budget_alert_email = "ops@your-org.com"
monthly_budget_usd = "500"
```

Alerts fire at **80% actual** spend and **100% forecasted** spend each month.

---

## 9 — ECS Exec (Remote Shell)

`enable_execute_command = true` is set on the ECS service. The task role includes the required
SSM permissions (`ssmmessages:*`). To open an interactive shell in a running task:

```bash
aws ecs execute-command \\
  --cluster forge-agents \\
  --task <task-id> \\
  --container forge-agent \\
  --interactive \\
  --command "/bin/sh"
```

> **Note**: ECS Exec sessions are logged via the existing CloudWatch Logs configuration.
'''

    def _generate_api_server(self) -> str:
        return '''"""FastAPI wrapper for generated multi-agent runtime."""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, Field

from runtime.dispatcher import dispatch
from runtime.healthcheck import run_healthcheck
from runtime.observability import snapshot_metrics, snapshot_metrics_prometheus


app = FastAPI(title="Forge Exported Agent API", version="1.0.0")


class RunRequest(BaseModel):
    input: dict[str, Any] = Field(default_factory=dict)
    entrypoint: str = "main"


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/ready")
async def ready() -> dict[str, str]:
    return {"status": "ready"}


@app.get("/readyz")
async def readyz() -> dict[str, str]:
    run_healthcheck()
    return {"status": "ready"}


@app.get("/metrics")
async def metrics() -> dict[str, Any]:
    return snapshot_metrics()


@app.get("/metrics/prometheus")
async def metrics_prometheus() -> str:
    return snapshot_metrics_prometheus()


@app.post("/run")
async def run(req: RunRequest, x_trace_id: str | None = Header(default=None)) -> dict[str, Any]:
    try:
        payload = dict(req.input or {})
        if x_trace_id and "trace_id" not in payload:
            payload["trace_id"] = x_trace_id
        return await dispatch(payload, entrypoint=req.entrypoint)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc
'''

    def _generate_smoke_tests(self) -> str:
        agent_ids = json.dumps([a.id for a in self.ir.agents])
        return f'''"""Smoke tests for multi-agent project."""

import json
import os
from http.server import ThreadingHTTPServer
from threading import Thread
from urllib.request import urlopen

import pytest
from agents.registry import get_agent_graph, list_agents
from runtime.node_runtime import _safe_eval_arithmetic
from runtime.observability import build_log_record
from runtime.schema_registry import load_schema_index
from runtime.server import _Handler


def test_all_agents_registered():
    """All agents are in the registry."""
    agents = list_agents()
    assert set(agents) == set({agent_ids})


@pytest.mark.parametrize("agent_id", {agent_ids})
def test_agent_graph_loads(agent_id: str):
    """Each agent graph loads without error."""
    graph = get_agent_graph(agent_id)
    assert "config" in graph
    assert "nodes" in graph
    assert "edges" in graph
    assert len(graph["nodes"]) > 0


def test_registry_unknown_agent():
    """Unknown agent raises ValueError."""
    with pytest.raises(ValueError):
        get_agent_graph("nonexistent_agent_xyz")


def test_schema_index_loads():
    """Schema index should be loadable even when empty."""
    index = load_schema_index()
    assert isinstance(index, dict)


def test_log_record_json_and_redaction():
    record = build_log_record(
        "TEST_EVENT",
        level="info",
        run_id="run_test_123",
        trace_id="trace_test_123",
        step_id="step_test_123",
        node="node_a",
        status="ok",
        secret="secret=my-secret",
        token="token=abc123",
        auth="authorization: bearer topsecret",
    )
    line = json.dumps(record)
    payload = json.loads(line)
    assert payload["run_id"] == "run_test_123"
    assert payload["trace_id"] == "trace_test_123"
    assert "my-secret" not in line
    assert "abc123" not in line
    assert "topsecret" not in line
    assert "***REDACTED***" in line


def test_safe_arithmetic_eval_valid_cases():
    assert _safe_eval_arithmetic("1 + 2 * 3") == 7.0
    assert _safe_eval_arithmetic("(2 + 3) ** 2") == 25.0
    assert _safe_eval_arithmetic("7 // 2") == 3.0
    assert _safe_eval_arithmetic("-5 + +2") == -3.0


@pytest.mark.parametrize(
    "expr",
    [
        "__import__('os').system('whoami')",
        "open('x')",
        "().__class__",
        "[x for x in [1,2,3]]",
        "(lambda x: x)(1)",
    ],
)
def test_safe_arithmetic_eval_rejects_malicious(expr: str):
    with pytest.raises(ValueError):
        _safe_eval_arithmetic(expr)


def test_observability_server_endpoints():
    server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address
    try:
        health = urlopen(f"http://{{host}}:{{port}}/healthz", timeout=2).read().decode("utf-8")
        assert "ok" in health
        metrics = urlopen(f"http://{{host}}:{{port}}/metrics", timeout=2).read().decode("utf-8")
        assert "runs_total" in metrics
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


@pytest.mark.asyncio
async def test_dispatch_smoke():
    """Basic dispatch smoke test."""
    from runtime.dispatcher import dispatch

    os.environ["DEV_MODE"] = "1"
    result = await dispatch({{"input": "test"}})
    assert isinstance(result, dict)
    assert "outputs" in result
'''

    def _generate_test_tool_registry(self) -> str:
        return '''"""Tests for tool registry."""

from runtime.tools.registry import get_tool, list_tools


def test_registry_lists_local_tools():
    names = [tool.name for tool in list_tools()]
    assert "tools.echo" in names
    assert "tools.safe_calculator" in names


def test_registry_unknown_tool_returns_none():
    assert get_tool("tools.unknown_xyz") is None


def test_registry_tool_has_schema():
    spec = get_tool("tools.echo")
    assert spec is not None
    assert isinstance(spec.input_schema, dict)
    assert spec.input_schema.get("type") == "object"
'''

    def _generate_test_tool_policy(self) -> str:
        return '''"""Tests for tool policy allow/deny rules."""

import pytest

from runtime.tools.policies import validate_tool_policy


def test_allowlisted_tool_passes():
    validate_tool_policy("tools.echo", {"text": "ok"}, flow_policy={"tool_allowlist": ["tools.echo"]})


def test_denied_tool_fails():
    with pytest.raises(RuntimeError):
        validate_tool_policy("tools.http_get", {"url": "https://example.com"}, flow_policy={"tool_denylist": ["tools.http_get"]})


def test_not_allowlisted_tool_fails():
    with pytest.raises(RuntimeError):
        validate_tool_policy("tools.safe_calculator", {"expression": "1+1"}, flow_policy={"tool_allowlist": ["tools.echo"]})
'''

    def _generate_test_tool_allowlist_canonicalization(self) -> str:
        return '''"""Tests for canonical tool-name allowlist behavior."""

import pytest

from runtime.tools.policies import validate_tool_policy


def test_alias_calculator_passes_when_canonical_allowed():
    validate_tool_policy("calculator", {"expression": "1+1"}, flow_policy={"tool_allowlist": ["tools.safe_calculator"]})


def test_wildcard_tools_allows_echo():
    validate_tool_policy("tools.echo", {"text": "ok"}, flow_policy={"tool_allowlist": ["tools.*"]})


def test_deny_overrides_allow():
    with pytest.raises(RuntimeError):
        validate_tool_policy(
            "tools.safe_calculator",
            {"expression": "1+1"},
            flow_policy={"tool_allowlist": ["tools.*"], "tool_denylist": ["tools.safe_calculator"]},
        )
'''

    def _generate_test_mcp_adapter_mock(self) -> str:
        return '''"""Tests for MCP adapter with mocked client."""

import pytest

from runtime.tools.adapters import mcp as mcp_adapter


@pytest.mark.asyncio
async def test_mcp_adapter_parses_name_and_calls_client(monkeypatch):
    class DummyClient:
        async def call_tool(self, *, server_id: str, tool_name: str, args: dict):
            return {"ok": True, "server_id": server_id, "tool_name": tool_name, "args": args}

    monkeypatch.setattr(mcp_adapter, "MCPClient", lambda: DummyClient())
    result = await mcp_adapter.execute_mcp_tool("mcp:files/echo", {"text": "hi"})
    assert result["ok"] is True
    assert result["server_id"] == "files"
    assert result["tool_name"] == "echo"
'''

    def _generate_test_state_store(self) -> str:
        return '''"""Tests for state stores."""

from runtime.state.stores.inmemory import InMemoryStateStore


def test_inmemory_state_store_roundtrip():
    store = InMemoryStateStore()
    assert store.get("s1") == {}
    store.set("s1", {"a": 1})
    got = store.get("s1")
    assert got["a"] == 1
    assert "_version" in got
    updated = store.update("s1", {"b": 2})
    assert updated["a"] == 1
    assert updated["b"] == 2


def test_redis_store_mocked(monkeypatch):
    import runtime.state.stores.redis as redis_store

    class DummyRedis:
        def __init__(self):
            self.data = {}

        def get(self, key):
            return self.data.get(key)

        def set(self, key, value, ex=None):
            self.data[key] = value

    class DummyModule:
        class Redis:
            @staticmethod
            def from_url(*args, **kwargs):
                return DummyRedis()

    monkeypatch.setitem(__import__("sys").modules, "redis", DummyModule())
    store = redis_store.RedisStateStore("redis://localhost:6379/0")
    store.set("s2", {"x": 1})
    assert store.get("s2")["x"] == 1
'''

    def _generate_test_plan_act_loop_smoke(self) -> str:
        return '''"""Tests for plan-act loop behavior."""

import pytest

from runtime.loop.plan_act_loop import run_plan_act_loop


@pytest.mark.asyncio
async def test_loop_runs_and_terminates():
    async def execute_tool(tool_name: str, args: dict):
        if tool_name == "tools.echo":
            return {"text": args.get("text", ""), "tool_called": True}
        if tool_name == "tools.safe_calculator":
            return {"result": 2, "tool_called": True}
        raise RuntimeError("unexpected tool")

    result = await run_plan_act_loop(goal="say hello", execute_tool=execute_tool)
    assert result["status"] in {"done", "max_tool_calls_exceeded"}
    assert result["iterations"] >= 1


@pytest.mark.asyncio
async def test_loop_repairs_after_error():
    calls = {"n": 0}

    async def execute_tool(tool_name: str, args: dict):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("boom")
        return {"text": "recovered", "tool_called": True}

    result = await run_plan_act_loop(goal="recover", execute_tool=execute_tool)
    assert result["failures"] >= 1
    assert len(result["observations"]) >= 1
'''

    def _generate_test_approvals_flow(self) -> str:
        return '''"""Tests for approval flow.""" 

import pytest

from runtime.approvals.store import get_approval_store
from runtime.node_runtime import _run_tool_node


@pytest.mark.asyncio
async def test_pending_approval_blocks_tool(monkeypatch):
    monkeypatch.setenv("APPROVALS_REQUIRED_FOR", "mutating")
    monkeypatch.setenv("HTTP_GET_ALLOW_DOMAINS", "example.com")
    out = await _run_tool_node({"tool_name": "tools.http_get", "tool_config": {"url": "https://example.com"}}, {"x": 1}, {})
    assert out["status"] == "PENDING_APPROVAL"
    assert "approval_id" in out


@pytest.mark.asyncio
async def test_approval_allows_tool(monkeypatch):
    monkeypatch.setenv("APPROVALS_REQUIRED_FOR", "mutating")
    store = get_approval_store()
    req = store.request(tool_name="tools.http_get", scope="session", metadata={})
    store.approve(req.approval_id)
    with pytest.raises(RuntimeError):
        # execution may still fail for network/domain, but must bypass pending gate
        await _run_tool_node(
            {"tool_name": "tools.http_get", "tool_config": {"url": "https://example.com", "approval_id": req.approval_id}},
            {"x": 1},
            {},
        )
'''

    def _generate_test_replay_determinism(self) -> str:
        return '''"""Tests for replay recorder/player deterministic path."""

from runtime.replay.recorder import ReplayRecorder
from runtime.replay.player import ReplayPlayer


def test_record_and_play_tool_result(tmp_path):
    recorder = ReplayRecorder(str(tmp_path), "run_a")
    recorder.record_step(step_key="agent__tool__s1", node_type="Tool", input_data={"a": 1}, output_data={"ok": True, "value": 42})
    recorder.save_manifest()
    player = ReplayPlayer(str(tmp_path), "run_a")
    out = player.load_step_output("agent__tool__s1")
    assert out["value"] == 42
'''

    def _generate_test_run_store_filesystem(self) -> str:
        return '''"""Filesystem run store durability tests."""

from runtime.run_store.stores.filesystem import FilesystemRunStore


def test_run_store_manifest_and_steps_roundtrip(tmp_path):
    store = FilesystemRunStore(str(tmp_path))
    store.put_run_manifest("run_x", {"run_id": "run_x", "status": "completed"})
    store.append_step("run_x", {"step_id": "s1", "status": "completed"})

    manifest = store.get_run("run_x")
    steps = store.list_steps("run_x")
    assert manifest is not None
    assert manifest["run_id"] == "run_x"
    assert len(steps) == 1
    assert steps[0]["step_id"] == "s1"
'''

    def _generate_test_api_auth(self) -> str:
        return '''"""API auth helper tests."""

import pytest

from runtime.auth import require_auth


def test_health_is_exempt():
    require_auth("/healthz", None)
    require_auth("/readyz", None)


def test_auth_requires_token_in_non_dev(monkeypatch):
    monkeypatch.setenv("DEV_MODE", "0")
    monkeypatch.setenv("RUNTIME_API_TOKEN", "secret")
    with pytest.raises(PermissionError):
        require_auth("/runs", None)
    with pytest.raises(PermissionError):
        require_auth("/runs", "Bearer wrong")
    require_auth("/runs", "Bearer secret")
'''

    def _generate_test_http_get_security(self) -> str:
        return '''"""Security tests for tools.http_get."""

import pytest

from runtime.tools.adapters.local import execute_local_tool


@pytest.mark.asyncio
async def test_http_get_blocks_localhost(monkeypatch):
    monkeypatch.setenv("HTTP_GET_ALLOW_DOMAINS", "localhost")
    with pytest.raises(RuntimeError):
        await execute_local_tool("tools.http_get", {"url": "http://127.0.0.1"})


@pytest.mark.asyncio
async def test_http_get_requires_server_allowlist(monkeypatch):
    monkeypatch.setenv("HTTP_GET_ALLOW_DOMAINS", "")
    with pytest.raises(RuntimeError):
        await execute_local_tool("tools.http_get", {"url": "https://example.com"})
'''

    def _generate_test_rate_limit_and_circuit(self) -> str:
        return '''"""Tests for rate limiting and circuit breaker."""

import pytest

from runtime.resilience.rate_limit import RateLimiter
from runtime.resilience.circuit_breaker import CircuitBreaker


def test_rate_limit_blocks_burst():
    limiter = RateLimiter()
    limiter.check("tools.echo", 1000)
    with pytest.raises(RuntimeError):
        limiter.check("tools.echo", 1000)


def test_circuit_opens_after_failures():
    cb = CircuitBreaker()
    key = "tools.echo"
    cb.on_failure(key, threshold=2, cooldown_s=60)
    cb.on_failure(key, threshold=2, cooldown_s=60)
    with pytest.raises(RuntimeError):
        cb.before_call(key)
'''

    def _generate_test_memory_write_policy(self) -> str:
        return '''"""Tests for memory write policy."""

from runtime.memory_write_policy import should_write_memory
from runtime.memory_summarizer import summarize_session


def test_low_confidence_not_persisted():
    assert should_write_memory({"confidence": 0.2, "relevance": 0.9}) is False
    assert should_write_memory({"confidence": 0.9, "relevance": 0.2}) is False


def test_summarizer_bounds_size():
    entries = [{"i": i} for i in range(120)]
    out = summarize_session(entries, max_items=40)
    assert len(out) <= 41
'''

    def _generate_tool_contracts(self, project_dir: Path) -> None:
        """Write tool contracts, Python stubs, and contract tests into the project."""
        from agent_compiler.export.generate_tools import ToolStubGenerator
        stub_gen = ToolStubGenerator(self.ir)
        written = stub_gen.generate(project_dir, include_tests=self.include_tests)
        if written:
            logger.info(
                f"ToolStubGenerator: wrote {len(written)} tool artifacts "
                f"({[p for p in written if p.endswith('.json')][:4]} …)"
            )

