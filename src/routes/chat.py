"""
Router: Chat
POST /v1/chat/stream — SSE streaming real-time với Intent Router.

Intent flow:
  general_inquiry => ask_general_inquiry()  
  enterprise      => RAG + ask_enterprise_llm()
  out_of_scope    => ask_out_of_scope()   
"""
from __future__ import annotations

import asyncio
import json
import logging

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse

from src.core.cache import get_vectorstore
from src.core.security import is_safe_query
from src.schemas.chat import ERROR_RESPONSES, ChatRequest
from src.services import session_store
from src.services.intent_classifier import classify_intent_with_fallback
from src.services.llm import ask_enterprise_llm, ask_general_inquiry, ask_out_of_scope
from src.services.rag import get_context
from src.services.vectorstore_cache import history_to_string

router = APIRouter(prefix="/v1", tags=["Chat"])
logger = logging.getLogger(__name__)


@router.post("/chat/stream", responses=ERROR_RESPONSES)
async def chat_stream(body: ChatRequest, request: Request):
    """
    SSE streaming : trả từng chunk text real-time.

    Intent Router phân loại câu hỏi trước khi xử lý:
    - general_inquiry : trả lời phiếm, không cần PDF
    - enterprise      : RAG trên tài liệu nội bộ
    - out_of_scope    : từ chối trả lời
    """
    # 1. Security gate 
    is_safe, err = is_safe_query(body.message)
    if not is_safe:
        raise HTTPException(status_code=400, detail=err)

    chat_history = history_to_string(body.history)

    # 2. Intent Classification (CPU-light LLM call, chạy trong thread) 
    intent = await asyncio.to_thread(classify_intent_with_fallback, body.message, chat_history)
    logger.info("chat_stream: intent=%s | msg='%s'", intent, body.message[:60])

    # 3. Branch theo intent 

    #  3a. General Inquiry, không cần PDF 
    if intent == "general_inquiry":
        def _general_sse():
            for chunk in ask_general_inquiry(body.message, chat_history):
                if chunk:
                    yield f"data: {json.dumps({'content': chunk, 'intent': 'general_inquiry'}, ensure_ascii=False)}\n\n"
            yield "data: [DONE]\n\n"

        return StreamingResponse(
            _general_sse(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    # 3b. Out-of-scope : từ chối lịch sự
    if intent == "out_of_scope":
        def _oos_sse():
            for chunk in ask_out_of_scope(body.message):
                if chunk:
                    yield f"data: {json.dumps({'content': chunk, 'intent': 'out_of_scope'}, ensure_ascii=False)}\n\n"
            yield "data: [DONE]\n\n"

        return StreamingResponse(
            _oos_sse(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    # 3c. Enterprise — RAG pipeline 
    # Kiểm tra session_id bắt buộc với enterprise intent
    if not body.session_id:
        def _no_session_sse():
            msg = (
                "Để trả lời câu hỏi doanh nghiệp, bạn cần upload tài liệu PDF nội bộ trước. "
                "Vui lòng upload file và thử lại."
            )
            yield f"data: {json.dumps({'content': msg, 'intent': 'enterprise'}, ensure_ascii=False)}\n\n"
            yield "data: [DONE]\n\n"

        return StreamingResponse(
            _no_session_sse(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    payload = await session_store.load_vectorstore_payload(
        request.app.state.redis, body.session_id
    )
    if payload is None:
        raise HTTPException(
            status_code=404,
            detail="Session không tồn tại hoặc đã hết hạn. Gọi lại /v1/ingest.",
        )

    # Chuẩn bị context trong thread pool (CPU-bound, không block event loop)
    vectorstore = await asyncio.to_thread(get_vectorstore, body.session_id, payload)
    context = await asyncio.to_thread(get_context, vectorstore, body.message)

    def _enterprise_sse():
        for chunk in ask_enterprise_llm(context, body.message, chat_history):
            if chunk:
                yield f"data: {json.dumps({'content': chunk, 'intent': 'enterprise'}, ensure_ascii=False)}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(
        _enterprise_sse(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )

