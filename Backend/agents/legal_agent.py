import logging
from datetime import datetime, timezone
from typing import Dict, Any

from core.state import TrustAgentState
from rag.retriever import get_legal_context
from z3_engine.solver import LegalSolver

logger = logging.getLogger("trustagent.agents.legal")
TEN_AGENT = "legal_agent"

async def legal_agent_node(state: TrustAgentState) -> dict:
    """
    LangGraph node: Pháp lý Agent (Legal Agent).
    Kết nối RAG để lấy ngữ cảnh pháp luật và Z3 Solver để chứng minh hợp lệ.
    """
    messages = list(state.get("messages", []))
    legal_violations = list(state.get("legal_violations", []))
    incident_id = state.get("incident_id", "UNKNOWN")
    
    # Lấy thông tin hợp đồng từ extracted_data
    extracted_data = state.get("extracted_data", {})
    contract_data = extracted_data.get("contract_data", {
        # Default mock if empty for demonstration
        "tong_gia_tri": 100000000,
        "phat_vi_pham": 9000000,  # 9% - will trigger UNSAT
        "thue_suat": 10
    })
    
    logger.info(f"[{TEN_AGENT}] Bắt đầu kiểm tra pháp lý cho phiên {incident_id}")
    
    # 1. RAG Retrieval
    query = "Quy định về mức phạt vi phạm hợp đồng thương mại và các mức thuế suất hợp lệ."
    legal_context = get_legal_context(query)
    logger.debug(f"[{TEN_AGENT}] Lấy ngữ cảnh RAG: {len(legal_context)} ký tự.")
    
    # 2. Z3 Solver Proof
    solver = LegalSolver()
    z3_status, violations = solver.check_compliance(contract_data, context_rules=legal_context)
    
    legal_violations.extend(violations)
    
    messages.append({
        "role": "assistant",
        "agent": TEN_AGENT,
        "content": (
            f"Kiểm tra pháp lý hoàn tất. Trạng thái Z3: {z3_status}. "
            f"Phát hiện {len(violations)} vi phạm pháp lý. "
            f"Ngữ cảnh tham chiếu từ RAG: {len(legal_context)} ký tự."
        ),
        "timestamp": datetime.now(tz=timezone.utc).isoformat(),
    })
    
    extracted_data_out = extracted_data.copy()
    extracted_data_out["legal_agent"] = z3_status
    
    return {
        "messages": messages,
        "z3_status": z3_status,
        "legal_violations": legal_violations,
        "extracted_data": extracted_data_out,
        "current_agent": "supervisor"
    }
