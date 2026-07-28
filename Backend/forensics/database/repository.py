"""
TrustAgent — Database Repository (Phase 4)

CRUD operations cho AuditLog.
Quy tắc: Chỉ INSERT và SELECT — KHÔNG UPDATE, KHÔNG DELETE.
Đây là "bất biến" của Forensics Layer.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from forensics.database.models import AuditLog

logger = logging.getLogger(__name__)


class AuditRepository:
    """
    Repository pattern cho AuditLog.

    Dùng trong FastAPI dependency injection:
        repo = AuditRepository(db_session)
        audit = await repo.save(...)
        record = await repo.get_by_id(audit_id)
    """

    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def save(
        self,
        user_input: str,
        scenario_type: str | None,
        legal_thresholds: dict[str, Any] | None,
        z3_status: str | None,
        is_compliant: bool | None,
        violations: list[dict] | None,
        explanation: str | None,
        duration_ms: float | None,
    ) -> AuditLog:
        """
        Lưu một lần kiểm tra vào audit trail.

        Args:
            user_input:       Câu nhập gốc của người dùng
            scenario_type:    "vn_payment" | "kr_tax_refund" | "unknown"
            legal_thresholds: {"VN_CASH_THRESHOLD": 20000000}
            z3_status:        "SAT" | "UNSAT" | "UNKNOWN"
            is_compliant:     True / False / None
            violations:       Danh sách vi phạm
            explanation:      Giải thích thân thiện
            duration_ms:      Tổng thời gian xử lý

        Returns:
            AuditLog instance đã được commit
        """
        audit = AuditLog(
            id=str(uuid.uuid4()),
            user_input=user_input,
            scenario_type=scenario_type,
            legal_thresholds=legal_thresholds,
            z3_status=z3_status,
            is_compliant=is_compliant,
            violations=violations or [],
            explanation=explanation,
            duration_ms=duration_ms,
        )
        self._db.add(audit)
        await self._db.flush()   # flush để lấy ID ngay, commit sẽ do session.commit()
        logger.info(f"[DB] Đã lưu audit: id={audit.id[:8]}... status={z3_status}")
        return audit

    async def get_by_id(self, audit_id: str) -> AuditLog | None:
        """
        Lấy một audit record theo ID.

        Args:
            audit_id: UUID string của audit record

        Returns:
            AuditLog hoặc None nếu không tìm thấy
        """
        stmt = select(AuditLog).where(AuditLog.id == audit_id)
        result = await self._db.execute(stmt)
        return result.scalar_one_or_none()

    async def list_recent(
        self,
        limit: int = 20,
        offset: int = 0,
        scenario_type: str | None = None,
        is_compliant: bool | None = None,
    ) -> list[AuditLog]:
        """
        Lấy danh sách audit records, sắp xếp mới nhất trước.

        Args:
            limit:         Số records tối đa trả về (max 100)
            offset:        Bỏ qua N records đầu (phân trang)
            scenario_type: Lọc theo scenario (optional)
            is_compliant:  Lọc theo compliance status (optional)

        Returns:
            List AuditLog
        """
        limit = min(limit, 100)   # Hard cap để tránh query quá lớn
        stmt = select(AuditLog).order_by(desc(AuditLog.created_at))

        if scenario_type is not None:
            stmt = stmt.where(AuditLog.scenario_type == scenario_type)
        if is_compliant is not None:
            stmt = stmt.where(AuditLog.is_compliant == is_compliant)

        stmt = stmt.limit(limit).offset(offset)
        result = await self._db.execute(stmt)
        return list(result.scalars().all())

    async def count_total(self) -> int:
        """Đếm tổng số audit records."""
        from sqlalchemy import func
        stmt = select(func.count()).select_from(AuditLog)
        result = await self._db.execute(stmt)
        return result.scalar_one()
