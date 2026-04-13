
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

### 1. Quy trình Nạp dữ liệu (Ingestion Pipeline)
- **Trích xuất thông minh**: Sử dụng `PyPDFLoader` để xử lý các file PDF được tải lên, trích xuất văn bản và giữ lại metadata cần thiết.
- **Phân đoạn văn bản (Chunking)**: Áp dụng `RecursiveCharacterTextSplitter` với kích thước chunk 1500 ký tự và độ chồng lặp (overlap) 300. Kỹ thuật này giúp duy trì ngữ cảnh giữa các đoạn văn bản, đảm bảo câu trả lời không bị mất thông tin tại các điểm cắt.
- **Số hóa nội dung (Embedding)**: Chuyển đổi văn bản thành không gian vector bằng mô hình local `all-MiniLM-L6-v2`. Việc sử dụng model local giúp bảo mật dữ liệu và giảm chi phí vận hành.
- **Lưu trữ đa tầng**:
    - **Vĩnh cửu (Redis)**: Index FAISS được nén và lưu trữ vào Redis kèm theo `session_id` để chia sẻ giữa các instance.
    - **Truy cập nhanh (LRU Cache)**: Các VectorStore thường dùng được giải mã và lưu tại bộ nhớ RAM (tối đa 50 sessions) giúp giảm tải CPU và tăng tốc độ phản hồi.

### 2. Quy trình Truy vấn & Phản hồi (Query Pipeline)
- **Lớp bảo mật (Security Layer)**: Mọi câu hỏi đều đi qua bộ lọc `is_safe_query` để phát hiện và ngăn chặn các hành vi Prompt Injection.
- **Định danh & Tracing**: Mỗi yêu cầu được gán một `X-Request-ID` duy nhất giúp theo dõi vết (tracing).
- **Truy xuất ngữ cảnh (Retrieval)**:
    - Hệ thống tìm kiếm 6 đoạn văn bản tương quan nhất từ cơ sở dữ liệu FAISS.
    - **Max Marginal Relevance (MMR)**: Thuật toán được tinh chỉnh để cân bằng giữa độ chính xác và tính đa dạng của thông tin, giảm thiểu sự trùng lặp và tối ưu hóa phạm vi kiến thức cho LLM.
- **Điều phối thông minh (LLM Routing)**: 
    - **Gemini 2.5 Flash**: Lựa chọn khi ngữ cảnh ngắn (< 4000 ký tự) để tối ưu độ chính xác và khả năng hiểu tiếng Việt.
    - **Groq (Llama 3.1)**: Tự động chuyển đổi khi dữ liệu lớn để đảm bảo tốc độ suy luận cực nhanh.
- **Chế độ phản hồi linh hoạt**:
    - **Standard Response**: Trả về kết quả hoàn chỉnh ngay khi LLM kết thúc quá trình suy luận.
    - **SSE Streaming**: Hỗ trợ Server-Sent Events thông qua endpoint `/v1/chat/stream`, trả từng từ (token) real-time.

## Triển khai Docker 

```bash
docker build -t pdfs-ai-assistant .
docker run -d --name pdf-api --env-file .env -p 8000:8000 pdfs-ai-assistant
```

