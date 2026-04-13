"""
FastAPI service để NestJS (hoặc client khác) gọi RAG PDF qua HTTP.
Chạy: uvicorn src.main:app --host 0.0.0.0 --port 8000 --reload
"""
from __future__ import annotations

import asyncio
import io
import json
import os
import threading
import uuid
import logging
from contextlib import asynccontextmanager
from typing import Any, Literal

import redis.asyncio as redis_async
from fastapi import FastAPI, File, HTTPException, UploadFile, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.base import BaseHTTPMiddleware
from cachetools import LRUCache

from src.core.config import REDIS_URL, SESSION_TTL_SECONDS
from src.core.security import is_safe_query
from src.services.llm import ask_llm
from src.services.rag import get_context, process_pdfs_to_vectorstore, get_embeddings
from src.services import session_store
from langchain_community.vectorstores import FAISS


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger(__name__)

# LRU Cache lưu tối đa 50 session trong RAM để giảm tải CPU giải mã
# cachetools.LRUCache không thread-safe → cần lock khi truy cập từ thread pool
_cache_lock = threading.Lock()
VECTORSTORE_CACHE = LRUCache(maxsize=50)

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info(f"Đang khởi tạo kết nối Redis tới {REDIS_URL}...")
    client = redis_async.from_url(REDIS_URL, decode_responses=False)
    try:
        await client.ping()
        logger.info("Kết nối Redis thành công!")
    except Exception as e:
        logger.error(f"Lỗi nối Redis: {e}")
        await client.aclose()
        raise RuntimeError(f"Không kết nối được Redis ({REDIS_URL}): {e}") from e
    app.state.redis = client
    yield
    logger.info("Đóng kết nối Redis...")
    await client.aclose()


app = FastAPI(
    title="PDFs AI Assistant API",
    description="RAG trên PDF.",
    version="1.0.0",
    lifespan=lifespan,
)


#Middleware: X-Request-ID để trace 
class RequestIDMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
        request.state.request_id = request_id
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response


app.add_middleware(RequestIDMiddleware)

_cors = os.getenv("CORS_ORIGINS", "http://localhost:3000")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in _cors.split(",") if o.strip()],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(StarletteHTTPException)
async def custom_http_exception_handler(request: Request, exc: StarletteHTTPException):
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
        content={"error": "INTERNAL_SERVER_ERROR", "message": "Đã xảy ra lỗi hệ thống nội bộ. Vui lòng thử lại sau."},
    )


#      Pydantic Models
class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str


class ChatRequest(BaseModel):
    session_id: str = Field(..., description="ID trả về từ POST /v1/ingest")
    message: str
    history: list[ChatMessage] = Field(default_factory=list)


class ChatResponse(BaseModel):
    answer: str


class IngestResponse(BaseModel):
    session_id: str
    message: str


class DeleteResponse(BaseModel):
    ok: bool
    message: str


class ErrorResponse(BaseModel):
    error: str
    message: str


class HealthResponse(BaseModel):
    status: str


# Khai báo error responses 
_error_responses = {
    400: {"model": ErrorResponse, "description": "Bad Request"},
    404: {"model": ErrorResponse, "description": "Not Found"},
    500: {"model": ErrorResponse, "description": "Internal Server Error"},
}


def _history_to_string(history: list[ChatMessage], max_turns: int = 5) -> str:
    tail = history[-max_turns:] if len(history) > max_turns else history
    lines: list[str] = []
    for m in tail:
        label = "Người dùng" if m.role == "user" else "Trợ lý AI"
        lines.append(f"{label}: {m.content}")
    return "\n".join(lines)


def _run_llm(context: str, message: str, chat_history: str) -> str:
    return "".join(chunk for chunk in ask_llm(context, message, chat_history) if chunk)


def _get_vectorstore(session_id: str, payload: bytes):
    with _cache_lock:
        if session_id in VECTORSTORE_CACHE:
            logger.info(f"Cache hit: Đã tìm thấy VectorStore của session='{session_id}' trong RAM")
            return VECTORSTORE_CACHE[session_id]

    # Deserialize ngoài lock (CPU-heavy, không block threads khác)
    logger.info(f"Cache miss: Đang giải mã VectorStore cho session='{session_id}'...")
    vectorstore = FAISS.deserialize_from_bytes(payload, get_embeddings(), allow_dangerous_deserialization=True)

    # Double-check: nếu thread khác đã deserialize xong trước → dùng kết quả đó
    with _cache_lock:
        if session_id not in VECTORSTORE_CACHE:
            VECTORSTORE_CACHE[session_id] = vectorstore
        else:
            vectorstore = VECTORSTORE_CACHE[session_id]
    return vectorstore


