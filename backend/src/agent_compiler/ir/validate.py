"""IR tool-reference validation.

Rules:
  - Every TOOL node's ``tool_name`` must be one of:
      1. A registered contract in ToolContractRegistry, OR
      2. An MCP wildcard (starts with "mcp:")
  - Unknown non-MCP tool names raise IRToolValidationError unless
    ``allow_unknown`` is True (soft-fail mode).
  - Global-tool entries in ``resources.global_tools`` are validated
    with the same rules.
"""

from __future__ import annotations

from typing import Any

from agent_compiler.models.ir import NodeType
from agent_compiler.models.ir_v2 import FlowIRv2
from agent_compiler.tools.contracts import get_tool_contract_registry
from agent_compiler.observability.logging import get_logger

logger = get_logger(__name__)


class IRToolValidationError(Exception):
    """Raised when an IR references an unknown, non-MCP tool."""

    def __init__(self, unknown_tools: list[str], locations: dict[str, list[str]]) -> None:
        self.unknown_tools = unknown_tools
        self.locations = locations  # tool_name -> [location strings]
        lines = [f"  - {t} (in: {', '.join(locs)})" for t, locs in locations.items()]
        super().__init__(
            "IR references unknown tool(s) not found in ToolContractRegistry:\n"
            + "\n".join(lines)
            + "\n\nAdd a ToolContract for each tool, or use an mcp:<name> tool name."
        )


def collect_tool_names(ir: FlowIRv2) -> dict[str, list[str]]:
    """Return {tool_name: [location_description, ...]} for every Tool node in the IR.

    Locations are strings like "agent 'toolsmith' node 'pubmed_search'".
    Global tools declared in resources are also included.
    """
    result: dict[str, list[str]] = {}

    def _add(name: str, location: str) -> None:
        result.setdefault(name, []).append(location)

    for agent in ir.agents:
        for node in agent.graph.nodes:
            if node.type != NodeType.TOOL:
                continue
            params: dict[str, Any] = node.params if isinstance(node.params, dict) else {}
            tool_name = params.get("tool_name", "")
            if tool_name:
                _add(str(tool_name), f"agent '{agent.id}' node '{node.id}'")

        # tools_allowlist on the agent itself is informational — not validated
        # (it may contain wildcards like "mcp:*").

    # global_tools in resources
    if ir.resources and ir.resources.global_tools:
        for tool_name in ir.resources.global_tools:
            _add(str(tool_name), "resources.global_tools")

    return result


def validate_tool_references(
    ir: FlowIRv2,
    *,
    allow_unknown: bool = False,
) -> list[str]:
    """Validate all TOOL node references in the IR.

    Args:
        ir: The FlowIRv2 to validate.
        allow_unknown: If True, unknown tools emit warnings instead of raising.

    Returns:
        List of warning messages (empty when all tools are known).

    Raises:
        IRToolValidationError: If unknown non-MCP tools are found and
            allow_unknown is False.
    """
    registry = get_tool_contract_registry()
    tool_locations = collect_tool_names(ir)

    unknown: dict[str, list[str]] = {}
    warnings: list[str] = []

    for tool_name, locations in tool_locations.items():
        _contract, is_known = registry.resolve(tool_name)
        if not is_known:
            msg = (
                f"Unknown tool '{tool_name}' referenced at: {', '.join(locations)}. "
                "Add a ToolContract or use an mcp:<name> tool name."
            )
            warnings.append(msg)
            unknown[tool_name] = locations

    if unknown:
        if allow_unknown:
            for w in warnings:
                logger.warning(w)
        else:
            raise IRToolValidationError(
                unknown_tools=list(unknown.keys()),
                locations=unknown,
            )

    return warnings
