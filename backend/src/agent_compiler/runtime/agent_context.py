"""Agent-level execution context for multi-agent flows.

Tracks per-agent budgets, tool allowlists, and provides budget enforcement.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from agent_compiler.models.ir import FallbackSpec, RetrySpec
from agent_compiler.models.ir_v2 import BudgetSpec, PolicySpec


class BudgetExceededError(Exception):
    """Raised when an agent exceeds its allocated budget."""

    def __init__(self, agent_id: str, resource: str, limit: int, used: int):
        self.agent_id = agent_id
        self.resource = resource
        self.limit = limit
        self.used = used
        super().__init__(
            f"Agent '{agent_id}' exceeded {resource} budget: "
            f"{used}/{limit}"
        )


@dataclass
class AgentRunContext:
    """Per-agent execution context with budget tracking and tool isolation."""

    agent_id: str
    run_id: str
    parent_run_context: AgentRunContext | None = None
    depth: int = 0
    memory_namespace: str | None = None
    tools_allowlist: list[str] = field(default_factory=list)
    budgets: BudgetSpec = field(default_factory=BudgetSpec)
    policies: PolicySpec | None = None
    retries: RetrySpec | None = None
    fallbacks: FallbackSpec | None = None

    # Tracking counters
    tokens_used: int = 0
    tool_calls_made: int = 0
    steps_executed: int = 0

    def check_budget(self) -> None:
        """Check if the agent is still within budget.

        Raises:
            BudgetExceededError: If any budget limit is exceeded.
        """
        if self.budgets.max_tokens is not None and self.tokens_used >= self.budgets.max_tokens:
            raise BudgetExceededError(
                self.agent_id, "max_tokens", self.budgets.max_tokens, self.tokens_used
            )
        if self.budgets.max_tool_calls is not None and self.tool_calls_made >= self.budgets.max_tool_calls:
            raise BudgetExceededError(
                self.agent_id, "max_tool_calls", self.budgets.max_tool_calls, self.tool_calls_made
            )
        if self.budgets.max_steps is not None and self.steps_executed >= self.budgets.max_steps:
            raise BudgetExceededError(
                self.agent_id, "max_steps", self.budgets.max_steps, self.steps_executed
            )

    def is_tool_allowed(self, tool_name: str) -> bool:
        """Check if a tool is in the agent's allowlist.

        If the allowlist is empty, all tools are allowed.
        """
        allowlist = self.tools_allowlist
        if self.policies and self.policies.tool_allowlist:
            allowlist = self.policies.tool_allowlist
        if not allowlist:
            return True
        return tool_name in allowlist
