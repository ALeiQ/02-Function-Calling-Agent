"""Conversation session and message-history management.

Keeps the per-session role/message list that the agent loop grows with tool
results. Sessions are immutable snapshots until persisted (M4); the CLI keeps
one in-memory session per chat.
"""

from __future__ import annotations

import uuid
from typing import Any


class Session:
    def __init__(self, session_id: str) -> None:
        self.session_id = session_id
        self.messages: list[dict[str, Any]] = []

    def add(self, message: dict[str, Any]) -> None:
        self.messages.append(message)


class SessionStore:
    """In-memory session store (no cross-process persistence yet)."""

    def __init__(self) -> None:
        self._sessions: dict[str, Session] = {}

    def get_or_create(self, session_id: str | None = None) -> Session:
        session_id = session_id or uuid.uuid4().hex[:8]
        if session_id not in self._sessions:
            self._sessions[session_id] = Session(session_id)
        return self._sessions[session_id]

    def clear(self, session_id: str) -> None:
        self._sessions.pop(session_id, None)

    def all(self) -> list[Session]:
        return list(self._sessions.values())


default_store = SessionStore()
