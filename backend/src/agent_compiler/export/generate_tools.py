"""Tool stub + contract test generator.

For each contract-only tool referenced in an IR this generator writes:

  project/
    app/
      tools/
        contracts/
          <tool_name>.json          <- serialised ToolContract
        impl/
          __init__.py
          <tool_name>.py            <- real impl for the 4 built-in contract tools
                                       OR typed stub (raises NotImplementedError)
        settings.py                 <- env-var helpers for policy settings
    tests/
      test_tool_contract_<tool_name>.py   <- contract + smoke tests

Built-in tools and MCP tools are skipped (they either have runtime impls
or are resolved dynamically).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from agent_compiler.ir.validate import collect_tool_names
from agent_compiler.models.ir_v2 import FlowIRv2
from agent_compiler.observability.logging import get_logger
from agent_compiler.tools.contracts import ToolContract, get_tool_contract_registry

logger = get_logger(__name__)

_INDENT = "    "

# ---------------------------------------------------------------------------
# Settings module — written once per export to app/tools/settings.py
# ---------------------------------------------------------------------------

_SETTINGS_MODULE = '''"""Tool policy settings — read from environment variables.

Set these in your .env file or deployment secrets manager.

  HTTP_ALLOWED_HOSTS          comma-separated hostnames (empty = unrestricted)
  S3_ALLOWED_BUCKETS          comma-separated bucket names (empty = unrestricted)
  DATABASE_URL                SQLAlchemy-compatible connection string
  PYTHON_SANDBOX_MAX_SECONDS  max execution time for python_sandbox (capped at 30)
"""

from __future__ import annotations

import os


def get_http_allowed_hosts() -> list[str]:
    """Return allowed HTTP hostnames. Empty list means unrestricted."""
    raw = os.environ.get("HTTP_ALLOWED_HOSTS", "")
    return [h.strip() for h in raw.split(",") if h.strip()]


def get_s3_allowed_buckets() -> list[str]:
    """Return allowed S3 bucket names. Empty list means unrestricted."""
    raw = os.environ.get("S3_ALLOWED_BUCKETS", "")
    return [b.strip() for b in raw.split(",") if b.strip()]


def get_database_url() -> str:
    """Return the SQLAlchemy database URL from environment."""
    url = os.environ.get("DATABASE_URL", "")
    if not url:
        raise RuntimeError("DATABASE_URL environment variable is not set.")
    return url


def get_python_sandbox_max_seconds() -> float:
    """Return the maximum sandbox execution time, capped at 30 seconds."""
    raw = os.environ.get("PYTHON_SANDBOX_MAX_SECONDS", "10")
    try:
        val = float(raw)
    except ValueError:
        val = 10.0
    return min(val, 30.0)
'''

# ---------------------------------------------------------------------------
# Real implementations for the 4 built-in contract-only tools
# ---------------------------------------------------------------------------

_TOOL_IMPLEMENTATIONS: dict[str, str] = {
    "http_request": '''"""
Auto-generated implementation for tool: http_request

Internal REST API call to allowed company endpoints.
Requires host allowlist and auth config.

Set HTTP_ALLOWED_HOSTS in the environment (comma-separated hostnames).
An empty list means all hosts are allowed.
"""

from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

import httpx
from pydantic import BaseModel

from app.tools.settings import get_http_allowed_hosts

_BODY_MAX_BYTES = 1_048_576  # 1 MB


class Input(BaseModel):
    url: str
    method: str = "GET"
    headers: dict[str, Any] | None = None
    body: str | None = None
    timeout: float = 10.0


class Output(BaseModel):
    status_code: int
    headers: dict[str, Any]
    body: str
    truncated: bool


def _check_host_allowed(url: str) -> None:
    """Raise PermissionError if the URL hostname is not in the allowlist."""
    allowed = get_http_allowed_hosts()
    if not allowed:
        return  # empty allowlist = unrestricted
    hostname = urlparse(url).hostname or ""
    if hostname not in allowed:
        raise PermissionError(
            "Host '" + hostname + "' is not in HTTP_ALLOWED_HOSTS. "
            "Allowed: " + str(allowed)
        )


async def http_request(payload: dict[str, Any]) -> dict[str, Any]:
    """Internal REST API call to allowed company endpoints."""
    data = Input.model_validate(payload)
    _check_host_allowed(data.url)

    async with httpx.AsyncClient(follow_redirects=True) as client:
        response = await client.request(
            method=data.method,
            url=data.url,
            headers=data.headers or {},
            content=data.body,
            timeout=data.timeout,
        )

    raw = response.content
    truncated = len(raw) > _BODY_MAX_BYTES
    body = raw[:_BODY_MAX_BYTES].decode("utf-8", errors="replace")

    return Output(
        status_code=response.status_code,
        headers=dict(response.headers),
        body=body,
        truncated=truncated,
    ).model_dump()
''',
    "s3_get_object": '''"""
