"""LangGraph export generator.

Generates production-grade LangGraph-based agent projects with:
- Async-first node implementations
- Proper error semantics with ERROR node
- Configurable checkpointing
- Settings management
- Structured logging and optional OTEL
"""

import json
from pathlib import Path
from typing import Any

from agent_compiler.models.ir import FlowIR, NodeType
from agent_compiler.observability.logging import get_logger

logger = get_logger(__name__)


class LangGraphGenerator:
    """Generator for LangGraph-based projects."""

    def __init__(self, flow_ir: FlowIR, include_tests: bool = True):
        self.flow_ir = flow_ir
        self.include_tests = include_tests

    def generate(self, project_dir: Path) -> None:
        """Generate the complete LangGraph project structure."""
        # Create directories
        src_dir = project_dir / "src" / "agent_app"
        nodes_dir = src_dir / "nodes"
        adapters_dir = src_dir / "adapters"
        tests_dir = project_dir / "tests"

        src_dir.mkdir(parents=True)
        nodes_dir.mkdir()
        adapters_dir.mkdir()
        tests_dir.mkdir()

        # Generate all files
        self._write_file(project_dir / "pyproject.toml", self._generate_pyproject())
        self._write_file(project_dir / "README.md", self._generate_readme())
        self._write_file(project_dir / ".env.example", self._generate_env_example())
        self._write_file(src_dir / "__init__.py", self._generate_init())
        self._write_file(src_dir / "settings.py", self._generate_settings())
        self._write_file(src_dir / "logging_config.py", self._generate_logging_config())
        self._write_file(src_dir / "state.py", self._generate_state())
        self._write_file(src_dir / "graph.py", self._generate_graph())
        self._write_file(src_dir / "main.py", self._generate_main())

        # Node modules
        self._write_file(nodes_dir / "__init__.py", self._generate_nodes_init())
        self._write_file(nodes_dir / "base.py", self._generate_base_node())
        self._write_file(nodes_dir / "llm_node.py", self._generate_llm_node())
        self._write_file(nodes_dir / "tool_node.py", self._generate_tool_node())
        self._write_file(nodes_dir / "retriever_node.py", self._generate_retriever_node())
        self._write_file(nodes_dir / "router_node.py", self._generate_router_node())
        self._write_file(nodes_dir / "memory_node.py", self._generate_memory_node())
        self._write_file(nodes_dir / "output_node.py", self._generate_output_node())
        self._write_file(nodes_dir / "error_node.py", self._generate_error_node())

        # Adapters
        self._write_file(adapters_dir / "__init__.py", self._generate_adapters_init())
        self._write_file(adapters_dir / "langchain_adapter.py", self._generate_langchain_adapter())
        self._write_file(adapters_dir / "llamaindex_adapter.py", self._generate_llamaindex_adapter())

        # Tests
        self._write_file(tests_dir / "__init__.py", "")
        if self.include_tests:
            self._write_file(tests_dir / "test_langgraph_smoke.py", self._generate_smoke_test())

        logger.info(f"Generated LangGraph project for flow: {self.flow_ir.flow.id}")

    def _write_file(self, path: Path, content: str) -> None:
        """Write content to a file."""
        path.write_text(content, encoding="utf-8")

    def _generate_pyproject(self) -> str:
        """Generate pyproject.toml with LangGraph dependencies."""
        flow = self.flow_ir.flow
        return f'''[project]
name = "{flow.id}-agent"
version = "{flow.version}"
description = "{flow.description or flow.name}"
requires-python = ">=3.11"

dependencies = [
    "pydantic>=2.5.0",
    "pydantic-settings>=2.0.0",
    "langgraph>=0.0.40",
    "langchain-core>=0.1.0",
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
postgres = [
    "psycopg[binary]>=3.1.0",
    "langgraph-checkpoint-postgres>=0.0.1",
]
otel = [
    "opentelemetry-api>=1.20.0",
    "opentelemetry-sdk>=1.20.0",
    "opentelemetry-exporter-otlp>=1.20.0",
]
all = [
    "{flow.id}-agent[langchain,llamaindex,otel]",
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

    def _generate_env_example(self) -> str:
        """Generate .env.example file."""
        return '''# LLM Provider Settings
# Provider is auto-detected from model name: gemini* → Gemini, else → OpenAI
# You can also set LLM_PROVIDER explicitly to "openai" or "gemini".
LLM_PROVIDER=
LLM_MODEL=gpt-3.5-turbo
LLM_TEMPERATURE=0.7

# OpenAI
OPENAI_API_KEY=sk-your-key-here
# Gemini
GOOGLE_API_KEY=

# RAG Settings
RAG_TOP_K=5
RAG_INDEX_NAME=default

# Checkpointing (optional)
CHECKPOINTER_ENABLED=false
CHECKPOINTER_DB_PATH=./checkpoints.db
# For Postgres: CHECKPOINTER_DB_URL=postgresql://user:pass@localhost/db

# Observability
LOG_LEVEL=INFO
JSON_LOGS=false
OTEL_ENABLED=false
OTEL_SERVICE_NAME={flow_id}-agent
OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4317
'''.format(flow_id=self.flow_ir.flow.id)

    def _generate_readme(self) -> str:
        """Generate README.md."""
        flow = self.flow_ir.flow
        node_types = [n.type.value for n in self.flow_ir.nodes]
        return f'''# {flow.name}

{flow.description or "An AI agent flow exported from Agent Compiler using LangGraph."}

## Version
{flow.version}

## Architecture
This project uses **LangGraph** for workflow orchestration, providing:
- Type-safe state management with TypedDict
- Async-first node implementations
- Conditional routing with error handling
- Built-in retry mechanisms
- Optional checkpointing/persistence
- Structured logging and optional OpenTelemetry

## Flow Structure
- **Nodes**: {len(self.flow_ir.nodes)} ({", ".join(set(node_types))})
- **Edges**: {len(self.flow_ir.edges)}
- **Engine Preference**: {flow.engine_preference.value}

## Setup

1. Install dependencies:
```bash
pip install -e ".[all]"
```

2. Configure environment:
```bash
cp .env.example .env
# Edit .env with your settings
```

3. Required environment variables:
   - **OpenAI**: `OPENAI_API_KEY`
   - **Gemini**: `GOOGLE_API_KEY`

## Configuration

See `.env.example` for all available settings:

| Variable | Default | Description |
|----------|---------|-------------|
| `LLM_PROVIDER` | (auto) | `openai` or `gemini`. Auto-detected from model name if empty. |
| `LLM_MODEL` | gpt-3.5-turbo | Model to use (e.g. `gpt-4o`, `gemini-1.5-pro`) |
| `LLM_TEMPERATURE` | 0.7 | Temperature for generation |
| `OPENAI_API_KEY` | - | OpenAI API key (required for OpenAI models) |
| `GOOGLE_API_KEY` | - | Gemini API key (required for Gemini models) |
| `CHECKPOINTER_ENABLED` | false | Enable state persistence |
| `CHECKPOINTER_DB_PATH` | ./checkpoints.db | SQLite path |
| `LOG_LEVEL` | INFO | Logging level |
| `JSON_LOGS` | false | Output JSON logs |
| `OTEL_ENABLED` | false | Enable OpenTelemetry |

## Usage

### Command Line
```bash
# Simple usage
run-agent "Your input here"

# With streaming
run-agent --stream "Your input here"

# JSON output
run-agent --json "Your input here"

# With run ID (for checkpointing)
run-agent --run-id my-session "Your input here"
```

### Python
```python
import asyncio
from agent_app.graph import create_graph
from agent_app.state import create_initial_state

async def main():
    graph = create_graph()
    state = create_initial_state("Your input here")
    result = await graph.ainvoke(state)
    print(result["final_output"])

asyncio.run(main())
```

