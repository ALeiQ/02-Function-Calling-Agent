"""FastAPI application entry point."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from src.api.routes import router

app = FastAPI(title="Function-Calling Agent", version="1.0.0")

app.include_router(router)

static_dir = Path(__file__).resolve().parent.parent.parent / "static"
app.mount("/", StaticFiles(directory=str(static_dir), html=True), name="static")
