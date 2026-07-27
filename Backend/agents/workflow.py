"""
TrustAgent — Public API cho LangGraph Workflow (Phase 3)

TrustAgentWorkflow là điểm vào chính của toàn bộ hệ thống.
Người dùng chỉ cần gọi .run(câu_yêu_cầu) và nhận kết quả đầy đủ.

Ví dụ sử dụng:
    workflow = TrustAgentWorkflow()
    result = workflow.run("Thanh toán tiền mặt 25 triệu cho sự kiện")
    print(result.is_compliant)    # False
    print(result.explanation)     # "❌ Giao dịch bị từ chối..."
    print(result.z3_status)       # "UNSAT"
"""

from __future__ import annotations

import logging
import time
import warnings
from dataclasses import dataclass, field

# Ẩn cảnh báo liên quan đến Pydantic/Langchain
warnings.filterwarnings("ignore", category=UserWarning)

from src.agents.graph import build_graph
from src.agents.state import AgentState

logger = logging.getLogger(__name__)


@dataclass
class WorkflowResult:
    """
    Kết quả cuối cùng sau khi chạy toàn bộ workflow.

    Đây là object người dùng nhận được từ TrustAgentWorkflow.run().
    Chứa đầy đủ thông tin để hiển thị, lưu audit trail, hoặc debug.
    """

    # Input gốc
    user_input: str = ""

    # Kết quả parse (Phase 2)
    scenario_type: str = "UNKNOWN"         # "VN_PAYMENT" | "KR_TAX_REFUND" | "UNKNOWN"
    parse_confidence: float = 0.0          # 0.0 - 1.0

    # Kết quả Z3 (Phase 1)
    z3_status: str = "UNKNOWN"             # "SAT" | "UNSAT" | "UNKNOWN"
    is_compliant: bool = False
    violations: list[dict] = field(default_factory=list)
    verify_time_ms: float = 0.0

    # Giải thích thân thiện
    explanation: str = ""

    # Thông tin debug
    error: str | None = None
    total_duration_ms: float = 0.0

    # Data trung gian (để debug)
    z3_data: dict = field(default_factory=dict)
    applicable_rules: list[str] = field(default_factory=list)
    legal_thresholds: dict = field(default_factory=dict)  # Từ Legal RAG Node

    @property
    def is_blocked(self) -> bool:
        """True nếu giao dịch bị chặn."""
        return not self.is_compliant

    @property
    def status_emoji(self) -> str:
        """Emoji tương ứng với kết quả."""
        if self.z3_status == "SAT":
            return "✅"
        elif self.z3_status == "UNSAT":
            return "❌"
        return "⚠️"

    def summary(self) -> str:
        """Tóm tắt ngắn gọn kết quả."""
        return (
            f"{self.status_emoji} [{self.z3_status}] "
            f"Scenario: {self.scenario_type} | "
            f"Tuân thủ: {'Có' if self.is_compliant else 'Không'} | "
            f"Thời gian: {self.total_duration_ms:.1f}ms"
        )

    def to_dict(self) -> dict:
        """Chuyển thành dict để lưu vào DB hoặc trả về API."""
        return {
            "user_input": self.user_input,
            "scenario_type": self.scenario_type,
            "parse_confidence": self.parse_confidence,
            "z3_status": self.z3_status,
            "is_compliant": self.is_compliant,
            "violations": self.violations,
            "verify_time_ms": self.verify_time_ms,
            "explanation": self.explanation,
            "error": self.error,
            "total_duration_ms": self.total_duration_ms,
        }


