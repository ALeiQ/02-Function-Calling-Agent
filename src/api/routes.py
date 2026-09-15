"""API routes: chat, SSE streaming, tools, model switching and health."""

from __future__ import annotations

import json
from collections.abc import Generator
from typing import Any

import requests
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from src.agent import loop
from src.agent.session import default_store
from src.api.schemas import (
    ChatRequest,
    ChatResponse,
    HealthResponse,
    ModelSelectRequest,
    ModelSelectResponse,
    ModelsResponse,
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


def _ollama_model_names() -> list[str]:
    """List models installed in Ollama that support tool calling.

    Models without a ``capabilities`` field are kept (older Ollama); embedding
    models are filtered out so they never appear in the switcher.
    """
    try:
        resp = requests.get(f"{settings.ollama_base_url}/api/tags", timeout=5)
        resp.raise_for_status()
    except requests.RequestException:
        return []
    names: list[str] = []
    for model in resp.json().get("models", []):
        capabilities = model.get("capabilities") or []
        if capabilities and "tools" not in capabilities:
            continue
        names.append(model["name"])
    return names


@router.get("/models", response_model=ModelsResponse)
def list_models() -> ModelsResponse:
    models = _ollama_model_names()
    return ModelsResponse(current=settings.ollama_model, models=models or [settings.ollama_model])


@router.post("/model", response_model=ModelSelectResponse)
def select_model(request: ModelSelectRequest) -> ModelSelectResponse:
    """Switch the server-wide default model (validated against local Ollama)."""
    available = _ollama_model_names()
    if request.model not in available:
        raise HTTPException(
            status_code=404,
            detail=f"模型不可用: {request.model}（需要已安装且支持 tools）",
        )
    settings.ollama_model = request.model
    return ModelSelectResponse(model=request.model)


@router.post("/chat", response_model=ChatResponse)
def chat(request: ChatRequest) -> ChatResponse:
    result = loop.chat(
        request.message,
        session_id=request.session_id,
        store=default_store,
        model=request.model,
    )
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
                request.message,
                session_id=request.session_id,
                store=default_store,
                model=request.model,
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
