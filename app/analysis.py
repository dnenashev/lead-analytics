import os
import asyncio
from typing import List, Optional
import httpx
from app.models import LeadAnalysisResult
from app.mock_services import (
    mock_get_crm_meta,
    mock_get_manager_actions,
    mock_get_campaign_cpl,
)
from app.bitrix_client import Bitrix24Client
from app.amocrm_client import AmoCRMClient
from app.ad_clients import get_ad_client
from app.paperclip_llm_client import PaperclipLLMAdapter
from app.redis_store import set_task

USE_DUAL_CRM = os.getenv("USE_DUAL_CRM", "true").lower() == "true"

LLM_PROVIDER = os.getenv("LLM_PROVIDER", "mock")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
MAX_RETRY_ATTEMPTS = int(os.getenv("MAX_RETRY_ATTEMPTS", "3"))

LANGCHAIN_TRACING_V2 = os.getenv("LANGCHAIN_TRACING_V2", "false")
LANGCHAIN_PROJECT = os.getenv("LANGCHAIN_PROJECT", "Cohort_Analyzer_Prod")
LANGCHAIN_API_KEY = os.getenv("LANGCHAIN_API_KEY", "")

PAPERCLIP_API_URL = os.getenv("PAPERCLIP_API_URL", "")
PAPERCLIP_API_KEY = os.getenv("PAPERCLIP_API_KEY", "")

USE_MOCKS = os.getenv("USE_MOCKS", "true").lower() == "true"

_task_store: dict = {}


async def _call_llm(system_prompt: str, user_data: dict) -> dict:
    if LLM_PROVIDER == "paperclip":
        adapter = PaperclipLLMAdapter(PAPERCLIP_API_URL, PAPERCLIP_API_KEY)
        return await adapter.analyze_lead(system_prompt, user_data)

    if LLM_PROVIDER == "mock" or not (GEMINI_API_KEY or DEEPSEEK_API_KEY):
        return {
            "lead_id": user_data.get("lead_id", ""),
            "cpl": user_data.get("cpl", 0),
            "manager_actions": user_data.get("manager_actions", []),
            "diagnosis": "Mock diagnosis: lead quality issue",
            "is_traffic_issue": True,
            "is_sales_issue": False,
        }

    try:
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
        )
        parser = PydanticOutputParser(pydantic_object=LeadAnalysisResult)
        chain = prompt | model | parser
        result = await chain.ainvoke({"data": str(user_data)})
        return result.model_dump()
    except ImportError:
        return {
            "lead_id": user_data.get("lead_id", ""),
            "cpl": user_data.get("cpl", 0),
            "manager_actions": user_data.get("manager_actions", []),
            "diagnosis": "LLM import error, using mock",
            "is_traffic_issue": False,
            "is_sales_issue": False,
        }


SYSTEM_PROMPT = """You are a lead quality analyst. Analyze the lead data and determine:
1. Whether this is a traffic quality issue (bad targeting, wrong audience)
2. Whether this is a sales processing issue (poor follow-up, missed calls)

Return a strict JSON with: lead_id, cpl, manager_actions, diagnosis, is_traffic_issue, is_sales_issue."""


