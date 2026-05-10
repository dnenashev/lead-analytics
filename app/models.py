from pydantic import BaseModel, field_validator
from typing import List, Optional
from uuid import uuid4


class AnalyzeRequest(BaseModel):
    campaign_names: List[str]
    sample_size: int = 10
    issue_id: Optional[str] = None


class AnalyzeResponse(BaseModel):
    task_id: str
    status: str = "processing"


class TaskStatusResponse(BaseModel):
    task_id: str
    status: str
    progress: Optional[str] = None
    results: Optional[List[dict]] = None


class HealthResponse(BaseModel):
    status: str = "ok"


class LeadAnalysisResult(BaseModel):
    lead_id: str
    cpl: float
    manager_actions: List[str]
    diagnosis: str
    is_traffic_issue: bool
    is_sales_issue: bool

    @field_validator("manager_actions")
    @classmethod
    def check_actions_not_empty_if_data_exists(cls, v):
        if not v:
            raise ValueError("manager_actions cannot be empty when CRM returned data")
        return v


def generate_task_id() -> str:
    return str(uuid4())
