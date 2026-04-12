import os
os.environ["TRANSFORMERS_VERBOSITY"] = "error"
os.environ["TOKENIZERS_PARALLELISM"] = "false"

import streamlit as st
from src.services.rag import process_pdfs_to_vectorstore, get_context
from src.services.llm import ask_llm
from src.core.security import is_safe_query
from src.core.config import check_keys

st.set_page_config(page_title="Chat with Multiple PDFs", page_icon="📚", layout="wide")

st.title("Chat with PDFs")

check_keys()



if "vectorstore" not in st.session_state:
    st.session_state.vectorstore = None

if "messages" not in st.session_state:
    st.session_state.messages = []

# ================= SIDEBAR ================= 
with st.sidebar:
    st.header("Upload tài liệu (PDFs)")
    pdf_docs = st.file_uploader(
        "Tải lên nhiều file PDF và nhấn 'Process'", 
        accept_multiple_files=True,
        type="pdf"
    )
    if st.button("Process"):
        with st.spinner("Đang xử lý..."):
            if pdf_docs:
                try:
                    vectorstore = process_pdfs_to_vectorstore(pdf_docs)
                    if vectorstore:
                        st.session_state.vectorstore = vectorstore
                        st.success("Đã xử lý thành công!")
                    else:
                        st.error("Không tìm thấy nội dung văn bản bên trong file PDF.")
                except Exception as e:
                    st.error(f"Đã có lỗi xảy ra trong quá trình xử lý: {e}")
            else:
                st.warning("Vui lòng tải lên tài liệu cần xử lý.")

# ================= MAIN CHAT ================= 
st.header("")

# Render lịch sử 
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

user_query = st.chat_input("Hãy đặt bất kỳ câu hỏi nào về nội dung file pdf...")

if user_query:
    # Append câu hỏi của user vào giao diện
    st.session_state.messages.append({"role": "user", "content": user_query})
    with st.chat_message("user"):
        st.markdown(user_query)
        
    with st.chat_message("assistant"):
        # Bước chặn Router
        is_safe, error_msg = is_safe_query(user_query)
        
        if not is_safe:
            st.error(error_msg)
            st.session_state.messages.append({"role": "assistant", "content": error_msg})
        else:
            if st.session_state.vectorstore is None:
                msg = "Vui lòng hoàn tất quá trình upload và process file PDF trước khi đặt câu hỏi."
                st.warning(msg)
                st.session_state.messages.append({"role": "assistant", "content": msg})
            else:
                with st.status("Đang suy nghĩ...", expanded=True) as status:
                    try:
                        # 1. Trích xuất lịch sử
                        chat_history = ""
                        for m in st.session_state.messages[-5:-1]: 
                            role = "Người dùng" if m["role"] == "user" else "Trợ lý AI"
                            chat_history += f"{role}: {m['content']}\n"

                        st.write("Đang tìm kiếm thông tin tương đồng...")
                        context = get_context(st.session_state.vectorstore, user_query)
                        
                        st.write("Đang tổng hợp dữ liệu...")
                        # 3. Gọi model AI (Dạng Stream cho hiệu ứng đang gõ)
                        response_stream = ask_llm(context, user_query, chat_history)

                        status.update(label="Đã phân tích xong!", state="complete", expanded=False)
                    except Exception as e:
                        status.update(label="Lỗi hệ thống", state="error", expanded=False)
                        st.error(f"Lỗi hệ thống LLM: {str(e)}")
                        response_stream = None
                
                
                if response_stream:
                    full_response = st.write_stream(response_stream)
                    st.session_state.messages.append({"role": "assistant", "content": full_response})
