"""
TrustAgent — Bộ quy tắc Z3 cho Nghị định 252/2026/NĐ-CP
(Quản lý Thuế)

Các ràng buộc Z3:
  - RULE T1: Có nợ thuế → Không được hoàn thuế (Điều 72 Khoản 2)
  - RULE T2: Đang bị thanh tra → Không được hoàn thuế trước kiểm tra (Điều 77)
  - RULE T3: Chậm nộp thuế → Phát sinh tiền phạt chậm nộp (Điều 59)
"""

from __future__ import annotations

from typing import Any

from z3 import Bool, BoolVal, Int, Implies, And, Not, Solver, sat

from .base_rule import BusinessRule

# Ngưỡng mặc định
DEFAULT_LATE_PAYMENT_PENALTY_PERMILLE: int = 3   # 0.03%/ngày = 3 phần nghìn/ngày (Điều 59)


class VietnamTaxMgmtRule(BusinessRule):
    """
    Bộ quy tắc Z3 cho Nghị định 252/2026/NĐ-CP về Quản lý Thuế.
    """

    @property
    def name(self) -> str:
        return "vn_tax_mgmt_nd252"

    @property
    def description(self) -> str:
        return (
            "Quản lý thuế theo Nghị định 252/2026/NĐ-CP — "
            "Kiểm chứng điều kiện hoàn thuế, nợ thuế, và phạt chậm nộp"
        )

    @property
    def legal_reference(self) -> str:
        return "Nghị định 252/2026/NĐ-CP về Quản lý Thuế"

    @property
    def severity(self) -> str:
        return "critical"

    def encode(
        self,
        solver: Solver,
        data: dict[str, Any],
        dynamic_thresholds: dict[str, int] | None = None,
    ) -> None:
        # Khai báo biến Z3
        z3_is_refund_request = Bool("is_refund_request")
        z3_has_tax_debt      = Bool("has_tax_debt")
        z3_under_inspection  = Bool("under_inspection")
        z3_payment_on_time   = Bool("payment_on_time")
        z3_days_overdue      = Int("days_overdue")

        # RULE T1: Yêu cầu hoàn thuế → Không được có nợ thuế (Điều 72 Khoản 2)
        solver.add(Implies(z3_is_refund_request, Not(z3_has_tax_debt)))

        # RULE T2: Đang bị thanh tra → Không được yêu cầu hoàn thuế ngay (Điều 77)
        solver.add(Implies(z3_is_refund_request, Not(z3_under_inspection)))

        # RULE T3: Nếu kê khai đúng hạn thì số ngày chậm = 0
        solver.add(Implies(z3_payment_on_time, z3_days_overdue == 0))

        # Bind dữ liệu thực tế
        solver.add(z3_is_refund_request == BoolVal(bool(data.get("is_refund_request", False))))
        solver.add(z3_has_tax_debt      == BoolVal(bool(data.get("has_tax_debt", False))))
        solver.add(z3_under_inspection  == BoolVal(bool(data.get("under_inspection", False))))
        solver.add(z3_payment_on_time   == BoolVal(bool(data.get("payment_on_time", False))))
        solver.add(z3_days_overdue      == int(data.get("days_overdue", 0)))

    def get_violation_detail(self, data: dict[str, Any]) -> str:
        violations: list[str] = []

        if data.get("is_refund_request"):
            if data.get("has_tax_debt"):
                debt_amount = data.get("tax_debt_million_vnd", 0)
                refund_amount = data.get("refund_amount_million_vnd", 0)
                
                if debt_amount > 0 and refund_amount > 0:
                    msg = (
                        "Căn cứ Điều 72 Khoản 2 — Nghị định 252/2026/NĐ-CP: "
                        f"Doanh nghiệp đang đề nghị hoàn thuế số tiền {refund_amount:,.0f} triệu đồng "
                        f"trong khi vẫn còn tồn đọng nợ thuế chưa thanh toán "
                        f"(khoảng {debt_amount:,.0f} triệu đồng). Theo quy định, cơ quan thuế sẽ "
                        "bù trừ số tiền hoàn vào khoản nợ thuế trước khi hoàn trả phần chênh lệch.\n"
                        "  → Hướng khắc phục: Doanh nghiệp cần thanh toán toàn bộ số nợ thuế "
                        "hiện có trước khi nộp hồ sơ đề nghị hoàn thuế, hoặc đề nghị cơ quan "
                        "thuế thực hiện bù trừ tự động theo Điều 72."
                    )
                else:
                    msg = (
                        "Căn cứ Điều 72 Khoản 2 — Nghị định 252/2026/NĐ-CP: "
                        "Doanh nghiệp đang đề nghị hoàn thuế trong khi vẫn còn tồn đọng nợ thuế "
                        "chưa thanh toán. Theo quy định, cơ quan thuế sẽ thực hiện bù trừ "
                        "số tiền hoàn vào khoản nợ thuế trước khi hoàn trả phần chênh lệch.\n"
                        "  → Hướng khắc phục: Doanh nghiệp cần thanh toán toàn bộ nợ thuế "
                        "hiện có trước khi nộp hồ sơ đề nghị hoàn thuế."
                    )
                violations.append(msg)

            if data.get("under_inspection"):
                violations.append(
                    "Căn cứ Điều 77 — Nghị định 252/2026/NĐ-CP: "
                    "Doanh nghiệp đang trong quá trình bị kiểm tra/thanh tra thuế và "
                    "đồng thời yêu cầu hoàn thuế. Cơ quan thuế sẽ tạm hoãn giải quyết "
                    "hồ sơ hoàn thuế cho đến khi kết thúc quá trình kiểm tra để đảm bảo "
                    "tính chính xác của số tiền thuế cần hoàn.\n"
                    "  → Hướng khắc phục: Chờ kết quả kết luận kiểm tra/thanh tra, sau đó "
                    "nộp lại hồ sơ hoàn thuế. Nếu cần gấp, có thể liên hệ cơ quan thuế "
                    "để được hướng dẫn thủ tục đặc biệt."
                )

        days_overdue = data.get("days_overdue", 0)
        if days_overdue > 0 and not data.get("payment_on_time"):
            penalty_rate = DEFAULT_LATE_PAYMENT_PENALTY_PERMILLE
            violations.append(
                f"Căn cứ Điều 59 — Nghị định 252/2026/NĐ-CP: "
                f"Doanh nghiệp chậm nộp thuế {days_overdue} ngày so với thời hạn quy định. "
                f"Tiền phạt chậm nộp được tính theo mức {penalty_rate/100:.2f}% mỗi ngày "
                f"trên số tiền thuế chậm nộp, tính từ ngày hết hạn đến ngày thực nộp.\n"
                f"  → Hướng khắc phục: Nộp ngay số tiền thuế còn thiếu kèm theo tiền phạt "
                f"chậm nộp tương ứng. Có thể liên hệ cơ quan thuế để xin gia hạn nộp thuế "
                f"theo Điều 62 nếu gặp khó khăn về tài chính."
            )

        if violations:
            return "\n\n".join(violations)
        return "Không phát hiện vi phạm — Hoạt động thuế đáp ứng đủ điều kiện theo Nghị định 252/2026/NĐ-CP."
