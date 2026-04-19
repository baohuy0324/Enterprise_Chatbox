"""
Router: Ingest PDF
POST /v1/ingest — nhận file, tạo FAISS vectorstore, lưu Redis, trả session_id.
"""
from __future__ import annotations

import asyncio
import io
import uuid

from fastapi import APIRouter, File, HTTPException, Request, UploadFile

from src.core.config import SESSION_TTL_SECONDS
from src.schemas.chat import ERROR_RESPONSES, IngestResponse
from src.services import session_store
from src.services.rag import process_pdfs_to_vectorstore

router = APIRouter(prefix="/v1", tags=["Ingest"])


@router.post(
    "/ingest",
    response_model=IngestResponse,
    responses=ERROR_RESPONSES,
)
async def ingest(request: Request, files: list[UploadFile] = File(...)):
    """
    Nhận 1 hoặc nhiều file, xây dựng FAISS vectorstore và lưu vào Redis.
    Trả về session_id để dùng cho các request /v1/chat tiếp theo.
    """
    if not files:
        raise HTTPException(status_code=400, detail="Cần ít nhất một file.")
    if len(files) > 2:
        raise HTTPException(status_code=400, detail="Chỉ được phép tải lên tối đa 2 file trong một lần.")

    file_wrappers: list[tuple[str, io.BytesIO]] = []
    for f in files:
        valid_exts = (".pdf", ".docx", ".xlsx", ".png", ".jpg", ".jpeg")
        if not f.filename or not any(f.filename.lower().endswith(ext) for ext in valid_exts):
            raise HTTPException(status_code=400, detail=f"Chỉ chấp nhận PDF, DOCX, XLSX, PNG, JPG: {f.filename!r}")
        data = await f.read()
        if not data:
            raise HTTPException(status_code=400, detail=f"File rỗng: {f.filename}")
        file_wrappers.append((f.filename, io.BytesIO(data)))

    try:
        vectorstore = await asyncio.to_thread(process_pdfs_to_vectorstore, file_wrappers)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Lỗi xử lý file: {e}") from e

    if vectorstore is None:
        raise HTTPException(status_code=400, detail="Không trích xuất được văn bản từ file.")

    sid = str(uuid.uuid4())
    try:
        await session_store.save_vectorstore(
            request.app.state.redis, sid, vectorstore, SESSION_TTL_SECONDS
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Lỗi lưu session Redis: {e}") from e

    return IngestResponse(session_id=sid, message="Đã tạo session và nạp vector store.")
