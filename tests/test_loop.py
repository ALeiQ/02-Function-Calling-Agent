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
    def fake(messages, tools, model=None, think=None):
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
    class NoCityResp:
        def raise_for_status(self) -> None:
            pass

        def json(self):
            return {"results": []}

    monkeypatch.setattr("src.tools.weather.requests.get", lambda *a, **k: NoCityResp())
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

    def always_calls_tool(messages, tools, model=None, think=None):
        return _reply(tool_calls=[_tool_call("now", {})])

    monkeypatch.setattr(loop, "_chat_once", always_calls_tool)
    result = loop.chat("一直调用工具", store=SessionStore())
    assert result["ok"] is False
    assert "max_turns" in result["answer"] or "最大调用轮数" in result["answer"]
    assert result["turns"] == 3


def test_request_exception_reported(monkeypatch) -> None:
    def failing(messages, tools, model=None, think=None):
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


def test_chat_stream_events_tool_turn(monkeypatch) -> None:
    script = iter(
        [
            iter(
                [("message", _reply(tool_calls=[_tool_call("calculator", {"expression": "2*3"})]))]
            ),
            iter([("message", _reply("答案是 6"))]),
        ]
    )

    def fake_stream_once(messages, tools, model=None, think=None):
        return next(script)

    monkeypatch.setattr(loop, "_chat_stream_once", fake_stream_once)
    events = list(loop.chat_stream("2×3？", store=SessionStore()))
    types = [e["type"] for e in events]
    assert types == ["tool_call", "tool_result", "chunk", "done"]
    assert events[0]["tool"] == "calculator"
    assert events[0]["index"] == 0
    assert events[1]["index"] == 0
    assert events[1]["result"] == "6"
    assert events[2]["text"] == "答案是 6"
    assert events[3]["answer"] == "答案是 6"


def test_chat_stream_events_token_chunks(monkeypatch) -> None:
    turns = iter(
        [
            iter(
                [
                    ("chunk", "答"),
                    ("chunk", "案是"),
                    ("message", {"role": "assistant", "content": "答案是", "tool_calls": []}),
                ]
            )
        ]
    )

    def fake_stream_once(messages, tools, model=None, think=None):
        return next(turns)

    monkeypatch.setattr(loop, "_chat_stream_once", fake_stream_once)
    events = list(loop.chat_stream("2×3？", store=SessionStore()))
    assert events[:-1] == [
        {"type": "chunk", "text": "答"},
        {"type": "chunk", "text": "案是"},
    ]
    assert events[-1] == {"type": "done", "answer": "答案是", "trace": [], "turns": 1, "ok": True}


def test_chat_once_wire_format(monkeypatch) -> None:
    """The non-streaming call posts the expected /api/chat payload."""
    class FakeResp:
        def raise_for_status(self) -> None:
            pass

        def json(self):
            return {"message": {"content": "ok", "tool_calls": []}}

    captured: dict = {}

    def fake_post(url, json, timeout, stream=None):
        captured["url"] = url
        captured["json"] = json
        return FakeResp()

    monkeypatch.setattr(loop._requests, "post", fake_post)
    reply = loop._chat_once([{"role": "user", "content": "hi"}], [{"type": "function"}])
    assert reply == {"content": "ok", "tool_calls": []}
    assert captured["url"].endswith("/api/chat")
    assert captured["json"]["stream"] is False
    assert captured["json"]["model"] == settings.ollama_model
    assert captured["json"]["options"]["temperature"] == settings.temperature


def test_chat_once_http_error_reported(monkeypatch) -> None:
    class BadResp:
        def raise_for_status(self) -> None:
            raise _requests.HTTPError("500 Internal Server Error")

    monkeypatch.setattr(loop._requests, "post", lambda *a, **k: BadResp())
    result = loop.chat("hi", store=SessionStore())
    assert result["ok"] is False
    assert "调用模型失败" in result["answer"]


def test_chat_stream_once_streams_tokens(monkeypatch) -> None:
    lines = iter(
        [
            b'data: {"message":{"role":"assistant","content":"\u7b54"}}',
            b'data: {"message":{"role":"assistant","content":"\u6848"}}',
            b'data: {"done":true}',
        ]
    )

    class FakeResp:
        def raise_for_status(self) -> None:
            pass

        def iter_lines(self, decode_unicode=False):
            return lines

        def close(self) -> None:
            pass

    captured: dict = {}

    def fake_post(url, json, timeout, stream=True):
        captured["url"] = url
        captured["json"] = json
        captured["stream"] = stream
        captured["timeout"] = timeout
        return FakeResp()

    monkeypatch.setattr(loop._requests, "post", fake_post)
    events = list(loop._chat_stream_once([{"role": "user", "content": "hi"}], []))
    assert events == [
        ("chunk", "答"),
        ("chunk", "案"),
        ("message", {"content": "答案", "tool_calls": []}),
    ]
    assert captured["json"]["stream"] is True
    assert captured["json"]["model"] == settings.ollama_model
    assert captured["stream"] is True


