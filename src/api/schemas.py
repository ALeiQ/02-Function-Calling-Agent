"""Pydantic request/response models for the HTTP API."""

from __future__ import annotations

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1)
    session_id: str | None = None


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


class HealthResponse(BaseModel):
    status: str
    model: str
