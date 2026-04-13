from collections.abc import Generator
import logging

from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_groq import ChatGroq
from src.core.config import GEMINI_API_KEY, GROQ_API_KEY
from src.core.prompt import SYSTEM_PROMPT

logger = logging.getLogger(__name__)

_gemini_llm = ChatGoogleGenerativeAI(
    model="gemini-2.5-flash",
    google_api_key=GEMINI_API_KEY,
    temperature=0.1,
)

_groq_llm = ChatGroq(
    model_name="llama-3.1-8b-instant",
    groq_api_key=GROQ_API_KEY,
    temperature=0.1,
)


def ask_gemini(context: str, query: str, chat_history: str = "") -> Generator[str, None, None]:
    """Uses Gemini API for answering the query."""
    prompt = SYSTEM_PROMPT.format(context=context, question=query, chat_history=chat_history)
    for chunk in _gemini_llm.stream(prompt):
        yield chunk.content

def ask_groq(context: str, query: str, chat_history: str = "") -> Generator[str, None, None]:
    """Uses Groq API for answering the query."""
    prompt = SYSTEM_PROMPT.format(context=context, question=query, chat_history=chat_history)
    for chunk in _groq_llm.stream(prompt):
        yield chunk.content

def ask_llm(context: str, query: str, chat_history: str = "") -> Generator[str, None, None]:
    """
    Router phân xử logic LLM dựa trên độ dài của ngữ cảnh.
    Context ngắn (< 4000 ký tự) -> Sử dụng Gemini.
    Context dài (>= 4000 ký tự) -> Sử dụng Groq để tính toán cực nhanh.
    """
    if not context or not context.strip():
        yield "Tôi không tìm thấy thông tin trong tài liệu."
        return

    if len(context) < 4000:
        logger.info("LLM Router: Context ngắn (%d chars), dùng Gemini", len(context))
        try:
            yield from ask_gemini(context, query, chat_history)
        except Exception as e:
            logger.warning("Gemini lỗi (%s), fallback sang Groq", e)
            yield from ask_groq(context, query, chat_history)
    else:
        logger.info("LLM Router: Context dài (%d chars), dùng Groq", len(context))
        yield from ask_groq(context, query, chat_history)