def test_chat_stream_once_http_error_falls_back(monkeypatch) -> None:
    class BadResp:
        def raise_for_status(self) -> None:
            raise _requests.HTTPError("500 Internal Server Error")

    monkeypatch.setattr(
        loop._requests,
        "post",
        lambda *a, **k: BadResp(),
    )
    monkeypatch.setattr(loop, "_chat_once", lambda m, t, model=None: _reply("答案"))
    events = list(loop._chat_stream_once([], []))
    assert events == [("message", _reply("答案"))]


def test_chat_stream_once_empty_stream_falls_back(monkeypatch) -> None:
    lines = iter([b'data: {"message":{}}'])

    class FakeResp:
        def raise_for_status(self) -> None:
            pass

        def iter_lines(self, decode_unicode=False):
            return lines

        def close(self) -> None:
            pass

    monkeypatch.setattr(loop._requests, "post", lambda *a, **k: FakeResp())
    monkeypatch.setattr(loop, "_chat_once", lambda m, t, model=None: _reply("答案"))
    events = list(loop._chat_stream_once([], []))
    assert events == [("message", _reply("答案"))]


def test_chat_stream_once_tool_call_message(monkeypatch) -> None:
    lines = iter(
        [
            b'data: {"message":{"role":"assistant","content":"","tool_calls":'
            b'[{"function":{"name":"now","arguments":{}}}]}}',
            b'data: {"done":true}',
        ]
    )

    class FakeResp:
        def raise_for_status(self) -> None:
            pass

        def iter_lines(self, decode_unicode=False):
            return lines

        def close(self) -> None:
            pass

    monkeypatch.setattr(loop._requests, "post", lambda *a, **k: FakeResp())
    events = [e for e in loop._chat_stream_once([], []) if e[0] == "message"]
    assert events == [
        (
            "message",
            {"content": "", "tool_calls": [_tool_call("now", {})]},
        )
    ]


def test_chat_model_override_reaches_model_call(monkeypatch) -> None:
    seen: dict[str, object] = {}

    def spy(messages, tools, model=None, think=None):
        seen["model"] = model
        return _reply("done")

    monkeypatch.setattr(loop, "_chat_once", spy)
    loop.chat("hi", model="qwen3:8b", store=SessionStore())
    assert seen["model"] == "qwen3:8b"


def test_chat_stream_model_override_reaches_model_call(monkeypatch) -> None:
    seen: dict[str, object] = {}

    def spy(messages, tools, model=None, think=None):
        seen["model"] = model
        yield "message", _reply("done")

    monkeypatch.setattr(loop, "_chat_stream_once", spy)
    list(loop.chat_stream("hi", model="qwen3:8b", store=SessionStore()))
    assert seen["model"] == "qwen3:8b"


def test_chat_stream_request_exception(monkeypatch) -> None:
    def failing(messages, tools, model=None, think=None):
        raise _requests.ConnectionError("boom")
        yield

    monkeypatch.setattr(loop, "_chat_stream_once", failing)
    events = list(loop.chat_stream("hi", store=SessionStore()))
    assert events[-1]["ok"] is False
    assert "调用模型失败" in events[-1]["answer"]
    assert events[-1]["turns"] == 1


def test_chat_stream_turn_cap(monkeypatch) -> None:
    monkeypatch.setattr(settings, "max_turns", 2)

    def always_tool(messages, tools, model=None, think=None):
        yield "message", _reply(tool_calls=[_tool_call("now", {})])

    monkeypatch.setattr(loop, "_chat_stream_once", always_tool)
    events = list(loop.chat_stream("hi", store=SessionStore()))
    assert events[-1]["ok"] is False
    assert "最大调用轮数" in events[-1]["answer"]
    assert events[-1]["turns"] == 2


# think 缺省→传给 Ollama 的 think=None(Ollama 顶层用服务器默认)
def test_chat_think_defaults_none(monkeypatch):
    import src.agent.loop as loop

    bag = {}

    def fake(messages, tools, model=None, think=None):
        bag["think"] = think
        return {"content": "hi", "tool_calls": []}

    monkeypatch.setattr(loop, "_chat_once", fake)
    loop.chat("hi")
    assert bag["think"] is None


def test_chat_think_true_reaches_model(monkeypatch):
    import src.agent.loop as loop

    bag = {}

    def fake(messages, tools, model=None, think=None):
        bag["think"] = think
        return {"content": "hi", "tool_calls": []}

    monkeypatch.setattr(loop, "_chat_once", fake)
    loop.chat("hi", think=True)
    assert bag["think"] is True