class TrustAgentWorkflow:
    """
    Public API cho toàn bộ TrustAgent pipeline.

    Nội bộ dùng LangGraph StateGraph (hoặc MockGraph nếu langgraph chưa cài)
    để điều phối: parse → verify → explain.

    Sử dụng:
        workflow = TrustAgentWorkflow()

        # Kiểm tra giao dịch VN
        result = workflow.run("Thanh toán tiền mặt 25 triệu cho sự kiện")
        print(result.summary())
        # ❌ [UNSAT] Scenario: VN_PAYMENT | Tuân thủ: Không | Thời gian: 5.2ms

        # Kiểm tra hoàn thuế KR
        result = workflow.run("Mua hàng 50,000 won, hoàn 5,000 KRW tại Incheon")
        print(result.summary())
        # ✅ [SAT] Scenario: KR_TAX_REFUND | Tuân thủ: Có | Thời gian: 3.1ms
    """

    def __init__(self) -> None:
        self._graph = build_graph()
        logger.info("TrustAgentWorkflow khởi tạo thành công")

    def run(self, user_input: str) -> WorkflowResult:
        """
        Chạy toàn bộ pipeline: NL Input → Parse → Verify → Explain.

        Args:
            user_input: Câu yêu cầu bằng tiếng Việt hoặc tiếng Anh

        Returns:
            WorkflowResult chứa đầy đủ thông tin kết quả

        Ví dụ Input/Output:
            Input:  "Thanh toán tiền mặt 25 triệu cho sự kiện"
            Output: WorkflowResult(
                user_input    = "Thanh toán tiền mặt 25 triệu cho sự kiện",
                scenario_type = "VN_PAYMENT",
                z3_status     = "UNSAT",
                is_compliant  = False,
                violations    = [{"rule_name": "vn_cash_payment_threshold", ...}],
                explanation   = "❌ Giao dịch bị từ chối...",
                verify_time_ms = 2.3,
                total_duration_ms = 5.7,
            )
        """
        t_start = time.perf_counter()
        logger.info(f"TrustAgentWorkflow.run() bắt đầu: '{user_input[:80]}'")

        # Khởi tạo state với input
        initial_state: AgentState = {  # type: ignore
            "user_input": user_input,
        }

        try:
            # Chạy graph
            final_state: AgentState = self._graph.invoke(initial_state)

            total_ms = (time.perf_counter() - t_start) * 1000

            result = WorkflowResult(
                user_input=user_input,
                scenario_type=final_state.get("scenario_type", "UNKNOWN"),
                parse_confidence=final_state.get("parse_confidence", 0.0),
                z3_status=final_state.get("z3_status", "UNKNOWN"),
                is_compliant=final_state.get("is_compliant", False),
                violations=final_state.get("violations", []),
                verify_time_ms=final_state.get("verify_time_ms", 0.0),
                explanation=final_state.get("explanation", ""),
                error=final_state.get("final_error"),
                total_duration_ms=total_ms,
                z3_data=final_state.get("z3_data", {}),
                applicable_rules=final_state.get("applicable_rules", []),
                legal_thresholds=final_state.get("legal_thresholds") or {},
            )

            logger.info(f"TrustAgentWorkflow.run() xong: {result.summary()}")
            return result

        except Exception as e:
            total_ms = (time.perf_counter() - t_start) * 1000
            logger.error(f"TrustAgentWorkflow.run() lỗi nghiêm trọng: {e}")
            return WorkflowResult(
                user_input=user_input,
                z3_status="UNKNOWN",
                is_compliant=False,
                explanation=f"⚠️ Lỗi hệ thống: {e}",
                error=str(e),
                total_duration_ms=total_ms,
            )

