"""
TrustAgent — FastAPI Dependencies (Phase 4)

Dependency Injection cho FastAPI.
Mỗi request sẽ nhận workflow và db session qua DI.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from forensics.agents.workflow import TrustAgentWorkflow
from forensics.database.session import get_db
from forensics.database.repository import AuditRepository

# Singleton workflow — khởi tạo 1 lần, dùng lại xuyên request
_workflow: TrustAgentWorkflow | None = None


def get_workflow() -> TrustAgentWorkflow:
    """FastAPI dependency — trả về singleton TrustAgentWorkflow."""
    global _workflow
    if _workflow is None:
        _workflow = TrustAgentWorkflow()
    return _workflow


def get_audit_repository(db: AsyncSession = Depends(get_db)) -> AuditRepository:
    """FastAPI dependency — trả về AuditRepository với DB session."""
    return AuditRepository(db)