### Streaming
```python
import asyncio
from agent_app.graph import create_graph
from agent_app.state import create_initial_state

async def main():
    graph = create_graph()
    state = create_initial_state("Your input here")
    async for event in graph.astream(state):
        print(event)

asyncio.run(main())
```

## Error Handling

The workflow includes an ERROR node that handles exceptions:
- All node exceptions are caught and logged
- Errors are recorded in `state["error"]` with full context
- The workflow routes to ERROR node on failure
- ERROR node formats a user-safe error response

## Testing
```bash
pytest tests/
```

## Project Structure
```
src/agent_app/
├── __init__.py
├── settings.py       # Configuration management
├── logging_config.py # Structured logging setup
├── state.py          # Typed state definition
├── graph.py          # LangGraph StateGraph assembly
├── main.py           # CLI entrypoint
├── nodes/            # Async node implementations
│   ├── base.py       # Base node utilities
│   ├── llm_node.py
│   ├── tool_node.py
│   ├── retriever_node.py
│   ├── router_node.py
│   ├── memory_node.py
│   ├── output_node.py
│   └── error_node.py # Error handler node
└── adapters/         # Engine adapters
    ├── langchain_adapter.py
    └── llamaindex_adapter.py
```

## Generated by Agent Compiler
This project was automatically generated using LangGraph target.
'''

    def _generate_init(self) -> str:
        """Generate __init__.py."""
        flow = self.flow_ir.flow
        return f'''"""
{flow.name} - AI Agent Application (LangGraph)

Generated by Agent Compiler.
"""

__version__ = "{flow.version}"

# Check LangGraph availability
try:
    import langgraph
except ImportError:
    raise ImportError(
        "LangGraph is required but not installed. "
        "Install with: pip install langgraph"
    )
'''

    def _generate_settings(self) -> str:
        """Generate settings.py with Pydantic BaseSettings."""
        return '''"""Configuration management using Pydantic BaseSettings."""

from functools import lru_cache
from typing import Optional

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # LLM Settings
    llm_provider: str = Field(
        default="",
        description="LLM provider: 'openai' or 'gemini'. Empty = auto-detect from model name.",
    )
    openai_api_key: str = Field(default="", description="OpenAI API key")
    google_api_key: str = Field(default="", description="Google (Gemini) API key")
    llm_model: str = Field(default="gpt-3.5-turbo", description="LLM model name")
    llm_temperature: float = Field(default=0.7, ge=0.0, le=2.0)
    llm_max_tokens: Optional[int] = Field(default=None, description="Max tokens")

    # RAG Settings
    rag_top_k: int = Field(default=5, ge=1, le=100)
    rag_index_name: str = Field(default="default")
    rag_relevance_threshold: float = Field(default=0.3, ge=0.0, le=1.0)

    # Checkpointer Settings
    checkpointer_enabled: bool = Field(default=False)
    checkpointer_db_path: str = Field(default="./checkpoints.db")
    checkpointer_db_url: Optional[str] = Field(
        default=None,
        description="Postgres URL for distributed checkpointing"
    )

    # Observability Settings
    log_level: str = Field(default="INFO")
    json_logs: bool = Field(default=False)
    otel_enabled: bool = Field(default=False)
    otel_service_name: str = Field(default="agent-app")
    otel_exporter_otlp_endpoint: str = Field(default="http://localhost:4317")


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
'''

    def _generate_logging_config(self) -> str:
        """Generate logging_config.py with structured logging."""
        return '''"""Structured logging configuration."""

import json
import logging
import sys
import time
import uuid
from contextvars import ContextVar
from typing import Any, Optional

from agent_app.settings import get_settings

# Context variables for correlation
run_id_var: ContextVar[str] = ContextVar("run_id", default="")
step_id_var: ContextVar[str] = ContextVar("step_id", default="")
node_id_var: ContextVar[str] = ContextVar("node_id", default="")


class JSONFormatter(logging.Formatter):
    """JSON log formatter."""

    def format(self, record: logging.LogRecord) -> str:
        log_data = {
            "timestamp": self.formatTime(record, self.datefmt),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "run_id": run_id_var.get(""),
            "step_id": step_id_var.get(""),
            "node_id": node_id_var.get(""),
        }

        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)

        # Add extra fields
        for key, value in record.__dict__.items():
            if key not in ("name", "msg", "args", "created", "filename",
                          "funcName", "levelname", "levelno", "lineno",
                          "module", "msecs", "pathname", "process",
                          "processName", "relativeCreated", "stack_info",
                          "thread", "threadName", "exc_info", "exc_text",
                          "message"):
                log_data[key] = value

        return json.dumps(log_data, default=str)


class TextFormatter(logging.Formatter):
    """Plain text formatter with context."""

    def format(self, record: logging.LogRecord) -> str:
        run_id = run_id_var.get("")
        node_id = node_id_var.get("")

        prefix = ""
        if run_id:
            prefix = f"[{run_id[:8]}]"
        if node_id:
            prefix = f"{prefix}[{node_id}]"

        if prefix:
            record.msg = f"{prefix} {record.msg}"

        return super().format(record)


def setup_logging() -> None:
    """Configure logging based on settings."""
    settings = get_settings()

    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, settings.log_level.upper()))

    # Remove existing handlers
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    # Create handler
    handler = logging.StreamHandler(sys.stdout)

    if settings.json_logs:
        handler.setFormatter(JSONFormatter())
    else:
        handler.setFormatter(TextFormatter(
            fmt="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        ))

    root_logger.addHandler(handler)


def get_logger(name: str) -> logging.Logger:
    """Get a logger instance."""
    return logging.getLogger(name)


def set_run_context(run_id: str) -> None:
    """Set the current run ID for logging."""
    run_id_var.set(run_id)


def set_step_context(step_id: str, node_id: str) -> None:
    """Set the current step context for logging."""
    step_id_var.set(step_id)
    node_id_var.set(node_id)


def generate_run_id() -> str:
    """Generate a unique run ID."""
    return str(uuid.uuid4())


def generate_step_id() -> str:
    """Generate a unique step ID."""
    return f"step_{int(time.time() * 1000)}_{uuid.uuid4().hex[:8]}"


# Optional OpenTelemetry integration
_tracer = None

def get_tracer():
    """Get OpenTelemetry tracer if enabled."""
    global _tracer

    if _tracer is not None:
        return _tracer

    settings = get_settings()
    if not settings.otel_enabled:
        return None

    try:
        from opentelemetry import trace
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
        from opentelemetry.sdk.resources import Resource

        resource = Resource.create({"service.name": settings.otel_service_name})
        provider = TracerProvider(resource=resource)

        exporter = OTLPSpanExporter(endpoint=settings.otel_exporter_otlp_endpoint)
        provider.add_span_processor(BatchSpanProcessor(exporter))

        trace.set_tracer_provider(provider)
        _tracer = trace.get_tracer(settings.otel_service_name)
        return _tracer

    except ImportError:
        return None


class SpanContext:
    """Context manager for optional OTEL spans."""

    def __init__(self, name: str, attributes: Optional[dict[str, Any]] = None):
        self.name = name
        self.attributes = attributes or {}
        self.span = None
        self.tracer = get_tracer()

    def __enter__(self):
        if self.tracer:
            self.span = self.tracer.start_span(self.name)
            for key, value in self.attributes.items():
                self.span.set_attribute(key, str(value))
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.span:
            if exc_type:
                self.span.set_attribute("error", True)
                self.span.set_attribute("error.message", str(exc_val))
            self.span.end()
        return False

    def set_attribute(self, key: str, value: Any) -> None:
        if self.span:
            self.span.set_attribute(key, str(value))
'''

    def _generate_state(self) -> str:
        """Generate state.py with typed state definition and error info."""
        return '''"""Typed state for the agent workflow."""

import traceback
from dataclasses import dataclass, field
from typing import Any, Optional, TypedDict

from pydantic import BaseModel, Field


@dataclass
class ErrorInfo:
    """Structured error information."""
    code: str
    message: str
    node_id: str
    traceback: Optional[str] = None
    retryable: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "message": self.message,
            "node_id": self.node_id,
            "traceback": self.traceback,
            "retryable": self.retryable,
        }

    @classmethod
    def from_exception(
        cls,
        exc: Exception,
        node_id: str,
        include_traceback: bool = False,
    ) -> "ErrorInfo":
        """Create ErrorInfo from an exception."""
        return cls(
            code=type(exc).__name__,
            message=str(exc),
            node_id=node_id,
            traceback=traceback.format_exc() if include_traceback else None,
            retryable=isinstance(exc, (TimeoutError, ConnectionError)),
        )


class Citation(BaseModel):
    """A citation from retrieved documents."""
    content: str
    source: str
    score: float = 0.0
    metadata: dict[str, Any] = Field(default_factory=dict)

    def format(self) -> str:
        """Format citation for prompt injection."""
        return f"[Source: {self.source}] {self.content}"


@dataclass
class StepLog:
    """Log entry for a single execution step."""
    step_id: str
    node_id: str
    node_type: str
    status: str = "started"  # started, completed, error
    input_summary: str = ""
    output_summary: str = ""
    error: Optional[dict[str, Any]] = None
    duration_ms: Optional[float] = None
    tokens_used: Optional[int] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "step_id": self.step_id,
            "node_id": self.node_id,
            "node_type": self.node_type,
            "status": self.status,
            "input_summary": self.input_summary,
            "output_summary": self.output_summary,
            "error": self.error,
            "duration_ms": self.duration_ms,
            "tokens_used": self.tokens_used,
        }


