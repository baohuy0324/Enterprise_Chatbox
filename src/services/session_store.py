"""Lưu FAISS vector store  trên Redis — dùng chung giữa nhiều worker/instance."""
from __future__ import annotations

import asyncio
import pickle
from typing import Any

import redis.asyncio as redis_async

_KEY_PREFIX = "pdf_rag:vs:"


def session_key(session_id: str) -> str:
    return f"{_KEY_PREFIX}{session_id}"


async def save_vectorstore(
    client: redis_async.Redis,
    session_id: str,
    vectorstore: Any,
    ttl_seconds: int,
) -> None:
    payload = await asyncio.to_thread(
        vectorstore.serialize_to_bytes
    )
    await client.setex(session_key(session_id), ttl_seconds, payload)

async def load_vectorstore_payload(
    client: redis_async.Redis, session_id: str
) -> bytes | None:
    raw = await client.get(session_key(session_id))
    if raw is None:
        return None
    return bytes(raw)


async def delete_session(client: redis_async.Redis, session_id: str) -> bool:
    return bool(await client.delete(session_key(session_id)))
