import os
os.environ["TRANSFORMERS_VERBOSITY"] = "error"
os.environ["TOKENIZERS_PARALLELISM"] = "false"

import hashlib
import streamlit as st
from src.services.rag import process_pdfs_to_vectorstore, get_context
from src.services.llm import ask_enterprise_llm, ask_general_inquiry, ask_out_of_scope
from src.services.intent_classifier import classify_intent
from src.core.security import is_safe_query
from src.core.config import check_keys

# Page Config 
st.set_page_config(
    page_title="Enterprise AI Assistant",
    layout="centered",
)

# Custom CSS — Enterprise Look 
st.markdown("""
<style>
/* Header branding */
.enterprise-header {
    background: linear-gradient(135deg, #0f172a 0%, #1e3a5f 100%);
    border-radius: 12px;
    padding: 20px 28px;
    margin-bottom: 20px;
    display: flex;
    align-items: center;
    gap: 14px;
    box-shadow: 0 4px 20px rgba(0,0,0,0.3);
}
.enterprise-header h1 {
    color: #e2e8f0;
    font-size: 1.5rem;
    margin: 0;
    font-weight: 700;
    letter-spacing: 0.5px;
}
.enterprise-header p {
    color: #94a3b8;
    font-size: 0.82rem;
    margin: 4px 0 0 0;
}
/* Intent badges */
.badge {
    display: inline-block;
    padding: 2px 10px;
    border-radius: 20px;
    font-size: 0.72rem;
    font-weight: 600;
    letter-spacing: 0.3px;
    margin-top: 6px;
}
.badge-general  { background:#dbeafe; color:#1d4ed8; }
.badge-enterprise { background:#dcfce7; color:#15803d; }
.badge-oos      { background:#fee2e2; color:#b91c1c; }
/* Upload hint */
.upload-hint {
    background: #f0f9ff;
    border-left: 4px solid #0ea5e9;
    border-radius: 0 8px 8px 0;
    padding: 10px 14px;
    font-size: 0.83rem;
    color: #0c4a6e;
    margin-bottom: 12px;
}
</style>
""", unsafe_allow_html=True)

check_keys()

# Session State
for key, default in [
    ("vectorstore", None),
    ("messages", []),
    ("processed_files_hash", None),
    ("processed_file_names", []),
]:
    if key not in st.session_state:
        st.session_state[key] = default


# Helpers 
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


def _auto_process(uploaded_files) -> bool:
    """Tự động process PDF và cập nhật vectorstore."""
    try:
        for f in uploaded_files:
            f.seek(0)
        vectorstore = process_pdfs_to_vectorstore(uploaded_files)
        if vectorstore:
            st.session_state.vectorstore = vectorstore
            st.session_state.processed_files_hash = _compute_files_hash(uploaded_files)
            st.session_state.processed_file_names = [f.name for f in uploaded_files]
            return True
        return False
    except Exception:
        return False


def _intent_badge(intent: str) -> str:
    """Trả về HTML badge tương ứng với intent."""
    mapping = {
        "general_inquiry": ('<span class="badge badge-general"> General Inquiry</span>', ),
        "enterprise":      ('<span class="badge badge-enterprise"> Enterprise</span>', ),
        "out_of_scope":    ('<span class="badge badge-oos"> Out of Scope</span>', ),
    }
    return mapping.get(intent, ('',))[0]


#Header 
st.markdown("""
<div class="enterprise-header">
    <div style="font-size:2.2rem"></div>
    <div>
        <h1>Enterprise AI Assistant</h1>
        <p>Chatbox doanh nghiệp</p>
    </div>
</div>
""", unsafe_allow_html=True)

#  PDF Upload in Sidebar
with st.sidebar:
    st.markdown("### 📎 Tài liệu của bạn")
    pdf_docs = st.file_uploader(
        "Tải lên file PDF để AI phân tích",
        accept_multiple_files=True,
        type="pdf",
    )
    
    # Hiển thị tên file đã upload
    if st.session_state.processed_file_names:
        st.divider()
        st.markdown("**Tài liệu đang dùng:**")
        for n in st.session_state.processed_file_names:
            st.caption(f"📄 {n}")

#  Chat History 
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])
        if "intent" in message and message["role"] == "assistant":
            st.markdown(_intent_badge(message["intent"]), unsafe_allow_html=True)

#  Chat Input
user_query = st.chat_input("Nhập câu hỏi của bạn...")

if user_query:
    st.session_state.messages.append({"role": "user", "content": user_query})
    with st.chat_message("user"):
        st.markdown(user_query)

    with st.chat_message("assistant"):
        #  Security check 
        is_safe, error_msg = is_safe_query(user_query)
        if not is_safe:
            st.markdown(error_msg)
            st.session_state.messages.append({"role": "assistant", "content": error_msg, "intent": "out_of_scope"})
            st.stop()

        # Intent Classification 
        with st.spinner("Đang phân tích yêu cầu..."):
            intent = classify_intent(user_query)

        #  Process PDF nếu có file mới upload 
        if pdf_docs:
            if _has_new_files(pdf_docs):
                with st.spinner("Đang xử lý tài liệu PDF..."):
                    success = _auto_process(pdf_docs)
                    if not success:
                        msg = " Không thể đọc được nội dung từ file PDF. Vui lòng thử file khác."
                        st.markdown(msg)
                        st.session_state.messages.append({"role": "assistant", "content": msg, "intent": "enterprise"})
                        st.stop()
        else:
            # Nếu không còn file → xoá vectorstore
            if st.session_state.vectorstore is not None:
                st.session_state.vectorstore = None
                st.session_state.processed_files_hash = None
                st.session_state.processed_file_names = []

        #  Branch theo intent 
        try:
            # Lấy trước chat_history dùng chung
            chat_history = ""
            for m in st.session_state.messages[-5:-1]:
                role = "Người dùng" if m["role"] == "user" else "Trợ lý AI"
                chat_history += f"{role}: {m['content']}\n"

            if intent == "general_inquiry":
                # Không cần PDF — trả lời phiếm
                response_stream = ask_general_inquiry(user_query, chat_history)

            elif intent == "out_of_scope":
                # Từ chối lịch sự
                response_stream = ask_out_of_scope(user_query)

            else:
                # enterprise — cần vectorstore
                if st.session_state.vectorstore is None:
                    msg = (
                        "Để trả lời câu hỏi về doanh nghiệp, vui lòng upload file PDF "
                        "(nội quy, chính sách, hợp đồng...) và gửi lại câu hỏi."
                    )
                    st.markdown(msg)
                    st.session_state.messages.append({"role": "assistant", "content": msg, "intent": "enterprise"})
                    st.stop()

                context = get_context(st.session_state.vectorstore, user_query)
                response_stream = ask_enterprise_llm(context, user_query, chat_history)

        except Exception as e:
            st.markdown(f" Lỗi hệ thống: {str(e)}")
            st.stop()

        #  Stream response 
        full_response = st.write_stream(response_stream)
        st.markdown(_intent_badge(intent), unsafe_allow_html=True)
        st.session_state.messages.append({
            "role": "assistant",
            "content": full_response,
            "intent": intent,
        })


