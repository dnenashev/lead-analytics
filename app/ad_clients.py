import os
from typing import Optional
from abc import ABC, abstractmethod
import httpx

YANDEX_DIRECT_TOKEN = os.getenv("YANDEX_DIRECT_TOKEN", "")
YANDEX_DIRECT_LOGIN = os.getenv("YANDEX_DIRECT_LOGIN", "")
VK_ADS_TOKEN = os.getenv("VK_ADS_TOKEN", "")
VK_ADS_ACCOUNT_ID = os.getenv("VK_ADS_ACCOUNT_ID", "")


class AdPlatformClient(ABC):
    @abstractmethod
    async def get_campaign_cpl(self, campaign_name: str) -> Optional[float]:
        ...


class YandexDirectClient(AdPlatformClient):
    def __init__(self, token: str = None, login: str = None):
        self.token = token or YANDEX_DIRECT_TOKEN
        self.login = login or YANDEX_DIRECT_LOGIN

    async def get_campaign_cpl(self, campaign_name: str) -> Optional[float]:
        if not self.token:
            return None
        url = "https://api.direct.yandex.com/json/v5/campaigns"
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Client-Login": self.login,
            "Accept-Language": "ru",
        }
        payload = {
            "method": "get",
            "params": {
                "SelectionCriteria": {},
                "FieldNames": ["Id", "Name", "CostPerLead"],
            },
        }
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.post(url, json=payload, headers=headers)
                resp.raise_for_status()
                data = resp.json()
                for campaign in data.get("result", {}).get("Campaigns", []):
                    if campaign_name in campaign.get("Name", ""):
                        return campaign.get("CostPerLead", {}).get("Amount", None)
        except Exception:
            pass
        return None


class VKAdsClient(AdPlatformClient):
    def __init__(self, token: str = None, account_id: str = None):
        self.token = token or VK_ADS_TOKEN
        self.account_id = account_id or VK_ADS_ACCOUNT_ID

    async def get_campaign_cpl(self, campaign_name: str) -> Optional[float]:
        if not self.token:
            return None
        url = "https://api.vk.com/method/ads.getCampaigns"
        params = {
            "access_token": self.token,
            "v": "5.131",
            "account_id": self.account_id,
        }
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.get(url, params=params)
                resp.raise_for_status()
                data = resp.json()
                for campaign in data.get("response", []):
                    if campaign_name in campaign.get("name", ""):
                        return campaign.get("cpl", None)
        except Exception:
            pass
        return None


def get_ad_client(campaign_name: str) -> AdPlatformClient:
    if "vk" in campaign_name.lower() or "vkontakte" in campaign_name.lower():
        return VKAdsClient()
    return YandexDirectClient()
