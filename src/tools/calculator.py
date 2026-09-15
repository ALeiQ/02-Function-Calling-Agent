"""Deterministic arithmetic calculator.

Uses an AST whitelist (numbers, + - * / and unary minus) instead of ``eval``,
so the agent can only trigger safe arithmetic on plain numbers.
"""

from __future__ import annotations

import ast

from pydantic import BaseModel, Field

from src.tools.registry import ToolError, tool


class CalculationError(ToolError):
    """Raised when an expression is syntactically or arithmetically invalid."""


class CalculatorArgs(BaseModel):
    expression: str = Field(..., description="数学表达式，例如 (12*8+9)/5")


_ALLOWED_BINOPS = {
    ast.Add: lambda a, b: a + b,
    ast.Sub: lambda a, b: a - b,
    ast.Mult: lambda a, b: a * b,
    ast.Div: lambda a, b: a / b,
}


def _eval(node: ast.AST) -> int | float:
    if isinstance(node, ast.Expression):
        return _eval(node.body)
    if (
        isinstance(node, ast.Constant)
        and isinstance(node.value, (int, float))
        and not isinstance(node.value, bool)
    ):
        return node.value
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
        value = _eval(node.operand)
        return value if isinstance(node.op, ast.UAdd) else -value
    if isinstance(node, ast.BinOp) and type(node.op) in _ALLOWED_BINOPS:
        left, right = _eval(node.left), _eval(node.right)
        if isinstance(node.op, ast.Div) and right == 0:
            raise CalculationError("除数不能为 0")
        return _ALLOWED_BINOPS[type(node.op)](left, right)
    raise CalculationError(f"表达式包含不支持的语法: {type(node).__name__}")


def _format(value: int | float) -> str:
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


def evaluate(expression: str) -> str:
    """Evaluate a safe arithmetic expression and return its result as text."""
    if not expression or not expression.strip():
        raise CalculationError("表达式不能为空")
    expression = expression.strip()
    try:
        tree = ast.parse(expression, mode="eval")
    except SyntaxError as exc:
        raise CalculationError(f"表达式语法错误: {exc.msg}") from exc
    return _format(_eval(tree))


@tool(
    description=(
        "精确计算数学表达式。当用户需要做加减乘除、括号等算术运算时使用，"
        "例如 '(12*8+9)/5'。不要自己心算，一律调用本工具。"
    ),
    args=CalculatorArgs,
)
def calculator(expression: str) -> str:
    return evaluate(expression)
