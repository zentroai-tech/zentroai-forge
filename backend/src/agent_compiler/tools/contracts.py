"""Tool Contract Registry.

Defines the normalized contract format for every tool referenced in IR flows.

A ToolContract describes:
  - input/output JSON schemas
  - auth requirements
  - network / data-access scopes
  - retry/timeout runtime config
  - whether the tool is implemented or is a stub (contract_only=True)

MCP tools (tool_name starting with "mcp:") are treated as a wildcard passthrough
and are NOT required to have a registered contract.

Built-in tools (web_search, search, url_reader, calculator, datetime, echo,
safe_calculator, http_get) are always registered and implemented by the runtime.

Contract-only tools (sql_query, http_request, python_sandbox, s3_get_object)
declare their schema and policy but require external implementation.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Contract models
# ---------------------------------------------------------------------------


class ToolAuthSpec(BaseModel):
    """Authentication requirements for a tool."""

    type: str = "none"  # aws_iam_role | api_key | oauth | none
    secret_ref: str | None = None  # e.g. "secrets://sql_query_creds"
    notes: str | None = None


class ToolNetworkSpec(BaseModel):
    """Network scope for a tool."""

    allowed_hosts: list[str] = Field(default_factory=list)
    timeout_seconds: int = 30
    no_network: bool = False


class ToolDataAccessSpec(BaseModel):
    """Data access scope for a tool."""

    allowed_schemas: list[str] = Field(default_factory=list)
    readonly: bool = True
    notes: str | None = None


class ToolPolicySpec(BaseModel):
    """Policy metadata for a tool."""

    redaction: bool = True
    pii_phi: bool = False
    notes: str | None = None


class ToolRuntimeSpec(BaseModel):
    """Runtime / retry configuration for a tool."""

    retries: dict[str, Any] = Field(
        default_factory=lambda: {"max_attempts": 3, "backoff_ms": 400}
    )
    sandbox: bool = False
    max_runtime_seconds: int | None = None


class ToolContract(BaseModel):
    """Normalized tool contract.

    Fields map 1-to-1 with the IR backlog spec format so that contracts
    can be serialised directly to JSON and included in exports.
    """

    name: str
    version: str = "1.0"
    description: str
    input_schema: dict[str, Any]
    output_schema: dict[str, Any]
    auth: ToolAuthSpec = Field(default_factory=ToolAuthSpec)
    network: ToolNetworkSpec = Field(default_factory=ToolNetworkSpec)
    data_access: ToolDataAccessSpec = Field(default_factory=ToolDataAccessSpec)
    policy: ToolPolicySpec = Field(default_factory=ToolPolicySpec)
    runtime: ToolRuntimeSpec = Field(default_factory=ToolRuntimeSpec)
    contract_only: bool = False  # True → stub generated, impl required externally


# ---------------------------------------------------------------------------
# Built-in contract definitions
# ---------------------------------------------------------------------------

_BUILTIN_CONTRACTS: list[ToolContract] = [
    # ------------------------------------------------------------------
    # Web / search tools (always implemented by runtime)
    # ------------------------------------------------------------------
    ToolContract(
        name="web_search",
        version="1.0",
        description="Full-text web search. Returns a ranked list of results.",
        input_schema={
            "type": "object",
            "required": ["query"],
            "properties": {
                "query": {"type": "string"},
                "max_results": {"type": "integer", "default": 5},
            },
        },
        output_schema={
            "type": "object",
            "required": ["results"],
            "properties": {
                "results": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "title": {"type": "string"},
                            "url": {"type": "string"},
                            "snippet": {"type": "string"},
                        },
                    },
                }
            },
        },
        auth=ToolAuthSpec(type="api_key", secret_ref="secrets://web_search_api_key"),
        network=ToolNetworkSpec(allowed_hosts=["*"], timeout_seconds=15),
        policy=ToolPolicySpec(redaction=True),
        contract_only=False,
    ),
    ToolContract(
        name="search",
        version="1.0",
        description="Alias for web_search — generic search tool.",
        input_schema={
            "type": "object",
            "required": ["query"],
            "properties": {"query": {"type": "string"}},
        },
        output_schema={
            "type": "object",
            "required": ["results"],
            "properties": {
                "results": {"type": "array", "items": {"type": "object"}}
            },
        },
        policy=ToolPolicySpec(redaction=True),
        contract_only=False,
    ),
    ToolContract(
        name="url_reader",
        version="1.0",
        description="Fetches and returns the text content of a URL.",
        input_schema={
            "type": "object",
            "required": ["url"],
            "properties": {"url": {"type": "string", "format": "uri"}},
        },
        output_schema={
            "type": "object",
            "required": ["content"],
            "properties": {
                "content": {"type": "string"},
                "status_code": {"type": "integer"},
            },
        },
        network=ToolNetworkSpec(allowed_hosts=["*"], timeout_seconds=20),
        policy=ToolPolicySpec(redaction=True),
        contract_only=False,
    ),
    ToolContract(
        name="calculator",
        version="1.0",
        description="Evaluates safe arithmetic expressions.",
        input_schema={
            "type": "object",
            "required": ["expression"],
            "properties": {"expression": {"type": "string"}},
        },
        output_schema={
            "type": "object",
            "required": ["result"],
            "properties": {"result": {"type": "number"}},
        },
        network=ToolNetworkSpec(no_network=True),
        contract_only=False,
    ),
    ToolContract(
        name="datetime",
        version="1.0",
        description="Returns current UTC datetime and timezone info.",
        input_schema={
            "type": "object",
            "properties": {"format": {"type": "string", "default": "iso8601"}},
        },
        output_schema={
            "type": "object",
            "required": ["utc_now"],
            "properties": {
                "utc_now": {"type": "string"},
                "timestamp": {"type": "number"},
            },
        },
        network=ToolNetworkSpec(no_network=True),
        contract_only=False,
    ),
    ToolContract(
        name="echo",
        version="1.0",
        description="Echoes input back — useful for testing pipelines.",
        input_schema={
            "type": "object",
            "required": ["message"],
            "properties": {"message": {"type": "string"}},
        },
        output_schema={
            "type": "object",
            "required": ["message"],
            "properties": {"message": {"type": "string"}},
        },
        network=ToolNetworkSpec(no_network=True),
        contract_only=False,
    ),
    ToolContract(
        name="safe_calculator",
        version="1.0",
        description="AST-safe arithmetic evaluator — no exec/eval.",
        input_schema={
            "type": "object",
            "required": ["expression"],
            "properties": {"expression": {"type": "string"}},
        },
        output_schema={
            "type": "object",
            "required": ["result"],
            "properties": {"result": {}},
        },
        network=ToolNetworkSpec(no_network=True),
        contract_only=False,
    ),
    ToolContract(
        name="http_get",
        version="1.0",
        description="Performs a GET request to an allowed external host.",
        input_schema={
            "type": "object",
            "required": ["url"],
            "properties": {
                "url": {"type": "string"},
                "headers": {"type": "object"},
            },
        },
        output_schema={
            "type": "object",
            "required": ["body", "status_code"],
            "properties": {
                "body": {"type": "string"},
                "status_code": {"type": "integer"},
            },
        },
        auth=ToolAuthSpec(type="none"),
        network=ToolNetworkSpec(
            allowed_hosts=["*"],
            timeout_seconds=15,
        ),
        policy=ToolPolicySpec(redaction=True),
        contract_only=False,
    ),
    # ------------------------------------------------------------------
    # Contract-only tools (stubs required — external implementation)
    # ------------------------------------------------------------------
    ToolContract(
        name="sql_query",
        version="1.0",
        description=(
            "Read-only SQL query against clinical/omics/pathology schemas. "
            "Requires external database connection config."
        ),
        input_schema={
            "type": "object",
            "required": ["query"],
            "properties": {
                "query": {"type": "string", "description": "SQL SELECT statement"},
                "params": {"type": "object", "description": "Bind parameters"},
            },
        },
        output_schema={
            "type": "object",
            "required": ["rows", "row_count"],
            "properties": {
                "rows": {"type": "array", "items": {"type": "object"}},
                "row_count": {"type": "integer"},
            },
        },
        auth=ToolAuthSpec(
            type="aws_iam_role",
            secret_ref="secrets://sql_db_credentials",
            notes="Configure DATABASE_URL in .env",
        ),
        network=ToolNetworkSpec(
            allowed_hosts=["internal.db.company"],
            timeout_seconds=30,
        ),
        data_access=ToolDataAccessSpec(
            allowed_schemas=["clinical", "omics", "pathology"],
            readonly=True,
        ),
        policy=ToolPolicySpec(redaction=True, pii_phi=True),
        runtime=ToolRuntimeSpec(retries={"max_attempts": 3, "backoff_ms": 400}),
        contract_only=True,
    ),
    ToolContract(
        name="http_request",
        version="1.0",
        description=(
            "Internal REST API call to allowed company endpoints. "
            "Requires host allowlist and auth config."
        ),
        input_schema={
            "type": "object",
            "required": ["url", "method"],
            "properties": {
                "url": {"type": "string"},
                "method": {"type": "string", "enum": ["GET", "POST", "PUT", "PATCH"]},
                "headers": {"type": "object"},
                "body": {"type": "object"},
            },
        },
        output_schema={
            "type": "object",
            "required": ["body", "status_code"],
            "properties": {
                "body": {},
                "status_code": {"type": "integer"},
                "headers": {"type": "object"},
            },
        },
        auth=ToolAuthSpec(
            type="api_key",
            secret_ref="secrets://internal_api_key",
            notes="Set INTERNAL_API_KEY in .env",
        ),
        network=ToolNetworkSpec(
            allowed_hosts=["internal.api.company", "clinical.api.company"],
            timeout_seconds=15,
        ),
        policy=ToolPolicySpec(redaction=True, pii_phi=True),
        runtime=ToolRuntimeSpec(retries={"max_attempts": 2, "backoff_ms": 300}),
        contract_only=True,
    ),
    ToolContract(
        name="python_sandbox",
        version="1.0",
        description=(
            "Sandboxed Python code execution (no network, no filesystem). "
            "Requires a sandbox runtime (e.g. RestrictedPython or Pyodide)."
        ),
        input_schema={
            "type": "object",
            "required": ["code"],
            "properties": {
                "code": {"type": "string", "description": "Python code to execute"},
                "context": {
                    "type": "object",
                    "description": "Variables injected into execution scope",
                },
            },
        },
        output_schema={
            "type": "object",
            "required": ["stdout", "result"],
            "properties": {
                "stdout": {"type": "string"},
                "stderr": {"type": "string"},
                "result": {"description": "Return value of last expression"},
            },
        },
        auth=ToolAuthSpec(type="none"),
        network=ToolNetworkSpec(no_network=True),
        policy=ToolPolicySpec(redaction=True),
        runtime=ToolRuntimeSpec(
            sandbox=True,
            max_runtime_seconds=10,
            retries={"max_attempts": 1, "backoff_ms": 0},
        ),
        contract_only=True,
    ),
    ToolContract(
        name="s3_get_object",
        version="1.0",
        description=(
            "Read-only S3 object retrieval. "
            "Requires AWS credentials and bucket allowlist."
        ),
        input_schema={
            "type": "object",
            "required": ["bucket", "key"],
            "properties": {
                "bucket": {"type": "string"},
                "key": {"type": "string"},
                "version_id": {"type": "string"},
            },
        },
        output_schema={
            "type": "object",
            "required": ["body", "content_type"],
            "properties": {
                "body": {"type": "string", "description": "Base64-encoded object body"},
                "content_type": {"type": "string"},
                "content_length": {"type": "integer"},
                "etag": {"type": "string"},
            },
        },
        auth=ToolAuthSpec(
            type="aws_iam_role",
            secret_ref="secrets://aws_credentials",
            notes="Set AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY or use IAM role",
        ),
        network=ToolNetworkSpec(
            allowed_hosts=["s3.amazonaws.com", "*.s3.amazonaws.com"],
            timeout_seconds=30,
        ),
        data_access=ToolDataAccessSpec(readonly=True),
        policy=ToolPolicySpec(redaction=True, pii_phi=True),
        runtime=ToolRuntimeSpec(retries={"max_attempts": 3, "backoff_ms": 500}),
        contract_only=True,
    ),
]


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


class ToolContractRegistry:
    """In-memory registry of tool contracts.

    Lookup is O(1) by exact tool name. MCP tools are treated as a wildcard
    and are NOT registered individually.
    """

    def __init__(self) -> None:
        self._contracts: dict[str, ToolContract] = {}

    def register(self, contract: ToolContract) -> None:
        """Register a single tool contract."""
        self._contracts[contract.name] = contract

    def get(self, name: str) -> ToolContract | None:
        """Get a contract by exact tool name."""
        return self._contracts.get(name)

    def get_all(self) -> list[ToolContract]:
        """Return all registered contracts."""
        return list(self._contracts.values())

    def list_names(self) -> list[str]:
        """Return all registered tool names."""
        return list(self._contracts.keys())

    def is_mcp(self, name: str) -> bool:
        """Return True if this tool name is an MCP wildcard."""
        return str(name).startswith("mcp:")

    def resolve(self, name: str) -> tuple[ToolContract | None, bool]:
        """Resolve a tool name.

        Returns:
            (contract, is_known) where is_known=True for registered tools
            and for mcp:* wildcards.
        """
        if self.is_mcp(name):
            return None, True
        contract = self.get(name)
        return contract, contract is not None

    def _register_defaults(self) -> None:
        for c in _BUILTIN_CONTRACTS:
            self.register(c)


# Singleton
_registry: ToolContractRegistry | None = None


def get_tool_contract_registry() -> ToolContractRegistry:
    """Return the singleton ToolContractRegistry."""
    global _registry
    if _registry is None:
        _registry = ToolContractRegistry()
        _registry._register_defaults()
    return _registry
