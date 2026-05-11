import os
import pytest
from httpx import AsyncClient, ASGITransport

os.environ["API_KEY"] = "test-key"
os.environ["USE_MOCKS"] = "true"
os.environ["LLM_PROVIDER"] = "mock"

from app.main import app as fastapi_app


@pytest.mark.asyncio
async def test_health():
    transport = ASGITransport(app=fastapi_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/health")
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok"}


@pytest.mark.asyncio
async def test_analyze_no_api_key():
    transport = ASGITransport(app=fastapi_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/api/analyze", json={"campaign_names": ["*pravila*"]})
        assert resp.status_code == 403


@pytest.mark.asyncio
async def test_analyze_with_api_key():
    transport = ASGITransport(app=fastapi_app)
    os.environ["API_KEY"] = "test-key"
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/api/analyze",
            json={"campaign_names": ["*pravila*"], "sample_size": 2},
            headers={"X-API-Key": "test-key"},
        )
        assert resp.status_code == 202
        data = resp.json()
        assert "task_id" in data
        assert data["status"] == "processing"


@pytest.mark.asyncio
async def test_analyze_status():
    transport = ASGITransport(app=fastapi_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/api/analyze",
            json={"campaign_names": ["*pravila*"], "sample_size": 2},
            headers={"X-API-Key": "test-key"},
        )
        task_id = resp.json()["task_id"]

        resp = await client.get(f"/api/analyze/{task_id}", headers={"X-API-Key": "test-key"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["task_id"] == task_id
        assert data["status"] in ("processing", "completed")


@pytest.mark.asyncio
async def test_analyze_not_found():
    transport = ASGITransport(app=fastapi_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/analyze/nonexistent-task-id", headers={"X-API-Key": "test-key"})
        assert resp.status_code == 404
