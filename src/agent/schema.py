"""Model-facing tool schema assembly.

Every tool's parameters are defined as a pydantic model in its module; the
registry turns each into the OpenAI/Ollama-style JSON schema the model sees.
"""

from __future__ import annotations

from typing import Any

from src.tools import registry


def tool_schema() -> list[dict[str, Any]]:
    """Build the OpenAI/Ollama-style tool definitions from the registry."""
    return registry()
