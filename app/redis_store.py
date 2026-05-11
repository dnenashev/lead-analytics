import os
import json
from typing import Optional
import asyncio

REDIS_URL = os.getenv("REDIS_URL", "")

_task_store: dict = {}

try:
    if REDIS_URL:
        import redis.asyncio as aioredis
        _redis_client = aioredis.from_url(REDIS_URL, decode_responses=True)
    else:
        _redis_client = None
except Exception:
    _redis_client = None


def _use_redis() -> bool:
    return _redis_client is not None


async def set_task(task_id: str, data: dict):
    if _use_redis():
        try:
            await _redis_client.set(f"task:{task_id}", json.dumps(data, ensure_ascii=False), ex=86400)
        except Exception:
            _task_store[task_id] = data
    else:
        _task_store[task_id] = data


async def get_task(task_id: str) -> Optional[dict]:
    if _use_redis():
        try:
            raw = await _redis_client.get(f"task:{task_id}")
            if raw:
                return json.loads(raw)
        except Exception:
            pass
    return _task_store.get(task_id)
