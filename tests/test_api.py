"""Tests for the FastAPI HTTP + SSE layer (model calls mocked away)."""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from src.agent import loop
from src.agent.session import SessionStore
from src.api.app import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def _clean_store(monkeypatch: pytest.MonkeyPatch) -> None:
    store = SessionStore()
    monkeypatch.setattr("src.api.routes.default_store", store)
    monkeypatch.setattr("src.agent.loop.default_store", store)


def test_health() -> None:
    resp = client.get("/api/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_tools() -> None:
    resp = client.get("/api/tools")
    assert resp.status_code == 200
    names = {t["name"] for t in resp.json()["tools"]}
    assert {"calculator", "weather", "sql", "now"} <= names


def test_chat(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_chat(message, session_id=None, store=None, model=None):
        return {
            "answer": "42",
            "trace": [
                {"index": 0, "tool": "calculator", "arguments": {"expr": "6*7"}, "result": "42"}
            ],
            "turns": 2,
            "ok": True,
        }

    monkeypatch.setattr(loop, "chat", fake_chat)
    resp = client.post("/api/chat", json={"message": "6乘7？"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["answer"] == "42"
    assert body["turns"] == 2
    assert body["ok"] is True
    assert body["trace"][0]["tool"] == "calculator"


def test_chat_model_override_reaches_loop(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict[str, object] = {}

    def fake_chat(message, session_id=None, store=None, model=None):
        seen["model"] = model
        return {"answer": "hi", "trace": [], "turns": 1, "ok": True}

    monkeypatch.setattr(loop, "chat", fake_chat)
    resp = client.post("/api/chat", json={"message": "hi", "model": "qwen3:8b"})
    assert resp.status_code == 200
    assert seen["model"] == "qwen3:8b"


def test_chat_requires_message() -> None:
    resp = client.post("/api/chat", json={"message": ""})
    assert resp.status_code == 422


def test_chat_stream_sse(monkeypatch: pytest.MonkeyPatch) -> None:
    events = [
        {"type": "tool_call", "index": 0, "tool": "now", "arguments": {}},
        {"type": "tool_result", "index": 0, "tool": "now", "result": "当前时间..."},
        {"type": "chunk", "text": "现在是"},
        {"type": "chunk", "text": "中午。"},
        {"type": "done", "answer": "现在是中午。", "trace": [], "turns": 2, "ok": True},
    ]

    def fake_stream(message, session_id=None, store=None, model=None):
        yield from events

    monkeypatch.setattr(loop, "chat_stream", fake_stream)
    resp = client.post("/api/chat/stream", json={"message": "几点了？"})
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/event-stream")

    frames: list[dict] = []
    for line in resp.text.splitlines():
        if line.startswith("data: "):
            frames.append(json.loads(line[6:]))
    assert frames == events


def test_streaming_chunks_reach_client(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_stream(message, session_id=None, store=None, model=None):
        yield {"type": "chunk", "text": "你"}
        yield {"type": "chunk", "text": "好"}
        yield {"type": "done", "answer": "你好", "trace": [], "turns": 1, "ok": True}

    monkeypatch.setattr(loop, "chat_stream", fake_stream)
    resp = client.post("/api/chat/stream", json={"message": "hi"})
    chunks = [json.loads(line[6:]) for line in resp.text.splitlines() if line.startswith("data: ")]
    assert [c["type"] for c in chunks] == ["chunk", "chunk", "done"]
    assert "".join(c["text"] for c in chunks if c["type"] == "chunk") == "你好"
    assert chunks[-1]["answer"] == "你好"


def test_index_served() -> None:
    resp = client.get("/")
    assert resp.status_code == 200
    assert "Function-Calling Agent" in resp.text


def test_stream_endpoint_reports_generator_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    def exploding(message, session_id=None, store=None, model=None):
        raise RuntimeError("kaboom")
        yield

    monkeypatch.setattr(loop, "chat_stream", exploding)
    resp = client.post("/api/chat/stream", json={"message": "hi"})
    assert resp.status_code == 200
    assert "服务端错误" in resp.text
    assert '"ok": false' in resp.text


def test_models_endpoint(monkeypatch: pytest.MonkeyPatch) -> None:
    available = ["qwen2.5:latest", "qwen3:8b"]
    monkeypatch.setattr("src.api.routes._ollama_model_names", lambda: available)
    from src.config import settings

    monkeypatch.setattr(settings, "ollama_model", "qwen2.5:latest")
    resp = client.get("/api/models")
    assert resp.status_code == 200
    body = resp.json()
    assert "qwen2.5:latest" in body["models"]
    assert "qwen3:8b" in body["models"]
    assert body["current"] == "qwen2.5:latest"


def test_select_model_switches_default(monkeypatch: pytest.MonkeyPatch) -> None:
    from src.config import settings

    monkeypatch.setattr(settings, "ollama_model", "qwen2.5:latest")
    monkeypatch.setattr(
        "src.api.routes._ollama_model_names", lambda: ["qwen2.5:latest", "qwen3:8b"]
    )
    resp = client.post("/api/model", json={"model": "qwen3:8b"})
    assert resp.status_code == 200
    assert resp.json()["model"] == "qwen3:8b"
    assert settings.ollama_model == "qwen3:8b"


def test_select_model_not_found(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("src.api.routes._ollama_model_names", lambda: ["qwen2.5:latest"])
    resp = client.post("/api/model", json={"model": "gpt-4o"})
    assert resp.status_code == 404
