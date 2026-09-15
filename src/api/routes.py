"""API routes: chat, SSE streaming, tools and health."""

from __future__ import annotations

import json
from collections.abc import Generator
from typing import Any

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from src.agent import loop
from src.agent.session import default_store
from src.api.schemas import (
    ChatRequest,
    ChatResponse,
    HealthResponse,
    ToolInfo,
    ToolsResponse,
)
from src.config import settings
from src.tools import registry

router = APIRouter(prefix="/api")


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(status="ok", model=settings.ollama_model)


@router.get("/tools", response_model=ToolsResponse)
def tools() -> ToolsResponse:
    defs = [
        ToolInfo(name=d["function"]["name"], description=d["function"]["description"])
        for d in registry()
    ]
    return ToolsResponse(tools=defs)


@router.post("/chat", response_model=ChatResponse)
def chat(request: ChatRequest) -> ChatResponse:
    result = loop.chat(request.message, session_id=request.session_id, store=default_store)
    return ChatResponse(
        answer=result["answer"],
        trace=result["trace"],
        turns=result["turns"],
        ok=result["ok"],
    )


def _sse(event: dict[str, Any]) -> str:
    return f"data: {json.dumps(event, ensure_ascii=False)}\n\n"


@router.post("/chat/stream")
def chat_stream(request: ChatRequest) -> StreamingResponse:
    def generator() -> Generator[str, None, None]:
        try:
            for event in loop.chat_stream(
                request.message, session_id=request.session_id, store=default_store
            ):
                yield _sse(event)
        except Exception as exc:  # keep the stream alive on unexpected errors
            yield _sse(
                {
                    "type": "done",
                    "answer": f"服务端错误: {exc}",
                    "trace": [],
                    "ok": False,
                }
            )

    return StreamingResponse(
        generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
