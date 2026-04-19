"""Security helpers for tool execution."""

from __future__ import annotations

import ast
import operator
from typing import Any


def is_tool_allowed(tool_name: str, allowlist: list[str]) -> bool:
    """Check if a tool name is allowed by an allowlist with wildcard support.

    Supported patterns:
    - "*": allow all
    - "prefix:*": allow any tool that starts with "prefix:"
    - exact match
    """
    if not allowlist:
        return False

    for pattern in allowlist:
        if pattern == "*":
            return True
        if pattern.endswith("*") and tool_name.startswith(pattern[:-1]):
            return True
        if pattern == tool_name:
            return True
    return False


_UNARY_OPS: dict[type[ast.AST], Any] = {
    ast.UAdd: operator.pos,
    ast.USub: operator.neg,
}

_BINARY_OPS: dict[type[ast.AST], Any] = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
}


def safe_calculator_eval(expression: str) -> float | int:
    """Evaluate a strictly arithmetic expression.

    Allowed:
    - numbers
    - +, -, *, /, //, %, **
    - unary + and -
    - parentheses
    """
    tree = ast.parse(expression, mode="eval")
    return _eval_node(tree.body)


def _eval_node(node: ast.AST) -> float | int:
    if isinstance(node, ast.Constant):
        if isinstance(node.value, (int, float)):
            return node.value
        raise ValueError("Only numeric constants are allowed")

    if isinstance(node, ast.UnaryOp):
        op = _UNARY_OPS.get(type(node.op))
        if op is None:
            raise ValueError(f"Unsupported unary operator: {type(node.op).__name__}")
        return op(_eval_node(node.operand))

    if isinstance(node, ast.BinOp):
        op = _BINARY_OPS.get(type(node.op))
        if op is None:
            raise ValueError(f"Unsupported binary operator: {type(node.op).__name__}")
        left = _eval_node(node.left)
        right = _eval_node(node.right)
        return op(left, right)

    raise ValueError(f"Unsupported expression element: {type(node).__name__}")
