"""
TrustAgent — Vietnam Data Law Rule (Nghị định 165/2025/NĐ-CP)
"""

from typing import Any
from z3 import Solver, Bool, Implies, Not, BoolVal

from .base_rule import BusinessRule
from ..models import RuleSeverity

class VietnamDataLawRule(BusinessRule):
    @property
    def name(self) -> str:
        return "vn_data_law_nd165"

    @property
    def description(self) -> str:
        return "Xử lý, lưu trữ, và chia sẻ dữ liệu quan trọng theo Luật Dữ liệu"

    @property
    def legal_reference(self) -> str:
        return "Nghị định 165/2025/NĐ-CP (Luật Dữ liệu)"

    @property
    def severity(self) -> str:
        return "critical"

    def encode(self, solver: Solver, data: dict[str, Any], dynamic_thresholds: dict[str, int] | None = None) -> None:
        """
        Encode các quy định cơ bản của NĐ 165.
        Ví dụ: Nếu là dữ liệu quan trọng/cốt lõi thì phải được lưu trữ trong nước (data localization).
        """
        # Z3 Variables
        z3_is_important_data = Bool('is_important_data')
        z3_is_stored_domestically = Bool('is_stored_domestically')
        
        # RULE: Dữ liệu quan trọng phải được lưu trữ tại Việt Nam
        solver.add(Implies(z3_is_important_data, z3_is_stored_domestically))
        
        # Bind actual data
        solver.add(z3_is_important_data == BoolVal(bool(data.get("is_important_data", False))))
        solver.add(z3_is_stored_domestically == BoolVal(bool(data.get("is_stored_domestically", False))))

    def get_violation_detail(self, data: dict[str, Any]) -> str:
        violations: list[str] = []

        if data.get("is_important_data") and not data.get("is_stored_domestically"):
            violations.append(
                "Căn cứ Nghị định 165/2025/NĐ-CP (Luật Dữ liệu): "
                "Dữ liệu quan trọng/cốt lõi của quốc gia bắt buộc phải được lưu trữ tại máy chủ trong nước. "
                "Hệ thống hiện tại đang xử lý dữ liệu quan trọng nhưng chưa đáp ứng yêu cầu lưu trữ nội địa (Data Localization).\n"
                "  → Hướng khắc phục: Dịch chuyển dữ liệu về trung tâm dữ liệu trong nước hoặc đăng ký ngoại lệ với cơ quan có thẩm quyền."
            )

        return "\n\n".join(violations) if violations else ""
