"""Declarative tool registry.

Collects every ``@tool``-decorated function into a single, auditable list of
tool definitions, generates the JSON schemas the model receives, and dispatches
incoming ``tool_calls`` to the matching executor.

Error contract
--------------
``execute`` never raises: tool failures (validation, guardrail, execution) are
returned as ``ERROR: <message>`` strings so the agent can feed them back to the
model and let it self-correct.
"""

from __future__ import annotations

from typing import Any, Callable

from pydantic import BaseModel, ValidationError

_TOOLS: dict[str, "_Tool"] = {}


class ToolError(Exception):
    """Base class for expected, user-facing tool failures."""


class DuplicateToolError(ToolError):
    """Raised when two tools register under the same name."""


class _Tool:
    def __init__(
        self,
        name: str,
        description: str,
        args_model: type[BaseModel],
        func: Callable[..., str],
    ) -> None:
        self.name = name
        self.description = description
        self.args_model = args_model
        self.func = func

    def schema(self) -> dict[str, Any]:
        """Return the OpenAI/Ollama-style tool definition for the model."""
        parameters = self.args_model.model_json_schema()
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": parameters,
            },
        }

    def run(self, arguments: dict[str, Any]) -> str:
        """Validate arguments against the pydantic model, then execute."""
        validated = self.args_model(**arguments)
        return self.func(**validated.model_dump())


def tool(
    name: str = "",
    description: str = "",
    args: type[BaseModel] | None = None,
):
    """Register a callable as an agent tool.

    Args:
        name: tool name sent to the model (defaults to the function name).
        description: what the tool does and when to call it.
        args: pydantic model defining the tool's parameters.

    Returns: the original callable, wired into the global registry.
    """

    def decorator(func: Callable[..., str]) -> Callable[..., str]:
        tool_name = name or func.__name__
        if tool_name in _TOOLS:
            raise DuplicateToolError(f"tool already registered: {tool_name}")
        if args is None:
            raise ValueError(f"tool '{tool_name}' requires an args pydantic model")
        _TOOLS[tool_name] = _Tool(tool_name, description, args, func)
        return func

    return decorator


def registry() -> list[dict[str, Any]]:
    """Return the OpenAI/Ollama-style tool definitions for all registered tools."""
    return [t.schema() for t in sorted(_TOOLS.values(), key=lambda t: t.name)]


def tool_names() -> list[str]:
    return sorted(_TOOLS)


def execute(call: dict[str, Any]) -> str:
    """Execute a single ``tool_calls`` entry and return its result as text.

    ``call`` shape (match Ollama's response)::

        {"function": {"name": "...", "arguments": {...}}}

    Always returns a string; on any failure it returns an ``ERROR:`` message.
    """
    try:
        fn = call.get("function", call)
        name = fn["name"]
        arguments = fn.get("arguments") or {}
        tool_def = _TOOLS.get(name)
        if tool_def is None:
            return f"ERROR: 未注册的工具: {name}"
        if not isinstance(arguments, dict):
            return f"ERROR: 工具参数必须是 JSON 对象，得到 {type(arguments).__name__}"
        return tool_def.run(arguments)
    except KeyError as exc:
        return f"ERROR: 工具调用缺少字段: {exc}"
    except ValidationError as exc:
        return f"ERROR: 参数校验失败: {exc.errors(include_url=False)}"
    except ToolError as exc:
        return f"ERROR: {exc}"
    except Exception as exc:  # unexpected — never crash the loop
        return f"ERROR: 工具执行异常 {type(exc).__name__}: {exc}"
