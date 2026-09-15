"""Deterministic arithmetic calculator.

Uses an AST whitelist (numbers, + - * / and parentheses) instead of ``eval``,
so the agent can only trigger safe arithmetic.

TODO(milestone 2): implement ``evaluate`` with ``ast`` and expose as a tool.
"""


class CalculationError(ValueError):
    """Raised when an expression is syntactically or arithmetically invalid."""