Auto-generated implementation for tool: s3_get_object

Read-only S3 object retrieval.
Requires AWS credentials and bucket allowlist.

Set S3_ALLOWED_BUCKETS in the environment (comma-separated bucket names).
An empty list means all buckets are allowed.
"""

from __future__ import annotations

from typing import Any

import boto3
from pydantic import BaseModel

from app.tools.settings import get_s3_allowed_buckets

_HARD_MAX_BYTES = 10_485_760  # 10 MB


class Input(BaseModel):
    bucket: str
    key: str
    max_bytes: int = 1_048_576


class Output(BaseModel):
    bucket: str
    key: str
    content: str
    content_type: str
    size: int
    truncated: bool


def _check_bucket_allowed(bucket: str) -> None:
    """Raise PermissionError if the bucket is not in the allowlist."""
    allowed = get_s3_allowed_buckets()
    if not allowed:
        return  # empty allowlist = unrestricted
    if bucket not in allowed:
        raise PermissionError(
            "Bucket '" + bucket + "' is not in S3_ALLOWED_BUCKETS. "
            "Allowed: " + str(allowed)
        )


async def s3_get_object(payload: dict[str, Any]) -> dict[str, Any]:
    """Read-only S3 object retrieval."""
    data = Input.model_validate(payload)
    _check_bucket_allowed(data.bucket)

    cap = min(data.max_bytes, _HARD_MAX_BYTES)
    client = boto3.client("s3")
    response = client.get_object(Bucket=data.bucket, Key=data.key)
    raw = response["Body"].read(cap + 1)
    truncated = len(raw) > cap
    content = raw[:cap].decode("utf-8", errors="replace")

    return Output(
        bucket=data.bucket,
        key=data.key,
        content=content,
        content_type=response.get("ContentType", "application/octet-stream"),
        size=response.get("ContentLength", len(raw)),
        truncated=truncated,
    ).model_dump()
''',
    "sql_query": '''"""
Auto-generated implementation for tool: sql_query

Read-only SQL query against clinical/omics/pathology schemas.
Requires external database connection config.

Set DATABASE_URL in the environment (SQLAlchemy connection string).
Only SELECT queries are permitted; write statements are rejected.
"""

from __future__ import annotations

import re
from typing import Any

from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.tools.settings import get_database_url

_WRITE_PATTERN = re.compile(
    r"\\b(INSERT|UPDATE|DELETE|DROP|CREATE|ALTER|TRUNCATE|REPLACE|MERGE|GRANT|REVOKE)\\b",
    re.IGNORECASE,
)
_MAX_ROW_LIMIT = 1_000


class Input(BaseModel):
    query: str
    params: dict[str, Any] | None = None
    row_limit: int = 100


class Output(BaseModel):
    columns: list[str]
    rows: list[list[Any]]
    row_count: int
    truncated: bool


def _check_readonly(query: str) -> None:
    """Raise ValueError if the query contains a write statement."""
    match = _WRITE_PATTERN.search(query)
    if match:
        raise ValueError(
            "Write statements are not allowed. Found: '"
            + match.group()
            + "'. Only SELECT queries are permitted."
        )


async def sql_query(payload: dict[str, Any]) -> dict[str, Any]:
    """Read-only SQL query."""
    data = Input.model_validate(payload)
    _check_readonly(data.query)

    row_limit = min(data.row_limit, _MAX_ROW_LIMIT)
    limited_query = data.query.rstrip().rstrip(";") + f" LIMIT {row_limit + 1}"

    engine = create_async_engine(get_database_url())
    async with engine.connect() as conn:
        result = await conn.execute(text(limited_query), data.params or {})
        columns = list(result.keys())
        all_rows = [list(row) for row in result.fetchall()]

    truncated = len(all_rows) > row_limit
    rows = all_rows[:row_limit]

    return Output(
        columns=columns,
        rows=rows,
        row_count=len(rows),
        truncated=truncated,
    ).model_dump()
''',
    "python_sandbox": '''"""
