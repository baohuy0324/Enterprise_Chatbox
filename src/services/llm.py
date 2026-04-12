from collections.abc import Generator

from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_groq import ChatGroq
from src.core.config import GEMINI_API_KEY, GROQ_API_KEY
from src.core.prompt import SYSTEM_PROMPT

def ask_gemini(context: str, query: str, chat_history: str = "") -> Generator[str, None, None]:
    """Uses Gemini API for answering the query."""
    llm = ChatGoogleGenerativeAI(
        model="gemini-2.5-flash", 
        google_api_key=GEMINI_API_KEY, 
        temperature=0.1
    )
    prompt = SYSTEM_PROMPT.format(context=context, question=query, chat_history=chat_history)
    for chunk in llm.stream(prompt):
        yield chunk.content

def ask_groq(context: str, query: str, chat_history: str = "") -> Generator[str, None, None]:
    """Uses Groq API for answering the query."""
    llm = ChatGroq(
        model_name="llama-3.1-8b-instant",  
        groq_api_key=GROQ_API_KEY, 
        temperature=0.1
    )
    prompt = SYSTEM_PROMPT.format(context=context, question=query, chat_history=chat_history)
    for chunk in llm.stream(prompt):
        yield chunk.content

def ask_llm(context: str, query: str, chat_history: str = "") -> str:
    """
    Router phân xử logic LLM dựa trên độ dài của ngữ cảnh.
    Context ngắn (< 4000 ký tự) -> Sử dụng Gemini.
    Context dài (>= 4000 ký tự) -> Sử dụng Groq để tính toán cực nhanh.
    """
    # Xử lý trường hợp context quá ngắn hoặc không có
    if not context or not context.strip():
        # Tuân thủ rule của prompt
        return "Tôi không tìm thấy thông tin trong tài liệu."
        
    if len(context) < 4000:
        print("LLM Router: Context length is short, redirecting to Gemini...")
        return ask_gemini(context, query, chat_history)
    else:
        print("LLM Router: Context length is long, redirecting to Groq...")
        return ask_groq(context, query, chat_history)
