import os
import asyncio
from typing import List, Optional
import httpx

BITRIX24_WEBHOOK_URL = os.getenv("BITRIX24_WEBHOOK_URL", "")
BITRIX_RATE_LIMIT = 2.0
MAX_RETRIES = 3
BASE_DELAY = 1.0


class Bitrix24Client:
    def __init__(self, webhook_url: str = None):
        self.webhook_url = webhook_url or BITRIX24_WEBHOOK_URL
        self._last_request_time = 0.0

    async def _rate_limited_request(self, method: str, params: dict = None) -> dict:
        now = asyncio.get_event_loop().time()
        elapsed = now - self._last_request_time
        if elapsed < 1.0 / BITRIX_RATE_LIMIT:
            await asyncio.sleep(1.0 / BITRIX_RATE_LIMIT - elapsed)
        self._last_request_time = asyncio.get_event_loop().time()

        for attempt in range(MAX_RETRIES):
            try:
                async with httpx.AsyncClient(timeout=30) as client:
                    url = f"{self.webhook_url}/{method}"
                    resp = await client.post(url, json=params or {})
                    resp.raise_for_status()
                    return resp.json()
            except (httpx.HTTPStatusError, httpx.TimeoutException) as e:
                if attempt < MAX_RETRIES - 1:
                    await asyncio.sleep(BASE_DELAY * (2 ** attempt))
                else:
                    raise

    async def get_crm_meta(self, lead_id: str) -> dict:
        if not self.webhook_url:
            return {"id": lead_id, "crm_status": "mock", "source": "mock"}
        result = await self._rate_limited_request("crm.lead.get", {"ID": lead_id})
        lead = result.get("result", {})
        return {
            "id": lead.get("ID", lead_id),
            "crm_status": lead.get("STATUS_ID", "unknown"),
            "source": lead.get("SOURCE_ID", "unknown"),
            "created_at": lead.get("DATE_CREATE", ""),
        }

    async def get_manager_actions(self, lead_id: str) -> List[str]:
        if not self.webhook_url:
            return []
        actions = []
        start = 0
        while True:
            result = await self._rate_limited_request(
                "crm.timeline.comment.list",
                {"filter": {"ENTITY_ID": lead_id, "ENTITY_TYPE": "lead"}, "start": start},
            )
            items = result.get("result", [])
            if not items:
                break
            for item in items:
                actions.append(f'{item.get("CREATED", "")} - {item.get("COMMENT", "")}')
            start += len(items)
            if len(items) < 50:
                break
        return actions
