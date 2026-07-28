"""
TrustAgent — API Pydantic Schemas (Phase 4)

Request/Response models cho FastAPI endpoints.
Tách biệt với ORM models (src/database/models.py) — đây là API contract.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


# ─────────────────────────────────────────────────────────────────────────────
# Request Models
# ─────────────────────────────────────────────────────────────────────────────

class VerifyRequest(BaseModel):
    """Request body cho POST /api/v1/verify"""

    user_input: str = Field(
        ...,
        min_length=3,
        max_length=2000,
        description="Câu mô tả giao dịch bằng tiếng Việt hoặc tiếng Anh",
        examples=["Thanh toán tiền mặt 25 triệu cho sự kiện"],
    )


# ─────────────────────────────────────────────────────────────────────────────
# Response Models
# ─────────────────────────────────────────────────────────────────────────────

class ViolationDetail(BaseModel):
    """Chi tiết một vi phạm pháp lý."""

    rule_name: str = Field(description="Tên rule bị vi phạm")
    rule_description: str = Field(description="Mô tả rule")
    severity: str = Field(description="critical | warning | info")
    violation_detail: str = Field(description="Giải thích vi phạm cụ thể")
    legal_reference: str = Field(description="Văn bản pháp lý căn cứ")


class VerifyResponse(BaseModel):
    """Response cho POST /api/v1/verify"""

    audit_id: str = Field(description="UUID của audit record — dùng để tra cứu lại")
    scenario_type: str = Field(description="vn_payment | kr_tax_refund | unknown")
    z3_status: str = Field(description="SAT (hợp lệ) | UNSAT (vi phạm) | UNKNOWN")
    is_compliant: bool = Field(description="True nếu giao dịch tuân thủ pháp luật")
    violations: list[ViolationDetail] = Field(
        default_factory=list,
        description="Danh sách các vi phạm (rỗng nếu SAT)",
    )
    legal_thresholds: dict[str, Any] = Field(
        default_factory=dict,
        description="Ngưỡng pháp lý đã dùng từ Legal RAG",
    )
    explanation: str = Field(description="Giải thích thân thiện bằng tiếng Việt")
    duration_ms: float = Field(description="Tổng thời gian xử lý (ms)")

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "audit_id": "550e8400-e29b-41d4-a716-446655440000",
                    "scenario_type": "vn_payment",
                    "z3_status": "UNSAT",
                    "is_compliant": False,
                    "violations": [
                        {
                            "rule_name": "vn_cash_payment_threshold",
                            "rule_description": "Thông tư 96/2015/TT-BTC",
                            "severity": "critical",
                            "violation_detail": "Số tiền 25,000,000 VNĐ ≥ ngưỡng 20,000,000 VNĐ...",
                            "legal_reference": "Thông tư 96/2015/TT-BTC, Điều 4, Khoản 1, Điểm c",
                        }
                    ],
                    "legal_thresholds": {"VN_CASH_THRESHOLD": 20000000},
                    "explanation": "❌ Giao dịch bị từ chối...",
                    "duration_ms": 5.2,
                }
            ]
        }
    }


class AuditResponse(BaseModel):
    """Response cho GET /api/v1/audit/{id} và GET /api/v1/audit"""

    id: str
    created_at: datetime
    user_input: str
    scenario_type: str | None
    legal_thresholds: dict[str, Any] | None
    z3_status: str | None
    is_compliant: bool | None
    violations: list[dict[str, Any]]
    explanation: str | None
    duration_ms: float | None

    model_config = {"from_attributes": True}


class AuditListResponse(BaseModel):
    """Response cho GET /api/v1/audit (danh sách)"""

    items: list[AuditResponse]
    total: int
    limit: int
    offset: int


class HealthResponse(BaseModel):
    """Response cho GET /health"""

    status: str = "ok"
    version: str = "0.4.0"
    tests_passing: int = 111
