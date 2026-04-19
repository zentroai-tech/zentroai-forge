# Tools and MCP

Forge supports two tool paths:

1. registered tool contracts
2. MCP tools referenced with the `mcp:` prefix

## Tool contracts

Tool contracts describe:

- input/output schema
- auth requirements
- network and data access scope
- runtime policy metadata
- whether the tool needs external implementation

Built-in implemented tools include:

- `web_search`
- `search`
- `url_reader`
- `calculator`
- `datetime`
- `echo`
- `safe_calculator`
- `http_get`

Contract-only tools currently include:

- `sql_query`
- `http_request`
- `python_sandbox`
- `s3_get_object`

## Generated tool files in exports

When a flow references tools, the exporter writes tool artifacts into the export,
including contracts and implementation files.

Typical structure:

```text
app/tools/contracts/
app/tools/impl/
tests/test_tool_contract_<tool>.py
```

## MCP

Any `tool_name` starting with `mcp:` is treated as an MCP tool.

MCP execution is controlled by:

- `AGENT_COMPILER_MCP_ENABLED`
- `AGENT_COMPILER_MCP_ALLOWED_COMMANDS`
- `AGENT_COMPILER_MCP_ALLOWED_TOOLS`
- timeout and response-size limits in backend settings

## Production note

Do not leave MCP unrestricted in production. An empty command allowlist means
subprocess spawning is effectively unrestricted.
