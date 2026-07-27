import operator
from typing import TypedDict, List, Optional, Any, Literal, Annotated
from langgraph.graph.message import add_messages

class TrustAgentState(TypedDict, total=False):
    """
    Siêu trạng thái (Unified State) của toàn bộ quá trình TrustAgent.
    Kết hợp cả luồng Thuế (TrustAgent) và Pháp lý (TrustAgent).
    """
    # --- Metadata (Thông tin đầu vào) ---
    incident_id: str                          # Session ID (thay thế ma_phien)
    user_prompt: Optional[str]                # Yêu cầu từ người dùng (nếu có)
    evidence_paths: List[str]                 # Đường dẫn file chứng từ (thay duong_dan_chung_tu)
    
    # --- Context (Dữ liệu trung gian) ---
    extracted_data: dict                      # Dữ liệu bóc tách chung
    hoa_don_list: Annotated[List[dict], operator.add]  # Danh sách hóa đơn (từ chung_tu_agent cũ)
    ket_qua_mst: Annotated[List[dict], operator.add]   # Kết quả tra cứu MST (từ tuan_thu_agent cũ)
    
    # --- Routing & Control (Điều hướng & Giám sát) ---
    scenario_type: Literal["tax_audit", "legal_verify", "full_audit"]
    current_agent: str                        # Tác nhân hiện tại đang xử lý
    iteration_count: int                      # Số vòng lặp chống loop vô hạn
    
    # --- Trạng thái Kiểm toán Thuế (Tax State) ---
    tax_warnings: Annotated[List[dict], operator.add]  # Các cảnh báo thuế (thay danh_sach_canh_bao)
    
    # --- Trạng thái Kiểm toán Pháp lý (Legal State) ---
    z3_status: Optional[str]                  # Trạng thái Z3 Solver (SAT/UNSAT/TIMEOUT_ERROR)
    legal_violations: Annotated[List[dict], operator.add] # Các vi phạm pháp lý phát hiện được
    
    # --- Output & Memory (Đầu ra & Lịch sử) ---
    final_audit_log: dict                     # Báo cáo tổng hợp cuối cùng (thay bao_cao_kiem_tra)
    messages: Annotated[List[Any], add_messages] # Lịch sử hội thoại/Agents
    error_log: Annotated[List[dict], operator.add] # Lịch sử lỗi để retry

