"""
FastAPI service để NestJS (hoặc client khác) gọi RAG PDF qua HTTP.
Chạy: uvicorn src.main:app --host 0.0.0.0 --port 8000 --reload
"""
from __future__ import annotations

import asyncio
import io
import os
import uuid
from contextlib import asynccontextmanager
from typing import Any, Literal

import redis.asyncio as redis_async
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from src.core.config import REDIS_URL, SESSION_TTL_SECONDS
from src.core.security import is_safe_query
from src.services.llm import ask_llm
from src.services.rag import get_context, process_pdfs_to_vectorstore, get_embeddings
from src.services import session_store
from langchain_community.vectorstores import FAISS


@asynccontextmanager
async def lifespan(app: FastAPI):
    client = redis_async.from_url(REDIS_URL, decode_responses=False)
    try:
        await client.ping()
    except Exception as e:
        await client.aclose()
        raise RuntimeError(f"Không kết nối được Redis ({REDIS_URL}): {e}") from e
    app.state.redis = client
    yield
    await client.aclose()


app = FastAPI(
    title="PDFs AI Assistant API",
    description="RAG trên PDF.",
    version="1.0.0",
    lifespan=lifespan,
)

_cors = os.getenv("CORS_ORIGINS", "http://localhost:3000")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in _cors.split(",") if o.strip()],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


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


class HealthResponse(BaseModel):
    status: str





def _history_to_string(history: list[ChatMessage], max_turns: int = 5) -> str:
    tail = history[-max_turns:] if len(history) > max_turns else history
    lines: list[str] = []
    for m in tail:
        label = "Người dùng" if m.role == "user" else "Trợ lý AI"
        lines.append(f"{label}: {m.content}")
    return "\n".join(lines)


def _run_llm(context: str, message: str, chat_history: str) -> str:
    out = ask_llm(context, message, chat_history)
    if isinstance(out, str):
        return out
    return "".join(chunk for chunk in out if chunk)


def _sync_rag_chat_from_payload(
    payload: bytes, message: str, chat_history: str
) -> str:
    """Chạy trong thread pool: unpickle FAISS + truy vấn + LLM (tránh chặn event loop)."""
    vectorstore = FAISS.deserialize_from_bytes(payload, get_embeddings(), allow_dangerous_deserialization=True)
    context = get_context(vectorstore, message)
    return _run_llm(context, message, chat_history)


@app.get("/health", response_model=HealthResponse)
async def health():
    try:
        await app.state.redis.ping()
    except Exception:
        raise HTTPException(status_code=503, detail="Redis không phản hồi.")
    return HealthResponse(status="ok")


@app.post("/v1/ingest", response_model=IngestResponse)
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


@app.post("/v1/chat", response_model=ChatResponse)
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
            _sync_rag_chat_from_payload, payload, body.message, chat_history
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Lỗi LLM/RAG: {e}") from e

    return ChatResponse(answer=answer)


@app.delete("/v1/sessions/{session_id}")
async def delete_session(session_id: str):
    removed = await session_store.delete_session(app.state.redis, session_id)
    if not removed:
        raise HTTPException(status_code=404, detail="Không tìm thấy session.")
    return {"ok": True}