Auto-generated implementation for tool: python_sandbox

Sandboxed Python code execution (no network, no filesystem write access).
Uses subprocess with -I flag and an import guard meta path hook.

Set PYTHON_SANDBOX_MAX_SECONDS in the environment to control the timeout cap.
"""

from __future__ import annotations

import subprocess
import sys
import textwrap
from typing import Any

from pydantic import BaseModel

from app.tools.settings import get_python_sandbox_max_seconds

_DEFAULT_ALLOWED_IMPORTS = frozenset([
    "math", "json", "re", "datetime", "collections",
    "itertools", "functools", "string", "random",
])

_IMPORT_GUARD_PRELUDE = textwrap.dedent("""
    import sys as _sys

    class _ImportGuard:
        def __init__(self, allowed):
            self._allowed = set(allowed)

        def find_module(self, name, path=None):
            top = name.split(".")[0]
            if top not in self._allowed:
                raise ImportError(
                    "Import of \'" + top + "\' is blocked by sandbox policy."
                )
            return None

    _sys.meta_path.insert(0, _ImportGuard({allowed_set!r}))
""")


class Input(BaseModel):
    code: str
    timeout: float = 10.0
    allowed_imports: list[str] | None = None


class Output(BaseModel):
    stdout: str
    stderr: str
    exit_code: int
    timed_out: bool


async def python_sandbox(payload: dict[str, Any]) -> dict[str, Any]:
    """Sandboxed Python code execution."""
    data = Input.model_validate(payload)
    max_seconds = get_python_sandbox_max_seconds()
    timeout = min(data.timeout, max_seconds)

    allowed = set(_DEFAULT_ALLOWED_IMPORTS)
    if data.allowed_imports:
        allowed = allowed | set(data.allowed_imports)

    prelude = _IMPORT_GUARD_PRELUDE.format(allowed_set=sorted(allowed))
    wrapped = prelude + "\\n" + data.code

    try:
        proc = subprocess.run(
            [sys.executable, "-I", "-c", wrapped],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return Output(
            stdout=proc.stdout,
            stderr=proc.stderr,
            exit_code=proc.returncode,
            timed_out=False,
        ).model_dump()
    except subprocess.TimeoutExpired:
        return Output(
            stdout="",
            stderr="Execution timed out.",
            exit_code=-1,
            timed_out=True,
        ).model_dump()
''',
}

# ---------------------------------------------------------------------------
# Integration tests for the 4 built-in contract-only tools
# ---------------------------------------------------------------------------

_TOOL_INTEGRATION_TESTS: dict[str, str] = {
    "http_request": '''"""Integration tests for tool: http_request."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.tools.impl.http_request import Input, _check_host_allowed, http_request


class TestHostAllowlist:
    def test_empty_allowlist_is_unrestricted(self):
        with patch("app.tools.impl.http_request.get_http_allowed_hosts", return_value=[]):
            _check_host_allowed("https://anything.example.com/path")  # must not raise

    def test_blocked_host_raises(self):
        with patch(
            "app.tools.impl.http_request.get_http_allowed_hosts",
            return_value=["safe.example.com"],
        ):
            with pytest.raises(PermissionError, match="not in HTTP_ALLOWED_HOSTS"):
                _check_host_allowed("https://evil.example.com/steal")

    def test_allowed_host_passes(self):
        with patch(
            "app.tools.impl.http_request.get_http_allowed_hosts",
            return_value=["safe.example.com"],
        ):
            _check_host_allowed("https://safe.example.com/api")  # must not raise


