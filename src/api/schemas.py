"""Pydantic request/response models for the HTTP API."""

from __future__ import annotations

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1)
    session_id: str | None = None
    model: str | None = Field(
        None,
        description="覆盖本次请求使用的模型；缺省用服务器当前默认模型",
        examples=["qwen3:8b"],
    )
    think: bool | None = Field(
        None,
        description="覆盖本次请求的思考模式；缺省用服务器当前默认(settings.ollama_think)",
        examples=[True],
    )
    think: bool | None = Field(
        None,
        description="覆盖本次请求的思考模式(true/思考)；缺省用服务器当前设置",
    )


class ToolCallTrace(BaseModel):
    index: int
    tool: str
    arguments: dict = {}
    result: str


class ChatResponse(BaseModel):
    answer: str
    trace: list[ToolCallTrace] = []
    turns: int
    ok: bool


class ToolInfo(BaseModel):
    name: str
    description: str


class ToolsResponse(BaseModel):
    tools: list[ToolInfo]


class ModelsResponse(BaseModel):
    current: str
    models: list[str]


class ModelSelectRequest(BaseModel):
    model: str


class ModelSelectResponse(BaseModel):
    model: str


class HealthResponse(BaseModel):
    status: str
    model: str


class SessionResponse(BaseModel):
    session_id: str
    messages: list[dict] = []
