import logging
import asyncio
from datetime import datetime, timezone
from typing import Any

from .state import TrustAgentState
from database.models import AsyncSessionLocal, AuditEvent

logger = logging.getLogger("trustagent.core.supervisor")

MAX_ITERATIONS: int = 15

async def supervisor_node(state: TrustAgentState) -> TrustAgentState:
    """
    LangGraph node: Giám Sát / Bộ Điều Phối Trung Tâm (Unified).
    """
    incident_id = state.get("incident_id", "UNKNOWN")
    iteration_count = state.get("iteration_count", 0) + 1
    scenario = state.get("scenario_type", "full_audit")
    
    logger.info(f"[Giám Sát] Vòng #{iteration_count} cho phiên={incident_id} (Scenario: {scenario})")

    messages = list(state.get("messages", []))
    messages.append({
        "role": "system",
        "agent": "supervisor",
        "content": f"Giám Sát vòng #{iteration_count} — đánh giá bước tiếp theo.",
        "timestamp": datetime.now(tz=timezone.utc).isoformat(),
    })

    if iteration_count >= MAX_ITERATIONS:
        logger.warning(f"[Giám Sát] Hết giới hạn vòng lặp cho phiên={incident_id}")
        return {
            "messages": messages,
            "iteration_count": iteration_count,
            "current_agent": "XONG",
            "final_audit_log": {"status": "partial_timeout", "iterations": iteration_count}
        }

    agent_tiep = _quyet_dinh_agent_tiep(state, scenario)

    if agent_tiep is None:
        logger.info("[Giám Sát] Tất cả agent hoàn tất — tổng hợp báo cáo.")
        final_log = _tao_bao_cao_tong_hop(state)
        
        # User requested to NOT save to real database yet
        # async def _save_to_db(...) has been removed

        return {
            "messages": messages,
            "iteration_count": iteration_count,
            "current_agent": "XONG",
            "final_audit_log": final_log
        }

    logger.info(f"[Giám Sát] Điều phối tới: {agent_tiep}")
    return {
        "messages": messages,
        "iteration_count": iteration_count,
        "current_agent": agent_tiep,
    }


def _quyet_dinh_agent_tiep(state: TrustAgentState, scenario: str) -> str | None:
    extracted_data = state.get("extracted_data", {})
    
    doc_xong = "document_agent" in extracted_data
    tax_xong = "tax_compliance_agent" in extracted_data
    legal_xong = "legal_agent" in extracted_data

    if scenario in ["tax_audit", "full_audit"]:
        if not doc_xong:
            return "document_agent"
        if not tax_xong:
            return "tax_compliance_agent"

    if scenario in ["legal_verify", "full_audit"]:
        if not legal_xong:
            return "legal_agent"

    return None

def _tao_bao_cao_tong_hop(state: TrustAgentState) -> dict[str, Any]:
    return {
        "incident_id": state.get("incident_id"),
        "tax_warnings": state.get("tax_warnings", []),
        "legal_violations": state.get("legal_violations", []),
        "z3_status": state.get("z3_status"),
        "completed_at": datetime.now(tz=timezone.utc).isoformat(),
    }
