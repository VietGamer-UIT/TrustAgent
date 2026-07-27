"""
TrustAgent — Bộ quy tắc Z3 cho Nghị định 200/2026/NĐ-CP
(Trái phiếu doanh nghiệp phát hành riêng lẻ)

Các ràng buộc Z3:
  - RULE B1: Phát hành trái phiếu → BẮT BUỘC BCTC đã kiểm toán (Điều 5)
  - RULE B2: Phát hành riêng lẻ → Chỉ bán cho nhà đầu tư chuyên nghiệp (Điều 6)
  - RULE B3: Phát hành → Công bố thông tin đúng hạn ≤ 5 ngày (Điều 20)
"""

from __future__ import annotations

from typing import Any

from z3 import Bool, BoolVal, Int, Implies, And, Solver, sat

from .base_rule import BusinessRule

# Ngưỡng mặc định
DEFAULT_DISCLOSURE_DAYS_LIMIT: int = 5   # Điều 20: Công bố trong 5 ngày


class VietnamBondRule(BusinessRule):
    """
    Bộ quy tắc Z3 cho Nghị định 200/2026/NĐ-CP về Trái phiếu doanh nghiệp.
    """

    @property
    def name(self) -> str:
        return "vn_bond_nd200"

    @property
    def description(self) -> str:
        return (
            "Trái phiếu doanh nghiệp theo Nghị định 200/2026/NĐ-CP — "
            "Kiểm chứng điều kiện phát hành, BCTC kiểm toán, nhà đầu tư chuyên nghiệp"
        )

    @property
    def legal_reference(self) -> str:
        return "Nghị định 200/2026/NĐ-CP về Trái phiếu Doanh nghiệp"

    @property
    def severity(self) -> str:
        return "critical"

    def encode(
        self,
        solver: Solver,
        data: dict[str, Any],
        dynamic_thresholds: dict[str, int] | None = None,
    ) -> None:
        th = dynamic_thresholds or {}
        disclosure_limit = th.get("DISCLOSURE_DAYS_LIMIT", DEFAULT_DISCLOSURE_DAYS_LIMIT)

        # Khai báo biến Z3
        z3_is_issuance         = Bool("is_issuance")
        z3_has_audited         = Bool("has_audited_financial")
        z3_professional_only   = Bool("sold_to_professional_investors_only")
        z3_disclosure_done     = Bool("disclosure_done")
        z3_disclosure_days     = Int("disclosure_days")

        # RULE B1: Phát hành → BCTC phải được kiểm toán (Điều 5 Khoản 1)
        solver.add(Implies(z3_is_issuance, z3_has_audited))

        # RULE B2: Phát hành riêng lẻ → Chỉ dành cho nhà đầu tư chuyên nghiệp (Điều 6)
        solver.add(Implies(z3_is_issuance, z3_professional_only))

        # RULE B3: Nếu đã phát hành và công bố → phải trong vòng disclosure_limit ngày (Điều 20)
        solver.add(Implies(
            And(z3_is_issuance, z3_disclosure_done),
            z3_disclosure_days <= disclosure_limit
        ))

        # Bind dữ liệu thực tế
        solver.add(z3_is_issuance       == BoolVal(bool(data.get("is_issuance", False))))
        solver.add(z3_has_audited       == BoolVal(bool(data.get("has_audited_financial", False))))
        solver.add(z3_professional_only == BoolVal(bool(data.get("sold_to_professional_investors_only", False))))
        solver.add(z3_disclosure_done   == BoolVal(bool(data.get("disclosure_done", False))))
        solver.add(z3_disclosure_days   == int(data.get("disclosure_days", 999)))

    def get_violation_detail(self, data: dict[str, Any]) -> str:
        violations: list[str] = []

        if data.get("is_issuance"):
            if not data.get("has_audited_financial"):
                violations.append(
                    "Căn cứ Điều 5 Khoản 1 — Nghị định 200/2026/NĐ-CP: "
                    "Doanh nghiệp dự định phát hành trái phiếu nhưng Báo cáo tài chính (BCTC) "
                    "chưa được kiểm toán độc lập theo quy định. Đây là điều kiện bắt buộc "
                    "trước khi tiến hành bất kỳ hoạt động phát hành nào.\n"
                    "  → Hướng khắc phục: Thuê đơn vị kiểm toán độc lập được Bộ Tài chính "
                    "chấp thuận để kiểm toán BCTC năm gần nhất trước khi nộp hồ sơ phát hành."
                )

            if not data.get("sold_to_professional_investors_only"):
                violations.append(
                    "Căn cứ Điều 6 — Nghị định 200/2026/NĐ-CP: "
                    "Trái phiếu phát hành riêng lẻ chỉ được phép chào bán cho nhà đầu tư "
                    "chứng khoán chuyên nghiệp. Hệ thống phát hiện kế hoạch phân phối không "
                    "giới hạn trong nhóm này, vi phạm quy định về đối tượng mua trái phiếu.\n"
                    "  → Hướng khắc phục: Xây dựng danh sách nhà đầu tư chuyên nghiệp được "
                    "xác nhận bởi Ủy ban Chứng khoán Nhà nước và giới hạn chào bán trong danh sách này."
                )

            disclosure_days = data.get("disclosure_days", 999)
            if data.get("disclosure_done") and disclosure_days > DEFAULT_DISCLOSURE_DAYS_LIMIT:
                violations.append(
                    f"Căn cứ Điều 20 — Nghị định 200/2026/NĐ-CP: "
                    f"Sau khi phát hành trái phiếu, doanh nghiệp công bố thông tin sau "
                    f"{disclosure_days} ngày, vượt quá thời hạn tối đa cho phép là "
                    f"{DEFAULT_DISCLOSURE_DAYS_LIMIT} ngày theo quy định.\n"
                    f"  → Hướng khắc phục: Thực hiện công bố thông tin qua Sở Giao dịch Chứng khoán "
                    f"trong vòng {DEFAULT_DISCLOSURE_DAYS_LIMIT} ngày làm việc kể từ ngày phát hành."
                )

        if violations:
            return "\n\n".join(violations)
        return "Không phát hiện vi phạm — Hồ sơ phát hành trái phiếu đáp ứng đủ điều kiện theo Nghị định 200/2026/NĐ-CP."
