"""
TrustAgent — Database Layer (Phase 4)

SQLAlchemy ORM models cho audit trail bất biến.

Thiết kế:
- SQLite trong dev/test (aiosqlite driver, zero config)
- PostgreSQL 17 trong production (asyncpg driver, chỉ đổi DATABASE_URL)
- JSON type được dùng thay JSONB để tương thích SQLite
- Mọi record là IMMUTABLE sau khi tạo — không có UPDATE/DELETE
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import (
    String,
    Boolean,
    Float,
    Text,
    DateTime,
    JSON,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def _utcnow() -> datetime:
    """Trả về UTC timestamp hiện tại (timezone-aware)."""
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    """SQLAlchemy declarative base class."""
    pass


class AuditLog(Base):
    """
    Bảng lưu toàn bộ lịch sử kiểm chứng giao dịch.

    Mỗi record = 1 lần gọi POST /api/v1/verify
    Records là IMMUTABLE — chỉ INSERT, không UPDATE/DELETE.
    Đây là "Forensics Layer" trong kiến trúc TrustAgent.

    Columns:
        id              UUID primary key (unique audit trail ID)
        created_at      Thời điểm kiểm tra (UTC)
        user_input      Câu nhập của người dùng (bằng chứng gốc)
        scenario_type   vn_payment | kr_tax_refund | unknown
        legal_thresholds JSON: ngưỡng pháp lý từ RAG
        z3_status       SAT | UNSAT | UNKNOWN
        is_compliant    True = hợp lệ, False = vi phạm
        violations      JSON: danh sách vi phạm
        explanation     Giải thích thân thiện cho người dùng
        duration_ms     Tổng thời gian xử lý (ms)
    """

    __tablename__ = "audit_logs"

    # Primary key — UUID string (tương thích cả SQLite và PostgreSQL)
    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )

    # Thời điểm kiểm tra
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=_utcnow,
        nullable=False,
        index=True,
    )

    # ── Input ──────────────────────────────────────────────────────────────
    user_input: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="Câu nhập gốc của người dùng — bất biến",
    )

    # ── Parse result ───────────────────────────────────────────────────────
    scenario_type: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
        index=True,
        comment="vn_payment | kr_tax_refund | unknown",
    )

    # ── RAG thresholds ─────────────────────────────────────────────────────
    legal_thresholds: Mapped[dict | None] = mapped_column(
        JSON,
        nullable=True,
        comment='Ngưỡng từ RAG: {"VN_CASH_THRESHOLD": 20000000}',
    )

    # ── Z3 verification result ─────────────────────────────────────────────
    z3_status: Mapped[str | None] = mapped_column(
        String(20),
        nullable=True,
        index=True,
        comment="SAT | UNSAT | UNKNOWN",
    )

    is_compliant: Mapped[bool | None] = mapped_column(
        Boolean,
        nullable=True,
        index=True,
        comment="True = giao dịch hợp lệ",
    )

    violations: Mapped[list | None] = mapped_column(
        JSON,
        nullable=True,
        comment="Danh sách vi phạm [{rule_name, violation_detail, ...}]",
    )

    # ── Response ───────────────────────────────────────────────────────────
    explanation: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Giải thích thân thiện cho người dùng",
    )

    duration_ms: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
        comment="Tổng thời gian xử lý (milliseconds)",
    )

    def to_dict(self) -> dict[str, Any]:
        """Chuyển record thành dict để serialize JSON."""
        return {
            "id": self.id,
            "created_at": (self.created_at.isoformat() + "Z").replace("+00:00Z", "Z") if self.created_at else None,
            "user_input": self.user_input,
            "scenario_type": self.scenario_type,
            "legal_thresholds": self.legal_thresholds,
            "z3_status": self.z3_status,
            "is_compliant": self.is_compliant,
            "violations": self.violations or [],
            "explanation": self.explanation,
            "duration_ms": self.duration_ms,
        }

    def __repr__(self) -> str:
        return (
            f"<AuditLog id={self.id[:8]}... "
            f"status={self.z3_status} "
            f"compliant={self.is_compliant}>"
        )