class AgentState(TypedDict, total=False):
    """State passed through the LangGraph workflow.

    Attributes:
        run_id: Unique run identifier for correlation
        user_input: Original user input string
        messages: Optional conversation history
        context: Retrieved documents with citations
        artifacts: Outputs from each node
        step_logs: Execution timeline
        current_node: Currently executing node ID
        next_node: Next node to execute (for routing)
        final_output: Final result of the workflow
        error: Error information if workflow failed
    """
    run_id: str
    user_input: str
    messages: list[dict[str, Any]]
    context: list[dict[str, Any]]  # Citations as dicts
    artifacts: dict[str, Any]
    step_logs: list[dict[str, Any]]
    current_node: str
    next_node: Optional[str]
    final_output: Any
    error: Optional[dict[str, Any]]  # ErrorInfo as dict


def create_initial_state(user_input: str, run_id: Optional[str] = None) -> AgentState:
    """Create initial state for workflow execution."""
    from agent_app.logging_config import generate_run_id

    return AgentState(
        run_id=run_id or generate_run_id(),
        user_input=user_input,
        messages=[],
        context=[],
        artifacts={},
        step_logs=[],
        current_node="",
        next_node=None,
        final_output=None,
        error=None,
    )


def get_citations_text(state: AgentState) -> str:
    """Get formatted citations from state context."""
    context = state.get("context", [])
    if not context:
        return ""

    citations = []
    for i, doc in enumerate(context, 1):
        source = doc.get("source", "unknown")
        content = doc.get("content", "")
        citations.append(f"[{i}] [Source: {source}] {content}")

    return "\\n\\n".join(citations)


def has_relevant_context(state: AgentState, threshold: float = 0.3) -> bool:
    """Check if context has documents above relevance threshold."""
    context = state.get("context", [])
    return any(doc.get("score", 0) >= threshold for doc in context)


def set_error(state: AgentState, error: ErrorInfo) -> AgentState:
    """Set error in state and route to ERROR node."""
    return {
        **state,
        "error": error.to_dict(),
        "next_node": "__error__",
    }


def add_step_log(
    state: AgentState,
    step_log: StepLog,
) -> AgentState:
    """Add a step log entry to state."""
    logs = list(state.get("step_logs", []))
    logs.append(step_log.to_dict())
    return {**state, "step_logs": logs}


def has_error(state: AgentState) -> bool:
    """Check if state has an error."""
    return state.get("error") is not None
'''

    def _generate_graph(self) -> str:
        """Generate graph.py with LangGraph StateGraph assembly."""
        flow = self.flow_ir.flow
        ir_json = json.dumps(self.flow_ir.model_dump(), indent=2)

        # Collect node info for imports and registration
        node_imports = []
        node_registrations = []
        edge_definitions = []

        # Track which node types are used
        used_types = set()
        for node in self.flow_ir.nodes:
            used_types.add(node.type)

        # Generate imports for used node types
        type_to_module = {
            NodeType.LLM: ("llm_node", "run_llm_node"),
            NodeType.TOOL: ("tool_node", "run_tool_node"),
            NodeType.RETRIEVER: ("retriever_node", "run_retriever_node"),
            NodeType.ROUTER: ("router_node", "run_router_node"),
            NodeType.MEMORY: ("memory_node", "run_memory_node"),
            NodeType.OUTPUT: ("output_node", "run_output_node"),
        }

        for node_type in used_types:
            if node_type in type_to_module:
                module, func = type_to_module[node_type]
                node_imports.append(f"from agent_app.nodes.{module} import {func}")

        # Generate node registrations
        type_to_func = {
            NodeType.LLM: "run_llm_node",
            NodeType.TOOL: "run_tool_node",
            NodeType.RETRIEVER: "run_retriever_node",
            NodeType.ROUTER: "run_router_node",
            NodeType.MEMORY: "run_memory_node",
            NodeType.OUTPUT: "run_output_node",
        }

        for node in self.flow_ir.nodes:
            func_name = type_to_func.get(node.type, "run_llm_node")
            node_registrations.append(
                f'    graph.add_node("{node.id}", make_node_runner("{node.id}", "{node.type.value}", {func_name}))'
            )

        # Find start node
        start_node_id = self.flow_ir.start_node_id

        # Generate edges
        router_nodes = {n.id for n in self.flow_ir.nodes if n.type == NodeType.ROUTER}

        for edge in self.flow_ir.edges:
            if edge.source in router_nodes:
                continue
            edge_definitions.append(f'    graph.add_edge("{edge.source}", "{edge.target}")')

        # Generate conditional edges for routers
        conditional_edges = []
        for node in self.flow_ir.nodes:
            if node.type == NodeType.ROUTER:
                routes = node.params.get("routes", {})
                default_route = node.params.get("default_route")
                successors = self.flow_ir.get_successors(node.id)

                if routes or successors:
                    route_map = {}
                    for condition, target in routes.items():
                        route_map[condition] = target

                    for succ in successors:
                        if succ not in route_map.values():
                            route_map[succ] = succ

                    conditional_edges.append(f'''
    # Conditional routing for {node.id}
    graph.add_conditional_edges(
        "{node.id}",
        route_or_error,
        {repr(route_map) if route_map else '{}'} | {{"__error__": "__error__"}}
    )''')

        imports_str = "\n".join(sorted(set(node_imports)))
        registrations_str = "\n".join(node_registrations)
        edges_str = "\n".join(edge_definitions)
        conditional_str = "\n".join(conditional_edges)

        return f'''"""LangGraph StateGraph assembly."""

import json
import time
from typing import Any, Callable, Optional

from langgraph.graph import StateGraph, END

from agent_app.state import (
    AgentState,
    ErrorInfo,
    StepLog,
    add_step_log,
    has_error,
    set_error,
)
from agent_app.logging_config import (
    get_logger,
    set_step_context,
    generate_step_id,
    SpanContext,
)
from agent_app.settings import get_settings
from agent_app.nodes.error_node import run_error_node
{imports_str}


logger = get_logger(__name__)


# Embedded flow IR
FLOW_IR_JSON = """
{ir_json}
"""


