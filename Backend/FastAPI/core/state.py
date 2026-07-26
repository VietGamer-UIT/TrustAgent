from typing import TypedDict, List, Optional, Any

class TrustAgentState(TypedDict):
    """
    Siêu trạng thái (Unified State) của toàn bộ quá trình Audit và Legal Verify.
    Kế thừa TypedDict theo chuẩn của LangGraph.
    """
    # --- Metadata (Thông tin đầu vào) ---
    incident_id: str
    user_prompt: Optional[str]
    evidence_paths: List[str]  # Đường dẫn file XML/PDF hóa đơn, hợp đồng
    
    # --- Context (Dữ liệu trung gian) ---
    extracted_data: dict  # Dữ liệu bóc tách được (OCR/Parser) từ evidence_paths
    
    # --- Routing (Điều hướng kịch bản) ---
    # Có 3 loại: 'tax_audit', 'legal_verify', 'full_audit'
    scenario_type: str
    
    # --- Tax State (Trạng thái Thuế/Kế toán) ---
    tax_warnings: List[dict]  # Các cảnh báo hoặc vi phạm chuẩn Thuế
    
    # --- Legal State (Trạng thái Pháp lý) ---
    z3_status: Optional[str]  # Trạng thái của Z3 Theorem Prover (SAT / UNSAT / TIMEOUT_ERROR)
    legal_violations: List[dict]  # Các vi phạm quy định Pháp luật
    
    # --- Output & Memory (Đầu ra & Bộ nhớ giao tiếp) ---
    final_audit_log: dict  # Báo cáo tổng hợp cuối cùng
    messages: List[Any]  # Lưu trữ lịch sử tin nhắn/agents tương tác (nếu dùng LLM agents)
