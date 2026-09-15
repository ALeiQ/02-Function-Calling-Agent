"""The multi-turn tool-calling loop.

Protocol
--------
1. Send messages + tool schemas to the model via Ollama ``/api/chat``.
2. If the reply contains ``tool_calls``: validate & execute each (possibly
   multiple in one turn), append one ``tool`` result message per call, loop.
3. If there are no ``tool_calls``, the reply ``content`` is the final answer.
4. If the turn budget (``settings.max_turns``) is exhausted, stop with a clear
   fallback instead of looping forever.

Tool errors come back as ``ERROR: ...`` strings inside ``tool`` messages, which
lets the model read the failure and self-correct on the next turn.
"""

from __future__ import annotations

from typing import Any, Generator

import requests as _requests

from src.agent.schema import tool_schema
from src.agent.session import Session, SessionStore, default_store
from src.config import settings
from src.tools import execute

SYSTEM_PROMPT = """你是一个具备工具调用能力的助手。

规则:
1. 需要实时数据、精确计算、数据库信息时，必须先调用工具获取结果，不要编造
2. 工具返回以 "ERROR:" 开头的消息时，根据错误提示修正参数后重试，或如实告诉用户失败原因
3. 一次只能并行调用相互独立的工具；存在依赖的前后工具必须分轮执行，
   后一工具的入参要用前一工具的真实结果，禁止用猜出来的值
4. 只有在拿到工具结果之后，才可以基于结果给出最终回答
5. 回答简洁准确，用中文"""

OLLAMA_BASE = settings.ollama_base_url


def _chat_once(
    messages: list[dict], tools: list[dict], model: str | None = None
) -> dict[str, Any]:
    """Call Ollama /api/chat once (non-streaming) and return the message dict.

    ``model=None`` falls back to ``settings.ollama_model``, so callers can
    override the model per request without touching global state.
    """
    resp = _requests.post(
        f"{OLLAMA_BASE}/api/chat",
        json={
            "model": model or settings.ollama_model,
            "messages": messages,
            "tools": tools,
            "options": {"temperature": settings.temperature},
            "stream": False,
        },
        timeout=180,
    )
    resp.raise_for_status()
    return resp.json()["message"]


def _ensure_system_prompt(session: Session) -> None:
    if not session.messages:
        session.add({"role": "system", "content": SYSTEM_PROMPT})


def _chat_stream_once(
    messages: list[dict], tools: list[dict], model: str | None = None
) -> Generator[tuple[str, Any], None, None]:
    """One model turn for the streaming endpoint.

    Ollama + qwen2.5 returns empty results when ``stream: True`` is combined
    with ``tools``, so this uses the non-streaming call (which reliably
    returns tool_calls) and yields the final message. Token-level streaming is
    therefore currently downgraded to a single content chunk per answer.
    """
    reply = _chat_once(messages, tools, model)
    yield "message", reply


def _append_tool_messages(
    session: Session, trace: list[dict], tool_calls: list[dict]
) -> list[dict]:
    """Validate + execute each tool call, append tool messages and trace entries."""
    entries: list[dict] = []
    for index, call in enumerate(tool_calls):
        name = call.get("function", {}).get("name", "?")
        result = execute(call)
        entry = {
            "index": index,
            "tool": name,
            "arguments": call.get("function", {}).get("arguments", {}),
            "result": result,
        }
        entries.append(entry)
        trace.append(entry)
        session.add({"role": "tool", "content": result, "name": name})
    return entries


def chat(
    message: str,
    session_id: str | None = None,
    store: SessionStore | None = None,
    model: str | None = None,
) -> dict[str, Any]:
    """Run the full loop for one user message and return the final reply."""
    store = store or default_store
    session = store.get_or_create(session_id)
    _ensure_system_prompt(session)
    session.add({"role": "user", "content": message})

    trace: list[dict] = []
    tools = tool_schema()
    for turn in range(1, settings.max_turns + 1):
        try:
            reply = _chat_once(session.messages, tools, model)
        except _requests.RequestException as exc:
            return {
                "answer": f"调用模型失败: {exc}",
                "trace": trace,
                "turns": turn,
                "ok": False,
            }
        content = reply.get("content") or ""
        tool_calls = reply.get("tool_calls") or []
        session.add({"role": "assistant", "content": content, "tool_calls": tool_calls})

        if not tool_calls:
            return {"answer": content, "trace": trace, "turns": turn, "ok": True}

        _append_tool_messages(session, trace, tool_calls)

    return {
        "answer": f"已达最大调用轮数（{settings.max_turns}），暂时无法完成，请换一种问法。",
        "trace": trace,
        "turns": settings.max_turns,
        "ok": False,
    }


def chat_stream(
    message: str,
    session_id: str | None = None,
    store: SessionStore | None = None,
    model: str | None = None,
) -> Generator[dict[str, Any], None, None]:
    """Run the loop with token-level streaming.

    Events: ``{"type": "chunk"|"tool_call"|"tool_result"|"done", ...}``.
    Chunks stream the final answer token by token; tool calls/results arrive as
    structured events clients (e.g. SSE + web UI) render in real time.
    """
    store = store or default_store
    session = store.get_or_create(session_id)
    _ensure_system_prompt(session)
    session.add({"role": "user", "content": message})

    trace: list[dict] = []
    tools = tool_schema()
    for turn in range(1, settings.max_turns + 1):
        content_parts: list[str] = []
        final_message: dict[str, Any] = {}
        try:
            for kind, payload in _chat_stream_once(session.messages, tools, model):
                if kind == "chunk":
                    content_parts.append(payload)
                    yield {"type": "chunk", "text": payload}
                else:
                    final_message = payload
        except _requests.RequestException as exc:
            yield {
                "type": "done",
                "answer": f"调用模型失败: {exc}",
                "trace": trace,
                "turns": turn,
                "ok": False,
            }
            return

        content = final_message.get("content") or "".join(content_parts)
        tool_calls = final_message.get("tool_calls") or []
        session.add({"role": "assistant", "content": content, "tool_calls": tool_calls})

        if not tool_calls:
            if content and not content_parts:
                yield {"type": "chunk", "text": content}
            yield {
                "type": "done",
                "answer": content,
                "trace": trace,
                "turns": turn,
                "ok": True,
            }
            return

        for index, call in enumerate(tool_calls):
            yield {
                "type": "tool_call",
                "index": index,
                "tool": call.get("function", {}).get("name", "?"),
                "arguments": call.get("function", {}).get("arguments", {}),
            }
        entries = _append_tool_messages(session, trace, tool_calls)
        for entry in entries:
            yield {
                "type": "tool_result",
                "index": entry["index"],
                "tool": entry["tool"],
                "result": entry["result"],
            }

    yield {
        "type": "done",
        "answer": f"已达最大调用轮数（{settings.max_turns}），暂时无法完成，请换一种问法。",
        "trace": trace,
        "turns": settings.max_turns,
        "ok": False,
    }
