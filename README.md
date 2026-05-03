
# Enterprise Chatbox

Chatbox doanh nghiệp

## Tech Stack
- **Framework**: [FastAPI](https://fastapi.tiangolo.com/)
- **Orchestration**: [LangChain](https://www.langchain.com/)
- **Vector Database**: [FAISS](https://github.com/facebookresearch/faiss) (Lưu trữ và tìm kiếm vector local)
- **Embeddings**: `all-MiniLM-L6-v2` (Model local HuggingFace)
- **Database/Cache**: [Redis](https://redis.io/) (Quản lý phiên làm việc và lưu trữ Vector Store)
- **LLMs**: Gemini 2.5 Flash (Google) & Llama 3 (Groq)
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

```bash
streamlit run app.py
```

---

## API Reference (for Frontend)

Base URL: `http://<server-ip>:8000`

---

### `GET /health`

Kiểm tra service còn sống.

**Response `200`**
```json
{ "status": "ok" }
```

**Response `503`** — Redis không phản hồi
```json
{ "detail": "Redis không phản hồi." }
```

---

### `POST /v1/ingest`

Upload 1–2 file (PDF, DOCX, XLSX, PNG, JPG). Trả về `session_id` dùng cho chat enterprise.

**Request** — `multipart/form-data`

| Field   | Type     | Mô tả                         |
|---------|----------|-------------------------------|
| `files` | `File[]` | Tối đa 2 file. Bắt buộc.      |

**Response `200`**
```json
{
  "session_id": "550e8400-e29b-41d4-a716-446655440000",
  "message": "Đã tạo session và nạp vector store."
}
```

**Response `400`** — Không có file / sai định dạng / file rỗng / quá 2 file
```json
{ "detail": "Chỉ được phép tải lên tối đa 2 file trong một lần." }
```

**Response `500`** — Lỗi xử lý hoặc lưu Redis
```json
{ "detail": "Lỗi xử lý file: ..." }
```

---

### `POST /v1/chat/stream`

Gửi câu hỏi, nhận phản hồi dạng **SSE (Server-Sent Events)** streaming real-time.

**Request** — `application/json`

```json
{
  "session_id": "550e8400-...",
  "message": "Doanh thu quý 2 là bao nhiêu?",
  "history": [
    { "role": "user",      "content": "Xin chào",   "intent": null },
    { "role": "assistant", "content": "Xin chào!", "intent": "general_inquiry" }
  ]
}
```

| Field        | Type            | Bắt buộc | Mô tả                                                   |
|--------------|-----------------|----------|---------------------------------------------------------|
| `session_id` | `string \| null`| Không*   | Từ `/v1/ingest`. Bắt buộc khi hỏi về tài liệu nội bộ. |
| `message`    | `string`        | Có       | Câu hỏi của user.                                       |
| `history`    | `ChatMessage[]` | Không    | Lịch sử hội thoại trước đó (để giữ ngữ cảnh).          |

**`ChatMessage` schema**
```ts
{
  role:    "user" | "assistant"
  content: string
  intent?: "general_inquiry" | "enterprise" | "out_of_scope" | null
}
```

**Response** — `text/event-stream`

Mỗi event có dạng:
```
data: {"content": "Doanh thu quý 2", "intent": "enterprise"}\n\n
data: {"content": " là 5 tỷ đồng.",  "intent": "enterprise"}\n\n
data: [DONE]\n\n
```

Khi nhận `data: [DONE]` → stream kết thúc.

**Intent values**

| Intent            | Ý nghĩa                                    |
|-------------------|--------------------------------------------|
| `general_inquiry` | Câu hỏi thông thường, không cần PDF        |
| `enterprise`      | Câu hỏi về tài liệu nội bộ (dùng RAG)     |
| `out_of_scope`    | Ngoài phạm vi, bị từ chối lịch sự          |

**Response `400`** — Câu hỏi không an toàn
```json
{ "detail": "..." }
```

**Response `404`** — Session không tồn tại / hết hạn (chỉ với enterprise intent)
```json
{ "detail": "Session không tồn tại hoặc đã hết hạn. Gọi lại /v1/ingest." }
```

**Ví dụ JS (fetch thay cho EventSource vì cần POST)**
```js
const res = await fetch('http://<server-ip>:8000/v1/chat/stream', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ session_id, message, history }),
});

const reader = res.body.getReader();
const decoder = new TextDecoder();

while (true) {
  const { done, value } = await reader.read();
  if (done) break;
  for (const line of decoder.decode(value).split('\n')) {
    if (!line.startsWith('data: ')) continue;
    const data = line.slice(6);
    if (data === '[DONE]') return;
    const { content, intent } = JSON.parse(data);
    // append content to UI
  }
}
```

---

### `GET /v1/sessions/{session_id}/history`

Lấy lịch sử hội thoại của một session (TTL 24 giờ).

**Response `200`**
```json
{
  "history": [
    { "role": "user",      "content": "Xin chào", "intent": null },
    { "role": "assistant", "content": "Xin chào!", "intent": "general_inquiry" }
  ]
}
```

Trả `{ "history": [] }` nếu chưa có lịch sử.

---

### `POST /v1/sessions/{session_id}/history`

Ghi đè lịch sử hội thoại. Gọi sau mỗi lượt chat để đồng bộ lên server.

**Request** — `application/json`
```json
{
  "history": [
    { "role": "user",      "content": "Xin chào", "intent": null },
    { "role": "assistant", "content": "Xin chào!", "intent": "general_inquiry" }
  ]
}
```

**Response `200`**
```json
{ "ok": true }
```

---

### `DELETE /v1/sessions/{session_id}`

Giải phóng bộ nhớ — xoá session khỏi Redis và RAM cache.

**Response `200`**
```json
{ "ok": true, "message": "Đã xoá session thành công." }
```

**Response `404`**
```json
{ "detail": "Không tìm thấy session." }
```

---

## Luồng tích hợp (FE Flow)

```
1. POST /v1/ingest                      → nhận session_id
2. POST /v1/chat/stream                 → stream câu trả lời (kèm session_id + history)
3. POST /v1/sessions/{id}/history       → lưu history sau mỗi lượt (tuỳ chọn)
4. DELETE /v1/sessions/{id}             → khi user đóng tab / kết thúc phiên
```

---

