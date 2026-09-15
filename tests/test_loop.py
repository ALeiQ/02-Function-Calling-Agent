"""Agent loop: multi-turn tool calls, parallel calls, error self-heal, turn cap.

The Ollama client is monkeypatched at the ``_chat_once`` seam so all scenarios
run hermetically without a model.
"""

import requests as _requests

from src.agent import loop
from src.agent.session import SessionStore
from src.config import settings


def _reply(content: str = "", tool_calls: list | None = None) -> dict:
    return {"content": content, "tool_calls": tool_calls or []}


def _tool_call(name: str, arguments: dict) -> dict:
    return {"function": {"name": name, "arguments": arguments}}


def _fake_client(script: list[dict], monkeypatch, seen: list | None = None):
    def fake(messages, tools):
        if seen is not None:
            seen.append((list(messages), list(tools)))
        if not script:
            raise AssertionError("模型应答脚本已耗尽")
        return script.pop(0)

    monkeypatch.setattr(loop, "_chat_once", fake)


def test_direct_answer_no_tools(monkeypatch) -> None:
    _fake_client([_reply("你好！")], monkeypatch)
    result = loop.chat("打个招呼", store=SessionStore())
    assert result["answer"] == "你好！"
    assert result["turns"] == 1
    assert result["ok"] is True
    assert result["trace"] == []


def test_single_tool_call_then_answer(monkeypatch) -> None:
    script = [
        _reply(tool_calls=[_tool_call("calculator", {"expression": "3*4"})]),
        _reply("结果是 12"),
    ]
    _fake_client(script, monkeypatch)
    result = loop.chat("3×4 等于多少？", store=SessionStore())
    assert result["answer"] == "结果是 12"
    assert result["turns"] == 2
    assert len(result["trace"]) == 1
    assert result["trace"][0]["tool"] == "calculator"
    assert result["trace"][0]["result"] == "12"


def test_parallel_tool_calls_in_one_turn(monkeypatch) -> None:
    script = [
        _reply(
            tool_calls=[
                _tool_call("now", {}),
                _tool_call("calculator", {"expression": "20/4"}),
            ]
        ),
        _reply("现在是今天，20/4 等于 5"),
    ]
    store = SessionStore()
    _fake_client(script, monkeypatch)
    result = loop.chat("现在几点？20 除以 4 呢？", store=store)
    assert len(result["trace"]) == 2
    assert {t["tool"] for t in result["trace"]} == {"now", "calculator"}
    session = list(store.all())[0]
    tool_msgs = [m for m in session.messages if m["role"] == "tool"]
    assert len(tool_msgs) == 2
    assert tool_msgs[0]["name"] == "now"
    assert tool_msgs[1]["name"] == "calculator"


def test_tool_error_returned_for_self_heal(monkeypatch) -> None:
    script = [
        _reply(tool_calls=[_tool_call("weather", {"city": "火星"})]),
        _reply("抱歉，城市「火星」不在支持列表中。"),
    ]
    _fake_client(script, monkeypatch)
    result = loop.chat("火星天气？", store=SessionStore())
    assert result["trace"][0]["result"].startswith("ERROR:")
    assert result["ok"] is True


def test_max_turns_cap(monkeypatch) -> None:
    monkeypatch.setattr(settings, "max_turns", 3)

    def always_calls_tool(messages, tools):
        return _reply(tool_calls=[_tool_call("now", {})])

    monkeypatch.setattr(loop, "_chat_once", always_calls_tool)
    result = loop.chat("一直调用工具", store=SessionStore())
    assert result["ok"] is False
    assert "max_turns" in result["answer"] or "最大调用轮数" in result["answer"]
    assert result["turns"] == 3


def test_request_exception_reported(monkeypatch) -> None:
    def failing(messages, tools):
        raise _requests.ConnectionError("refused")

    monkeypatch.setattr(loop, "_chat_once", failing)
    result = loop.chat("hi", store=SessionStore())
    assert result["ok"] is False
    assert "调用模型失败" in result["answer"]


def test_session_preserves_history(monkeypatch) -> None:
    script = [
        _reply("第一轮回答"),
        _reply(tool_calls=[_tool_call("now", {})]),
        _reply("第二轮，并给出时间"),
    ]
    store = SessionStore()
    _fake_client(script, monkeypatch)
    loop.chat("问题一", session_id="s1", store=store)
    loop.chat("问题二", session_id="s1", store=store)
    session = store.get_or_create("s1")
    roles = [m["role"] for m in session.messages]
    assert roles == ["system", "user", "assistant", "user", "assistant", "tool", "assistant"]
    assert session.messages[1]["content"] == "问题一"
    assert session.messages[3]["content"] == "问题二"


def test_tools_schemas_sent_to_model(monkeypatch) -> None:
    seen: list = []
    _fake_client([_reply("done")], monkeypatch, seen=seen)
    loop.chat("hi", store=SessionStore())
    _, tools = seen[0]
    names = [t["function"]["name"] for t in tools]
    assert set(names) == {"calculator", "weather", "sql", "now"}


def test_chat_stream_events(monkeypatch) -> None:
    script = [
        _reply(tool_calls=[_tool_call("calculator", {"expression": "2*3"})]),
        _reply("答案是 6"),
    ]
    _fake_client(script, monkeypatch)
    events = list(loop.chat_stream("2×3？", store=SessionStore()))
    types = [e["type"] for e in events]
    assert types == ["tool_call", "tool_result", "done"]
    assert events[0]["tool"] == "calculator"
    assert events[1]["result"] == "6"
    assert events[2]["answer"] == "答案是 6"
