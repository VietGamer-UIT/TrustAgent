"""
TrustAgent — B2B API Endpoint (Enterprise Integration)

Endpoint dành cho doanh nghiệp tích hợp.
AI Agent của doanh nghiệp chỉ cần gọi 1 endpoint duy nhất:

    POST /api/v1/audit
    Headers: X-API-Key: <trustagent_api_key>
    Body:    {"description": "Mô tả hành vi/giao dịch cần kiểm toán"}

Response trả về ngay lập tức, không cần cài thêm gì.
"""

from __future__ import annotations

import os
import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Header, status
from pydantic import BaseModel, Field

from forensics.agents.workflow import TrustAgentWorkflow

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["B2B-Enterprise"])

# ---------------------------------------------------------------------------
# Singleton workflow (khởi tạo 1 lần, tái dùng)
# ---------------------------------------------------------------------------
_workflow: TrustAgentWorkflow | None = None


def _get_workflow() -> TrustAgentWorkflow:
    global _workflow
    if _workflow is None:
        _workflow = TrustAgentWorkflow()
    return _workflow


# ---------------------------------------------------------------------------
# API Key Authentication (đơn giản, phù hợp giai đoạn Pilot)
# ---------------------------------------------------------------------------
def _verify_api_key(x_api_key: Annotated[str | None, Header()] = None) -> str:
    """
    Xác thực API Key từ header X-Api-Key.
    Set TRUSTAGENT_API_KEY trong .env để bật tính năng này.
    Nếu không set → bỏ qua xác thực (development mode).
    """
    expected_key = os.getenv("TRUSTAGENT_API_KEY", "").strip()
    if not expected_key:
        # Development mode — không cần API key
        return "dev"
    if not x_api_key or x_api_key.strip() != expected_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API key. Provide X-Api-Key header.",
        )
    return x_api_key


# ---------------------------------------------------------------------------
# Request / Response Schemas
# ---------------------------------------------------------------------------
class AuditRequest(BaseModel):
    """
    Request body để kiểm toán một hành vi/giao dịch.

    Ví dụ:
        {"description": "Thanh toán hợp đồng 500 triệu, mức phạt vi phạm 60 triệu"}
        {"description": "Hệ thống AI xử lý dữ liệu vân tay 2000 nhân viên chưa mã hóa"}
        {"description": "Phát hành trái phiếu doanh nghiệp, chưa công bố thông tin sau 5 ngày"}
    """

    description: str = Field(
        ...,
        min_length=5,
        max_length=2000,
        description="Mô tả hành vi doanh nghiệp bằng tiếng Việt",
        examples=[
            "Thanh toán hợp đồng dịch vụ tư vấn 200 triệu, mức phạt vi phạm 25 triệu.",
        ],
    )

    class Config:
        json_schema_extra = {
            "example": {
                "description": "Hợp đồng cung cấp dịch vụ phần mềm trị giá 500 triệu VNĐ. Điều khoản phạt vi phạm được ghi là 60 triệu VNĐ."
            }
        }


class ViolationItem(BaseModel):
    rule: str = Field(description="Tên quy tắc pháp lý bị vi phạm")
    detail: str = Field(description="Chi tiết vi phạm")
    severity: str = Field(description="critical | warning | info")
    legal_ref: str = Field(description="Điều khoản pháp lý căn cứ")


class AuditResult(BaseModel):
    """
    Kết quả kiểm toán pháp lý từ TrustAgent.

    Ý nghĩa các trường:
        is_compliant: True = hợp lệ, False = có vi phạm
        z3_status:    SAT = hợp lệ, UNSAT = vi phạm, UNKNOWN = không xác định
        scenario:     Lĩnh vực pháp lý đã phát hiện
        violations:   Danh sách vi phạm cụ thể (rỗng nếu hợp lệ)
        explanation:  Giải thích dễ đọc bằng tiếng Việt
        duration_ms:  Thời gian xử lý (ms)
    """

    is_compliant: bool
    z3_status: str
    scenario: str
    violations: list[ViolationItem]
    explanation: str
    duration_ms: float

    class Config:
        json_schema_extra = {
            "example": {
                "is_compliant": False,
                "z3_status": "UNSAT",
                "scenario": "vn_contract_penalty",
                "violations": [
                    {
                        "rule": "vn_contract_penalty_cap",
                        "detail": "Mức phạt 60 triệu vượt quá 8% giá trị hợp đồng (40 triệu).",
                        "severity": "critical",
                        "legal_ref": "Điều 301 Luật Thương mại 2005",
                    }
                ],
                "explanation": "❌ Phát hiện 1 vi phạm pháp lý...",
                "duration_ms": 12.5,
            }
        }


