import os
import logging

logger = logging.getLogger(__name__)

CPL_THRESHOLD_TRAFFIC = 20.0
CPL_THRESHOLD_HIGH = 40.0


class PaperclipLLMAdapter:
    def __init__(self, api_url: str = None, api_key: str = None):
        self.api_url = api_url or os.getenv("PAPERCLIP_API_URL", "")
        self.api_key = api_key or os.getenv("PAPERCLIP_API_KEY", "")

    async def analyze_lead(self, system_prompt: str, user_data: dict) -> dict:
        lead_id = user_data.get("lead_id", "unknown")
        cpl = user_data.get("cpl", 0)
        crm_status = user_data.get("crm_status", "unknown")
        source = user_data.get("source", "unknown")
        manager_actions = user_data.get("manager_actions", [])

        logger.info("Paperclip LLM adapter: analyzing lead %s (CPL=%.2f, status=%s)", lead_id, cpl, crm_status)

        result = self._heuristic_analyze(cpl, crm_status, manager_actions, source)
        return {
            "lead_id": lead_id,
            "cpl": cpl,
            "manager_actions": manager_actions,
            "diagnosis": result["diagnosis"],
            "is_traffic_issue": result["is_traffic_issue"],
            "is_sales_issue": result["is_sales_issue"],
        }

    def _heuristic_analyze(self, cpl: float, crm_status: str, manager_actions: list, source: str) -> dict:
        is_traffic_issue = False
        is_sales_issue = False
        diagnosis_parts = []

        if cpl >= CPL_THRESHOLD_TRAFFIC:
            is_traffic_issue = True
            if cpl >= CPL_THRESHOLD_HIGH:
                diagnosis_parts.append(f"High CPL (${cpl:.2f}) — possible targeting or audience issue")
            else:
                diagnosis_parts.append(f"Elevated CPL (${cpl:.2f}) — review campaign targeting")

        if crm_status in ("junk", "lose"):
            is_traffic_issue = True
            diagnosis_parts.append(f"Lead marked as {crm_status} — possible traffic quality problem")
        elif crm_status == "new":
            diagnosis_parts.append("Lead still in 'new' status — may need faster assignment")

        if not manager_actions:
            is_sales_issue = True
            diagnosis_parts.append("No manager actions — lead may not have been processed")
        else:
            calls = sum(1 for a in manager_actions if isinstance(a, dict) and a.get("type") == "call")
            emails = sum(1 for a in manager_actions if isinstance(a, dict) and a.get("type") == "email")
            if calls == 0 and emails == 0:
                is_sales_issue = True
                diagnosis_parts.append("No calls or emails by manager — possible sales processing gap")
            elif calls == 0:
                is_sales_issue = True
                diagnosis_parts.append("No call attempts — review sales outreach process")

        if not diagnosis_parts:
            diagnosis_parts.append("Lead appears healthy based on available data")

        return {
            "diagnosis": "; ".join(diagnosis_parts),
            "is_traffic_issue": is_traffic_issue,
            "is_sales_issue": is_sales_issue,
        }