if __name__ == "__main__":
    import sys
    import os
    
    # Ép buộc stdout sử dụng UTF-8 để hỗ trợ in emoji 🛡️, ✅, 🚫
    sys.stdout.reconfigure(encoding='utf-8')
    
    # Kích hoạt ANSI escape codes trên Windows
    if os.name == 'nt':
        os.system('color')
        
    GREEN = "[92m"
    RED = "[91m"
    CYAN = "[96m"
    YELLOW = "[93m"
    BOLD = "[1m"
    RESET = "[0m"

    print(f"{BOLD}================================================================================{RESET}")
    print(f"{BOLD}🛡️ TRUSTAGENT.LEGAL - HỆ THỐNG KIỂM TOÁN TỰ ĐỘNG (INTERACTIVE DEMO){RESET}")
    print(f"{BOLD}================================================================================{RESET}")
    print(f"Luật hỗ trợ: {CYAN}NĐ 356{RESET} (Bảo vệ dữ liệu) | {CYAN}NĐ 165{RESET} (Luật Dữ liệu) | {CYAN}NĐ 200{RESET} (Trái phiếu) ")
    print(f"              {CYAN}NĐ 252{RESET} (Quản lý thuế)   | {CYAN}TT 90{RESET} (Đăng ký thuế)")
    print("Gõ 'exit' hoặc 'quit' để thoát.")
    print("-" * 80)
    
    workflow = TrustAgentWorkflow()
    
    # Từ điển ánh xạ RAG threshold keys sang tiếng Việt dễ đọc
    rag_keys_vn = {
        "CROSS_BORDER_DOSSIER_DAYS": "Thời hạn nộp hồ sơ dữ liệu xuyên biên giới (ngày)",
        "NATIONAL_SECURITY_BASIC_THRESHOLD": "Ngưỡng cảnh báo an ninh (Dữ liệu cơ bản - cá nhân)",
        "NATIONAL_SECURITY_SENSITIVE_THRESHOLD": "Ngưỡng cảnh báo an ninh (Dữ liệu nhạy cảm - cá nhân)",
        "BREACH_NOTICE_HOURS": "Thời hạn bắt buộc thông báo khi sự cố rò rỉ (giờ)",
        "BREACH_RETENTION_YEARS": "Thời gian tối thiểu lưu trữ nhật ký hệ thống (năm)",
        "DISCLOSURE_DAYS_LIMIT": "Thời hạn công bố thông tin trái phiếu (ngày)",
        "REGISTRATION_DAYS_LIMIT": "Thời hạn đăng ký/thay đổi thông tin thuế (ngày)",
        "LATE_PAYMENT_PENALTY_RATE_PERMILLE": "Tỷ lệ phạt nợ thuế chậm nộp (phần nghìn/ngày)"
    }
    
    while True:
        try:
            user_input = input(f"\n[{CYAN}NHẬP HÀNH ĐỘNG DOANH NGHIỆP{RESET}]: ").strip()
            if not user_input:
                continue
            if user_input.lower() in ['exit', 'quit']:
                print("\nĐang thoát...")
                break
                
            print(f"\n{YELLOW}Đang xử lý phân tích logic pháp lý...{RESET}\n")
            result = workflow.run(user_input)
            
            print(f"{BOLD}================================================================================{RESET}")
            print(f"{BOLD}🛡️ KẾT QUẢ KIỂM TOÁN HỆ THỐNG (AUDIT TRAIL){RESET}")
            print(f"{BOLD}================================================================================{RESET}")
            
            # Map Scenario
            scenario_mapping = {
                "vn_data_protection": "Bảo vệ dữ liệu cá nhân — NĐ 356/2025/NĐ-CP",
                "vn_data_law":        "Luật Dữ liệu — NĐ 165/2025/NĐ-CP",
                "vn_bond":            "Trái phiếu doanh nghiệp — NĐ 200/2026/NĐ-CP",
                "vn_tax_mgmt":        "Quản lý thuế — NĐ 252/2026/NĐ-CP",
                "vn_tax_register":    "Đăng ký thuế — TT 90/2026/TT-BTC",
                "unknown":            "Không xác định kịch bản pháp lý",
            }
            scenario_name = scenario_mapping.get(result.scenario_type, result.scenario_type)
            
            status_z3 = f"{GREEN}ĐẠT — Tuân thủ pháp luật{RESET}" if result.is_compliant else f"{RED}KHÔNG ĐẠT — Vi phạm pháp luật{RESET}"
            conclusion = f"{GREEN}✅ HÀNH VI HỢP LỆ PHÁP LÝ{RESET}" if result.is_compliant else f"{RED}❌ HÀNH VI VI PHẠM PHÁP LUẬT{RESET}"
            
            print(f"🔹 Lĩnh vực pháp lý  : {CYAN}{scenario_name}{RESET}")
            print(f"🔹 Trạng thái kiểm chứng: {status_z3}")
            print(f"🔹 Kết luận chung    : {conclusion}")
            
            if result.legal_thresholds:
                print(f"\n[{CYAN}NGƯỠNG PHÁP LÝ ÁP DỤNG CHO KỊCH BẢN NÀY{RESET}]")
                rag_context_vn = {
                    "CROSS_BORDER_DOSSIER_DAYS":           ("Hạn nộp hồ sơ chuyển dữ liệu xuyên biên giới", "ngày", "Khoản 4 Điều 18 NĐ356"),
                    "NATIONAL_SECURITY_BASIC_THRESHOLD":   ("Ngưỡng an ninh quốc gia — bản ghi cơ bản", "người", "Mẫu 09 NĐ356"),
                    "NATIONAL_SECURITY_SENSITIVE_THRESHOLD":("Ngưỡng an ninh quốc gia — bản ghi nhạy cảm", "người", "Mẫu 09 NĐ356"),
                    "BREACH_NOTICE_HOURS":                 ("Hạn thông báo sự cố rò rỉ dữ liệu", "giờ", "Điều 29 NĐ356"),
                    "BREACH_RETENTION_YEARS":              ("Thời gian lưu hồ sơ sự cố tối thiểu", "năm", "Điều 29 NĐ356"),
                    "DISCLOSURE_DAYS_LIMIT":               ("Hạn công bố thông tin sau phát hành trái phiếu", "ngày làm việc", "Điều 20 NĐ200"),
                    "REGISTRATION_DAYS_LIMIT":             ("Hạn đăng ký mã số thuế kể từ ngày phát sinh nghĩa vụ", "ngày", "Điều 10 TT90"),
                    "LATE_PAYMENT_PENALTY_RATE_PERMILLE":  ("Tỷ lệ phạt chậm nộp thuế", "phần nghìn/ngày (~0,03%/ngày)", "Điều 59 NĐ252"),
                }
                # Only show keys we know — skip raw/internal keys
                shown = False
                for k, v in result.legal_thresholds.items():
                    ctx = rag_context_vn.get(k)
                    if not ctx:
                        continue  # skip internal/unknown keys like INSPECTION_STATUTE_OF_LIMITATIONS_YEARS
                    label, unit, ref = ctx
                    if isinstance(v, int) and v >= 1000:
                        v_str = f"{v:,}".replace(",", ".")
                    else:
                        v_str = str(v)
                    print(f"  • {label}: {GREEN}{v_str} {unit}{RESET} ({CYAN}{ref}{RESET})")
                    shown = True
                if not shown:
                    print(f"  (Không có ngưỡng pháp lý cụ thể cần hiển thị cho kịch bản này)")
                
            print(f"\n[{CYAN}BÁO CÁO GIẢI THÍCH CHI TIẾT{RESET}]")
            print(result.explanation.strip())
            
        except KeyboardInterrupt:
            print("\\nĐang thoát...")
            break
        except Exception as e:
            print(f"\\n{RED}⚠️ Lỗi hệ thống: {e}{RESET}")
