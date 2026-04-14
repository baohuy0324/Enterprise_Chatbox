from collections.abc import Generator
from datetime import datetime
from functools import lru_cache
import logging

from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_groq import ChatGroq
from src.core.config import GEMINI_API_KEY, GROQ_API_KEY
from src.core.prompt import (
    GENERAL_INQUIRY_PROMPT,
    OUT_OF_SCOPE_RESPONSE_EN,
    OUT_OF_SCOPE_RESPONSE_VI,
    SYSTEM_PROMPT,
)

logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def _get_gemini() -> ChatGoogleGenerativeAI:
    return ChatGoogleGenerativeAI(
        model="gemini-1.5-flash-latest",
        google_api_key=GEMINI_API_KEY,
        temperature=0.1,
    )


@lru_cache(maxsize=1)
def _get_groq() -> ChatGroq:
    return ChatGroq(
        model_name="llama-3.1-8b-instant",
        groq_api_key=GROQ_API_KEY,
        temperature=0.1,
    )


def ask_gemini(context: str, query: str, chat_history: str = "") -> Generator[str, None, None]:
    """Uses Gemini API for answering the query."""
    prompt = SYSTEM_PROMPT.format(context=context, question=query, chat_history=chat_history)
    for chunk in _get_gemini().stream(prompt):
        yield chunk.content


def ask_groq(context: str, query: str, chat_history: str = "") -> Generator[str, None, None]:
    """Uses Groq API for answering the query."""
    prompt = SYSTEM_PROMPT.format(context=context, question=query, chat_history=chat_history)
    for chunk in _get_groq().stream(prompt):
        yield chunk.content



# General Inquiry Handler: câu hỏi phiếm, chào hỏi, hỏi ngày giờ
def ask_general_inquiry(query: str, chat_history: str = "") -> Generator[str, None, None]:
    """
    Xử lý câu hỏi General Inquiry
    Dùng Groq + GENERAL_INQUIRY_PROMPT cùng datetime thực.
    """
    # Inject ngày giờ thực để bot trả lời đúng nếu user hỏi "hôm nay là thứ mấy"
    now = datetime.now()
    weekdays_vi = ["Thứ Hai", "Thứ Ba", "Thứ Tư", "Thứ Năm", "Thứ Sáu", "Thứ Bảy", "Chủ Nhật"]
    current_datetime = (
        f"{weekdays_vi[now.weekday()]}, ngày {now.day:02d}/{now.month:02d}/{now.year} "
        f"lúc {now.hour:02d}:{now.minute:02d} (Giờ Việt Nam)"
    )

    prompt = GENERAL_INQUIRY_PROMPT.format(
        current_datetime=current_datetime,
        chat_history=chat_history,
        question=query,
    )

    try:
        for chunk in _get_groq().stream(prompt):
            yield chunk.content
    except Exception as e:
        logger.warning("ask_general_inquiry Groq lỗi (%s), fallback Gemini", e)
        for chunk in _get_gemini().stream(prompt):
            yield chunk.content



# Out-of-scope Handler: từ chối nếu hỏi ngoài phạm vi doanh nghiệp (không gọi LLM, dùng static response)
def ask_out_of_scope(query: str) -> Generator[str, None, None]:
    """
    Từ chối câu hỏi ngoài phạm vi doanh nghiệp
    Dùng static response
    Tự detect ngôn ngữ 
    """
    # Heuristic: nếu câu hỏi chứa ký tự tiếng Việt => dùng tiếng Việt
    has_vietnamese = any(
        "\u00c0" <= ch <= "\u024f" or "\u1e00" <= ch <= "\u1eff" for ch in query
    )
    response = OUT_OF_SCOPE_RESPONSE_VI if has_vietnamese else OUT_OF_SCOPE_RESPONSE_EN
    yield response



# Enterprise LLM Router ưu tiên Gemini, fallback Groq
def ask_enterprise_llm(context: str, query: str, chat_history: str = "") -> Generator[str, None, None]:
    """
    Router phân xử logic LLM dựa trên độ dài của ngữ cảnh.
    Context ngắn (< 10000 ký tự) => Gemini (chính xác hơn tiếng Việt).
    Context dài (>= 10000 ký tự) => Groq (tốc độ cao hơn).
    """
    if not context or not context.strip():
        yield "Tôi không tìm thấy thông tin trong tài liệu."
        return

    if len(context) < 10000:
        logger.info("LLM Router: Context ngắn (%d chars), dùng Gemini", len(context))
        has_yielded = False
        try:
            for chunk in ask_gemini(context, query, chat_history):
                has_yielded = True
                yield chunk
        except Exception as e:
            if has_yielded:
                logger.warning("Gemini bị ngắt kết nối giữa chừng (%s). Không thể fallback.", e)
                yield "\n\n*(Đã xảy ra lỗi kết nối mạng với mô hình, xin vui lòng gửi lại câu hỏi)*"
            else:
                logger.warning("Gemini lỗi (%s), fallback sang Groq", e)
                yield from ask_groq(context, query, chat_history)
    else:
        logger.info("LLM Router: Context dài (%d chars), dùng Groq", len(context))
        yield from ask_groq(context, query, chat_history)


# Backward compatibility alias 
def ask_llm(context: str, query: str, chat_history: str = "") -> Generator[str, None, None]:
    """Alias backward-compatible cho ask_enterprise_llm."""
    yield from ask_enterprise_llm(context, query, chat_history)
