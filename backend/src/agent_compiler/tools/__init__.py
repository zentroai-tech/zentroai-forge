"""Tool Contracts module.

Provides a normalized registry of tool contracts (input/output schemas,
auth requirements, network/data scopes) and runtime tool resolution.
"""

from agent_compiler.tools.contracts import (
    ToolContract,
    ToolContractRegistry,
    get_tool_contract_registry,
)

__all__ = [
    "ToolContract",
    "ToolContractRegistry",
    "get_tool_contract_registry",
]