class TestHttpRequestImpl:
    @pytest.mark.asyncio
    async def test_smoke_allowed_host(self):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.content = b"hello world"
        mock_response.headers = {"content-type": "text/plain"}

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.request = AsyncMock(return_value=mock_response)

        with patch("app.tools.impl.http_request.get_http_allowed_hosts", return_value=[]):
            with patch("app.tools.impl.http_request.httpx.AsyncClient", return_value=mock_client):
                result = await http_request({"url": "https://example.com", "method": "GET"})

        assert result["status_code"] == 200
        assert result["body"] == "hello world"
        assert result["truncated"] is False

    @pytest.mark.asyncio
    async def test_blocked_host_raises_before_network(self):
        with patch(
            "app.tools.impl.http_request.get_http_allowed_hosts",
            return_value=["safe.example.com"],
        ):
            with pytest.raises(PermissionError):
                await http_request({"url": "https://evil.example.com", "method": "GET"})

    def test_input_model_validates(self):
        inp = Input.model_validate({"url": "https://example.com", "method": "POST"})
        assert inp.method == "POST"
''',
    "s3_get_object": '''"""Integration tests for tool: s3_get_object."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.tools.impl.s3_get_object import Input, _check_bucket_allowed, s3_get_object


class TestBucketAllowlist:
    def test_empty_allowlist_is_unrestricted(self):
        with patch("app.tools.impl.s3_get_object.get_s3_allowed_buckets", return_value=[]):
            _check_bucket_allowed("any-bucket")  # must not raise

    def test_blocked_bucket_raises(self):
        with patch(
            "app.tools.impl.s3_get_object.get_s3_allowed_buckets",
            return_value=["safe-bucket"],
        ):
            with pytest.raises(PermissionError, match="not in S3_ALLOWED_BUCKETS"):
                _check_bucket_allowed("evil-bucket")

    def test_allowed_bucket_passes(self):
        with patch(
            "app.tools.impl.s3_get_object.get_s3_allowed_buckets",
            return_value=["safe-bucket"],
        ):
            _check_bucket_allowed("safe-bucket")  # must not raise


class TestS3GetObjectImpl:
    @pytest.mark.asyncio
    async def test_smoke_allowed_bucket(self):
        mock_body = MagicMock()
        mock_body.read = MagicMock(return_value=b"file content here")
        mock_response = {
            "Body": mock_body,
            "ContentType": "text/plain",
            "ContentLength": 17,
        }

        mock_client = MagicMock()
        mock_client.get_object = MagicMock(return_value=mock_response)

        with patch("app.tools.impl.s3_get_object.get_s3_allowed_buckets", return_value=[]):
            with patch("app.tools.impl.s3_get_object.boto3.client", return_value=mock_client):
                result = await s3_get_object({"bucket": "my-bucket", "key": "data/file.txt"})

        assert result["content"] == "file content here"
        assert result["truncated"] is False
        assert result["bucket"] == "my-bucket"

    @pytest.mark.asyncio
    async def test_blocked_bucket_raises_before_s3_call(self):
        with patch(
            "app.tools.impl.s3_get_object.get_s3_allowed_buckets",
            return_value=["safe-bucket"],
        ):
            with pytest.raises(PermissionError):
                await s3_get_object({"bucket": "evil-bucket", "key": "data.txt"})

    def test_input_model_validates(self):
        inp = Input.model_validate({"bucket": "my-bucket", "key": "path/to/file"})
        assert inp.bucket == "my-bucket"
''',
    "sql_query": '''"""Integration tests for tool: sql_query."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.tools.impl.sql_query import Input, _check_readonly, sql_query


class TestReadonlyCheck:
    @pytest.mark.parametrize("bad_stmt", [
        "INSERT INTO t VALUES (1)",
        "UPDATE t SET x=1",
        "DELETE FROM t WHERE id=1",
        "DROP TABLE t",
        "CREATE TABLE t (id INT)",
        "ALTER TABLE t ADD COLUMN x INT",
        "TRUNCATE TABLE t",
    ])
    def test_write_statements_rejected(self, bad_stmt: str):
        with pytest.raises(ValueError, match="Write statements are not allowed"):
            _check_readonly(bad_stmt)

    def test_select_passes(self):
        _check_readonly("SELECT * FROM patients WHERE id = 1")  # must not raise

    def test_select_with_subquery_passes(self):
        _check_readonly("SELECT * FROM (SELECT id FROM t) sub")  # must not raise


