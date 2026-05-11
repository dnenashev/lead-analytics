import os
import asyncio
from typing import List, Optional
import httpx
import jwt

AMOCRM_TOKEN = os.getenv("AMOCRM_TOKEN", "")
AMOCRM_RATE_LIMIT = 4.0
MAX_RETRIES = 3
BASE_DELAY = 1.0

_decoded_token = None


def _get_amocrm_config() -> dict:
    global _decoded_token
    if _decoded_token is None and AMOCRM_TOKEN:
        try:
            _decoded_token = jwt.decode(AMOCRM_TOKEN, options={"verify_signature": False})
        except Exception:
            _decoded_token = {}
    return _decoded_token or {}


def _get_amocrm_base_url() -> str:
    config = _get_amocrm_config()
    api_domain = config.get("api_domain", "api-b.amocrm.ru")
    return f"https://{api_domain}/api/v4"


def _get_amocrm_account_id() -> str:
    config = _get_amocrm_config()
    return str(config.get("account_id", ""))


class AmoCRMClient:
    def __init__(self, token: str = None):
        self.token = token or AMOCRM_TOKEN
        self.base_url = _get_amocrm_base_url()
        self._last_request_time = 0.0

    async def _rate_limited_request(self, method: str, url: str, params: dict = None) -> dict:
        now = asyncio.get_event_loop().time()
        elapsed = now - self._last_request_time
        if elapsed < 1.0 / AMOCRM_RATE_LIMIT:
            await asyncio.sleep(1.0 / AMOCRM_RATE_LIMIT - elapsed)
        self._last_request_time = asyncio.get_event_loop().time()

        for attempt in range(MAX_RETRIES):
            try:
                async with httpx.AsyncClient(timeout=30) as client:
                    resp = await client.request(
                        method, url,
                        headers={"Authorization": f"Bearer {self.token}"},
                        params=params,
                    )
                    resp.raise_for_status()
                    return resp.json()
            except (httpx.HTTPStatusError, httpx.TimeoutException) as e:
                if attempt < MAX_RETRIES - 1:
                    await asyncio.sleep(BASE_DELAY * (2 ** attempt))
                else:
                    raise

    async def get_crm_meta(self, lead_id: str) -> dict:
        if not self.token:
            return {"id": lead_id, "crm_status": "mock", "source": "mock"}
        url = f"{self.base_url}/leads/{lead_id}"
        data = await self._rate_limited_request("GET", url)
        return {
            "id": str(data.get("id", lead_id)),
            "crm_status": str(data.get("status_id", "unknown")),
            "source": str(data.get("custom_fields_values", [{}])[0].get("values", [{}])[0].get("value", "unknown"))
            if data.get("custom_fields_values") else "unknown",
            "created_at": str(data.get("created_at", "")),
        }

    async def get_manager_actions(self, lead_id: str) -> List[str]:
        if not self.token:
            return []
        actions = []
        page = 1
        while True:
            url = f"{self.base_url}/leads/{lead_id}/notes"
            data = await self._rate_limited_request(
                "GET", url,
                params={"page": page, "limit": 50},
            )
            items = data.get("_embedded", {}).get("notes", [])
            if not items:
                break
            for item in items:
                note_type = item.get("note_type", "")
                created = item.get("created_at", "")
                if note_type == "call_out":
                    duration = item.get("params", {}).get("duration", 0)
                    link = item.get("params", {}).get("link", "")
                    actions.append(f"call: {created} - duration={duration}s, link={link}")
                else:
                    text = item.get("params", {}).get("text", "")
                    actions.append(f"note: {created} - {text}")
            page += 1
            if len(items) < 50:
                break
        return actions
