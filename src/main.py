"""
FastAPI entry point — Enterprise Chatbox.
Chạy: uvicorn src.main:app --host 0.0.0.0 --port 8000 --reload

Cấu trúc module:
  src/core/lifespan.py      — Redis startup/shutdown
  src/core/middleware.py    — RequestIDMiddleware, CORS
  src/core/cache.py         — LRU Cache thread-safe
  src/schemas/chat.py       — Pydantic models
  src/routers/health.py     — GET  /health
  src/routers/ingest.py     — POST /v1/ingest
  src/routers/chat.py       — POST /v1/chat/stream
  src/routers/sessions.py   — DELETE /v1/sessions/{id}
  src/services/             — llm, rag, session_store, vectorstore_cache
"""
from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from src.core.lifespan import lifespan
from src.core.middleware import register_middlewares
from src.routes import chat, health, ingest, sessions


# Logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

# App
app = FastAPI(
    title="Enterprise Chatbox API",
    description="Enterprise chatbox.",
    version="1.0.0",
    lifespan=lifespan,
)

register_middlewares(app)

# Exception handlers toàn cục
@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    logger.warning(f"HTTP Error {exc.status_code} at {request.url.path}: {exc.detail}")
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": "HTTP_EXCEPTION", "message": exc.detail},
    )


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"Unhandled Exception at {request.url.path}: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={
            "error": "INTERNAL_SERVER_ERROR",
            "message": "Đã xảy ra lỗi hệ thống nội bộ. Vui lòng thử lại sau.",
        },
    )


# Routers
app.include_router(health.router)
app.include_router(ingest.router)
app.include_router(chat.router)
app.include_router(sessions.router)
