"""
Pydantic schemas cho toàn bộ API.
"""
from typing import Literal

from pydantic import BaseModel, Field

# Intent được phân loại bởi IntentClassifier
IntentLiteral = Literal["general_inquiry", "enterprise", "out_of_scope"]


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str


class ChatRequest(BaseModel):
    # session_id là Optional — general_inquiry không cần PDF session
    session_id: str | None = Field(
        None,
        description="ID trả về từ POST /v1/ingest (bắt buộc với câu hỏi enterprise)",
    )
    message: str
    history: list[ChatMessage] = Field(default_factory=list)


class IntentResponse(BaseModel):
    intent: IntentLiteral


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


ERROR_RESPONSES = {
    400: {"model": ErrorResponse, "description": "Bad Request"},
    404: {"model": ErrorResponse, "description": "Not Found"},
    500: {"model": ErrorResponse, "description": "Internal Server Error"},
}

