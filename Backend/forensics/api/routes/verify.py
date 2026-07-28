"""
TrustAgent — Verify Route (Phase 4)

POST /api/v1/verify — endpoint chính của hệ thống.

Luồng xử lý:
    1. Nhận user_input từ request body
    2. Gọi TrustAgentWorkflow.run() → pipeline RAG → Z3
    3. Lưu kết quả vào audit_logs table
    4. Trả về VerifyResponse
"""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from forensics.agents.workflow import TrustAgentWorkflow
from forensics.api.dependencies import get_workflow, get_audit_repository
from forensics.api.schemas import VerifyRequest, VerifyResponse, ViolationDetail
from forensics.database.repository import AuditRepository

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/forensics", tags=["forensics-verify"])


@router.post(
    "/verify",
    response_model=VerifyResponse,
    status_code=status.HTTP_200_OK,
    summary="Kiểm chứng giao dịch tài chính",
    description=(
        "Nhận mô tả giao dịch bằng ngôn ngữ tự nhiên (tiếng Việt hoặc tiếng Anh), "
        "thực hiện kiểm chứng qua pipeline Neural → RAG → Z3, "
        "và trả về kết quả tuân thủ pháp luật."
    ),
)
async def verify_transaction(
    request: VerifyRequest,
    workflow: Annotated[TrustAgentWorkflow, Depends(get_workflow)],
    repo: Annotated[AuditRepository, Depends(get_audit_repository)],
) -> VerifyResponse:
    """
    POST /api/v1/verify

    Input:  {"user_input": "Thanh toán tiền mặt 25 triệu cho sự kiện"}
    Output: VerifyResponse với audit_id, z3_status, violations, explanation

    Pipeline:
        parse_node → legal_rag_node → verify_node → explain_node → audit trail
    """
    logger.info(f"[verify] Nhận request: '{request.user_input[:80]}...' "
                if len(request.user_input) > 80
                else f"[verify] Nhận request: '{request.user_input}'")

    try:
        # 1. Chạy workflow LangGraph (parse → RAG → Z3 → explain)
        result = workflow.run(request.user_input)

        # 2. Chuyển violations thành ViolationDetail objects
        violation_details: list[ViolationDetail] = []
        for v in result.violations:
            violation_details.append(ViolationDetail(
                rule_name=v.get("rule_name", ""),
                rule_description=v.get("rule_description", ""),
                severity=v.get("severity", "critical"),
                violation_detail=v.get("violation_detail", ""),
                legal_reference=v.get("legal_reference", ""),
            ))

        # 3. Lấy legal_thresholds từ workflow state (nếu có)
        legal_thresholds: dict = {}
        if hasattr(result, "legal_thresholds") and result.legal_thresholds:
            legal_thresholds = result.legal_thresholds

        # 4. Lưu audit trail vào database
        audit = await repo.save(
            user_input=request.user_input,
            scenario_type=result.scenario_type,
            legal_thresholds=legal_thresholds,
            z3_status=result.z3_status,
            is_compliant=result.is_compliant,
            violations=[v.model_dump() for v in violation_details],
            explanation=result.explanation,
            duration_ms=result.total_duration_ms,
        )

        logger.info(
            f"[verify] Hoàn thành: audit_id={audit.id[:8]}... "
            f"status={result.z3_status} compliant={result.is_compliant}"
        )

        return VerifyResponse(
            audit_id=audit.id,
            scenario_type=result.scenario_type or "unknown",
            z3_status=result.z3_status or "UNKNOWN",
            is_compliant=result.is_compliant if result.is_compliant is not None else False,
            violations=violation_details,
            legal_thresholds=legal_thresholds,
            explanation=result.explanation or "Không thể xử lý yêu cầu.",
            duration_ms=result.total_duration_ms or 0.0,
        )

    except Exception as e:
        logger.error(f"[verify] Lỗi không mong muốn: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Lỗi hệ thống khi xử lý: {str(e)}",
        )