class TestSqlQueryImpl:
    @pytest.mark.asyncio
    async def test_smoke_select(self):
        mock_result = MagicMock()
        mock_result.keys = MagicMock(return_value=["id", "name"])
        mock_result.fetchall = MagicMock(return_value=[(1, "Alice"), (2, "Bob")])

        mock_conn = AsyncMock()
        mock_conn.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_conn.__aexit__ = AsyncMock(return_value=False)
        mock_conn.execute = AsyncMock(return_value=mock_result)

        mock_engine = MagicMock()
        mock_engine.connect = MagicMock(return_value=mock_conn)

        with patch(
            "app.tools.impl.sql_query.get_database_url",
            return_value="sqlite+aiosqlite:///:memory:",
        ):
            with patch("app.tools.impl.sql_query.create_async_engine", return_value=mock_engine):
                result = await sql_query({"query": "SELECT * FROM patients", "row_limit": 10})

        assert result["columns"] == ["id", "name"]
        assert result["row_count"] == 2
        assert result["truncated"] is False

    @pytest.mark.asyncio
    async def test_write_statement_rejected(self):
        with pytest.raises(ValueError, match="Write statements are not allowed"):
            await sql_query({"query": "DROP TABLE patients"})

    def test_input_model_validates(self):
        inp = Input.model_validate({"query": "SELECT 1"})
        assert inp.row_limit == 100
