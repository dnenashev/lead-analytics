from typing import List, Optional
import random


async def mock_get_crm_meta(lead_id: str) -> dict:
    return {
        "id": lead_id,
        "crm_status": random.choice(["new", "in_work", "negotiation", "closed"]),
        "source": random.choice(["form", "call", "email", "site"]),
        "created_at": "2026-05-10T12:00:00Z",
    }


async def mock_get_manager_actions(lead_id: str) -> List[str]:
    actions = [
        "call: 2026-05-09 10:00 - no answer",
        "call: 2026-05-09 14:00 - talked, interested",
        "email: 2026-05-10 09:00 - sent presentation",
        "stage_change: new -> in_work at 2026-05-09",
    ]
    n = random.randint(0, len(actions))
    return actions[:n] if n > 0 else []


async def mock_get_campaign_cpl(campaign_name: str) -> Optional[float]:
    cpl_map = {
        "*pravila*": 450.0,
        "*form_dod*": 320.0,
        "*traffic*": 280.0,
        "*retarget*": 190.0,
    }
    return cpl_map.get(campaign_name, random.uniform(150, 500))


async def mock_get_platform(campaign_name: str) -> str:
    if "vk" in campaign_name.lower() or "vkontakte" in campaign_name.lower():
        return "vk"
    return "yandex"
