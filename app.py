import os
os.environ["TRANSFORMERS_VERBOSITY"] = "error"
os.environ["TOKENIZERS_PARALLELISM"] = "false"

import hashlib
import streamlit as st
from src.services.rag import process_pdfs_to_vectorstore, get_context
from src.services.llm import ask_llm
from src.core.security import is_safe_query
from src.core.config import check_keys

st.set_page_config(page_title="Chat with Multiple PDFs")

check_keys()

#  SESSION STATE 
if "vectorstore" not in st.session_state:
    st.session_state.vectorstore = None

if "messages" not in st.session_state:
    st.session_state.messages = []

if "processed_files_hash" not in st.session_state:
    st.session_state.processed_files_hash = None

if "processed_file_names" not in st.session_state:
    st.session_state.processed_file_names = []


def _compute_files_hash(files) -> str | None:
    if not files:
        return None
    h = hashlib.md5()
    for f in sorted(files, key=lambda x: x.name):
        h.update(f.name.encode())
        h.update(str(f.size).encode())
    return h.hexdigest()


def _has_new_files(uploaded_files) -> bool:
    current_hash = _compute_files_hash(uploaded_files)
    if current_hash is None:
        return False
    return current_hash != st.session_state.processed_files_hash


def _auto_process(uploaded_files):
    """Tự động process PDF và cập nhật vectorstore. Trả về True/False."""
    try:
        for f in uploaded_files:
            f.seek(0)
        
        vectorstore = process_pdfs_to_vectorstore(uploaded_files)
        if vectorstore:
            st.session_state.vectorstore = vectorstore
            st.session_state.processed_files_hash = _compute_files_hash(uploaded_files)
            st.session_state.processed_file_names = [f.name for f in uploaded_files]
            return True
        else:
            return False
    except Exception:
        return False


# MAIN UI 
st.title("Chat with PDFs")

pdf_docs = st.file_uploader(
    "Upload PDF",
    accept_multiple_files=True,
    type="pdf",
    label_visibility="collapsed",
)

for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

user_query = st.chat_input("Nhập câu hỏi về nội dung PDF...")

if user_query:
    st.session_state.messages.append({"role": "user", "content": user_query})
    with st.chat_message("user"):
        st.markdown(user_query)

    with st.chat_message("assistant"):
        # process 
        if pdf_docs and _has_new_files(pdf_docs):
            success = _auto_process(pdf_docs)
            if not success:
                msg = "Không thể đọc được nội dung từ file PDF. Vui lòng thử file khác."
                st.markdown(msg)
                st.session_state.messages.append({"role": "assistant", "content": msg})
                st.stop()

        if st.session_state.vectorstore is None:
            msg = "Vui lòng upload file PDF rồi gửi câu hỏi."
            st.markdown(msg)
            st.session_state.messages.append({"role": "assistant", "content": msg})
            st.stop()

        is_safe, error_msg = is_safe_query(user_query)
        if not is_safe:
            st.markdown(error_msg)
            st.session_state.messages.append({"role": "assistant", "content": error_msg})
            st.stop()

        # RAG + LLM — trả lời trực tiếp
        try:
            chat_history = ""
            for m in st.session_state.messages[-5:-1]:
                role = "Người dùng" if m["role"] == "user" else "Trợ lý AI"
                chat_history += f"{role}: {m['content']}\n"

            context = get_context(st.session_state.vectorstore, user_query)
            response_stream = ask_llm(context, user_query, chat_history)
        except Exception as e:
            st.markdown(f"Lỗi hệ thống: {str(e)}")
            response_stream = None

        if response_stream:
            full_response = st.write_stream(response_stream)
            st.session_state.messages.append({"role": "assistant", "content": full_response})
