"""
TrustAgent — mount API routes cho module Forensics.
"""

from __future__ import annotations

from fastapi import FastAPI

from forensics.api.routes import verify, audit


def mount_forensics_routes(app: FastAPI) -> None:
    """Đăng ký Forensics routes dưới /api/v1/forensics/*."""
    app.include_router(verify.router)
    app.include_router(audit.router)
