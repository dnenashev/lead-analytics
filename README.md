# Lead Analytics Service

Microservice for deep cohort analysis of leads — integrates Paperclip + FastAPI + LangSmith.

## Stack

- **Backend:** Python 3.12, FastAPI, Pydantic v2
- **LLM:** Gemini / DeepSeek via langchain-core
- **CRM:** Bitrix24 (rate-limited, paginated)
- **Ad Platforms:** Yandex.Direct, VK Ads
- **Observability:** LangSmith tracing, JSON structured logs
- **Auth:** X-API-Key header
- **Infrastructure:** Docker, docker-compose

## Quick Start

```bash
cp .env.example .env
# Edit .env with your API keys
docker compose up -d
```

## API

- `GET /health` — health check (no auth)
- `POST /api/analyze` — start cohort analysis (X-API-Key required)
  ```json
  {
    "campaign_names": ["*pravila*", "*form_dod*"],
    "sample_size": 10,
    "issue_id": "DMI-XXXX"
  }
  ```
- `GET /api/analyze/{task_id}` — polling status + results

## Test

```bash
pip install -r requirements.txt
pytest tests/ -v
```

## Architecture

See [DMI-1867](https://paperclip-production-04e9.up.railway.app/issues/DMI-1867) for full spec.
