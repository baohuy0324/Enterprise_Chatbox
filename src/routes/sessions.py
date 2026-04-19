"""
Router: Sessions
DELETE /v1/sessions/{session_id} — xoá session khỏi Redis và RAM cache.
"""
from fastapi import APIRouter, HTTPException, Request

from src.core.cache import evict_session
from src.schemas.chat import DeleteResponse, ErrorResponse
from src.services import session_store

router = APIRouter(prefix="/v1", tags=["Sessions"])


@router.delete(
    "/sessions/{session_id}",
    response_model=DeleteResponse,
    responses={404: {"model": ErrorResponse, "description": "Not Found"}},
)
async def delete_session(session_id: str, request: Request):
    """Xoá session khỏi Redis và xoá cache RAM để giải phóng bộ nhớ."""
    removed = await session_store.delete_session(request.app.state.redis, session_id)

    # Luôn xoá RAM cache dù Redis key có tồn tại hay không
    evict_session(session_id)

    if not removed:
        raise HTTPException(status_code=404, detail="Không tìm thấy session.")
    return DeleteResponse(ok=True, message="Đã xoá session thành công.")

@router.post("/sessions/{session_id}/history")
async def update_history(session_id: str, payload: dict, request: Request):
    import json
    # payload: {"history": [...]}
    await session_store.save_history(request.app.state.redis, session_id, json.dumps(payload.get("history", [])), 86400)
    return {"ok": True}

@router.get("/sessions/{session_id}/history")
async def get_history(session_id: str, request: Request):
    import json
    raw = await session_store.load_history(request.app.state.redis, session_id)
    if not raw:
        return {"history": []}
    return {"history": json.loads(raw)}