def _sync_rag_chat(
    session_id: str, payload: bytes, message: str, chat_history: str
) -> str:
    """Chạy trong thread pool: get vectorstore từ Cache + truy vấn + LLM (tránh chặn event loop)."""
    vectorstore = _get_vectorstore(session_id, payload)
    context = get_context(vectorstore, message)
    return _run_llm(context, message, chat_history)


@app.get("/health", response_model=HealthResponse, responses={503: {"model": ErrorResponse}})
async def health():
    try:
        await app.state.redis.ping()
    except Exception:
        raise HTTPException(status_code=503, detail="Redis không phản hồi.")
    return HealthResponse(status="ok")


@app.post("/v1/ingest", response_model=IngestResponse, responses=_error_responses)
async def ingest(files: list[UploadFile] = File(...)):
    if not files:
        raise HTTPException(status_code=400, detail="Cần ít nhất một file PDF.")
    pdf_wrappers: list[Any] = []
    for f in files:
        if not f.filename or not f.filename.lower().endswith(".pdf"):
            raise HTTPException(status_code=400, detail=f"Chỉ chấp nhận PDF: {f.filename!r}")
        data = await f.read()
        if not data:
            raise HTTPException(status_code=400, detail=f"File rỗng: {f.filename}")
        pdf_wrappers.append(io.BytesIO(data))

    try:
        vectorstore = await asyncio.to_thread(
            process_pdfs_to_vectorstore, pdf_wrappers
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Lỗi xử lý PDF: {e}") from e

    if vectorstore is None:
        raise HTTPException(status_code=400, detail="Không trích xuất được văn bản từ PDF.")

    sid = str(uuid.uuid4())
    try:
        await session_store.save_vectorstore(
            app.state.redis, sid, vectorstore, SESSION_TTL_SECONDS
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Lỗi lưu session Redis: {e}") from e

    return IngestResponse(session_id=sid, message="Đã tạo session và nạp vector store.")


@app.post("/v1/chat", response_model=ChatResponse, responses=_error_responses)
async def chat(body: ChatRequest):
    is_safe, err = is_safe_query(body.message)
    if not is_safe:
        raise HTTPException(status_code=400, detail=err)

    payload = await session_store.load_vectorstore_payload(
        app.state.redis, body.session_id
    )
    if payload is None:
        raise HTTPException(
            status_code=404,
            detail="Session không tồn tại hoặc đã hết hạn. Gọi lại /v1/ingest.",
        )

    chat_history = _history_to_string(body.history)
    try:
        answer = await asyncio.to_thread(
            _sync_rag_chat, body.session_id, payload, body.message, chat_history
        )
    except StarletteHTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Lỗi LLM/RAG: {e}") from e

    return ChatResponse(answer=answer)


@app.post("/v1/chat/stream", responses=_error_responses)
async def chat_stream(body: ChatRequest):
    """SSE streaming — trả từng chunk text real-time."""
    is_safe, err = is_safe_query(body.message)
    if not is_safe:
        raise HTTPException(status_code=400, detail=err)

    payload = await session_store.load_vectorstore_payload(
        app.state.redis, body.session_id
    )
    if payload is None:
        raise HTTPException(
            status_code=404,
            detail="Session không tồn tại hoặc đã hết hạn. Gọi lại /v1/ingest.",
        )

    chat_history = _history_to_string(body.history)

    # Chuẩn bị context trong thread pool (CPU-bound)
    vectorstore = await asyncio.to_thread(
        _get_vectorstore, body.session_id, payload
    )
    context = await asyncio.to_thread(get_context, vectorstore, body.message)

    def _sse_generator():
        for chunk in ask_llm(context, body.message, chat_history):
            if chunk:
                yield f"data: {json.dumps({'content': chunk}, ensure_ascii=False)}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(
        _sse_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.delete("/v1/sessions/{session_id}", response_model=DeleteResponse, responses=_error_responses)
async def delete_session(session_id: str):
    removed = await session_store.delete_session(app.state.redis, session_id)
    with _cache_lock:
        if session_id in VECTORSTORE_CACHE:
            del VECTORSTORE_CACHE[session_id]
            logger.info(f"Đã xoá session='{session_id}'.")

    if not removed:
        raise HTTPException(status_code=404, detail="Không tìm thấy session.")
    return DeleteResponse(ok=True, message="Đã xoá session thành công.")
