import logging
from typing import Dict, Any, Literal
from langgraph.graph import StateGraph, START, END

from core.state import TrustAgentState
from agents.document_agent import chung_tu_agent_node
from agents.tax_compliance_agent import tuan_thu_agent_node
from agents.legal_agent import legal_agent_node

# Bỏ import PostgreSQL
# from database.models import AuditEvent, AsyncSessionLocal

logger = logging.getLogger("trustagent.core.graph_builder")

def supervisor_router(state: TrustAgentState) -> Literal["document_agent", "tax_compliance_agent", "legal_agent", "compiler_node"]:
    """
    Điều hướng luồng xử lý:
    1. START -> supervisor -> Nếu có file (evidence_paths có data và chưa extract qua document_agent) -> document_agent.
    2. Từ document_agent -> tax_compliance_agent.
    3. Từ tax_compliance_agent -> legal_agent.
    4. Nếu ko có file, chỉ có hợp đồng -> legal_agent.
    5. Cuối cùng -> compiler_node (hoặc END)
    """
    evidence_paths = state.get("evidence_paths", [])
    extracted = state.get("extracted_data", {})
    
    # 1. Nếu có file hóa đơn/bảng kê mà chưa được document_agent xử lý
    if evidence_paths and "document_agent" not in extracted:
        return "document_agent"
        
    # 2. Nếu đã qua document_agent nhưng chưa qua tax_compliance_agent
    if "document_agent" in extracted and "tax_compliance_agent" not in extracted:
        return "tax_compliance_agent"
        
    # 3. Đã qua tax (nếu có) hoặc không có file (tức là chỉ có hợp đồng)
    if "legal_agent" not in extracted:
        return "legal_agent"
        
    # 4. Khi đã qua hết các agent cần thiết
    return "compiler_node"

import json
import os
import datetime

async def compiler_node(state: TrustAgentState) -> Dict[str, Any]:
    """Node cuối tổng hợp kết quả (final_audit_log) và lưu DB."""
    logger.info("[Compiler] Tổng hợp báo cáo kiểm toán cuối cùng.")
    
    # Xây dựng mảng audit_trail_steps cho giao diện Forensic
    audit_trail_steps = []
    
    extracted_data = state.get("extracted_data", {})
    if "document_agent" in extracted_data:
        audit_trail_steps.append({
            "step": "Document Parsing (OCR)",
            "status": "PASS",
            "details": f"Trích xuất thành công {len(state.get('hoa_don_list', []))} chứng từ."
        })
    if "tax_compliance_agent" in extracted_data:
        tax_warnings = state.get("tax_warnings", [])
        audit_trail_steps.append({
            "step": "Tax Compliance Check",
            "status": "WARNING" if tax_warnings else "PASS",
            "details": f"Phát hiện {len(tax_warnings)} cảnh báo thuế."
        })
    if "legal_agent" in extracted_data:
        z3_status = state.get("z3_status", "UNKNOWN")
        legal_violations = state.get("legal_violations", [])
        audit_trail_steps.append({
            "step": "Legal Z3 Validation",
            "status": "FAIL" if z3_status == "UNSAT" else "PASS",
            "details": f"Z3 Trạng thái: {z3_status}. Vi phạm: {len(legal_violations)}."
        })

    audit_log = {
        "incident_id": state.get("incident_id"),
        "status": "COMPLETED",
        "tong_hoa_don": len(state.get("hoa_don_list", [])),
        "tong_loi_thue": len(state.get("tax_warnings", [])),
        "z3_status": state.get("z3_status", "UNKNOWN"),
        "tong_loi_phap_ly": len(state.get("legal_violations", [])),
        "tax_warnings": state.get("tax_warnings", []),
        "legal_violations": state.get("legal_violations", []),
        "messages": state.get("messages", []),
        "audit_trail_steps": audit_trail_steps,
        "timestamp": datetime.datetime.now().isoformat()
    }

    # Ghi log ra file local (In-Memory/JSON Logger thay vì Postgres)
    try:
        log_file = os.path.join(os.path.dirname(os.path.dirname(__file__)), "audit_logs.json")
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(audit_log, ensure_ascii=False) + "\n")
        logger.info(f"[Compiler] Đã lưu Audit Log {audit_log['incident_id']} vào {log_file}.")
    except Exception as e:
        logger.error(f"[Compiler] Lỗi khi ghi Local JSON Log: {e}")

    return {
        "final_audit_log": audit_log
    }

def build_trustagent_graph():
    builder = StateGraph(TrustAgentState)
    
    # Thêm các nodes
    builder.add_node("document_agent", chung_tu_agent_node)
    builder.add_node("tax_compliance_agent", tuan_thu_agent_node)
    builder.add_node("legal_agent", legal_agent_node)
    builder.add_node("compiler_node", compiler_node)
    
    # Thêm conditional edges từ START qua router
    builder.add_conditional_edges(
        START,
        supervisor_router,
        {
            "document_agent": "document_agent",
            "legal_agent": "legal_agent",
            "compiler_node": "compiler_node"
        }
    )
    
    # Các agent sau khi xử lý sẽ quay về router để quyết định bước tiếp theo
    builder.add_conditional_edges(
        "document_agent", 
        supervisor_router,
        {
            "tax_compliance_agent": "tax_compliance_agent",
            "legal_agent": "legal_agent",
            "compiler_node": "compiler_node"
        }
    )
    
    builder.add_conditional_edges(
        "tax_compliance_agent", 
        supervisor_router,
        {
            "legal_agent": "legal_agent",
            "compiler_node": "compiler_node"
        }
    )
    
    builder.add_conditional_edges(
        "legal_agent", 
        supervisor_router,
        {
            "compiler_node": "compiler_node"
        }
    )
    
    # compiler_node kết thúc quy trình
    builder.add_edge("compiler_node", END)
    
    graph = builder.compile()
    return graph
