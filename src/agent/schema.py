"""Pydantic parameter models shared by tools, schemas and the API.

Every tool's arguments are defined as a pydantic model so that we get both the
model-facing JSON schema (``model_json_schema()``) and strict, deterministic
runtime validation.

TODO(milestone 2): add per-tool argument models here.
"""

from typing import Any


def tool_schema() -> list[dict[str, Any]]:
    """Build the OpenAI/Ollama-style tool definitions from the registry."""
    raise NotImplementedError