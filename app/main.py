import os
import uuid
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, BackgroundTasks, Request
from fastapi.responses import JSONResponse
from app.models import (
    AnalyzeRequest,
    AnalyzeResponse,
    TaskStatusResponse,
    HealthResponse,
    generate_task_id,
)
from app.middleware import APIKeyMiddleware
from app.analysis import analyze_cohort, _task_store
from app.redis_store import set_task, get_task
from app.logging_config import setup_logging

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

logger = setup_logging()


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("lead-analytics service starting")

    env_vars = {
        "API_KEY": bool(os.getenv("API_KEY")),
        "PAPERCLIP_API_URL": bool(os.getenv("PAPERCLIP_API_URL")),
        "PAPERCLIP_API_KEY": bool(os.getenv("PAPERCLIP_API_KEY")),
        "PAPERCLIP_SERVICE_TOKEN": bool(os.getenv("PAPERCLIP_SERVICE_TOKEN")),
        "BITRIX24_WEBHOOK_URL": bool(os.getenv("BITRIX24_WEBHOOK_URL")),
        "AMOCRM_WEBHOOK_URL": bool(os.getenv("AMOCRM_WEBHOOK_URL")),
        "YANDEX_DIRECT_TOKEN": bool(os.getenv("YANDEX_DIRECT_TOKEN")),
        "VK_ADS_TOKEN": bool(os.getenv("VK_ADS_TOKEN")),
        "USE_MOCKS": os.getenv("USE_MOCKS", "not set"),
        "LLM_PROVIDER": os.getenv("LLM_PROVIDER", "not set"),
        "GEMINI_API_KEY": bool(os.getenv("GEMINI_API_KEY")),
        "DEEPSEEK_API_KEY": bool(os.getenv("DEEPSEEK_API_KEY")),
    }
    logger.info("Startup env check: %s", env_vars)

    yield
    logger.info("lead-analytics service shutting down")


app = FastAPI(
    title="Lead Analytics Service",
    description="Microservice for deep lead cohort analysis",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(APIKeyMiddleware)


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error("Unhandled exception", extra={"path": str(request.url)}, exc_info=True)
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})


@app.get("/health", response_model=HealthResponse)
async def health():
    return {"status": "ok"}


@app.post("/api/analyze", response_model=AnalyzeResponse, status_code=202)
async def start_analysis(req: AnalyzeRequest, background_tasks: BackgroundTasks):
    task_id = generate_task_id()
    await set_task(task_id, {"status": "processing", "progress": "0/0 leads", "results": None})
    _task_store[task_id] = {"status": "processing", "progress": "0/0 leads", "results": None}

    background_tasks.add_task(
        analyze_cohort,
        campaign_names=req.campaign_names,
        sample_size=req.sample_size,
        issue_id=req.issue_id,
        task_id=task_id,
    )

    logger.info(
        "Analysis started",
        extra={
            "task_id": task_id,
            "campaigns": req.campaign_names,
            "sample_size": req.sample_size,
        },
    )
    return {"task_id": task_id, "status": "processing"}


@app.get("/api/analyze/{task_id}", response_model=TaskStatusResponse)
async def get_analysis_status(task_id: str):
    task = await get_task(task_id) or _task_store.get(task_id)
    if not task:
        return JSONResponse(status_code=404, content={"detail": "Task not found"})
    return {
        "task_id": task_id,
        "status": task["status"],
        "progress": task.get("progress"),
        "results": task.get("results"),
    }
