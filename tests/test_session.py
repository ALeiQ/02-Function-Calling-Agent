"""Session and SessionStore: creation, reuse, clear and message history."""

from __future__ import annotations

from src.agent.session import Session, SessionStore


def test_get_or_create_generates_id() -> None:
    store = SessionStore()
    session = store.get_or_create()
    assert session.session_id
    assert len(store.all()) == 1


def test_get_or_create_reuses_session() -> None:
    store = SessionStore()
    first = store.get_or_create("s1")
    second = store.get_or_create("s1")
    assert first is second
    assert len(store.all()) == 1


def test_session_add_appends_messages() -> None:
    session = Session("s1")
    session.add({"role": "user", "content": "hi"})
    session.add({"role": "assistant", "content": "hello"})
    assert [m["role"] for m in session.messages] == ["user", "assistant"]


def test_clear_removes_only_target() -> None:
    store = SessionStore()
    store.get_or_create("s1")
    store.get_or_create("s2")
    store.clear("s1")
    assert list(store.all())[0].session_id == "s2"


def test_clear_missing_id_is_noop() -> None:
    store = SessionStore()
    store.clear("nonexistent")
    assert store.all() == []