''',
    "python_sandbox": '''"""Integration tests for tool: python_sandbox."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from app.tools.impl.python_sandbox import Input, python_sandbox


class TestPythonSandboxImpl:
    @pytest.mark.asyncio
    async def test_safe_code_runs(self):
        with patch(
            "app.tools.impl.python_sandbox.get_python_sandbox_max_seconds",
            return_value=10.0,
        ):
            result = await python_sandbox({"code": "print(1+1)"})

        assert result["exit_code"] == 0
        assert result["timed_out"] is False
        assert "2" in result["stdout"]

    @pytest.mark.asyncio
    async def test_blocked_import_fails(self):
        with patch(
            "app.tools.impl.python_sandbox.get_python_sandbox_max_seconds",
            return_value=10.0,
        ):
            result = await python_sandbox({"code": "import os; print(os.getcwd())"})

        # The import guard blocks os, so the process exits non-zero
        assert result["exit_code"] != 0
        assert (
            "blocked" in result["stderr"].lower()
            or "ImportError" in result["stderr"]
        )

    @pytest.mark.asyncio
    async def test_timeout_returns_timed_out_flag(self):
        import subprocess

        with patch(
            "app.tools.impl.python_sandbox.get_python_sandbox_max_seconds",
            return_value=30.0,
        ):
            with patch(
                "app.tools.impl.python_sandbox.subprocess.run",
                side_effect=subprocess.TimeoutExpired("python", 1),
            ):
                result = await python_sandbox({"code": "while True: pass", "timeout": 0.001})

        assert result["timed_out"] is True
        assert result["exit_code"] == -1

    def test_input_model_validates(self):
        inp = Input.model_validate({"code": "print('hello')"})
        assert inp.timeout == 10.0
''',
}


class ToolStubGenerator:
    """Generates contract JSON, Python stubs, and contract tests for tools in an IR."""

    def __init__(self, ir: FlowIRv2) -> None:
        self.ir = ir
        self._registry = get_tool_contract_registry()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def generate(
        self,
        project_dir: Path,
        include_tests: bool = True,
    ) -> list[str]:
        """Write all tool artifacts into *project_dir*.

        Returns a list of relative paths that were written.
        """
        contracts_dir = project_dir / "app" / "tools" / "contracts"
        impl_dir = project_dir / "app" / "tools" / "impl"
        tests_dir = project_dir / "tests"

        contracts_dir.mkdir(parents=True, exist_ok=True)
        impl_dir.mkdir(parents=True, exist_ok=True)

        written: list[str] = []

        tool_locations = collect_tool_names(self.ir)

        for tool_name in tool_locations:
            contract, is_known = self._registry.resolve(tool_name)

            if not is_known:
                # Unknown tool — write a minimal stub so export doesn't crash.
                contract = self._make_unknown_contract(tool_name)
                logger.warning(
                    f"Tool '{tool_name}' has no registered contract — generating minimal stub."
                )

            if contract is None:
                # MCP wildcard — skip
                continue

            # 1) Contract JSON
            contract_path = contracts_dir / f"{tool_name}.json"
            contract_path.write_text(json.dumps(contract.model_dump(), indent=2), encoding="utf-8")
            written.append(str(contract_path.relative_to(project_dir)))

            # 2) Python stub (or real implementation)
            stub_path = impl_dir / f"{tool_name}.py"
            stub_path.write_text(self._generate_stub(contract), encoding="utf-8")
            written.append(str(stub_path.relative_to(project_dir)))

            # 3) Contract tests
            if include_tests:
                tests_dir.mkdir(parents=True, exist_ok=True)
                test_path = tests_dir / f"test_tool_contract_{tool_name}.py"
                test_path.write_text(self._generate_contract_test(contract), encoding="utf-8")
                written.append(str(test_path.relative_to(project_dir)))

        # Write impl/__init__.py
        init_path = impl_dir / "__init__.py"
        init_path.write_text("", encoding="utf-8")
        written.append(str(init_path.relative_to(project_dir)))

        # Write app/tools/settings.py
        settings_path = project_dir / "app" / "tools" / "settings.py"
        settings_path.write_text(_SETTINGS_MODULE, encoding="utf-8")
        written.append(str(settings_path.relative_to(project_dir)))

        logger.info(
            f"ToolStubGenerator wrote {len(written)} artifacts for "
            f"{len(tool_locations)} referenced tools."
        )
        return written

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _make_unknown_contract(tool_name: str) -> ToolContract:
        """Minimal contract for a tool that isn't in the registry."""
        return ToolContract(
            name=tool_name,
            version="0.0",
            description=(
                f"Auto-generated stub for unknown tool '{tool_name}'. "
                "Add a ToolContract entry and implement this tool."
            ),
            input_schema={"type": "object", "properties": {}},
            output_schema={"type": "object", "properties": {}},
            contract_only=True,
        )

    @staticmethod
    def _schema_to_pydantic_fields(schema: dict[str, Any]) -> list[str]:
        """Convert a JSON schema object into a list of Pydantic field lines."""
        lines: list[str] = []
        props = schema.get("properties", {})
        required = set(schema.get("required", []))
        type_map = {
            "string": "str",
            "integer": "int",
            "number": "float",
            "boolean": "bool",
            "array": "list[Any]",
            "object": "dict[str, Any]",
        }
        for field_name, field_schema in props.items():
            if not isinstance(field_schema, dict):
                py_type = "Any"
            else:
                json_type = field_schema.get("type", "object")
                py_type = type_map.get(str(json_type), "Any")

            if field_name in required:
                lines.append(f"{_INDENT}{field_name}: {py_type}")
            else:
                default = field_schema.get("default") if isinstance(field_schema, dict) else None
                if default is None:
                    lines.append(f"{_INDENT}{field_name}: {py_type} | None = None")
                else:
                    lines.append(f"{_INDENT}{field_name}: {py_type} = {default!r}")
        if not lines:
            lines.append(f"{_INDENT}pass")
        return lines

    def _generate_stub(self, contract: ToolContract) -> str:
        """Generate a typed Python stub (or real implementation) for a tool contract."""
        # For the 4 built-in contract-only tools, return the real implementation.
        if contract.contract_only and contract.name in _TOOL_IMPLEMENTATIONS:
            return _TOOL_IMPLEMENTATIONS[contract.name]

        tool_name = contract.name
        fn_name = tool_name.replace("-", "_").replace(".", "_")
        desc = contract.description.replace('"', '\\"')

        input_fields = self._schema_to_pydantic_fields(contract.input_schema)
        output_fields = self._schema_to_pydantic_fields(contract.output_schema)

        impl_note = (
            f'raise NotImplementedError("Implement {fn_name} in app/tools/impl/{tool_name}.py")'
            if contract.contract_only
            else "# Built-in tool — this stub should not be reached."
        )

        lines = [
            '"""',
            f"Auto-generated stub for tool: {tool_name}",
            "",
            contract.description,
            "",
            "CONTRACT NOTES:",
        ]
        if contract.auth and contract.auth.type != "none":
            lines.append(
                f"  Auth:    {contract.auth.type} — {contract.auth.notes or contract.auth.secret_ref or ''}"
            )
        if contract.network and contract.network.allowed_hosts:
            lines.append(f"  Network: allowed_hosts={contract.network.allowed_hosts}")
        if contract.data_access and contract.data_access.allowed_schemas:
            lines.append(f"  Data:    allowed_schemas={contract.data_access.allowed_schemas}")
        if contract.contract_only:
            lines.append("  STATUS:  CONTRACT ONLY — implementation required.")
        lines += ['"""', ""]

        lines += [
            "from __future__ import annotations",
            "",
            "from typing import Any",
            "",
            "from pydantic import BaseModel",
            "",
            "",
            "class Input(BaseModel):",
        ]
        lines += input_fields
        lines += [
            "",
            "",
            "class Output(BaseModel):",
        ]
        lines += output_fields
        lines += [
            "",
            "",
            f"async def {fn_name}(payload: dict[str, Any]) -> dict[str, Any]:",
            f'    """{desc}"""',
            "    _data = Input.model_validate(payload)",  # validates input
            f"    {impl_note}",
        ]

        return "\n".join(lines) + "\n"

    def _generate_contract_test(self, contract: ToolContract) -> str:
        """Generate pytest tests for a tool contract."""
        # For the 4 built-in contract-only tools, return the real integration test.
        if contract.contract_only and contract.name in _TOOL_INTEGRATION_TESTS:
            return _TOOL_INTEGRATION_TESTS[contract.name]

        tool_name = contract.name
        fn_name = tool_name.replace("-", "_").replace(".", "_")
        module_path = f"app.tools.impl.{fn_name}"

        # Build a minimal valid input from the schema
        input_example = self._make_example_input(contract.input_schema)
        input_repr = json.dumps(input_example)

        lines = [
            f'"""Contract tests for tool: {tool_name}."""',
            "",
            "import pytest",
            "import importlib",
            "import json",
            "",
            f'TOOL_NAME = "{tool_name}"',
            f'MODULE_PATH = "{module_path}"',
            f"INPUT_EXAMPLE = {input_repr}",
            "",
            "",
            "class TestToolContractSchema:",
            f'    """Schema round-trip tests for {tool_name}."""',
            "",
            "    def test_input_schema_is_valid_json_schema(self):",
            '        """Input schema must be a dict with type=object."""',
            "        from app.tools.contracts import load_contract",
            f'        c = load_contract("{tool_name}")',
            '        assert isinstance(c["input_schema"], dict)',
            '        assert c["input_schema"].get("type") == "object"',
            "",
            "    def test_output_schema_is_valid_json_schema(self):",
            '        """Output schema must be a dict with type=object."""',
            "        from app.tools.contracts import load_contract",
            f'        c = load_contract("{tool_name}")',
            '        assert isinstance(c["output_schema"], dict)',
            '        assert c["output_schema"].get("type") == "object"',
            "",
            "",
            "class TestToolContractImpl:",
            f'    """Implementation tests for {tool_name}."""',
            "",
            "    def test_stub_module_importable(self):",
            '        """The stub module must be importable."""',
            "        mod = importlib.import_module(MODULE_PATH)",
            f"        assert hasattr(mod, '{fn_name}')",
            "",
            "    @pytest.mark.asyncio",
            "    async def test_stub_raises_not_implemented(self):",
            '        """Calling the stub with valid input must raise NotImplementedError.',
            "        Once implemented, replace with a smoke test using mocked deps.",
            '        """',
            "        mod = importlib.import_module(MODULE_PATH)",
            f"        fn = getattr(mod, '{fn_name}')",
            "        with pytest.raises(NotImplementedError):",
            "            await fn(INPUT_EXAMPLE)",
            "",
            "    def test_input_model_validates_example(self):",
            '        """Pydantic Input model must accept the example payload."""',
            "        mod = importlib.import_module(MODULE_PATH)",
            "        validated = mod.Input.model_validate(INPUT_EXAMPLE)",
            "        assert validated is not None",
        ]

        return "\n".join(lines) + "\n"

    @staticmethod
    def _make_example_input(schema: dict[str, Any]) -> dict[str, Any]:
        """Build a minimal valid example dict from a JSON schema."""
        example: dict[str, Any] = {}
        props = schema.get("properties", {})
        required = set(schema.get("required", []))
        type_defaults: dict[str, Any] = {
            "string": "example",
            "integer": 1,
            "number": 1.0,
            "boolean": True,
            "array": [],
            "object": {},
        }
        for field_name in required:
            field_schema = props.get(field_name, {})
            json_type = (
                field_schema.get("type", "string") if isinstance(field_schema, dict) else "string"
            )
            example[field_name] = field_schema.get(
                "default", type_defaults.get(str(json_type), "example")
            )  # type: ignore[union-attr]
        return example
