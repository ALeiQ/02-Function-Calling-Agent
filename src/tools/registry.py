"""Declarative tool registry.

Collects every ``@tool``-decorated function into a single, auditable list of
tool definitions, generates the JSON schemas the model receives, and dispatches
incoming ``tool_calls`` to the matching executor.

TODO(milestone 2): full implementation.
"""

from __future__ import annotations

from typing import Any


def tool(name: str = "", description: str = ""):
    """Register a callable as an agent tool.

    Returns: the original callable, wired into the global registry.
    TODO(milestone 2): implement.
    """
    raise NotImplementedError


def registry() -> list[dict[str, Any]]:
    """Return the OpenAI/Ollama-style tool definitions for all registered tools."""
    raise NotImplementedError


def execute(call: dict[str, Any]) -> str:
    """Execute a single ``tool_calls`` entry and return its result as text.

    TODO(milestone 2): implement dispatch, argument validation and error capture.
    """
    raise NotImplementedError