def get_flow_ir() -> dict[str, Any]:
    """Get the flow IR as a dictionary."""
    return json.loads(FLOW_IR_JSON)


def get_node_config(node_id: str) -> dict[str, Any]:
    """Get configuration for a specific node."""
    ir = get_flow_ir()
    for node in ir["nodes"]:
        if node["id"] == node_id:
            return node
    raise ValueError(f"Node not found: {{node_id}}")


def route_or_error(state: AgentState) -> str:
    """Route to next node or ERROR node if error occurred."""
    if has_error(state):
        return "__error__"
    return state.get("next_node") or END


def should_continue(state: AgentState) -> str:
    """Check if workflow should continue or route to error."""
    if has_error(state):
        return "__error__"
    return "continue"


def make_node_runner(
    node_id: str,
    node_type: str,
    handler: Callable[[AgentState, dict[str, Any]], AgentState],
) -> Callable[[AgentState], AgentState]:
    """Create an async node runner that wraps execution with logging and error handling."""

    async def runner(state: AgentState) -> AgentState:
        step_id = generate_step_id()
        set_step_context(step_id, node_id)

        config = get_node_config(node_id)
        state = {{**state, "current_node": node_id}}

        step_log = StepLog(
            step_id=step_id,
            node_id=node_id,
            node_type=node_type,
            status="started",
            input_summary=str(state.get("user_input", ""))[:100],
        )

        start_time = time.perf_counter()

        with SpanContext(f"node.{{node_id}}", {{"node.type": node_type}}):
            try:
                logger.info(f"Executing node: {{node_id}} ({{node_type}})")

                # Call the async handler
                result = await handler(state, config)

                duration_ms = (time.perf_counter() - start_time) * 1000
                step_log.status = "completed"
                step_log.duration_ms = duration_ms
                step_log.output_summary = str(result.get("artifacts", {{}}).get(node_id, ""))[:100]

                # Extract tokens if available
                node_output = result.get("artifacts", {{}}).get(node_id, {{}})
                if isinstance(node_output, dict):
                    step_log.tokens_used = node_output.get("tokens_used")

                logger.info(f"Node {{node_id}} completed in {{duration_ms:.2f}}ms")
                result = add_step_log(result, step_log)
                return result

            except Exception as e:
                duration_ms = (time.perf_counter() - start_time) * 1000
                logger.error(f"Node {{node_id}} failed: {{e}}")

                error_info = ErrorInfo.from_exception(e, node_id, include_traceback=True)
                step_log.status = "error"
                step_log.duration_ms = duration_ms
                step_log.error = error_info.to_dict()

                state = add_step_log(state, step_log)
                return set_error(state, error_info)

    return runner


def get_checkpointer():
    """Get checkpointer based on settings."""
    settings = get_settings()

    if not settings.checkpointer_enabled:
        return None

    try:
        if settings.checkpointer_db_url:
            # Use Postgres checkpointer
            from langgraph.checkpoint.postgres import PostgresSaver
            return PostgresSaver.from_conn_string(settings.checkpointer_db_url)
        else:
            # Use SQLite checkpointer
            from langgraph.checkpoint.sqlite import SqliteSaver
            return SqliteSaver.from_conn_string(settings.checkpointer_db_path)
    except ImportError as e:
        logger.warning(f"Checkpointer not available: {{e}}")
        return None


def create_graph() -> StateGraph:
    """Create and compile the LangGraph workflow."""
    graph = StateGraph(AgentState)

    # Add nodes
{registrations_str}

    # Add ERROR node
    graph.add_node("__error__", run_error_node)

    # Set entry point
    graph.set_entry_point("{start_node_id}")

    # Add edges
{edges_str}
{conditional_str}

    # Find terminal nodes (no outgoing edges)
    ir = get_flow_ir()
    all_sources = {{e["source"] for e in ir["edges"]}}
    all_nodes = {{n["id"] for n in ir["nodes"]}}
    terminal_nodes = all_nodes - all_sources

    # Connect terminal nodes to END (unless they're routers)
    for terminal in terminal_nodes:
        node_config = get_node_config(terminal)
        if node_config["type"] != "Router":
            # Add conditional edge to check for errors
            graph.add_conditional_edges(
                terminal,
                should_continue,
                {{"continue": END, "__error__": "__error__"}}
            )

    # ERROR node always goes to END
    graph.add_edge("__error__", END)

    # Compile with optional checkpointer
    checkpointer = get_checkpointer()
    return graph.compile(checkpointer=checkpointer)


async def run_graph(user_input: str, run_id: Optional[str] = None) -> dict[str, Any]:
    """Run the graph with user input."""
    from agent_app.state import create_initial_state
    from agent_app.logging_config import set_run_context

    graph = create_graph()
    initial_state = create_initial_state(user_input, run_id)
    set_run_context(initial_state["run_id"])

    config = {{"configurable": {{"thread_id": initial_state["run_id"]}}}}
    result = await graph.ainvoke(initial_state, config)
    return result
'''

    def _generate_main(self) -> str:
        """Generate main.py CLI entrypoint."""
        flow = self.flow_ir.flow
        return f'''#!/usr/bin/env python3
"""
CLI entry point for {flow.name} (LangGraph).

Usage:
    run-agent "Your input here"
    run-agent --stream "Your input here"
    run-agent --json "Your input here"
    run-agent --run-id my-session "Your input here"
"""

import argparse
import asyncio
import json
import sys
from typing import Optional

from agent_app.logging_config import setup_logging, set_run_context


async def run_async(
    user_input: str,
    run_id: Optional[str],
    stream: bool,
    json_output: bool,
) -> int:
    """Async entry point."""
    from agent_app.graph import create_graph, run_graph
    from agent_app.state import create_initial_state

    if stream:
        graph = create_graph()
        initial_state = create_initial_state(user_input, run_id)
        set_run_context(initial_state["run_id"])

        config = {{"configurable": {{"thread_id": initial_state["run_id"]}}}}

        async for event in graph.astream(initial_state, config):
            if json_output:
                print(json.dumps(event, default=str))
            else:
                for node_name, node_output in event.items():
                    if node_name != "__end__":
                        print(f"[{{node_name}}] {{node_output}}")
        return 0

    else:
        result = await run_graph(user_input, run_id)

        if json_output:
            print(json.dumps(result, indent=2, default=str))
        else:
            # Check for error
            if result.get("error"):
                error = result["error"]
                print(f"Error: {{error.get('message', 'Unknown error')}}", file=sys.stderr)
                return 1

            final = result.get("final_output")
            if isinstance(final, dict):
                output = final.get("output", final)
            else:
                output = final or result.get("artifacts", {{}})
            print(output)

        return 0


