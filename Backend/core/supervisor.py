import os
import time
from typing import Dict, Any, Literal
from loguru import logger
from langgraph.graph import StateGraph, END
from langgraph.errors import GraphRecursionError

# Import state
from .state import TrustAgentState

# --- UTILS (Worst-case handling) ---

def timeout(seconds: int):
    """
    Decorator mô phỏng chống treo server (Z3 Timeout).
    Trong thực tế, có thể dùng asyncio.wait_for hoặc concurrent.futures.
    Ở đây ta mô phỏng logic.
    """
    def decorator(func):
        def wrapper(*args, **kwargs):
            start = time.time()
            result = func(*args, **kwargs)
            if time.time() - start > seconds:
                logger.warning(f"Z3 Timeout: Hàm {func.__name__} chạy vượt quá {seconds}s.")
            return result
        return wrapper
    return decorator


# --- NODES ---

def gateway_node(state: TrustAgentState) -> TrustAgentState:
    """
    Node đầu tiên: Đọc input, kiểm tra bảo mật và quyết định scenario.
    """
    logger.info("--- [GATEWAY NODE] Đang phân tích đầu vào ---")
    
    prompt = state.get("user_prompt", "")
    evidences = state.get("evidence_paths", [])
    
    # 1. Bảo mật Input (Worst-case)
    # Kiểm tra prompt injection cơ bản hoặc file không tồn tại
    if prompt and ("ignore all previous instructions" in prompt.lower()):
        logger.error("Phát hiện Prompt Injection!")
        state["scenario_type"] = "security_error"
        state["final_audit_log"] = {"error": "Phát hiện mã độc trong Prompt."}
        return state
        
    if evidences:
        for path in evidences:
            # Trong thực tế sẽ dùng os.path.exists(path)
            if not path.endswith(".xml") and not path.endswith(".pdf"):
                logger.error(f"File không đúng định dạng: {path}")
                state["scenario_type"] = "security_error"
                state["final_audit_log"] = {"error": "File evidence không hợp lệ."}
                return state

    # 2. Quyết định Scenario
    has_prompt = bool(prompt and prompt.strip())
    has_evidence = bool(evidences and len(evidences) > 0)
    
    if has_evidence and not has_prompt:
        state["scenario_type"] = "tax_audit"
    elif has_prompt and not has_evidence:
        state["scenario_type"] = "legal_verify"
    elif has_prompt and has_evidence:
        # Nếu có cả hai, hoặc user nhắc từ khóa "toàn diện"
        state["scenario_type"] = "full_audit"
    else:
        state["scenario_type"] = "security_error"
        state["final_audit_log"] = {"error": "Không có dữ liệu đầu vào."}
        
    logger.info(f"Đã phân loại kịch bản: {state['scenario_type']}")
    return state


def tax_agent_node(state: TrustAgentState) -> TrustAgentState:
    """
    Agent chuyên xử lý Hóa đơn, Thuế, OCR.
    """
    logger.info("--- [TAX AGENT NODE] Kiểm toán Hóa đơn ---")
    
    if "tax_warnings" not in state or state["tax_warnings"] is None:
        state["tax_warnings"] = []
    if "extracted_data" not in state or state["extracted_data"] is None:
        state["extracted_data"] = {}
        
    try:
        # Giả lập logic bóc tách và kiểm tra
        state["extracted_data"]["tong_tien"] = 15000000
        
        # Thêm một cảnh báo giả định
        state["tax_warnings"].append({
            "rule": "TaxValidation",
            "message": "Nghi ngờ sai lệch thuế suất GTGT 8% thay vì 10%."
        })
        logger.info("Đã quét xong hóa đơn.")
    except Exception as e:
        # Data Fallback: Không làm sập cả graph nếu OCR lỗi
        logger.error(f"Lỗi khi quét Hóa đơn: {e}")
        state["tax_warnings"].append({
            "rule": "SystemError",
            "message": "Lỗi OCR, không thể trích xuất toàn bộ dữ liệu."
        })
        # Vẫn tiếp tục với lượng dữ liệu còn lại
        
    return state


@timeout(seconds=10)
def legal_agent_node(state: TrustAgentState) -> TrustAgentState:
    """
    Agent chuyên Kiểm chứng Pháp lý bằng RAG và Z3 Theorem Prover.
    """
    logger.info("--- [LEGAL AGENT NODE] Rà soát Pháp lý ---")
    
    if "legal_violations" not in state or state["legal_violations"] is None:
        state["legal_violations"] = []
        
    try:
        # Đọc extracted_data từ tax_agent (nếu full_audit) hoặc từ prompt
        extracted_data = state.get("extracted_data", {})
        
        # Mô phỏng Z3 Solver
        state["z3_status"] = "UNSAT"
        state["legal_violations"].append({
            "rule": "Z3_Constraint",
            "message": "Hợp đồng vi phạm Điều 15 Luật Doanh nghiệp 2020."
        })
        logger.info("Đã chạy xong Z3 Solver.")
    except Exception as e:
        logger.error(f"Lỗi Z3 Solver: {e}")
        state["z3_status"] = "TIMEOUT_ERROR"
        
    return state


