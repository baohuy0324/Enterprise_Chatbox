
# Enterprise Chatbox

Chatbox doanh nghiệp

## Tech Stack
- **Framework**: [FastAPI](https://fastapi.tiangolo.com/)
- **Orchestration**: [LangChain](https://www.langchain.com/)
- **Vector Database**: [FAISS](https://github.com/facebookresearch/faiss) (Lưu trữ và tìm kiếm vector local)
- **Embeddings**: `all-MiniLM-L6-v2` (Model local HuggingFace)
- **Database/Cache**: [Redis](https://redis.io/) (Quản lý phiên làm việc và lưu trữ Vector Store)
- **LLMs**: Gemini 1.5 Flash (Google) & Llama 3 (Groq)
- **Interface**: [Streamlit](https://streamlit.io/) (Demo UI)

---

## Cấu hình môi trường (.env)

`GEMINI_API_KEY:` [Google AI Studio](https://aistudio.google.com/app/apikey)

`GROQ_API_KEY:` [Groq Console](https://console.groq.com/keys) 


---

## Quick Start

### 1. Cài đặt & Cấu hình
```bash
git clone https://github.com/baohuy0324/Enterprise_Chatbox.git
cd Enterprise_Chatbox

# Khởi tạo môi trường
python -m venv venv
# Windows: .\venv\Scripts\Activate.ps1
pip install -r requirements.txt
# Tạo file cấu hình
cp .env.example .env
```
*Điền các API Key vào file `.env`.*

### 2. Khởi động hệ thống

**Bước 1: Chạy Redis (Dùng Docker)**
```bash
docker run -d --name redis-pdf -p 6379:6379 redis:7-alpine
```

**Bước 2: Chạy REST API**
```bash
uvicorn src.main:app --host 0.0.0.0 --port 8000 --reload
# Xem Swagger UI tại: http://127.0.0.1:8000/docs
```

**Bước 3: Chạy giao diện kiểm thử Streamlit (Tùy chọn)**

*(Lưu ý: Bạn phải đảm bảo API ở Bước 2 đang chạy, vì Streamlit hiện đóng vai trò là Frontend gọi qua REST API).*
```bash
streamlit run app.py
```

---

## Các API Endpoints

| Method   | Endpoint                      | Payload | Mô tả |
|----------|-------------------------------|---------|-------|
| `GET`    | `/health`                     | None    | Kiểm tra sự sống của hệ thống và Redis. |
| `POST`   | `/v1/ingest`                  | `multipart/form-data` | Upload file PDF, trả về `session_id`. |
| `POST`   | `/v1/chat/stream`             | `application/json` | Gửi câu hỏi dựa trên `session_id` đã có. Trả về stream SSE. |
| `DELETE` | `/v1/sessions/{session_id}`   | Path    | Giải phóng bộ nhớ, xoá session ngay lập tức khỏi Redis và RAM cache. |

---


## Triển khai Docker 

```bash
docker build -t Enterprise_Chatbox .
docker run -d --name Enterprise_Chatbox --env-file .env -p 8000:8000 Enterprise_Chatbox
```