def main() -> None:
    """CLI entry point."""
    setup_logging()

    parser = argparse.ArgumentParser(
        description="{flow.description or flow.name}"
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
        "--stream",
        action="store_true",
        help="Stream output events",
    )
    parser.add_argument(
        "--run-id",
        help="Run ID for checkpointing/correlation",
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
            data = json.load(f)
            user_input = data.get("input") or data.get("user_input") or str(data)
    elif args.input:
        user_input = args.input
    else:
        print("Enter input (Ctrl+D to finish):", file=sys.stderr)
        user_input = sys.stdin.read().strip()

    try:
        exit_code = asyncio.run(run_async(
            user_input=user_input,
            run_id=args.run_id,
            stream=args.stream,
            json_output=args.json,
        ))
        sys.exit(exit_code)
    except KeyboardInterrupt:
        print("\\nInterrupted", file=sys.stderr)
        sys.exit(130)
    except Exception as e:
        print(f"Error: {{e}}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
'''

    def _generate_nodes_init(self) -> str:
        """Generate nodes/__init__.py."""
        return '''"""Node implementations for LangGraph workflow.

All nodes are async-first and follow the pattern:
    async def run_xxx_node(state: AgentState, config: dict) -> AgentState
"""

from agent_app.nodes.llm_node import run_llm_node
from agent_app.nodes.tool_node import run_tool_node
from agent_app.nodes.retriever_node import run_retriever_node
from agent_app.nodes.router_node import run_router_node
from agent_app.nodes.memory_node import run_memory_node
from agent_app.nodes.output_node import run_output_node
from agent_app.nodes.error_node import run_error_node

__all__ = [
    "run_llm_node",
    "run_tool_node",
    "run_retriever_node",
    "run_router_node",
    "run_memory_node",
    "run_output_node",
    "run_error_node",
]
'''

    def _generate_base_node(self) -> str:
        """Generate base.py with common node utilities."""
        return '''"""Base utilities for node implementations."""

from typing import Any

from agent_app.state import AgentState, get_citations_text


def render_template(template: str, state: AgentState) -> str:
    """Render a template string with state values."""
    user_input = state.get("user_input", "")
    citations = get_citations_text(state)
    artifacts = state.get("artifacts", {})

    result = template
    result = result.replace("{input}", user_input)
    result = result.replace("{user_input}", user_input)
    result = result.replace("{citations}", citations)
    result = result.replace("{context}", citations)

    # Replace {current} with most recent artifact output
    current = ""
    for key, value in reversed(list(artifacts.items())):
        if isinstance(value, dict):
            current = str(value.get("output", value.get("result", "")))
            if current:
                break
    result = result.replace("{current}", current)
    result = result.replace("{result}", current)

    # Replace artifact references
    for key, value in artifacts.items():
        if isinstance(value, dict):
            result = result.replace(f"{{node.{key}}}", str(value.get("output", value)))
        else:
            result = result.replace(f"{{node.{key}}}", str(value))

    return result


def get_adapter(engine: str):
    """Get the appropriate adapter based on engine preference."""
    if engine == "llamaindex":
        from agent_app.adapters.llamaindex_adapter import LlamaIndexAdapter
        return LlamaIndexAdapter()
    else:
        from agent_app.adapters.langchain_adapter import LangChainAdapter
        return LangChainAdapter()
'''

    def _generate_llm_node(self) -> str:
        """Generate llm_node.py (async)."""
        return '''"""LLM node implementation (async)."""

from typing import Any

from agent_app.state import AgentState, get_citations_text, has_relevant_context
from agent_app.nodes.base import render_template, get_adapter
from agent_app.settings import get_settings
from agent_app.logging_config import SpanContext


async def run_llm_node(state: AgentState, config: dict[str, Any]) -> AgentState:
    """Execute an LLM node asynchronously."""
    params = config.get("params", {})
    node_id = config["id"]
    settings = get_settings()

    # Determine engine
    engine = params.get("engine") or "langchain"
    if engine == "auto":
        engine = "langchain"

    adapter = get_adapter(engine)

    # Render prompt template
    prompt_template = params.get("prompt_template", "{input}")
    prompt = render_template(prompt_template, state)

    # Check for abstain if retrieval was done but no relevant docs
    context = state.get("context", [])
    threshold = settings.rag_relevance_threshold
    if context and not has_relevant_context(state, threshold):
        output = {
            "output": "I don't have enough relevant information to answer. Could you provide more context?",
            "abstained": True,
        }
        artifacts = dict(state.get("artifacts", {}))
        artifacts[node_id] = output
        return {**state, "artifacts": artifacts, "final_output": output}

    # Inject citations if available
    if context:
        citations = get_citations_text(state)
        prompt = f"Context from retrieved documents:\\n{citations}\\n\\n{prompt}"

    # Get system prompt
    system_prompt = params.get("system_prompt")
    if system_prompt:
        system_prompt = render_template(system_prompt, state)

    # Get model settings
    model = params.get("model") or settings.llm_model
    temperature = params.get("temperature", settings.llm_temperature)
    max_tokens = params.get("max_tokens") or settings.llm_max_tokens

    with SpanContext("llm.call", {"model": model}):
        response = await adapter.run_llm(
            prompt=prompt,
            model=model,
            temperature=temperature,
            system_prompt=system_prompt,
            max_tokens=max_tokens,
        )

    output = {
        "output": response.content,
        "model": response.model,
        "tokens_used": response.tokens_used,
    }
    artifacts = dict(state.get("artifacts", {}))
    artifacts[node_id] = output

    return {**state, "artifacts": artifacts, "final_output": output}
'''

    def _generate_tool_node(self) -> str:
        """Generate tool_node.py with retry support (async)."""
        return '''"""Tool node implementation with retry support (async)."""

import asyncio
from typing import Any

from agent_app.state import AgentState
from agent_app.nodes.base import get_adapter
from agent_app.logging_config import get_logger, SpanContext

logger = get_logger(__name__)


async def run_tool_with_retry(
    adapter,
    tool_name: str,
    tool_input: dict[str, Any],
    tool_config: dict[str, Any] | None,
    max_retries: int = 2,
    retry_delay: float = 1.0,
) -> dict[str, Any]:
    """Run a tool with retry logic."""
    last_error = None

    for attempt in range(max_retries + 1):
        try:
            with SpanContext("tool.call", {"tool": tool_name, "attempt": attempt}):
                return await adapter.run_tool(
                    tool_name=tool_name,
                    tool_input=tool_input,
                    tool_config=tool_config,
                )
        except Exception as e:
            last_error = e
            logger.warning(f"Tool '{tool_name}' attempt {attempt + 1} failed: {e}")
            if attempt < max_retries:
                await asyncio.sleep(retry_delay * (attempt + 1))

    raise RuntimeError(
        f"Tool '{tool_name}' failed after {max_retries + 1} attempts: {last_error}"
    ) from last_error


async def run_tool_node(state: AgentState, config: dict[str, Any]) -> AgentState:
    """Execute a Tool node with retry support."""
    params = config.get("params", {})
    node_id = config["id"]

    # Determine engine
    engine = params.get("engine") or "langchain"
    if engine == "auto":
        engine = "langchain"

    adapter = get_adapter(engine)

    # Build tool input
    tool_input = {
        "input": state.get("user_input", ""),
        "context": state.get("context", []),
        "artifacts": state.get("artifacts", {}),
    }

    # Get retry config
    max_retries = params.get("max_retries", 2)

    result = await run_tool_with_retry(
        adapter=adapter,
        tool_name=params["tool_name"],
        tool_input=tool_input,
        tool_config=params.get("tool_config"),
        max_retries=max_retries,
    )

    output = {"result": result}
    artifacts = dict(state.get("artifacts", {}))
    artifacts[node_id] = output

    return {**state, "artifacts": artifacts}
'''

    def _generate_retriever_node(self) -> str:
        """Generate retriever_node.py (async, uses LlamaIndex by default)."""
        return '''"""Retriever node implementation (async).

Uses LlamaIndex by default for retrieval operations.
"""

from typing import Any

from agent_app.state import AgentState
from agent_app.nodes.base import render_template, get_adapter
from agent_app.settings import get_settings
from agent_app.logging_config import SpanContext


async def run_retriever_node(state: AgentState, config: dict[str, Any]) -> AgentState:
    """Execute a Retriever node."""
    params = config.get("params", {})
    node_id = config["id"]
    settings = get_settings()

    # Determine engine (default to LlamaIndex for retrieval)
    engine = params.get("engine") or "auto"
    if engine == "auto":
        engine = "llamaindex"

    adapter = get_adapter(engine)

    # Render query template
    query_template = params.get("query_template", "{input}")
    query = render_template(query_template, state)

    # Get retrieval settings
    top_k = params.get("top_k") or settings.rag_top_k
    index_name = params.get("index_name") or settings.rag_index_name

    with SpanContext("retriever.call", {"top_k": top_k, "index": index_name}):
        docs = await adapter.retrieve(
            query=query,
            top_k=top_k,
            index_name=index_name,
            index_config=params.get("index_config"),
        )

    # Convert to citation format and add to context
    citations = [
        {"content": d.content, "source": d.source, "score": d.score, "metadata": d.metadata}
        for d in docs
    ]

    # Merge with existing context
    existing_context = list(state.get("context", []))
    existing_context.extend(citations)

    output = {
        "documents": citations,
        "num_documents": len(docs),
        "avg_score": sum(d.score for d in docs) / len(docs) if docs else 0,
    }

    artifacts = dict(state.get("artifacts", {}))
    artifacts[node_id] = output

    return {**state, "context": existing_context, "artifacts": artifacts}
'''

    def _generate_router_node(self) -> str:
        """Generate router_node.py (async)."""
        return '''"""Router node implementation for conditional routing (async)."""

from typing import Any

from agent_app.state import AgentState
from agent_app.logging_config import get_logger

logger = get_logger(__name__)


async def run_router_node(state: AgentState, config: dict[str, Any]) -> AgentState:
    """Execute a Router node.

    Sets the next_node in state based on routing conditions.
    The graph's conditional_edges will use this to determine the path.
    """
    params = config.get("params", {})
    node_id = config["id"]

    routes = params.get("routes", {})
    default_route = params.get("default_route")

    # Get the current value to route on
    artifacts = state.get("artifacts", {})

    # Find the most recent output to route on
    current_value = ""
    for artifact_key, artifact_value in reversed(list(artifacts.items())):
        if isinstance(artifact_value, dict):
            output = artifact_value.get("output", artifact_value.get("result", ""))
            if output:
                current_value = str(output).lower()
                break

    if not current_value:
        current_value = state.get("user_input", "").lower()

    # Simple condition matching
    selected_route = default_route
    for condition, target in routes.items():
        if condition.lower() in current_value:
            selected_route = target
            logger.info(f"Router {node_id}: matched condition '{condition}' -> {target}")
            break

    if selected_route == default_route:
        logger.info(f"Router {node_id}: using default route -> {default_route}")

    output = {
        "selected_route": selected_route,
        "condition_matched": selected_route != default_route,
        "input_value": current_value[:100],
    }

    artifacts = dict(state.get("artifacts", {}))
    artifacts[node_id] = output

    return {**state, "artifacts": artifacts, "next_node": selected_route}
'''

    def _generate_memory_node(self) -> str:
        """Generate memory_node.py with store abstraction (async)."""
        return '''"""Memory node implementation with store abstraction (async)."""

import json
import sqlite3
import time
from pathlib import Path
from typing import Any, Optional

from agent_app.state import AgentState
from agent_app.settings import get_settings
from agent_app.logging_config import get_logger

logger = get_logger(__name__)


class MemoryStore:
    """Simple key-value memory store with optional persistence."""

    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path
        self._memory: dict[str, Any] = {}

        if db_path:
            self._init_db()

    def _init_db(self) -> None:
        """Initialize SQLite database for persistent storage."""
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS memory (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                created_at REAL NOT NULL,
                ttl_seconds REAL,
                metadata TEXT
            )
        """)
        conn.commit()
        conn.close()

    def get(self, key: str) -> Optional[Any]:
        """Get a value from memory."""
        if self.db_path:
            return self._get_persistent(key)
        return self._memory.get(key)

    def set(
        self,
        key: str,
        value: Any,
        ttl_seconds: Optional[float] = None,
        metadata: Optional[dict] = None,
    ) -> None:
        """Set a value in memory."""
        if self.db_path:
            self._set_persistent(key, value, ttl_seconds, metadata)
        else:
            self._memory[key] = value

    def _get_persistent(self, key: str) -> Optional[Any]:
        """Get from SQLite with TTL check."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT value, created_at, ttl_seconds FROM memory WHERE key = ?",
            (key,)
        )
        row = cursor.fetchone()
        conn.close()

        if not row:
            return None

        value_json, created_at, ttl = row

        # Check TTL
        if ttl and (time.time() - created_at) > ttl:
            self.delete(key)
            return None

        return json.loads(value_json)

    def _set_persistent(
        self,
        key: str,
        value: Any,
        ttl_seconds: Optional[float],
        metadata: Optional[dict],
    ) -> None:
        """Set in SQLite."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("""
            INSERT OR REPLACE INTO memory (key, value, created_at, ttl_seconds, metadata)
            VALUES (?, ?, ?, ?, ?)
        """, (
            key,
            json.dumps(value, default=str),
            time.time(),
            ttl_seconds,
            json.dumps(metadata) if metadata else None,
        ))
        conn.commit()
        conn.close()

    def delete(self, key: str) -> None:
        """Delete a key from memory."""
        if self.db_path:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute("DELETE FROM memory WHERE key = ?", (key,))
            conn.commit()
            conn.close()
        else:
            self._memory.pop(key, None)


# Global store instance
_store: Optional[MemoryStore] = None


def get_memory_store() -> MemoryStore:
    """Get or create the memory store."""
    global _store
    if _store is None:
        settings = get_settings()
        db_path = settings.checkpointer_db_path if settings.checkpointer_enabled else None
        _store = MemoryStore(db_path)
    return _store


async def run_memory_node(state: AgentState, config: dict[str, Any]) -> AgentState:
    """Execute a Memory node.

    Supports operations:
    - write: Store current context/output
    - read: Retrieve stored memory
    - clear: Clear memory for key
    """
    params = config.get("params", {})
    node_id = config["id"]

    memory_type = params.get("memory_type", "buffer")
    operation = params.get("operation", "write")
    key = params.get("key", f"memory_{node_id}")
    ttl_seconds = params.get("ttl_seconds")

    store = get_memory_store()
    run_id = state.get("run_id", "default")
    full_key = f"{run_id}:{key}"

    if operation == "read":
        stored = store.get(full_key)
        output = {
            "operation": "read",
            "key": key,
            "value": stored,
            "found": stored is not None,
        }
    elif operation == "clear":
        store.delete(full_key)
        output = {
            "operation": "clear",
            "key": key,
        }
    else:  # write
        # Determine what to store
        if memory_type == "context":
            value = state.get("context", [])
        elif memory_type == "artifacts":
            value = state.get("artifacts", {})
        else:  # buffer - store current state snapshot
            value = {
                "user_input": state.get("user_input"),
                "context_count": len(state.get("context", [])),
                "artifacts_count": len(state.get("artifacts", {})),
            }

        store.set(full_key, value, ttl_seconds=ttl_seconds)
        logger.info(f"Memory stored: {key} (type={memory_type})")

        output = {
            "operation": "write",
            "key": key,
            "memory_type": memory_type,
            "ttl_seconds": ttl_seconds,
        }

    # Add to messages as a system memory marker
    messages = list(state.get("messages", []))
    messages.append({
        "role": "system",
        "content": f"[Memory: {operation} {key}]",
    })

    artifacts = dict(state.get("artifacts", {}))
    artifacts[node_id] = output

    return {**state, "messages": messages, "artifacts": artifacts}
'''

    def _generate_output_node(self) -> str:
        """Generate output_node.py (async)."""
        return '''"""Output node implementation (async)."""

from typing import Any

from agent_app.state import AgentState
from agent_app.nodes.base import render_template


async def run_output_node(state: AgentState, config: dict[str, Any]) -> AgentState:
    """Execute an Output node."""
    params = config.get("params", {})
    node_id = config["id"]

    output_template = params.get("output_template", "{current}")
    output_format = params.get("format", "text")

    # Render the output
    rendered = render_template(output_template, state)

    output = {"output": rendered, "format": output_format}

    # Handle JSON format
    if output_format == "json":
        try:
            import json
            output["output"] = json.loads(rendered)
        except json.JSONDecodeError:
            output["format_error"] = "Could not parse as JSON"

    artifacts = dict(state.get("artifacts", {}))
    artifacts[node_id] = output

    return {**state, "artifacts": artifacts, "final_output": output}
'''

    def _generate_error_node(self) -> str:
        """Generate error_node.py for handling errors."""
        return '''"""Error node implementation.

Handles errors that occur during workflow execution.
Formats user-safe error output and ensures clean termination.
"""

from typing import Any

from agent_app.state import AgentState
from agent_app.logging_config import get_logger

logger = get_logger(__name__)


async def run_error_node(state: AgentState, config: dict[str, Any] = None) -> AgentState:
    """Handle workflow errors.

    This node is called when any other node raises an exception.
    It formats a user-safe error response and terminates the workflow.
    """
    error = state.get("error", {})

    if not error:
        # No error info - should not happen but handle gracefully
        error = {
            "code": "UnknownError",
            "message": "An unexpected error occurred",
            "node_id": "unknown",
        }

    error_code = error.get("code", "Error")
    error_message = error.get("message", "An error occurred")
    error_node = error.get("node_id", "unknown")

    logger.error(f"Workflow error at {error_node}: [{error_code}] {error_message}")

    # Format user-safe output
    user_message = f"I encountered an error while processing your request. "

    if error.get("retryable"):
        user_message += "This may be a temporary issue - please try again."
    else:
        user_message += f"Error: {error_message}"

    output = {
        "output": user_message,
        "error_code": error_code,
        "error_node": error_node,
        "is_error": True,
    }

    artifacts = dict(state.get("artifacts", {}))
    artifacts["__error__"] = output

    return {
        **state,
        "artifacts": artifacts,
        "final_output": output,
    }
'''

    def _generate_adapters_init(self) -> str:
        """Generate adapters/__init__.py."""
        return '''"""Engine adapters for LangGraph workflow."""

from agent_app.adapters.langchain_adapter import LangChainAdapter
from agent_app.adapters.llamaindex_adapter import LlamaIndexAdapter

__all__ = ["LangChainAdapter", "LlamaIndexAdapter"]
'''

    def _generate_langchain_adapter(self) -> str:
        """Generate langchain_adapter.py (async, multi-provider)."""
        return '''"""LangChain adapter for LangGraph workflow (async).

Supports OpenAI and Gemini providers.  Provider is auto-detected from
the model name (gemini* -> Gemini, else -> OpenAI) unless
``settings.llm_provider`` is set explicitly.
"""

import os
from dataclasses import dataclass, field
from typing import Any, Optional

from agent_app.settings import get_settings


@dataclass
class LLMResponse:
    """Response from LLM call."""
    content: str
    model: str
    tokens_used: Optional[int] = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class RetrievalResult:
    """Result from retrieval operation."""
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
    provider: str | None = None,
    model: str = "gpt-3.5-turbo",
    temperature: float = 0.7,
    max_tokens: int | None = None,
    api_key: str | None = None,
    api_key_env: str | None = None,
    timeout_s: int | None = None,
) -> Any:
    """Build a LangChain chat model for the requested provider."""
    if provider is None or provider == "":
        provider = _infer_provider(model)

    if provider == "gemini":
        try:
            from langchain_google_genai import ChatGoogleGenerativeAI
        except ImportError:
            raise RuntimeError(
                "Gemini provider selected but langchain-google-genai is not installed. "
                "Install with:  pip install langchain-google-genai"
            )
        env_var = api_key_env or "GOOGLE_API_KEY"
        resolved_key = api_key or os.environ.get(env_var, "")
        if not resolved_key:
            raise RuntimeError(
                f"Gemini provider selected but API key not found. "
                f"Set the {env_var} environment variable."
            )
        kwargs: dict[str, Any] = {
            "model": model,
            "temperature": temperature,
            "google_api_key": resolved_key,
        }
        if max_tokens is not None:
            kwargs["max_output_tokens"] = max_tokens
        if timeout_s is not None:
            kwargs["timeout"] = timeout_s
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
    env_var = api_key_env or "OPENAI_API_KEY"
    resolved_key = api_key or os.environ.get(env_var, "")
    if not resolved_key:
        raise RuntimeError(
            f"OpenAI provider selected but API key not found. "
            f"Set the {env_var} environment variable."
        )
    kwargs = {
        "model": model,
        "temperature": temperature,
        "api_key": resolved_key,
    }
    if max_tokens is not None:
        kwargs["max_tokens"] = max_tokens
    if timeout_s is not None:
        kwargs["request_timeout"] = timeout_s
    return ChatOpenAI(**kwargs)


# ---------------------------------------------------------------------------
#  Adapter
# ---------------------------------------------------------------------------

class LangChainAdapter:
    """Adapter for LangChain operations (async, multi-provider)."""

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
        system_prompt: Optional[str] = None,
        max_tokens: Optional[int] = None,
    ) -> LLMResponse:
        """Run an LLM using LangChain (OpenAI or Gemini)."""
        if not self.is_available():
            raise RuntimeError(
                "LangChain is not installed. "
                "Install with: pip install langchain langchain-openai"
            )

        settings = get_settings()
        provider = settings.llm_provider or None  # empty string -> auto

        llm = build_chat_model(
            provider=provider,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            api_key=(
                settings.google_api_key
                if (_infer_provider(model) == "gemini" and not provider)
                   or provider == "gemini"
                else settings.openai_api_key
            ),
        )

        try:
            from langchain_core.messages import HumanMessage, SystemMessage
        except ImportError:
            from langchain.schema import HumanMessage, SystemMessage

        messages = []
        if system_prompt:
            messages.append(SystemMessage(content=system_prompt))
        messages.append(HumanMessage(content=prompt))

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
        index_name: Optional[str] = None,
        index_config: Optional[dict[str, Any]] = None,
    ) -> list[RetrievalResult]:
        """Retrieve documents using LangChain."""
        # Placeholder - implement with your vector store
        return [
            RetrievalResult(
                content=f"Document for query: {query}",
                source="placeholder",
                score=0.5,
            )
        ]

    async def run_tool(
        self,
        tool_name: str,
        tool_input: dict[str, Any],
        tool_config: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        """Execute a tool using LangChain."""
        # Placeholder - implement with LangChain tools
        return {"tool_name": tool_name, "input": tool_input, "result": "placeholder"}
'''

    def _generate_llamaindex_adapter(self) -> str:
        """Generate llamaindex_adapter.py (async)."""
        return '''"""LlamaIndex adapter for LangGraph workflow (async)."""

from dataclasses import dataclass, field
from typing import Any, Optional

from agent_app.settings import get_settings


@dataclass
class LLMResponse:
    """Response from LLM call."""
    content: str
    model: str
    tokens_used: Optional[int] = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class RetrievalResult:
    """Result from retrieval operation."""
    content: str
    source: str
    score: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)


class LlamaIndexAdapter:
    """Adapter for LlamaIndex operations (async, preferred for retrieval)."""

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
        system_prompt: Optional[str] = None,
        max_tokens: Optional[int] = None,
    ) -> LLMResponse:
        """Run an LLM using LlamaIndex."""
        if not self.is_available():
            raise RuntimeError(
                "LlamaIndex is not installed. Install with: pip install llama-index"
            )

        settings = get_settings()

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
            api_key=settings.openai_api_key,
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
        index_name: Optional[str] = None,
        index_config: Optional[dict[str, Any]] = None,
    ) -> list[RetrievalResult]:
        """Retrieve documents using LlamaIndex."""
        # Placeholder - implement with your LlamaIndex index
        return [
            RetrievalResult(
                content=f"Document for query: {query}",
                source="llamaindex_placeholder",
                score=0.7,
            )
        ]

    async def run_tool(
        self,
        tool_name: str,
        tool_input: dict[str, Any],
        tool_config: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        """Execute a tool using LlamaIndex."""
        return {"tool_name": tool_name, "input": tool_input, "result": "placeholder"}
'''

    def _generate_smoke_test(self) -> str:
        """Generate test_langgraph_smoke.py with success and error path tests."""
        flow = self.flow_ir.flow
        return f'''"""Smoke tests for the LangGraph workflow."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import os


# Set test environment
os.environ.setdefault("OPENAI_API_KEY", "test-key")
os.environ.setdefault("CHECKPOINTER_ENABLED", "false")


# Mock adapters for testing without API calls
class MockLLMResponse:
    def __init__(self, content: str = "Mock response"):
        self.content = content
        self.model = "mock-model"
        self.tokens_used = 100


class MockRetrievalResult:
    def __init__(self):
        self.content = "Mock document content"
        self.source = "mock_source"
        self.score = 0.8
        self.metadata = {{}}


class MockAdapter:
    """Mock adapter for testing."""

    async def run_llm(self, **kwargs):
        return MockLLMResponse()

    async def retrieve(self, **kwargs):
        return [MockRetrievalResult()]

    async def run_tool(self, **kwargs):
        return {{"result": "mock_tool_result"}}


class FailingAdapter:
    """Adapter that always fails for error testing."""

    async def run_llm(self, **kwargs):
        raise RuntimeError("Simulated LLM failure")

    async def retrieve(self, **kwargs):
        raise RuntimeError("Simulated retrieval failure")

    async def run_tool(self, **kwargs):
        raise RuntimeError("Simulated tool failure")


def test_graph_imports():
    """Test that graph module imports correctly."""
    from agent_app.graph import create_graph, get_flow_ir

    ir = get_flow_ir()
    assert ir["ir_version"] == "2"
    assert ir["flow"]["id"] == "{flow.id}"


def test_state_imports():
    """Test that state module imports correctly."""
    from agent_app.state import (
        AgentState,
        ErrorInfo,
        create_initial_state,
        get_citations_text,
        has_relevant_context,
        set_error,
        has_error,
    )

    state = create_initial_state("test input")
    assert state["user_input"] == "test input"
    assert state["context"] == []
    assert state["artifacts"] == {{}}
    assert state["error"] is None
    assert has_error(state) is False


def test_error_info():
    """Test ErrorInfo creation and serialization."""
    from agent_app.state import ErrorInfo

    error = ErrorInfo(
        code="TestError",
        message="Test message",
        node_id="test_node",
        retryable=True,
    )
    d = error.to_dict()
    assert d["code"] == "TestError"
    assert d["retryable"] is True


def test_error_from_exception():
    """Test ErrorInfo.from_exception."""
    from agent_app.state import ErrorInfo

    try:
        raise ValueError("Test error")
    except ValueError as e:
        error = ErrorInfo.from_exception(e, "test_node")

    assert error.code == "ValueError"
    assert error.message == "Test error"
    assert error.node_id == "test_node"


def test_create_graph():
    """Test that graph creation works."""
    from agent_app.graph import create_graph

    graph = create_graph()
    assert graph is not None


def test_node_imports():
    """Test that all node modules import correctly."""
    from agent_app.nodes import (
        run_llm_node,
        run_tool_node,
        run_retriever_node,
        run_router_node,
        run_memory_node,
        run_output_node,
        run_error_node,
    )

    # All should be coroutines
    import asyncio
    assert asyncio.iscoroutinefunction(run_llm_node)
    assert asyncio.iscoroutinefunction(run_tool_node)
    assert asyncio.iscoroutinefunction(run_retriever_node)
    assert asyncio.iscoroutinefunction(run_router_node)
    assert asyncio.iscoroutinefunction(run_memory_node)
    assert asyncio.iscoroutinefunction(run_output_node)
    assert asyncio.iscoroutinefunction(run_error_node)


def test_citations_formatting():
    """Test citation formatting."""
    from agent_app.state import get_citations_text

    state = {{
        "context": [
            {{"content": "Doc 1", "source": "src1", "score": 0.9}},
            {{"content": "Doc 2", "source": "src2", "score": 0.8}},
        ]
    }}

    citations = get_citations_text(state)
    assert "Doc 1" in citations
    assert "src1" in citations
    assert "Doc 2" in citations


def test_has_relevant_context():
    """Test relevance checking."""
    from agent_app.state import has_relevant_context

    assert has_relevant_context({{"context": []}}) is False
    assert has_relevant_context({{"context": [{{"score": 0.1}}]}}) is False
    assert has_relevant_context({{"context": [{{"score": 0.8}}]}}) is True


def test_settings():
    """Test settings loading."""
    from agent_app.settings import get_settings

    settings = get_settings()
    assert settings.llm_model == "gpt-3.5-turbo"
    assert settings.llm_temperature == 0.7


def test_logging_setup():
    """Test logging configuration."""
    from agent_app.logging_config import setup_logging, get_logger

    setup_logging()
    logger = get_logger("test")
    assert logger is not None


@pytest.mark.asyncio
async def test_graph_success_path():
    """Test graph execution success path with mocked adapters."""
    from agent_app.graph import run_graph

    with patch("agent_app.nodes.base.get_adapter", return_value=MockAdapter()):
        result = await run_graph("Test question")

        assert "artifacts" in result
        assert "step_logs" in result
        assert "run_id" in result
        # Should not have error in success path
        assert result.get("error") is None


@pytest.mark.asyncio
async def test_graph_error_path():
    """Test that errors route to ERROR node and set state.error."""
    from agent_app.graph import run_graph

    with patch("agent_app.nodes.base.get_adapter", return_value=FailingAdapter()):
        result = await run_graph("Test question")

        # Should have error set
        assert result.get("error") is not None
        error = result["error"]
        assert "code" in error
        assert "message" in error
        assert "node_id" in error

        # Should have error node output
        assert "__error__" in result.get("artifacts", {{}})
        error_output = result["artifacts"]["__error__"]
        assert error_output.get("is_error") is True


@pytest.mark.asyncio
async def test_error_node_directly():
    """Test error node handler directly."""
    from agent_app.nodes.error_node import run_error_node
    from agent_app.state import create_initial_state, ErrorInfo, set_error

    state = create_initial_state("test")
    error = ErrorInfo(
        code="TestError",
        message="Test failure",
        node_id="test_node",
        retryable=False,
    )
    state = set_error(state, error)

    result = await run_error_node(state)

    assert "__error__" in result["artifacts"]
    output = result["artifacts"]["__error__"]
    assert output["is_error"] is True
    assert "error" in output["output"].lower()


def test_flow_structure():
    """Test flow IR structure is correct."""
    from agent_app.graph import get_flow_ir, get_node_config

    ir = get_flow_ir()

    assert "flow" in ir
    assert "nodes" in ir
    assert "edges" in ir

    assert ir["flow"]["name"] == "{flow.name}"
    assert ir["flow"]["version"] == "{flow.version}"

    for node in ir["nodes"]:
        config = get_node_config(node["id"])
        assert config["id"] == node["id"]
        assert config["type"] == node["type"]


@pytest.mark.asyncio
async def test_memory_store():
    """Test memory store operations."""
    from agent_app.nodes.memory_node import MemoryStore

    store = MemoryStore()  # In-memory only

    store.set("test_key", {{"value": 123}})
    result = store.get("test_key")
    assert result == {{"value": 123}}

    store.delete("test_key")
    assert store.get("test_key") is None


@pytest.mark.asyncio
async def test_memory_store_with_ttl(tmp_path):
    """Test memory store with TTL and persistence."""
    import time
    from agent_app.nodes.memory_node import MemoryStore

    db_path = str(tmp_path / "test_memory.db")
    store = MemoryStore(db_path)

    # Set with very short TTL
    store.set("ttl_key", "value", ttl_seconds=0.1)

    # Should exist immediately
    assert store.get("ttl_key") == "value"

    # Wait for TTL to expire
    time.sleep(0.15)

    # Should be gone now
    assert store.get("ttl_key") is None
'''