def final_reporter_node(state: TrustAgentState) -> TrustAgentState:
    """
    Quy tụ mọi luồng, tổng hợp Báo cáo cuối cùng.
    """
    logger.info("--- [FINAL REPORTER NODE] Tổng hợp Báo cáo ---")
    
    # Nếu bị lỗi bảo mật từ Gateway thì đã có final_audit_log, không ghi đè
    if state.get("final_audit_log") and "error" in state["final_audit_log"]:
        return state
        
    report = {
        "incident_id": state.get("incident_id"),
        "scenario_executed": state.get("scenario_type"),
        "tax_issues": state.get("tax_warnings", []),
        "legal_issues": state.get("legal_violations", []),
        "z3_status": state.get("z3_status"),
        "overall_status": "FAILED" if (state.get("tax_warnings") or state.get("legal_violations")) else "PASSED"
    }
    
    state["final_audit_log"] = report
    logger.info("Đã hoàn tất báo cáo.")
    return state


# --- ROUTING LOGIC ---

def route_scenario(state: TrustAgentState) -> str:
    """
    Điều hướng từ gateway_node sang các node phù hợp.
    """
    scenario = state.get("scenario_type")
    
    if scenario == "security_error":
        return "final_reporter_node"
        
    if scenario == "tax_audit":
        return "tax_agent_node"
        
    if scenario == "legal_verify":
        return "legal_agent_node"
        
    if scenario == "full_audit":
        # Full audit đi qua tax trước để lấy extracted_data cứng
        return "tax_agent_node"
        
    return "final_reporter_node"

def route_after_tax(state: TrustAgentState) -> str:
    """
    Điều hướng sau khi chạy xong tax_agent_node.
    Nếu full_audit -> đi tiếp sang legal_agent_node.
    Nếu tax_audit -> xong việc, đi tới final_reporter_node.
    """
    if state.get("scenario_type") == "full_audit":
        return "legal_agent_node"
    return "final_reporter_node"


# --- BUILD GRAPH ---

def build_trustagent_graph():
    # 1. Khởi tạo StateGraph
    workflow = StateGraph(TrustAgentState)
    
    # 2. Add Nodes
    workflow.add_node("gateway_node", gateway_node)
    workflow.add_node("tax_agent_node", tax_agent_node)
    workflow.add_node("legal_agent_node", legal_agent_node)
    workflow.add_node("final_reporter_node", final_reporter_node)
    
    # 3. Add Edges
    workflow.set_entry_point("gateway_node")
    
    # Gateway -> Agent(s) / Reporter
    workflow.add_conditional_edges(
        "gateway_node",
        route_scenario,
        {
            "tax_agent_node": "tax_agent_node",
            "legal_agent_node": "legal_agent_node",
            "final_reporter_node": "final_reporter_node"
        }
    )
    
    # Tax -> Legal (nếu full_audit) hoặc Final Reporter
    workflow.add_conditional_edges(
        "tax_agent_node",
        route_after_tax,
        {
            "legal_agent_node": "legal_agent_node",
            "final_reporter_node": "final_reporter_node"
        }
    )
    
    # Legal -> Final Reporter
    workflow.add_edge("legal_agent_node", "final_reporter_node")
    
    # Final Reporter -> END
    workflow.add_edge("final_reporter_node", END)
    
    # 4. Compile Graph
    # Cấu hình recursion_limit chống infinite loop
    app = workflow.compile(interrupt_before=[], interrupt_after=[])
    app.step_timeout = 30 # Thêm giới hạn timeout mức đồ thị nếu cần
    return app


# --- TEST CASES ---
if __name__ == "__main__":
    import json
    import sys
    if sys.stdout.encoding.lower() != 'utf-8':
        sys.stdout.reconfigure(encoding='utf-8')
    from rich.console import Console
    from rich.panel import Panel
    
    console = Console()
    app = build_trustagent_graph()
    
    # Khởi tạo state gốc rỗng để chuẩn hóa (có thể bỏ qua)
    def init_state(incident_id, prompt, evidences) -> TrustAgentState:
        return {
            "incident_id": incident_id,
            "user_prompt": prompt,
            "evidence_paths": evidences,
            "extracted_data": {},
            "scenario_type": "",
            "tax_warnings": [],
            "z3_status": None,
            "legal_violations": [],
            "final_audit_log": {},
            "messages": []
        }

    scenarios = [
        {
            "name": "SCENARIO 1: Ch\u1ec9 H\u00f3a \u0111\u01a1n (Tax Audit)",
            "state": init_state("INC-001", None, ["invoice_123.xml"])
        },
        {
            "name": "SCENARIO 2: Ch\u1ec9 Prompt Lu\u1eadt (Legal Verify)",
            "state": init_state("INC-002", "Kiểm tra luật doanh nghiệp khoản 3", [])
        },
        {
            "name": "SCENARIO 3: Combo C\u1ea3 2 (Full Audit)",
            "state": init_state("INC-003", "Kiểm tra hợp đồng và hóa đơn đính kèm", ["contract.pdf", "invoice.xml"])
        }
    ]

    for scenario in scenarios:
        console.print(f"\n[bold magenta]=== {scenario['name']} ===[/bold magenta]")
        
        try:
            # Chạy qua LangGraph
            config = {"recursion_limit": 10} # Cấu hình chống infinite loop
            # Ở LangGraph bản mới (0.1.x+), invoke nhận dict state và trả về dict final state
            final_state = app.invoke(scenario["state"], config=config)
            
            # In kết quả Report
            log = final_state.get("final_audit_log", {})
            console.print(Panel(json.dumps(log, indent=2, ensure_ascii=False), title=f"Report {scenario['state']['incident_id']}", border_style="cyan"))
            
        except GraphRecursionError:
            logger.error(f"Đã bắt được Infinite Loop trong Scenario {scenario['name']}")
        except Exception as e:
            logger.error(f"Lỗi không xác định: {e}")
