import os
import json
import logging
import httpx

from app.models import LeadAnalysisResult

logger = logging.getLogger(__name__)

COMPANY_ID = os.getenv("PAPERCLIP_COMPANY_ID", "a4a04515-96a8-478f-b624-732c5dbc2d3f")
AGENT_ID = os.getenv("LEAD_ANALYTICS_BOT_ID", "")


class PaperclipLLMAdapter:
    def __init__(self, api_url: str | None = None, api_key: str | None = None):
        self.api_url = (
            api_url
            or os.getenv("PAPERCLIP_API_URL", "")
            or os.getenv("PAPERCLIP_SERVICE_URL", "")
        ).rstrip("/")
        self.api_key = (
            api_key
            or os.getenv("PAPERCLIP_API_KEY", "")
            or os.getenv("PAPERCLIP_SERVICE_TOKEN", "")
        )

    async def analyze_lead(self, system_prompt: str, user_data: dict) -> dict:
        lead_id = user_data.get("lead_id", "unknown")
        cpl = user_data.get("cpl", 0)
        crm_status = user_data.get("crm_status", "unknown")
        manager_actions = user_data.get("manager_actions", [])
        source = user_data.get("source", "unknown")

        logger.info("Paperclip adapter: analyzing lead %s via Paperclip API", lead_id)

        if not self.api_url or not self.api_key:
            return self._fallback(user_data, "Paperclip API not configured")

        try:
            diagnosis = await self._create_diagnosis_issue(lead_id, cpl, crm_status, manager_actions, source, system_prompt)
            return {
                "lead_id": lead_id,
                "cpl": cpl,
                "manager_actions": manager_actions,
                "diagnosis": diagnosis.get("diagnosis", "Processing — see Paperclip issue"),
                "is_traffic_issue": diagnosis.get("is_traffic_issue", False),
                "is_sales_issue": diagnosis.get("is_sales_issue", False),
            }
        except Exception as e:
            logger.warning("Paperclip API diagnosis failed for lead %s: %s", lead_id, e)
            return self._fallback(user_data, f"Paperclip API error: {e}")

    async def _find_existing_diagnosis_issue(self, lead_id: str) -> dict | None:
        title = f"LLM Diagnosis: lead {lead_id}"
        known_statuses = ("in_progress", "todo", "backlog")
        page = 1
        page_size = 200

        async with httpx.AsyncClient(timeout=15.0) as client:
            while True:
                resp = await client.get(
                    f"{self.api_url}/api/companies/{COMPANY_ID}/issues",
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json",
                    },
                    params={
                        "status": "in_progress,todo,backlog",
                        "limit": page_size,
                        "offset": (page - 1) * page_size,
                    },
                )
                if resp.status_code >= 400:
                    logger.warning(
                        "Failed to check existing issues: HTTP %s", resp.status_code
                    )
                    return None

                data = resp.json()
                issues = (
                    data
                    if isinstance(data, list)
                    else data.get("issues", data.get("data", []))
                )
                if not issues:
                    logger.info(
                        "No more issues to check (page %s returned empty)", page
                    )
                    return None

                for issue in issues:
                    if issue.get("title") == title and issue.get("status") in known_statuses:
                        existing_id = issue.get("identifier") or issue.get("id", "unknown")
                        logger.info(
                            "Found existing diagnosis issue %s for lead %s",
                            existing_id,
                            lead_id,
                        )
                        return existing_id

                if len(issues) < page_size:
                    logger.info(
                        "Reached last page (page %s had %s issues, expected %s)",
                        page,
                        len(issues),
                        page_size,
                    )
                    return None

                page += 1

    async def _create_diagnosis_issue(self, lead_id: str, cpl: float, crm_status: str, manager_actions: list, source: str, system_prompt: str) -> dict:
        existing = await self._find_existing_diagnosis_issue(lead_id)
        if existing:
            return {"diagnosis": f"Diagnosis already requested in Paperclip issue {existing}", "is_traffic_issue": False, "is_sales_issue": False}

        issue_data = {
            "title": f"LLM Diagnosis: lead {lead_id}",
            "description": (
                f"## Lead Analysis Request\n\n"
                f"**Lead ID:** {lead_id}\n"
                f"**CPL:** ${cpl:.2f}\n"
                f"**CRM Status:** {crm_status}\n"
                f"**Source:** {source}\n"
                f"**Manager Actions:** {json.dumps(manager_actions, ensure_ascii=False, indent=2)}\n\n"
                f"**System Prompt:** {system_prompt}\n\n"
                f"Analyze this lead and determine:\n"
                f"1. Is this a traffic quality issue (bad targeting, wrong audience)?\n"
                f"2. Is this a sales processing issue (poor follow-up, missed calls)?\n"
                f"3. Provide a short diagnosis."
            ),
            "labels": ["lead-diagnosis"],
        }
        if AGENT_ID:
            issue_data["assigneeAgentId"] = AGENT_ID

        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(
                f"{self.api_url}/api/companies/{COMPANY_ID}/issues",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json=issue_data,
            )
            if resp.status_code == 503:
                return self._fallback_result("Paperclip API unavailable (503)")
            if resp.status_code >= 400:
                err = await resp.text()
                logger.warning("Paperclip issue creation failed: HTTP %s — %s", resp.status_code, err[:200])
                return self._fallback_result(f"Paperclip API error: HTTP {resp.status_code}")
            result = resp.json()
            issue_id = result.get("identifier") or result.get("id", "unknown")
            logger.info("Created diagnosis issue %s for lead %s", issue_id, lead_id)
            return {"diagnosis": f"Diagnosis requested in Paperclip issue {issue_id}", "is_traffic_issue": False, "is_sales_issue": False}

    def _fallback(self, user_data: dict, reason: str) -> dict:
        return {
            "lead_id": user_data.get("lead_id", ""),
            "cpl": user_data.get("cpl", 0),
            "manager_actions": user_data.get("manager_actions", []),
            "diagnosis": f"Paperclip LLM unavailable: {reason}",
            "is_traffic_issue": False,
            "is_sales_issue": False,
        }

    def _fallback_result(self, reason: str) -> dict:
        return {"diagnosis": reason, "is_traffic_issue": False, "is_sales_issue": False}
