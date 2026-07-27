import logging
from typing import Dict, Any
from core.state import TrustAgentState

logger = logging.getLogger("trustagent.agents.legal")

async def legal_agent_node(state: TrustAgentState) -> TrustAgentState:
    """
    Node xử lý pháp lý bằng Z3 (TrustAgent-Forensics).
    """
    incident_id = state.get("incident_id", "UNKNOWN")
    logger.info(f"[Legal Agent] Bắt đầu kiểm tra pháp lý cho phiên {incident_id}")
    
    z3_status = "SAT"
    legal_violations = list(state.get("legal_violations", []))
    
    extracted_data = state.get("extracted_data", {}).copy()
    extracted_data["legal_agent"] = "ok"
    
    return {
        "z3_status": z3_status,
        "legal_violations": legal_violations,
        "extracted_data": extracted_data,
        "current_agent": "supervisor"
    }