# ---------------------------------------------------------------------------
# Main B2B Endpoint
# ---------------------------------------------------------------------------
@router.post(
    "/audit",
    response_model=AuditResult,
    status_code=status.HTTP_200_OK,
    summary="[B2B] Kiểm toán pháp lý tự động",
    description=(
        "**Endpoint chính cho tích hợp doanh nghiệp (B2B).**\n\n"
        "Nhận mô tả hành vi/giao dịch → chạy pipeline Neural→RAG→Z3 → "
        "trả về kết quả kiểm toán pháp lý.\n\n"
        "**Xác thực:** Gửi header `X-Api-Key` với giá trị được cấp.\n\n"
        "**Lĩnh vực kiểm toán hỗ trợ:**\n"
        "- 📋 Bảo vệ dữ liệu cá nhân (NĐ 356/2025)\n"
        "- 📊 Trái phiếu doanh nghiệp (NĐ 200/2026)\n"
        "- 💰 Quản lý thuế (NĐ 252/2026)\n"
        "- 📝 Đăng ký thuế (TT 90/2026)\n"
        "- 🗄️ Luật Dữ liệu (NĐ 165/2025)\n"
    ),
)
async def audit_transaction(
    request: AuditRequest,
    _: Annotated[str, Depends(_verify_api_key)],
) -> AuditResult:
    """
    B2B Legal Audit Endpoint.

    AI Agent của doanh nghiệp gửi mô tả hành vi → TrustAgent kiểm toán →
    trả về kết quả SAT/UNSAT kèm chi tiết vi phạm (nếu có).
    """
    logger.info(f"[B2B /audit] Input: '{request.description[:80]}'")

    try:
        workflow = _get_workflow()
        result = workflow.run(request.description)

        # Chuyển violations sang schema đơn giản hơn cho B2B
        violation_items = []
        for v in result.violations:
            violation_items.append(
                ViolationItem(
                    rule=v.get("rule_name", v.get("rule", "unknown_rule")),
                    detail=v.get("violation_detail", v.get("description", "")),
                    severity=v.get("severity", "critical"),
                    legal_ref=v.get("legal_reference", v.get("legal_basis", "")),
                )
            )

        logger.info(
            f"[B2B /audit] Done: z3={result.z3_status}, "
            f"compliant={result.is_compliant}, "
            f"violations={len(violation_items)}, "
            f"time={result.total_duration_ms:.1f}ms"
        )

        return AuditResult(
            is_compliant=result.is_compliant,
            z3_status=result.z3_status or "UNKNOWN",
            scenario=result.scenario_type or "unknown",
            violations=violation_items,
            explanation=result.explanation or "Không xử lý được yêu cầu.",
            duration_ms=result.total_duration_ms or 0.0,
        )

    except Exception as e:
        logger.error(f"[B2B /audit] Lỗi: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Lỗi hệ thống khi kiểm toán: {str(e)}",
        )


# ---------------------------------------------------------------------------
# Health check riêng cho B2B
# ---------------------------------------------------------------------------
@router.get(
    "/audit/health",
    tags=["B2B-Enterprise"],
    summary="Kiểm tra trạng thái TrustAgent API",
)
async def audit_health():
    """Ping endpoint để doanh nghiệp kiểm tra kết nối."""
    return {
        "status": "ok",
        "service": "TrustAgent Legal Audit API",
        "version": "1.0.0",
        "supported_scenarios": [
            "Bảo vệ dữ liệu cá nhân (NĐ 356/2025)",
            "Trái phiếu doanh nghiệp (NĐ 200/2026)",
            "Quản lý thuế (NĐ 252/2026)",
            "Đăng ký thuế (TT 90/2026)",
            "Luật Dữ liệu (NĐ 165/2025)",
        ],
        "note": "Gửi POST /api/v1/audit với header X-Api-Key để kiểm toán.",
    }
