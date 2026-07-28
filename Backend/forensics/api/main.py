"""
TrustAgent — Forensics standalone app (dev only).

Production: dùng Backend/main.py (đã mount routes Forensics).

    cd Backend
    uvicorn forensics.api.main:app --reload --port 8001
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from collections.abc import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from forensics.api.routes import verify, audit
from forensics.api.schemas import HealthResponse
from forensics.database.session import create_tables, dispose_engine
from forensics.config import get_settings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    settings = get_settings()
    logger.info(
        "[startup] Forensics standalone API (env=%s) — "
        "ưu tiên dùng TrustAgent main:app trong production",
        settings.app_env,
    )
    await create_tables()
    yield
    await dispose_engine()


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="TrustAgent (Forensics module)",
        description="Module Forensics của TrustAgent. Production dùng main:app.",
        version="0.4.0",
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"] if settings.app_env == "development" else [],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(verify.router)
    app.include_router(audit.router)

    @app.get("/", include_in_schema=False)
    async def root() -> JSONResponse:
        return JSONResponse({
            "name": "TrustAgent",
            "module": "forensics",
            "endpoints": {
                "verify": "POST /api/v1/forensics/verify",
                "audit_list": "GET /api/v1/forensics/audit",
                "audit_detail": "GET /api/v1/forensics/audit/{id}",
            },
        })

    @app.get("/health", response_model=HealthResponse, tags=["system"])
    async def health() -> HealthResponse:
        return HealthResponse()

    return app


app = create_app()
