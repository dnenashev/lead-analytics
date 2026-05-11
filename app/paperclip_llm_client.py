import os
import asyncio
import json
from typing import Optional, List
import httpx

PAPERCLIP_API_URL = os.getenv("PAPERCLIP_API_URL", "")
PAPERCLIP_API_KEY = os.getenv("PAPERCLIP_API_KEY", "")


class PaperclipLLMAdapter:
    def __init__(self, api_url: str = None, api_key: str = None):
        self.api_url = (api_url or PAPERCLIP_API_URL).rstrip("/")
        self.api_key = api_key or PAPERCLIP_API_KEY

    async def analyze_lead(self, system_prompt: str, user_data: dict) -> dict:
        if not self.api_url or not self.api_key:
            return self._fallback_mock(user_data)

        async with httpx.AsyncClient(timeout=120) as client:
            resp = await client.post(
                f"{self.api_url}/api/issues",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "title": f"LLM Diagnostic: lead {user_data.get('lead_id', 'unknown')}",
                    "description": f"Analyze this lead:\n\n```json\n{json.dumps(user_data, ensure_ascii=False, indent=2)}\n```\n\nSystem prompt: {system_prompt}",
                    "status": "backlog",
                },
                timeout=120,
            )
            if resp.status_code == 503:
                return await self._fallback_local(user_data)
            if resp.status_code >= 400:
                return self._fallback_mock(user_data)

            result = resp.json()
            return result if "diagnosis" in result else self._fallback_mock(user_data)

    def _fallback_mock(self, user_data: dict) -> dict:
        return {
            "lead_id": user_data.get("lead_id", ""),
            "cpl": user_data.get("cpl", 0),
            "manager_actions": user_data.get("manager_actions", []),
            "diagnosis": "Mock diagnosis (Paperclip adapter unavailable)",
            "is_traffic_issue": True,
            "is_sales_issue": False,
        }

    async def _fallback_local(self, user_data: dict) -> dict:
        return self._fallback_mock(user_data)
