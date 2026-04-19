"""Export service for generating production Python projects."""

import io
import json
import os
import re
import shutil
import tempfile
import uuid
import zipfile
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Literal

from agent_compiler.config import get_settings
from agent_compiler.models.ir import FlowIR, SchemaKind, SchemaRef, LLMProvider
from agent_compiler.models.ir_v2 import FlowIRv2, HandoffRule
from agent_compiler.observability.logging import get_logger
from agent_compiler.services.export_config import (
    ExportConfig,
    ExportEngine,
    ExportPackaging,
    ExportSurface,
)

logger = get_logger(__name__)
settings = get_settings()


class ExportTarget(str, Enum):
    """Export target types."""

    LANGGRAPH = "langgraph"
    RUNTIME = "runtime"
    API_SERVER = "api_server"
    AWS_ECS = "aws-ecs"


class ExportService:
    """Service for exporting flows as production Python projects."""

    def __init__(self):
        # Ensure export directory exists
        self.export_base_dir = settings.export_temp_dir
        self.export_base_dir.mkdir(parents=True, exist_ok=True)

    def export_flow(
        self,
        flow_ir: FlowIRv2,
        target: ExportTarget = ExportTarget.LANGGRAPH,
        include_tests: bool = True,
        *,
        config: ExportConfig | None = None,
    ) -> bytes:
        """Export a flow as a zipped Python project.

        Args:
            flow_ir: The flow IR to export
            target: Legacy preset target (used when config is None)
            include_tests: Whether to include test files
            config: Composable export config (takes priority over target)

        Returns:
            Bytes of the zip file
        """
        effective_config = config if config is not None else ExportConfig.from_preset(target.value)
        effective_config.validate_composition()

        # Create temporary directory
        with tempfile.TemporaryDirectory() as temp_dir:
            project_dir = Path(temp_dir) / "exported"
            project_dir.mkdir()

            materialized_dir = Path(temp_dir) / "_materialized_schemas"
            materialized_dir.mkdir(parents=True, exist_ok=True)
            prepared_ir = self._prepare_export_ir(flow_ir, materialized_dir)

            # v2-only export path
            self._validate_multiagent_export(prepared_ir)
            self._export_multiagent(project_dir, prepared_ir, config=effective_config, include_tests=include_tests)

            # Create zip file
            zip_buffer = io.BytesIO()
            with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
                for file_path in project_dir.rglob("*"):
                    if file_path.is_file():
                        if not self._should_include_in_zip(file_path, project_dir):
                            continue
                        arcname = file_path.relative_to(project_dir)
                        zf.write(file_path, arcname)

            return zip_buffer.getvalue()

    def export_flow_persistent(
        self,
        flow_ir: FlowIRv2,
        export_id: str | None = None,
        target: ExportTarget = ExportTarget.LANGGRAPH,
        include_tests: bool = True,
        *,
        config: ExportConfig | None = None,
    ) -> tuple[Path, Path]:
        """Export a flow and persist it to disk.

        Args:
            flow_ir: The flow IR to export
            export_id: Optional export ID (generates one if not provided)
            target: Legacy preset target (used when config is None)
            include_tests: Whether to include test files
            config: Composable export config (takes priority over target)

        Returns:
            Tuple of (export_dir_path, zip_path)
        """
        effective_config = config if config is not None else ExportConfig.from_preset(target.value)
        effective_config.validate_composition()

        if export_id is None:
            export_id = str(uuid.uuid4())

        # Create persistent export directory
        export_dir = self.export_base_dir / export_id / "exported"
        export_dir.mkdir(parents=True, exist_ok=True)

        materialized_dir = self.export_base_dir / export_id / "_materialized_schemas"
        materialized_dir.mkdir(parents=True, exist_ok=True)
        prepared_ir = self._prepare_export_ir(flow_ir, materialized_dir)

        # v2-only export path
        self._validate_multiagent_export(prepared_ir)
        self._export_multiagent(export_dir, prepared_ir, config=effective_config, include_tests=include_tests)

        # Create ZIP file
        zip_filename = self._build_zip_filename(flow_ir, effective_config)
        zip_path = self.export_base_dir / export_id / zip_filename
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for file_path in export_dir.rglob("*"):
                if file_path.is_file():
                    if not self._should_include_in_zip(file_path, export_dir):
                        continue
                    arcname = file_path.relative_to(export_dir)
                    zf.write(file_path, arcname)

        logger.info(f"Created persistent export ({effective_config.cache_key}): {export_id} at {export_dir}")
        return export_dir, zip_path

    def _build_zip_filename(self, flow_ir: FlowIRv2, config: ExportConfig) -> str:
        """Build portable zip filename with target + date: <name>_export_<target>_DD_MM_YYYY.zip."""
        raw_name = (
            str(getattr(flow_ir.flow, "name", "")).strip()
            or str(getattr(flow_ir.flow, "id", "")).strip()
            or "forge_export"
        )
        # Keep alnum, dash and underscore; normalize spaces/other symbols to underscore.
        safe_name = re.sub(r"[^A-Za-z0-9_-]+", "_", raw_name).strip("_") or "forge_export"
        safe_target = re.sub(r"[^A-Za-z0-9_-]+", "_", config.cache_key).strip("_") or "target"
        date_suffix = datetime.now().strftime("%d_%m_%Y")
        return f"{safe_name}_export_{safe_target}_{date_suffix}.zip"

    def _should_include_in_zip(self, file_path: Path, project_root: Path) -> bool:
        """Exclude transient files/caches from exported zip artifacts."""
        relative_parts = set(file_path.relative_to(project_root).parts)
        excluded_dirs = {".pytest_cache", ".mypy_cache", ".ruff_cache", "__pycache__", ".venv"}
        if relative_parts & excluded_dirs:
            return False
        if file_path.suffix in {".pyc", ".pyo", ".pyd"}:
            return False
        return True

    def cleanup_export(self, export_id: str) -> bool:
        """Clean up an export directory.

        Args:
            export_id: The export ID to clean up

        Returns:
            True if cleanup successful
        """
        export_path = self.export_base_dir / export_id
        if export_path.exists():
            shutil.rmtree(export_path)
            logger.info(f"Cleaned up export: {export_id}")
            return True
        return False

    def _validate_multiagent_export(self, ir: FlowIRv2) -> None:
        """Fail-fast validation for multi-agent export."""
        # Validate tool references against the contract registry (soft-fail: warn only).
        # We use allow_unknown=True so exports still succeed for contract-only tools;
        # stubs will be generated instead.
        try:
            from agent_compiler.ir.validate import validate_tool_references
            warnings = validate_tool_references(ir, allow_unknown=True)
            for w in warnings:
                logger.warning(f"[tool-contract] {w}")
        except Exception as exc:  # pragma: no cover
            logger.warning(f"Tool reference validation skipped: {exc}")

        agent_ids = {a.id for a in ir.agents}
        supported_providers = {p.value for p in LLMProvider}

        # Validate handoff references
        for h in ir.handoffs:
            if h.from_agent_id not in agent_ids:
                raise ValueError(
                    f"Handoff references unknown agent: {h.from_agent_id}"
                )
            if h.to_agent_id not in agent_ids:
                raise ValueError(
                    f"Handoff references unknown agent: {h.to_agent_id}"
                )

        # Validate entrypoint references
        for ep in ir.entrypoints:
            if ep.agent_id not in agent_ids:
                raise ValueError(
                    f"Entrypoint '{ep.name}' references unknown agent: {ep.agent_id}"
                )

        # Validate each agent has at least one node
        for agent in ir.agents:
            if not agent.graph.nodes:
                raise ValueError(
                    f"Agent '{agent.id}' has no nodes"
                )
            if agent.fallbacks:
                for idx, binding in enumerate(agent.fallbacks.llm_chain):
                    provider = str(binding.get("provider", "auto"))
                    if provider not in supported_providers:
                        raise ValueError(
                            f"Agent '{agent.id}' fallback llm_chain[{idx}] uses unsupported provider '{provider}'"
                        )

            for node in agent.graph.nodes:
                params = node.params if isinstance(node.params, dict) else {}
                for schema_key in ("input_schema", "output_schema"):
                    self._validate_schema_ref(
                        params.get(schema_key),
                        location=f"agent '{agent.id}' node '{node.id}' {schema_key}",
                        resources=ir.resources,
                    )

        for idx, handoff in enumerate(ir.handoffs):
            self._validate_schema_ref(
                handoff.input_schema,
                location=f"handoff[{idx}] input_schema",
                resources=ir.resources,
            )
            self._validate_schema_ref(
                handoff.output_schema,
                location=f"handoff[{idx}] output_schema",
                resources=ir.resources,
            )

    def _validate_schema_ref(
        self,
        schema_ref: Any,
        *,
        location: str,
        resources: Any | None = None,
    ) -> None:
        """Validate schema references and enforce fail-fast for unresolved refs."""
        if schema_ref is None:
            return

        ref_obj: SchemaRef
        if isinstance(schema_ref, SchemaRef):
            ref_obj = schema_ref
        elif isinstance(schema_ref, dict):
            ref_obj = SchemaRef.model_validate(schema_ref)
        else:
            raise ValueError(f"Invalid schema ref in {location}: expected object")

        if ref_obj.kind == "json_schema":
            if str(ref_obj.ref).startswith("schema://"):
                schema_id = str(ref_obj.ref).replace("schema://", "", 1).strip()
                contracts = getattr(resources, "schema_contracts", {}) if resources is not None else {}
                if not schema_id or schema_id not in contracts:
                    raise ValueError(
                        f"Missing schema id for {location}: '{ref_obj.ref}'"
                    )
                return
            schema_path = Path(ref_obj.ref)
            if not schema_path.exists():
                raise ValueError(
                    f"Missing schema file for {location}: '{ref_obj.ref}'"
                )
            return

        raise ValueError(
            f"Unsupported schema kind '{ref_obj.kind}' in {location}. "
            "Use json_schema refs for export."
        )

    def _prepare_export_ir(self, ir: FlowIRv2, materialized_dir: Path) -> FlowIRv2:
        """Normalize schema refs to json_schema and materialize all required files."""
        ir_copy = ir.model_copy(deep=True)
        schema_contracts = (
            ir_copy.resources.schema_contracts if getattr(ir_copy, "resources", None) is not None else {}
        )

        for idx, handoff in enumerate(ir_copy.handoffs):
            if isinstance(handoff, dict):
                handoff = HandoffRule.model_validate(handoff)
                ir_copy.handoffs[idx] = handoff
            handoff.input_schema = self._normalize_schema_ref_for_export(
                handoff.input_schema,
                location=f"handoff[{idx}] input_schema",
                materialized_dir=materialized_dir,
                schema_contracts=schema_contracts,
            )
            handoff.output_schema = self._normalize_schema_ref_for_export(
                handoff.output_schema,
                location=f"handoff[{idx}] output_schema",
                materialized_dir=materialized_dir,
                schema_contracts=schema_contracts,
            )

        for agent in ir_copy.agents:
            for node in agent.graph.nodes:
                params = node.params if isinstance(node.params, dict) else {}
                for schema_key in ("input_schema", "output_schema"):
                    if schema_key not in params:
                        continue
                    normalized = self._normalize_schema_ref_for_export(
                        params.get(schema_key),
                        location=f"agent '{agent.id}' node '{node.id}' {schema_key}",
                        materialized_dir=materialized_dir,
                        schema_contracts=schema_contracts,
                    )
                    params[schema_key] = normalized.model_dump() if normalized is not None else None

        return ir_copy

    def _normalize_schema_ref_for_export(
        self,
        schema_ref: Any,
        *,
        location: str,
        materialized_dir: Path,
        schema_contracts: dict[str, dict[str, Any]] | None = None,
    ) -> SchemaRef | None:
        """Convert supported schema refs into materialized json_schema refs."""
        if schema_ref is None:
            return None

        ref_obj: SchemaRef
        if isinstance(schema_ref, SchemaRef):
            ref_obj = schema_ref
        elif isinstance(schema_ref, dict):
            ref_obj = SchemaRef.model_validate(schema_ref)
        else:
            raise ValueError(f"Invalid schema ref in {location}: expected object")

        if ref_obj.kind == SchemaKind.JSON_SCHEMA:
            if str(ref_obj.ref).startswith("schema://"):
                schema_id = str(ref_obj.ref).replace("schema://", "", 1).strip()
                contracts = schema_contracts or {}
                schema_obj = contracts.get(schema_id)
                if not schema_id or not isinstance(schema_obj, dict):
                    raise ValueError(
                        f"Missing schema id for {location}: '{ref_obj.ref}'"
                    )
                safe_name = f"{schema_id.replace('/', '_').replace('.', '_')}.schema.json"
                out_path = materialized_dir / safe_name
                out_path.write_text(json.dumps(schema_obj, indent=2), encoding="utf-8")
                return SchemaRef(kind=SchemaKind.JSON_SCHEMA, ref=str(out_path))
            schema_path = Path(ref_obj.ref)
            if not schema_path.exists():
                raise ValueError(
                    f"Missing schema file for {location}: '{ref_obj.ref}'"
                )
            return ref_obj

        # pydantic/zod contract refs can be materialized only for known contracts.
        builtin_contracts: dict[str, dict[str, Any]] = {
            "contracts.HandoffInput": {
                "type": "object",
                "required": ["input"],
                "properties": {"input": {}},
                "additionalProperties": True,
            },
            "contracts.HandoffOutput": {
                "type": "object",
                "required": ["result"],
                "properties": {"result": {}},
                "additionalProperties": True,
            },
        }
        schema = builtin_contracts.get(ref_obj.ref)
        if schema is None:
            raise ValueError(
                f"Unsupported {ref_obj.kind.value} schema ref in {location}: '{ref_obj.ref}'. "
                "Provide a json_schema ref for export."
            )

        safe_name = ref_obj.ref.replace(".", "_").replace("/", "_")
        out_path = materialized_dir / f"{safe_name}.schema.json"
        out_path.write_text(json.dumps(schema, indent=2), encoding="utf-8")
        return SchemaRef(kind=SchemaKind.JSON_SCHEMA, ref=str(out_path))

    def _export_multiagent(
        self,
        project_dir: Path,
        ir: FlowIRv2,
        config: ExportConfig,
        include_tests: bool = True,
    ) -> None:
        """Generate a multi-agent project using MultiAgentGenerator."""
        from agent_compiler.services.multiagent_generator import MultiAgentGenerator

        generator = MultiAgentGenerator(ir, include_tests=include_tests, config=config)
        generator.generate(project_dir)

    def _generate_langgraph_project(
        self,
        project_dir: Path,
        flow_ir: FlowIR,
        include_tests: bool = True,
    ) -> None:
        """Generate a LangGraph-based project structure."""
        from agent_compiler.services.langgraph_generator import LangGraphGenerator

        generator = LangGraphGenerator(flow_ir, include_tests=include_tests)
        generator.generate(project_dir)

    def _generate_api_server_project(self, project_dir: Path, flow_ir: FlowIR) -> None:
        """Generate a FastAPI-based API server project for the flow."""
        # First generate the base runtime project
        self._generate_project_structure(project_dir, flow_ir)

        # Add API server file
        api_py = '''"""Auto-generated FastAPI API server for {flow_name}."""

import json
import os
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

app = FastAPI(
    title="{flow_name} API",
    description="Auto-generated API server for the {flow_name} agent.",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class ChatRequest(BaseModel):
    """Request body for chat endpoint."""
    message: str = Field(..., min_length=1)
    conversation_id: str | None = None


class ChatResponse(BaseModel):
    """Response body for chat endpoint."""
    response: str
    conversation_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class RunRequest(BaseModel):
    """Request body for run endpoint."""
    input: dict[str, Any] = Field(default_factory=dict)


class RunResponse(BaseModel):
    """Response body for run endpoint."""
    output: dict[str, Any]
    status: str
    metadata: dict[str, Any] = Field(default_factory=dict)


@app.get("/health")
async def health():
    """Health check."""
    return {{"status": "healthy", "flow": "{flow_name}"}}


@app.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest):
    """Chat with the agent."""
    from src.agent_app.main import run_flow

    try:
        result = run_flow({{"input": req.message}})
        # Extract output text
        output_text = str(result.get("output", result))
        return ChatResponse(
            response=output_text,
            conversation_id=req.conversation_id,
            metadata={{"raw_output": result}},
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/run", response_model=RunResponse)
async def run(req: RunRequest):
    """Run the flow with custom input."""
    from src.agent_app.main import run_flow

    try:
        result = run_flow(req.input)
        return RunResponse(
            output=result if isinstance(result, dict) else {{"output": result}},
            status="completed",
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)
'''.format(flow_name=flow_ir.flow.name)

        (project_dir / "api.py").write_text(api_py)

        # Add Dockerfile
        dockerfile = '''FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8080

CMD ["uvicorn", "api:app", "--host", "0.0.0.0", "--port", "8080"]
'''
        (project_dir / "Dockerfile").write_text(dockerfile)

        # Add docker-compose
        docker_compose = '''version: "3.8"

services:
  agent-api:
    build: .
    ports:
      - "8080:8080"
    env_file:
      - .env
    restart: unless-stopped
'''
        (project_dir / "docker-compose.yml").write_text(docker_compose)

        # Update requirements to include fastapi + uvicorn
        req_path = project_dir / "requirements.txt"
        existing = req_path.read_text() if req_path.exists() else ""
        if "fastapi" not in existing:
            existing += "\nfastapi>=0.100.0\nuvicorn[standard]>=0.20.0\n"
            req_path.write_text(existing)

        # Update README
        readme_path = project_dir / "README.md"
        existing_readme = readme_path.read_text() if readme_path.exists() else ""
        api_readme = f"""

## API Server

This project includes a FastAPI API server.

### Run locally

```bash
pip install -r requirements.txt
python api.py
```

Server starts at http://localhost:8080

### Endpoints

- `GET /health` — Health check
- `POST /chat` — Chat with the agent ({{"message": "Hello"}})
- `POST /run` — Run with custom input ({{"input": {{"key": "value"}}}})

### Docker

```bash
docker compose up --build
```
"""
        readme_path.write_text(existing_readme + api_readme)

        logger.info(f"Generated API server project for: {flow_ir.flow.name}")

    def _generate_project_structure(self, project_dir: Path, flow_ir: FlowIR) -> None:
        """Generate the complete project structure."""
        # Create directories
        src_dir = project_dir / "src" / "agent_app"
        adapters_dir = src_dir / "adapters"
        tests_dir = project_dir / "tests"

        src_dir.mkdir(parents=True)
        adapters_dir.mkdir()
        tests_dir.mkdir()

        # Generate all files
        self._write_file(project_dir / "pyproject.toml", self._generate_pyproject(flow_ir))
        self._write_file(project_dir / "README.md", self._generate_readme(flow_ir))
        self._write_file(src_dir / "__init__.py", self._generate_init(flow_ir))
        self._write_file(src_dir / "ir.py", self._generate_ir_module(flow_ir))
        self._write_file(src_dir / "runtime.py", self._generate_runtime_module())
        self._write_file(adapters_dir / "__init__.py", self._generate_adapters_init())
        self._write_file(adapters_dir / "langchain_adapter.py", self._generate_langchain_adapter())
        self._write_file(adapters_dir / "llamaindex_adapter.py", self._generate_llamaindex_adapter())
        self._write_file(src_dir / "main.py", self._generate_main(flow_ir))
        self._write_file(tests_dir / "__init__.py", "")
        self._write_file(tests_dir / "test_flow_smoke.py", self._generate_smoke_test(flow_ir))

    def _write_file(self, path: Path, content: str) -> None:
        """Write content to a file."""
        path.write_text(content, encoding="utf-8")

    def _generate_pyproject(self, flow_ir: FlowIR) -> str:
        """Generate pyproject.toml."""
        return f'''[project]
name = "{flow_ir.flow.id}-agent"
version = "{flow_ir.flow.version}"
description = "{flow_ir.flow.description or flow_ir.flow.name}"
requires-python = ">=3.11"

dependencies = [
    "pydantic>=2.5.0",
]

[project.optional-dependencies]
langchain = [
    "langchain>=0.1.0",
    "langchain-openai>=0.0.5",
    "langchain-google-genai>=1.0.0",
]
llamaindex = [
    "llama-index>=0.10.0",
    "llama-index-llms-openai>=0.1.0",
]
all = [
    "{flow_ir.flow.id}-agent[langchain,llamaindex]",
]
dev = [
    "pytest>=7.4.0",
    "pytest-asyncio>=0.23.0",
]

[project.scripts]
run-agent = "agent_app.main:main"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/agent_app"]

[tool.pytest.ini_options]
asyncio_mode = "auto"
'''

    def _generate_readme(self, flow_ir: FlowIR) -> str:
        """Generate README.md."""
        node_types = [n.type.value for n in flow_ir.nodes]
        return f'''# {flow_ir.flow.name}

{flow_ir.flow.description or "An AI agent flow exported from Agent Compiler."}

## Version
{flow_ir.flow.version}

## Flow Structure
- **Nodes**: {len(flow_ir.nodes)} ({", ".join(set(node_types))})
- **Edges**: {len(flow_ir.edges)}
- **Engine Preference**: {flow_ir.flow.engine_preference.value}

## Setup

1. Install dependencies:
```bash
pip install -e ".[all]"
```

2. Set your API key:
```bash
# For OpenAI models (gpt-3.5-turbo, gpt-4o, etc.):
export OPENAI_API_KEY="your-key-here"

# For Gemini models (gemini-1.5-pro, gemini-1.5-flash, etc.):
export GOOGLE_API_KEY="your-key-here"
```

## Usage

### Command Line
```bash
run-agent "Your input here"
```

### Python
```python
import asyncio
from agent_app.main import run_flow

result = asyncio.run(run_flow({{"input": "Your input here"}}))
print(result)
```

## Testing
```bash
pytest tests/
```

## Generated by Agent Compiler
This project was automatically generated from a flow definition.
'''

    def _generate_init(self, flow_ir: FlowIR) -> str:
        """Generate __init__.py."""
        return f'''"""
{flow_ir.flow.name} - AI Agent Application

Generated by Agent Compiler.
"""

__version__ = "{flow_ir.flow.version}"
'''

    def _generate_ir_module(self, flow_ir: FlowIR) -> str:
        """Generate ir.py with the embedded flow definition."""
        ir_json = json.dumps(flow_ir.model_dump(), indent=2)
        return f'''"""Flow IR definition."""

import json
from typing import Any

# Embedded flow IR
FLOW_IR_JSON = """
{ir_json}
"""

def get_flow_ir() -> dict[str, Any]:
    """Get the flow IR as a dictionary."""
    return json.loads(FLOW_IR_JSON)


def get_node(node_id: str) -> dict[str, Any] | None:
    """Get a node by ID."""
    ir = get_flow_ir()
    for node in ir["nodes"]:
        if node["id"] == node_id:
            return node
    return None


def get_topological_order() -> list[str]:
    """Get nodes in topological order."""
    ir = get_flow_ir()
    nodes = {{n["id"] for n in ir["nodes"]}}
    adjacency: dict[str, list[str]] = {{nid: [] for nid in nodes}}

    for edge in ir["edges"]:
        adjacency[edge["source"]].append(edge["target"])

    in_degree: dict[str, int] = {{nid: 0 for nid in nodes}}
    for edge in ir["edges"]:
        in_degree[edge["target"]] += 1

    queue = [nid for nid, deg in in_degree.items() if deg == 0]
    result: list[str] = []

    while queue:
        queue.sort()
        node = queue.pop(0)
        result.append(node)
        for neighbor in adjacency[node]:
            in_degree[neighbor] -= 1
            if in_degree[neighbor] == 0:
                queue.append(neighbor)

    return result
'''

    def _generate_runtime_module(self) -> str:
        """Generate runtime.py."""
        return '''"""Runtime execution for the agent flow."""

import os
from dataclasses import dataclass, field
from typing import Any

from agent_app.ir import get_flow_ir, get_node, get_topological_order


@dataclass
class RetrievalResult:
    """Result from retrieval."""
    content: str
    source: str
    score: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_citation(self) -> str:
        return f"[Source: {self.source}] {self.content}"


@dataclass
class ExecutionContext:
    """Context for flow execution."""
    user_input: dict[str, Any] = field(default_factory=dict)
    node_outputs: dict[str, Any] = field(default_factory=dict)
    retrieved_docs: list[RetrievalResult] = field(default_factory=list)
    current_value: Any = None
    variables: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if "input" in self.user_input and self.current_value is None:
            self.current_value = self.user_input["input"]

    def set_node_output(self, node_id: str, output: Any) -> None:
        self.node_outputs[node_id] = output
        self.current_value = output

    def get_citations_context(self) -> str:
        if not self.retrieved_docs:
            return ""
        return "\\n\\n".join(
            f"[{i}] {doc.to_citation()}"
            for i, doc in enumerate(self.retrieved_docs, 1)
        )

    def has_relevant_docs(self, threshold: float = 0.3) -> bool:
        return any(doc.score >= threshold for doc in self.retrieved_docs)

    def render_template(self, template: str) -> str:
        context = {
            "input": self.user_input.get("input", ""),
            "current": str(self.current_value) if self.current_value else "",
            "citations": self.get_citations_context(),
            **self.variables,
        }
        for node_id, output in self.node_outputs.items():
            context[f"node.{node_id}"] = str(output) if output else ""

        result = template
        for key, value in context.items():
            result = result.replace(f"{{{key}}}", str(value))
        return result


def get_adapter(engine: str):
    """Get the appropriate engine adapter."""
    if engine == "llamaindex":
        from agent_app.adapters.llamaindex_adapter import LlamaIndexAdapter
        return LlamaIndexAdapter()
    else:
        from agent_app.adapters.langchain_adapter import LangChainAdapter
        return LangChainAdapter()


async def execute_node(
    node: dict[str, Any],
    context: ExecutionContext,
    flow_engine: str,
) -> dict[str, Any]:
    """Execute a single node."""
    node_type = node["type"]
    params = node.get("params", {})
    engine = params.get("engine") or flow_engine

    # Auto engine selection
    if engine == "auto":
        engine = "llamaindex" if node_type == "Retriever" else "langchain"

    adapter = get_adapter(engine)

    if node_type == "LLM":
        return await _execute_llm(node, context, adapter)
    elif node_type == "Retriever":
        return await _execute_retriever(node, context, adapter)
    elif node_type == "Tool":
        return await _execute_tool(node, context, adapter)
    elif node_type == "Router":
        return _execute_router(node, context)
    elif node_type == "Memory":
        return _execute_memory(node, context)
    elif node_type == "Output":
        return _execute_output(node, context)
    else:
        raise ValueError(f"Unknown node type: {node_type}")


async def _execute_llm(
    node: dict[str, Any],
    context: ExecutionContext,
    adapter,
) -> dict[str, Any]:
    """Execute LLM node."""
    params = node.get("params", {})
    prompt_template = params.get("prompt_template", "{input}")
    prompt = context.render_template(prompt_template)

    # Check for abstain if retrieval was done
    if context.retrieved_docs and not context.has_relevant_docs():
        return {
            "output": "I don't have enough relevant information. Could you provide more context?",
            "abstained": True,
        }

    # Inject citations if available
    if context.retrieved_docs:
        citations = context.get_citations_context()
        prompt = f"Context from retrieved documents:\\n{citations}\\n\\n{prompt}"

    system_prompt = params.get("system_prompt")
    if system_prompt:
        system_prompt = context.render_template(system_prompt)

    response = await adapter.run_llm(
        prompt=prompt,
        model=params.get("model", "gpt-3.5-turbo"),
        temperature=params.get("temperature", 0.7),
        system_prompt=system_prompt,
        max_tokens=params.get("max_tokens"),
    )

    return {"output": response.content, "model": response.model}


async def _execute_retriever(
    node: dict[str, Any],
    context: ExecutionContext,
    adapter,
) -> dict[str, Any]:
    """Execute Retriever node."""
    params = node.get("params", {})
    query_template = params.get("query_template", "{input}")
    query = context.render_template(query_template)

    docs = await adapter.retrieve(
        query=query,
        top_k=params.get("top_k", 5),
        index_name=params.get("index_name"),
        index_config=params.get("index_config"),
    )

    context.retrieved_docs.extend(docs)

    return {
        "documents": [{"content": d.content, "source": d.source, "score": d.score} for d in docs],
        "num_documents": len(docs),
    }


async def _execute_tool(
    node: dict[str, Any],
    context: ExecutionContext,
    adapter,
) -> dict[str, Any]:
    """Execute Tool node."""
    params = node.get("params", {})
    tool_input = {"input": context.current_value, **context.variables}

    result = await adapter.run_tool(
        tool_name=params["tool_name"],
        tool_input=tool_input,
        tool_config=params.get("tool_config"),
    )

    return {"result": result}


def _execute_router(
    node: dict[str, Any],
    context: ExecutionContext,
) -> dict[str, Any]:
    """Execute Router node."""
    params = node.get("params", {})
    current = str(context.current_value).lower() if context.current_value else ""

    selected = params.get("default_route")
    for condition, target in params.get("routes", {}).items():
        if condition.lower() in current:
            selected = target
            break

    return {"selected_route": selected}


def _execute_memory(
    node: dict[str, Any],
    context: ExecutionContext,
) -> dict[str, Any]:
    """Execute Memory node."""
    params = node.get("params", {})
    return {
        "memory_stored": {
            "type": params.get("memory_type", "buffer"),
            "content": str(context.current_value),
        }
    }


def _execute_output(
    node: dict[str, Any],
    context: ExecutionContext,
) -> dict[str, Any]:
    """Execute Output node."""
    params = node.get("params", {})
    output_template = params.get("output_template", "{result}")
    output = context.render_template(output_template)

    return {"output": output, "format": params.get("format", "text")}


async def run_flow(input_data: dict[str, Any]) -> dict[str, Any]:
    """Run the flow with given input."""
    ir = get_flow_ir()
    flow = ir["flow"]
    flow_engine = flow.get("engine_preference", "langchain")

    context = ExecutionContext(user_input=input_data)
    execution_order = get_topological_order()

    results: dict[str, Any] = {}

    for node_id in execution_order:
        node = get_node(node_id)
        if node is None:
            raise ValueError(f"Node not found: {node_id}")

        output = await execute_node(node, context, flow_engine)
        context.set_node_output(node_id, output)
        results[node_id] = output

    return {
        "final_output": context.current_value,
        "node_outputs": results,
    }
'''

    def _generate_adapters_init(self) -> str:
        """Generate adapters/__init__.py."""
        return '''"""Engine adapters."""

from agent_app.adapters.langchain_adapter import LangChainAdapter
from agent_app.adapters.llamaindex_adapter import LlamaIndexAdapter

__all__ = ["LangChainAdapter", "LlamaIndexAdapter"]
'''

    def _generate_langchain_adapter(self) -> str:
        """Generate langchain_adapter.py (multi-provider)."""
        return '''"""LangChain adapter — supports OpenAI and Gemini.

Provider is auto-detected from the model name (gemini* -> Gemini, else -> OpenAI).
"""

import os
from dataclasses import dataclass, field
from typing import Any


@dataclass
class LLMResponse:
    content: str
    model: str
    tokens_used: int | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class RetrievalResult:
    content: str
    source: str
    score: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
#  Provider-aware model factory
# ---------------------------------------------------------------------------

def _infer_provider(model: str) -> str:
    """Return 'gemini' when model starts with 'gemini', else 'openai'."""
    return "gemini" if model.lower().startswith("gemini") else "openai"


def build_chat_model(
    *,
    model: str = "gpt-3.5-turbo",
    temperature: float = 0.7,
    max_tokens: int | None = None,
) -> Any:
    """Build a LangChain chat model for the detected provider."""
    provider = _infer_provider(model)

    if provider == "gemini":
        try:
            from langchain_google_genai import ChatGoogleGenerativeAI
        except ImportError:
            raise RuntimeError(
                "Gemini provider selected but langchain-google-genai is not installed. "
                "Install with:  pip install langchain-google-genai"
            )
        api_key = os.environ.get("GOOGLE_API_KEY", "")
        if not api_key:
            raise RuntimeError(
                "Gemini provider selected but GOOGLE_API_KEY is not set."
            )
        kwargs: dict[str, Any] = {
            "model": model,
            "temperature": temperature,
            "google_api_key": api_key,
        }
        if max_tokens is not None:
            kwargs["max_output_tokens"] = max_tokens
        return ChatGoogleGenerativeAI(**kwargs)

    # --- OpenAI (default) ---
    try:
        from langchain_openai import ChatOpenAI
    except ImportError:
        try:
            from langchain.chat_models import ChatOpenAI
        except ImportError:
            raise RuntimeError(
                "OpenAI provider selected but langchain-openai is not installed. "
                "Install with:  pip install langchain-openai"
            )
    api_key = os.environ.get("OPENAI_API_KEY", "")
    if not api_key:
        raise RuntimeError(
            "OpenAI provider selected but OPENAI_API_KEY is not set."
        )
    kwargs = {
        "model": model,
        "temperature": temperature,
        "api_key": api_key,
    }
    if max_tokens is not None:
        kwargs["max_tokens"] = max_tokens
    return ChatOpenAI(**kwargs)


# ---------------------------------------------------------------------------
#  Adapter
# ---------------------------------------------------------------------------

class LangChainAdapter:
    """Adapter for LangChain engine (multi-provider)."""

    @property
    def name(self) -> str:
        return "langchain"

    def is_available(self) -> bool:
        try:
            import langchain
            return True
        except ImportError:
            return False

    async def run_llm(
        self,
        prompt: str,
        model: str = "gpt-3.5-turbo",
        temperature: float = 0.7,
        system_prompt: str | None = None,
        max_tokens: int | None = None,
    ) -> LLMResponse:
        """Run an LLM using LangChain (OpenAI or Gemini)."""
        if not self.is_available():
            raise RuntimeError(
                "LangChain is not installed. "
                "Install with: pip install langchain langchain-openai"
            )

        try:
            from langchain_core.messages import HumanMessage, SystemMessage
        except ImportError:
            from langchain.schema import HumanMessage, SystemMessage

        messages = []
        if system_prompt:
            messages.append(SystemMessage(content=system_prompt))
        messages.append(HumanMessage(content=prompt))

        llm = build_chat_model(
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
        )

        response = await llm.ainvoke(messages)

        tokens = None
        if hasattr(response, "response_metadata"):
            tokens = response.response_metadata.get(
                "token_usage", {}
            ).get("total_tokens")

        return LLMResponse(
            content=response.content,
            model=model,
            tokens_used=tokens,
        )

    async def retrieve(
        self,
        query: str,
        top_k: int = 5,
        index_name: str | None = None,
        index_config: dict[str, Any] | None = None,
    ) -> list[RetrievalResult]:
        """Retrieve documents using LangChain."""
        # Placeholder - implement with your vector store
        return [
            RetrievalResult(
                content=f"Document for: {query}",
                source="placeholder",
                score=0.5,
            )
        ]

    async def run_tool(
        self,
        tool_name: str,
        tool_input: dict[str, Any],
        tool_config: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Execute a tool."""
        return {"tool_name": tool_name, "input": tool_input, "result": "placeholder"}
'''

    def _generate_llamaindex_adapter(self) -> str:
        """Generate llamaindex_adapter.py."""
        return '''"""LlamaIndex adapter."""

import os
from dataclasses import dataclass, field
from typing import Any


@dataclass
class LLMResponse:
    content: str
    model: str
    tokens_used: int | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class RetrievalResult:
    content: str
    source: str
    score: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)


class LlamaIndexAdapter:
    """Adapter for LlamaIndex engine."""

    @property
    def name(self) -> str:
        return "llamaindex"

    def is_available(self) -> bool:
        try:
            import llama_index
            return True
        except ImportError:
            return False

    async def run_llm(
        self,
        prompt: str,
        model: str = "gpt-3.5-turbo",
        temperature: float = 0.7,
        system_prompt: str | None = None,
        max_tokens: int | None = None,
    ) -> LLMResponse:
        """Run an LLM using LlamaIndex."""
        if not self.is_available():
            raise RuntimeError("LlamaIndex not installed")

        try:
            from llama_index.llms.openai import OpenAI
            from llama_index.core.llms import ChatMessage, MessageRole
        except ImportError:
            from llama_index.llms import OpenAI
            from llama_index.llms.base import ChatMessage, MessageRole

        messages = []
        if system_prompt:
            messages.append(ChatMessage(role=MessageRole.SYSTEM, content=system_prompt))
        messages.append(ChatMessage(role=MessageRole.USER, content=prompt))

        llm = OpenAI(
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            api_key=os.environ.get("OPENAI_API_KEY"),
        )

        response = await llm.achat(messages)

        return LLMResponse(
            content=response.message.content,
            model=model,
        )

    async def retrieve(
        self,
        query: str,
        top_k: int = 5,
        index_name: str | None = None,
        index_config: dict[str, Any] | None = None,
    ) -> list[RetrievalResult]:
        """Retrieve documents using LlamaIndex."""
        # Placeholder - implement with your vector store
        return [
            RetrievalResult(
                content=f"Document for: {query}",
                source="placeholder",
                score=0.5,
            )
        ]

    async def run_tool(
        self,
        tool_name: str,
        tool_input: dict[str, Any],
        tool_config: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Execute a tool."""
        return {"tool_name": tool_name, "input": tool_input, "result": "placeholder"}
'''

    def _generate_main(self, flow_ir: FlowIR) -> str:
        """Generate main.py."""
        return f'''#!/usr/bin/env python3
"""
CLI entry point for {flow_ir.flow.name}.

Usage:
    run-agent "Your input here"
    python -m agent_app.main "Your input here"
"""

import argparse
import asyncio
import json
import sys

from agent_app.runtime import run_flow


def main() -> None:
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="{flow_ir.flow.description or flow_ir.flow.name}"
    )
    parser.add_argument(
        "input",
        nargs="?",
        help="Input text for the agent",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output result as JSON",
    )
    parser.add_argument(
        "--input-file",
        "-f",
        help="Read input from a JSON file",
    )

    args = parser.parse_args()

    # Get input data
    if args.input_file:
        with open(args.input_file) as f:
            input_data = json.load(f)
    elif args.input:
        input_data = {{"input": args.input}}
    else:
        # Read from stdin if no input provided
        print("Enter input (Ctrl+D to finish):", file=sys.stderr)
        input_data = {{"input": sys.stdin.read().strip()}}

    # Run the flow
    try:
        result = asyncio.run(run_flow(input_data))

        if args.json:
            print(json.dumps(result, indent=2))
        else:
            # Print just the final output for human-readable mode
            final = result.get("final_output")
            if isinstance(final, dict):
                output = final.get("output", final)
            else:
                output = final
            print(output)
    except Exception as e:
        print(f"Error: {{e}}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
'''

    def _generate_smoke_test(self, flow_ir: FlowIR) -> str:
        """Generate smoke test."""
        return f'''"""Smoke tests for the agent flow."""

import pytest
from agent_app.ir import get_flow_ir, get_node, get_topological_order


def test_flow_ir_loads():
    """Test that the flow IR loads correctly."""
    ir = get_flow_ir()
    assert ir["ir_version"] == "2"
    assert ir["flow"]["id"] == "{flow_ir.flow.id}"
    assert ir["flow"]["name"] == "{flow_ir.flow.name}"


def test_flow_has_nodes():
    """Test that the flow has nodes."""
    ir = get_flow_ir()
    assert len(ir["nodes"]) == {len(flow_ir.nodes)}


def test_topological_order():
    """Test that topological order is computed correctly."""
    order = get_topological_order()
    assert len(order) == {len(flow_ir.nodes)}
    # First node should be one with no incoming edges
    ir = get_flow_ir()
    incoming = {{e["target"] for e in ir["edges"]}}
    assert order[0] not in incoming or any(
        n.get("params", {{}}).get("is_start")
        for n in ir["nodes"]
        if n["id"] == order[0]
    )


def test_all_nodes_accessible():
    """Test that all nodes can be retrieved by ID."""
    ir = get_flow_ir()
    for node in ir["nodes"]:
        retrieved = get_node(node["id"])
        assert retrieved is not None
        assert retrieved["id"] == node["id"]


@pytest.mark.asyncio
async def test_flow_execution_smoke():
    """Smoke test for flow execution."""
    # This is a basic smoke test - it may fail if dependencies aren't installed
    # or API keys aren't configured
    from agent_app.runtime import run_flow

    try:
        result = await run_flow({{"input": "test"}})
        assert "final_output" in result
        assert "node_outputs" in result
    except RuntimeError as e:
        # Expected if engines aren't installed
        if "not installed" in str(e).lower():
            pytest.skip(f"Engine not installed: {{e}}")
        raise
    except Exception as e:
        # May fail due to API key or other config issues
        if "api" in str(e).lower() or "key" in str(e).lower():
            pytest.skip(f"API configuration issue: {{e}}")
        raise
'''