async def analyze_single_lead(lead_id: str, campaign_name: str) -> dict:
    try:
        if USE_MOCKS:
            crm_meta = await mock_get_crm_meta(lead_id)
            manager_actions = await mock_get_manager_actions(lead_id)
            cpl = await mock_get_campaign_cpl(campaign_name)
        else:
            crm_meta = {"id": lead_id, "crm_status": "unknown", "source": "unknown"}
            manager_actions = []
            if USE_DUAL_CRM:
                bitrix = Bitrix24Client()
                amocrm = AmoCRMClient()
                b_meta, b_actions, a_meta, a_actions = await asyncio.gather(
                    bitrix.get_crm_meta(lead_id), bitrix.get_manager_actions(lead_id),
                    amocrm.get_crm_meta(lead_id), amocrm.get_manager_actions(lead_id),
                    return_exceptions=True,
                )
                if not isinstance(b_meta, Exception) and b_meta.get("crm_status") != "mock":
                    crm_meta = b_meta
                    manager_actions = b_actions if not isinstance(b_actions, Exception) else []
                if not isinstance(a_meta, Exception) and a_meta.get("crm_status") != "mock":
                    crm_meta = a_meta
                    if isinstance(a_actions, list) and a_actions:
                        manager_actions = a_actions
            else:
                crm = Bitrix24Client()
                crm_meta = await crm.get_crm_meta(lead_id)
                manager_actions = await crm.get_manager_actions(lead_id)
            ad_client = get_ad_client(campaign_name)
            cpl = await ad_client.get_campaign_cpl(campaign_name)

        user_data = {
            "lead_id": lead_id,
            "cpl": cpl or 0,
            "manager_actions": manager_actions,
            "crm_status": crm_meta.get("crm_status", "unknown"),
            "source": crm_meta.get("source", "unknown"),
        }

        last_error = None
        for attempt in range(MAX_RETRY_ATTEMPTS):
            try:
                result = await _call_llm(SYSTEM_PROMPT, user_data)
                validated = LeadAnalysisResult(**result)
                return validated.model_dump()
            except Exception as e:
                last_error = str(e)
                continue

        return {
            "lead_id": lead_id,
            "cpl": user_data["cpl"],
            "manager_actions": user_data["manager_actions"],
            "diagnosis": f"FAILED after {MAX_RETRY_ATTEMPTS} attempts: {last_error}",
            "is_traffic_issue": False,
            "is_sales_issue": False,
        }
    except Exception as e:
        return {
            "lead_id": lead_id,
            "cpl": 0,
            "manager_actions": [],
            "diagnosis": f"FAILED_API_ERROR: {str(e)}",
            "is_traffic_issue": False,
            "is_sales_issue": False,
        }


async def post_paperclip_comment(issue_id: str, text: str):
    if not PAPERCLIP_API_URL or not PAPERCLIP_API_KEY:
        return
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            await client.post(
                f"{PAPERCLIP_API_URL}/api/issues/{issue_id}/comments",
                headers={
                    "Authorization": f"Bearer {PAPERCLIP_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={"body": text},
            )
    except Exception:
        pass


async def search_leads_by_campaign(campaign_names: List[str], sample_size: int) -> dict:
    if USE_MOCKS:
        result = {}
        for campaign in campaign_names:
            result[campaign] = [f"lead_{campaign.strip('*')}_{i+1}" for i in range(sample_size)]
        return result

    result = {}
    for campaign in campaign_names:
        lead_ids = []
        try:
            if USE_DUAL_CRM:
                bitrix = Bitrix24Client()
                amocrm = AmoCRMClient()
                b_ids, a_ids = await asyncio.gather(
                    bitrix.search_leads_by_campaign(campaign),
                    amocrm.search_leads_by_campaign(campaign),
                    return_exceptions=True,
                )
                if not isinstance(b_ids, Exception):
                    lead_ids.extend(b_ids)
                if not isinstance(a_ids, Exception):
                    lead_ids.extend(a_ids)
            else:
                bitrix = Bitrix24Client()
                lead_ids = await bitrix.search_leads_by_campaign(campaign)
        except Exception:
            lead_ids = [f"lead_{campaign.strip('*')}_{i+1}" for i in range(sample_size)]
        result[campaign] = lead_ids[:sample_size]
    return result


async def analyze_cohort(campaign_names: List[str], sample_size: int, issue_id: Optional[str] = None, task_id: str = ""):
    import logging
    logger = logging.getLogger(__name__)
    results = []
    total = sample_size * len(campaign_names)
    processed = 0

    leads_by_campaign = await search_leads_by_campaign(campaign_names, sample_size)

    for campaign in campaign_names:
        lead_ids = leads_by_campaign.get(campaign, [])
        for lead_id in lead_ids:
            result = await analyze_single_lead(lead_id, campaign)
            result["campaign"] = campaign
            results.append(result)
            processed += 1

            if processed % 5 == 0 and issue_id:
                await post_paperclip_comment(
                    issue_id,
                    f"Progress: {processed}/{total} leads analyzed ({campaign})",
                )

    completed = {
        "status": "completed",
        "progress": f"{total}/{total} leads analyzed",
        "results": results,
    }
    _task_store[task_id] = completed
    await set_task(task_id, completed)

    if issue_id and results:
        traffic_issues = sum(1 for r in results if r.get("is_traffic_issue"))
        sales_issues = sum(1 for r in results if r.get("is_sales_issue"))
        avg_cpl = sum(r.get("cpl", 0) for r in results) / len(results) if results else 0
        await post_paperclip_comment(
            issue_id,
            f"✅ Analysis complete: {len(results)} leads, "
            f"{traffic_issues} traffic issues, {sales_issues} sales issues, "
            f"avg CPL: {avg_cpl:.2f}",
        )

    return results
