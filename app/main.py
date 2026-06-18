#!/usr/bin/env python3
"""FastAPI application entrypoint for GPT2API_IIAP."""

from __future__ import annotations

from contextlib import asynccontextmanager

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles

from app.api_admin import router as admin_router
from app.api_public import router as public_router
from app.config import settings
from app.queue_manager import QueueManager
from app.service import AppService
from storage.control import ControlDb
from upstream.chatgpt import ChatgptUpstreamClient


@asynccontextmanager
async def lifespan(app: FastAPI):
    storage_dir = settings.storage_dir
    storage_dir.mkdir(parents=True, exist_ok=True)
    control_db = ControlDb(storage_dir / "control.db")
    upstream = ChatgptUpstreamClient(
        base_url=settings.chatgpt_base_url,
        proxy_url=settings.upstream_proxy,
    )
    service = AppService(
        storage=control_db,
        admin_token=settings.admin_token,
        upstream=upstream,
    )
    # Auto-import account from .env if present
    if settings.openai_access_token:
        service.import_accounts([("token", settings.openai_access_token)])
    # Refresh metadata for all accounts
    await service.refresh_accounts()
    # Start global generation queue
    queue = QueueManager(service, workers=8)
    await queue.start()
    app.state.service = service
    app.state.queue = queue
    yield
    await queue.stop()
    # teardown if needed


app = FastAPI(title="GPT2API_IIAP", version="0.1.0", lifespan=lifespan)
app.include_router(public_router)
app.include_router(admin_router)

# Serve React frontend static files under /ui
frontend_dir = Path(__file__).parent.parent / "frontend"
if frontend_dir.exists():
    app.mount("/ui", StaticFiles(directory=str(frontend_dir), html=True), name="frontend")

    @app.get("/")
    async def root():
        return RedirectResponse(url="/ui/")

    @app.get("/favicon.ico", include_in_schema=False)
    async def favicon():
        return Response(status_code=204)

    @app.get("/panel")
    async def admin_page():
        return FileResponse(str(frontend_dir / "admin.html"))


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host=settings.host,
        port=settings.port,
        reload=False,
    )
