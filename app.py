import os
import hashlib
import json
import requests
import streamlit as st
import time
import mimetypes

# Page Config 
st.set_page_config(
    page_title="Enterprise AI Assistant",
    layout="centered",
)

API_URL = "http://localhost:8000"

# Custom CSS 
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

# Session State
for key, default in [
    ("api_session_id", None),
    ("messages", []),
    ("processed_files_hash", None),
    ("processed_file_names", []),
    ("last_intent", ""), 
    ("session_start_idx", 0),
]:
    if key not in st.session_state:
        st.session_state[key] = default

# Tải lại lịch sử chat nếu URL có params session_id
if "session_id" in st.query_params and st.session_state.api_session_id is None:
    sid = st.query_params["session_id"]
    try:
        r = requests.get(f"{API_URL}/v1/sessions/{sid}/history")
        if r.status_code == 200:
            st.session_state.api_session_id = sid
            st.session_state.messages = r.json().get("history", [])
            st.session_state.session_start_idx = len(st.session_state.messages)
    except:
        pass

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
    """Gọi API POST /v1/ingest"""
    try:
        files_data = []
        for f in uploaded_files:
            f.seek(0)
            mime_type = mimetypes.guess_type(f.name)[0] or "application/octet-stream"
            files_data.append(("files", (f.name, f.read(), mime_type)))
            
        response = requests.post(f"{API_URL}/v1/ingest", files=files_data)
        if response.status_code == 200:
            data = response.json()
            st.session_state.api_session_id = data.get("session_id")
            st.query_params["session_id"] = data.get("session_id")
            st.session_state.processed_files_hash = _compute_files_hash(uploaded_files)
            st.session_state.processed_file_names = [f.name for f in uploaded_files]
            return True
        else:
            try:
                err_json = response.json()
                error_detail = err_json.get("message", err_json.get("detail", response.text))
                st.error(f"API Error ({response.status_code}): {error_detail}")
            except Exception:
                st.error(f"API Error ({response.status_code}): {response.text}")
            return False
    except requests.exceptions.ConnectionError:
        st.error(f"Không thể kết nối đến API tại {API_URL}. Vui lòng kiểm tra xem FastAPI đã chạy chưa.")
        return False
    except Exception as e:
        st.error(f"Lỗi: {e}")
        return False

def _intent_badge(intent: str) -> str:
    """Trả về HTML badge tương ứng với intent."""
    mapping = {
        "general_inquiry": ('<span class="badge badge-general"> General Inquiry</span>', ),
        "enterprise":      ('<span class="badge badge-enterprise"> Enterprise</span>', ),
        "out_of_scope":    ('<span class="badge badge-oos"> Out of Scope</span>', ),
    }
    return mapping.get(intent, ('',))[0]


# Header
st.markdown("""
<div class="enterprise-header">
    <div style="font-size:2.2rem"></div>
    <div>
        <h1>Enterprise AI Assistant</h1>
    </div>
</div>
""", unsafe_allow_html=True)

#  PDF Upload in Sidebar
with st.sidebar:
    st.markdown("### Tài liệu của bạn")
    pdf_docs = st.file_uploader(
        label="Tải lên file tài liệu hoặc hình ảnh (PDF, Word, Excel, PNG, JPG)",
        accept_multiple_files=True,
        type=["pdf", "docx", "xlsx", "png", "jpg", "jpeg"],
    )
    
    # Xử lý tự động ngay khi có thay đổi file
    if pdf_docs:
        if len(pdf_docs) > 2:
            st.error("Bạn chỉ có thể tải lên tối đa 2 file trong một lần.")
        elif _has_new_files(pdf_docs):
            with st.spinner("Đang xử lý tài liệu..."):
                success = _auto_process(pdf_docs)
                if success:
                    st.session_state.session_start_idx = len(st.session_state.messages)
                else:
                    st.error("Không thể gửi tài liệu lên API.")
    else:
        # Nếu không còn file => xoá api_session_id
        if st.session_state.api_session_id is not None:
            st.session_state.api_session_id = None
            st.session_state.processed_files_hash = None
            st.session_state.processed_file_names = []
            st.session_state.session_start_idx = len(st.session_state.messages)
            if "session_id" in st.query_params:
                del st.query_params["session_id"]

    # Hiển thị tên file đã upload qua API
    if st.session_state.processed_file_names:
        st.divider()
        st.markdown("**Tài liệu đang dùng:**")
        for n in st.session_state.processed_file_names:
            st.caption(f" {n}")
        if st.session_state.api_session_id:
            st.caption(f"`session_id: {st.session_state.api_session_id[:8]}...`")

#  Chat History 
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])
        if "intent" in message and message["role"] == "assistant":
            st.markdown(_intent_badge(message["intent"]), unsafe_allow_html=True)

#  Chat Input
user_query = st.chat_input("Nhập câu hỏi của bạn")

if user_query:
    st.session_state.messages.append({"role": "user", "content": user_query})
    with st.chat_message("user"):
        st.markdown(user_query)

    with st.chat_message("assistant"):
        with st.spinner():
            try:
                # Prepare payload for API
                session_messages = st.session_state.messages[st.session_state.session_start_idx : -1]
                history = [{"role": m["role"], "content": m["content"]} for m in session_messages[-5:]]
                
                payload = {
                    "session_id": st.session_state.api_session_id,
                    "message": user_query,
                    "history": history
                }

                # Streaming definition
                def stream_api_response():
                    st.session_state.last_intent = ""
                    with requests.post(f"{API_URL}/v1/chat/stream", json=payload, stream=True) as response:
                        if response.status_code != 200:
                            try:
                                err_json = response.json()
                                msg = err_json.get("message", err_json.get("detail", response.text))
                                yield f"Lỗi API: {response.status_code} - {msg}"
                            except:
                                yield f"Lỗi API: {response.status_code} - {response.text}"
                            return
                        
                        buffer = ""
                        for line in response.iter_lines():
                            if line:
                                decoded_line = line.decode('utf-8')
                                if decoded_line.startswith("data: "):
                                    data_str = decoded_line[6:]
                                    if data_str == "[DONE]":
                                        break
                                    buffer += data_str
                                    try:
                                        data = json.loads(buffer)
                                        buffer = "" # reset buffer khi decode thành công
                                        # Cập nhật intent để hiển thị badge sau
                                        if "intent" in data:
                                            st.session_state.last_intent = data["intent"]
                                        if "content" in data:
                                            yield data["content"]
                                    except json.JSONDecodeError:
                                        pass
                                        
                response_stream = stream_api_response()
                full_response = st.write_stream(response_stream)
                
                intent = st.session_state.last_intent
                if intent:
                    st.markdown(_intent_badge(intent), unsafe_allow_html=True)
                
                st.session_state.messages.append({
                    "role": "assistant",
                    "content": full_response,
                    "intent": intent,
                })
                
                # Cập nhật lịch sử về Redis Backend sau khi trao đổi xong
                if st.session_state.api_session_id:
                    try:
                        requests.post(f"{API_URL}/v1/sessions/{st.session_state.api_session_id}/history", json={"history": st.session_state.messages})
                    except:
                        pass
                
            except requests.exceptions.ConnectionError:
                st.error(f"Không thể kết nối đến API tại {API_URL}. Vui lòng khởi động API bằng cổng 8000:\\n`uvicorn src.main:app --host 0.0.0.0 --port 8000`")
            except Exception as e:
                st.markdown(f" Lỗi hệ thống: {str(e)}")
