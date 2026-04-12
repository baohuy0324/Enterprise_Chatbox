# PDFs AI Assistant

RAG (Retrieval-Augmented Generation) trên PDF: Upload tài liệu $\rightarrow$ Đặt câu hỏi $\rightarrow$ Nhận câu trả lời dựa trên nội dung.

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
git clone https://github.com/baohuy0324/pdfs-aiAssistant2.git
cd pdfs-aiAssistant2

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

**Bước 3: Chạy giao diện kiểm thử (Tùy chọn)**
```bash
streamlit run app.py
```

---

## Các API Endpoints

| Method   | Endpoint                      | Payload | Mô tả |
|----------|-------------------------------|---------|-------|
| `GET`    | `/health`                     | None    | Kiểm tra sự sống của hệ thống và Redis. |
| `POST`   | `/v1/ingest`                  | `multipart/form-data` | Upload file PDF, trả về `session_id`. |
| `POST`   | `/v1/chat`                    | `application/json` | Gửi câu hỏi dựa trên `session_id` đã có. |
| `DELETE` | `/v1/sessions/{session_id}`   | Path    | Giải phóng bộ nhớ, xoá session ngay lập tức. |

---

## Cơ chế RAG & Luồng dữ liệu


### 1. Giai đoạn Nạp dữ liệu (Ingestion Phase)
- **Tải lên & Trích xuất**: File PDF được tải lên và trích xuất nội dung văn bản bằng `PyPDFLoader`.
- **Chia nhỏ văn bản (Chunking)**: Văn bản được chia thành các đoạn nhỏ 1500 ký tự (Overlap 300) để tối ưu khả năng xử lý của AI.
- **Số hóa (Embedding local)**: Chuyển đổi văn bản thành Vector bằng model `all-MiniLM-L6-v2` chạy trực tiếp trên máy.
- **Lưu trữ (Redis)**: Index FAISS được nén và lưu vào Redis kèm theo `session_id`.

### 2. Giai đoạn Truy vấn & Trả lời (Query Phase)
- **Bảo mật**: Kiểm tra tính an toàn của câu hỏi (Security Filter).
- **Tìm kiếm (Retrieval)**: Dựa trên `session_id`, hệ thống tìm ra 6 đoạn văn bản có nội dung liên quan nhất trong file PDF.
- **Điều phối (LLM Router)**: Tự động chọn model phù hợp:
    - **Gemini**: Cho các đoạn văn bản ngắn (< 4000 ký tự).
    - **Groq (Llama 3)**: Cho các đoạn văn bản dài để đảm bảo tốc độ xử lý.
- **Kết quả**: Trả về câu trả lời chính xác dựa trên kiến thức từ file.

## Triển khai Docker 

```bash
docker build -t pdfs-ai-assistant .
docker run -d --name pdf-api --env-file .env -p 8000:8000 pdfs-ai-assistant
```
