"""CLI commands: chat / repl / tools / seed / serve (model calls mocked)."""

from __future__ import annotations

import pytest
from typer.testing import CliRunner

from src.agent import loop
from src.main import app

runner = CliRunner()


def test_tools_command_lists_names() -> None:
    result = runner.invoke(app, ["tools"])
    assert result.exit_code == 0
    for name in ("calculator", "weather", "sql", "now"):
        assert name in result.output


def test_chat_command_prints_answer(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_chat(message, session_id=None, store=None):
        return {"answer": "你好世界", "trace": [], "turns": 1, "ok": True}

    monkeypatch.setattr(loop, "chat", fake_chat)
    result = runner.invoke(app, ["chat", "打个招呼"])
    assert result.exit_code == 0
    assert "你好世界" in result.output


def test_chat_command_prints_trace(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_chat(message, session_id=None, store=None):
        return {
            "answer": "结果是 6",
            "trace": [{"tool": "calculator", "arguments": {"expression": "3*2"}, "result": "6"}],
            "turns": 2,
            "ok": True,
        }

    monkeypatch.setattr(loop, "chat", fake_chat)
    result = runner.invoke(app, ["chat", "3*2"])
    assert result.exit_code == 0
    assert "calculator" in result.output
    assert "结果是 6" in result.output


def test_seed_command(monkeypatch: pytest.MonkeyPatch) -> None:
    called: list[str] = []

    def fake_build(path: str | None = None) -> str:
        called.append(path)
        return path or "fake.db"

    monkeypatch.setattr("scripts.seed_db.build", fake_build)
    result = runner.invoke(app, ["seed"])
    assert result.exit_code == 0
    assert called, "seed 应调用 scripts.seed_db.build"


def test_serve_command_starts_uvicorn(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: dict = {}

    def fake_run(app_path, host=None, port=None, reload=None):
        calls.update(app=app_path, host=host, port=port, reload=reload)

    monkeypatch.setattr("uvicorn.run", fake_run)
    result = runner.invoke(app, ["serve", "--port", "8999"])
    assert result.exit_code == 0
    assert calls["app"] == "src.api.app:app"
    assert calls["port"] == 8999


def test_repl_conversation_and_exit(monkeypatch: pytest.MonkeyPatch) -> None:
    messages: list[str] = []

    def fake_chat(message, session_id=None, store=None):
        messages.append(message)
        return {"answer": "收到: " + message, "trace": [], "turns": 1, "ok": True}

    monkeypatch.setattr(loop, "chat", fake_chat)
    result = runner.invoke(app, ["repl"], input="你好吗？\n/exit\n")
    assert result.exit_code == 0
    assert messages == ["你好吗？"]
    assert "收到: 你好吗？" in result.output


def test_repl_clear_command(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        loop, "chat", lambda *a, **k: {"answer": "a", "trace": [], "turns": 1, "ok": True}
    )
    result = runner.invoke(app, ["repl"], input="/clear\n/exit\n")
    assert result.exit_code == 0
    assert "已清空会话历史" in result.output


def test_repl_skips_blank_lines(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        loop, "chat", lambda *a, **k: {"answer": "a", "trace": [], "turns": 1, "ok": True}
    )
    result = runner.invoke(app, ["repl"], input="   \n/exit\n")
    assert result.exit_code == 0


def test_repl_eof_exits_gracefully() -> None:
    result = runner.invoke(app, ["repl"], input="")
    assert result.exit_code == 0
    assert "再见" in result.output
