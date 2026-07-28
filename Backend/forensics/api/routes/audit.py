"""
TrustAgent — Audit Route (Phase 4)

GET /api/v1/audit/{id}  — xem chi tiết một lần kiểm tra
GET /api/v1/audit       — danh sách lịch sử (paginated)

Đây là "Forensics Layer" — mọi record là bất biến, chỉ đọc.
"""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status

from forensics.api.dependencies import get_audit_repository
from forensics.api.schemas import AuditResponse, AuditListResponse
from forensics.database.repository import AuditRepository

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/forensics", tags=["forensics-audit"])


@router.get(
    "/audit/{audit_id}",
    response_model=AuditResponse,
    summary="Xem chi tiết một lần kiểm tra",
    description="Lấy toàn bộ thông tin của một audit record theo UUID.",
)
async def get_audit(
    audit_id: str,
    repo: Annotated[AuditRepository, Depends(get_audit_repository)],
) -> AuditResponse:
    """
    GET /api/v1/audit/{audit_id}

    Returns: AuditResponse với đầy đủ thông tin kiểm tra
    Raises: 404 nếu không tìm thấy audit_id
    """
    audit = await repo.get_by_id(audit_id)
    if audit is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Audit record '{audit_id}' không tìm thấy.",
        )
    return AuditResponse(
        id=audit.id,
        created_at=audit.created_at,
        user_input=audit.user_input,
        scenario_type=audit.scenario_type,
        legal_thresholds=audit.legal_thresholds,
        z3_status=audit.z3_status,
        is_compliant=audit.is_compliant,
        violations=audit.violations or [],
        explanation=audit.explanation,
        duration_ms=audit.duration_ms,
    )


@router.get(
    "/audit",
    response_model=AuditListResponse,
    summary="Danh sách lịch sử kiểm tra",
    description="Lấy danh sách các audit records gần nhất, có thể lọc theo scenario và kết quả.",
)
async def list_audits(
    repo: Annotated[AuditRepository, Depends(get_audit_repository)],
    limit: int = Query(default=20, ge=1, le=100, description="Số records tối đa (1-100)"),
    offset: int = Query(default=0, ge=0, description="Bỏ qua N records đầu"),
    scenario_type: str | None = Query(default=None, description="Lọc: vn_payment | kr_tax_refund"),
    is_compliant: bool | None = Query(default=None, description="Lọc: true=hợp lệ, false=vi phạm"),
) -> AuditListResponse:
    """
    GET /api/v1/audit?limit=20&offset=0&scenario_type=vn_payment&is_compliant=false

    Returns: Paginated list of AuditResponse
    """
    records = await repo.list_recent(
        limit=limit,
        offset=offset,
        scenario_type=scenario_type,
        is_compliant=is_compliant,
    )
    total = await repo.count_total()

    items = [
        AuditResponse(
            id=r.id,
            created_at=r.created_at,
            user_input=r.user_input,
            scenario_type=r.scenario_type,
            legal_thresholds=r.legal_thresholds,
            z3_status=r.z3_status,
            is_compliant=r.is_compliant,
            violations=r.violations or [],
            explanation=r.explanation,
            duration_ms=r.duration_ms,
        )
        for r in records
    ]

    return AuditListResponse(items=items, total=total, limit=limit, offset=offset)
