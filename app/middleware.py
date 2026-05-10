import os
from fastapi import Request, HTTPException
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

API_KEY = os.getenv("API_KEY", "dev-key-change-in-production")
PUBLIC_PATHS = {"/health", "/docs", "/openapi.json", "/redoc"}


class APIKeyMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if request.method == "OPTIONS":
            return await call_next(request)
        path = request.url.path.rstrip("/")
        if path in PUBLIC_PATHS or path.startswith("/docs") or path.startswith("/openapi.json") or path.startswith("/redoc"):
            return await call_next(request)
        api_key = request.headers.get("X-API-Key")
        if not api_key or api_key != API_KEY:
            return JSONResponse(status_code=403, content={"detail": "Invalid or missing X-API-Key"})
        return await call_next(request)
