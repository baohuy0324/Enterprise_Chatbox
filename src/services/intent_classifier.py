"""
Intent Classifier Service — Phân loại câu hỏi thành một trong 3 nhóm:
  - general_inquiry : câu hỏi phiếm, chào hỏi, hỏi ngày giờ, hỏi về bot
  - enterprise      : câu hỏi liên quan đến hoạt động/tài liệu doanh nghiệp
  - out_of_scope    : câu hỏi nằm ngoài phạm vi phục vụ

LLM:
  1. Gemini Flash 
  2. Nếu Gemini lỗi (429/503) => fallback Groq Llama 
  3. Nếu cả hai đều lỗi => fallback mặc định = "enterprise" 
"""
from __future__ import annotations

import json
import logging

from src.core.prompt import INTENT_CLASSIFIER_PROMPT
from src.schemas.chat import IntentLiteral

logger = logging.getLogger(__name__)

_VALID_INTENTS: set[str] = {"general_inquiry", "enterprise", "out_of_scope"}
_FALLBACK_INTENT: IntentLiteral = "enterprise"


def _parse_intent(raw: str) -> IntentLiteral | None:
    """Parse JSON response từ LLM, trả None nếu không hợp lệ."""
    raw = raw.strip()
    # Xử lý markdown code fence nếu LLM bọc JSON trong ```json...```
    if raw.startswith("```"):
        raw = raw.strip("`").strip()
        if raw.lower().startswith("json"):
            raw = raw[4:].strip()
    try:
        data = json.loads(raw)
        intent = data.get("intent", "").strip().lower()
        return intent if intent in _VALID_INTENTS else None  # type: ignore[return-value]
    except json.JSONDecodeError:
        return None


def classify_intent(query: str, chat_history: str = "") -> IntentLiteral:
    """
    Phân loại câu hỏi của user bằng LLM.

    Trả về một trong: "general_inquiry" | "enterprise" | "out_of_scope".
    Fallback chain: Groq => Gemini => "enterprise".
    """
    from src.services.llm import _get_gemini, _get_groq  # noqa: PLC0415

    prompt = INTENT_CLASSIFIER_PROMPT.format(question=query, chat_history=chat_history)

    # 1. Groq 
    try:
        response = _get_groq().invoke(prompt)
        intent = _parse_intent(response.content)
        if intent:
            logger.info("IntentClassifier [Groq]: '%s' → %s", query[:60], intent)
            return intent
        logger.warning("IntentClassifier [Groq]: intent không hợp lệ, thử Gemini...")
    except Exception as e:
        logger.warning("IntentClassifier [Groq] lỗi (%s), fallback → Gemini", type(e).__name__)

    # 2. Fallback Gemini
    try:
        response = _get_gemini().invoke(prompt)
        intent = _parse_intent(response.content)
        if intent:
            logger.info("IntentClassifier [Gemini]: '%s' → %s", query[:60], intent)
            return intent
        logger.warning("IntentClassifier [Gemini]: intent không hợp lệ, fallback → %s", _FALLBACK_INTENT)
    except Exception as e:
        logger.error("IntentClassifier [Gemini] lỗi (%s), fallback → %s", type(e).__name__, _FALLBACK_INTENT)

    # 3. Fallback mặc định
    return _FALLBACK_INTENT

