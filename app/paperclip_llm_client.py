import os
import logging
from typing import Any

from app.models import LeadAnalysisResult

logger = logging.getLogger(__name__)

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")


class PaperclipLLMAdapter:
    def __init__(self, api_url: str | None = None, api_key: str | None = None):
        self.api_url = api_url or os.getenv("PAPERCLIP_API_URL", "")
        self.api_key = api_key or os.getenv("PAPERCLIP_API_KEY", "")

    async def analyze_lead(self, system_prompt: str, user_data: dict) -> dict:
        lead_id = user_data.get("lead_id", "unknown")
        cpl = user_data.get("cpl", 0)
        crm_status = user_data.get("crm_status", "unknown")
        manager_actions = user_data.get("manager_actions", [])
        source = user_data.get("source", "unknown")

        logger.info("Paperclip adapter: analyzing lead %s (CPL=%.2f, status=%s)", lead_id, cpl, crm_status)

        # Try Gemini first
        if GEMINI_API_KEY:
            try:
                return await self._call_gemini(system_prompt, user_data)
            except Exception as e:
                logger.warning("Gemini failed for lead %s: %s — trying fallback", lead_id, e)

        # No LLM available — explain clearly
        return {
            "lead_id": lead_id,
            "cpl": cpl,
            "manager_actions": manager_actions,
            "diagnosis": (
                "Paperclip LLM adapter: no LLM configured. "
                "Set GEMINI_API_KEY or DEEPSEEK_API_KEY env var on Railway, "
            ),
            "is_traffic_issue": False,
            "is_sales_issue": False,
        }

    async def _call_gemini(self, system_prompt: str, user_data: dict) -> dict:
        from langchain_core.prompts import ChatPromptTemplate
        from langchain_core.output_parsers import PydanticOutputParser
        from langchain_google_genai import ChatGoogleGenerativeAI

        prompt = ChatPromptTemplate.from_messages([
            ("system", system_prompt),
            ("human", "Analyze this lead data: {data}"),
        ])
        model = ChatGoogleGenerativeAI(
            model="gemini-2.0-flash",
            google_api_key=GEMINI_API_KEY,
            temperature=0.1,
        )
        parser = PydanticOutputParser(pydantic_object=LeadAnalysisResult)
        chain = prompt | model | parser
        result = await chain.ainvoke({"data": str(user_data)})
        return result.model_dump()


