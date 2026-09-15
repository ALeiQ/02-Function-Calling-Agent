"""The multi-turn tool-calling loop.

Protocol
--------
1. Send messages + tool schemas to the model via Ollama ``/api/chat``.
2. If the reply contains ``tool_calls``: execute each (possibly parallel),
   append one ``tool`` result message per call, and loop again.
3. If there are no ``tool_calls``, the reply ``content`` is the final answer.
4. If the turn budget (``settings.max_turns``) is exhausted, stop with a clear
   fallback instead of looping forever.

TODO(milestone 2): implement ``chat``, ``chat_stream`` and the loop.
"""

from __future__ import annotations

from typing import Any


def chat(message: str, session_id: str | None = None, **kwargs: Any) -> dict:
    """Run the full loop for one user message and return the final reply.

    TODO(milestone 2): implement.
    """
    raise NotImplementedError


def chat_stream(message: str, session_id: str | None = None, **kwargs: Any) -> Any:
    """Same as ``chat`` but yields tool-call events and answer chunks.

    TODO(milestone 2): implement as a generator.
    """
    raise NotImplementedError