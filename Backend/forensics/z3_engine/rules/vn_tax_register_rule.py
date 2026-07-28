"""
TrustAgent — Bộ quy tắc Z3 cho Thông tư 90/2026/TT-BTC
(Đăng ký Thuế)

Các ràng buộc Z3:
  - RULE R1: Nhà cung cấp nước ngoài → Phải đăng ký qua cơ chế điện tử (Điều 76)
  - RULE R2: Sàn TMĐT → Phải kê khai thay cho người bán (Điều 78)
  - RULE R3: Đăng ký/cập nhật không được chậm hạn (Điều 10, 14)
"""

from __future__ import annotations

from typing import Any

from z3 import Bool, BoolVal, Int, Implies, And, Solver, sat

from .base_rule import BusinessRule

# Ngưỡng mặc định
DEFAULT_REGISTRATION_DAYS_LIMIT: int = 10  # Điều 10: đăng ký trong 10 ngày kể từ ngày thành lập/phát sinh


class VietnamTaxRegisterRule(BusinessRule):
    """
    Bộ quy tắc Z3 cho Thông tư 90/2026/TT-BTC về Đăng ký Thuế.
    """

    @property
    def name(self) -> str:
        return "vn_tax_register_tt90"

    @property
    def description(self) -> str:
        return (
            "Đăng ký thuế theo Thông tư 90/2026/TT-BTC — "
            "Kiểm chứng đăng ký nhà cung cấp nước ngoài, sàn TMĐT, và thời hạn đăng ký"
        )

    @property
    def legal_reference(self) -> str:
        return "Thông tư 90/2026/TT-BTC về Đăng ký Thuế"

    @property
    def severity(self) -> str:
        return "warning"

    def encode(
        self,
        solver: Solver,
        data: dict[str, Any],
        dynamic_thresholds: dict[str, int] | None = None,
    ) -> None:
        th = dynamic_thresholds or {}
        reg_days_limit = th.get("REGISTRATION_DAYS_LIMIT", DEFAULT_REGISTRATION_DAYS_LIMIT)

        # Khai báo biến Z3
        z3_has_tax_code          = Bool("has_tax_code")
        z3_is_foreign_supplier   = Bool("is_foreign_supplier")
        z3_is_ecommerce_platform = Bool("is_ecommerce_platform")
        z3_days_overdue          = Int("registration_days_overdue")
        z3_update_on_time        = Bool("update_on_time")

        # RULE R1: Nhà cung cấp nước ngoài phải có mã số thuế (Điều 76)
        solver.add(Implies(z3_is_foreign_supplier, z3_has_tax_code))

        # RULE R2: Sàn TMĐT phải có mã số thuế (Điều 78)
        solver.add(Implies(z3_is_ecommerce_platform, z3_has_tax_code))

        # RULE R3: Số ngày đăng ký chậm phải = 0 (đúng hạn)
        solver.add(z3_days_overdue == 0)

        # Bind dữ liệu thực tế
        solver.add(z3_has_tax_code          == BoolVal(bool(data.get("has_tax_code", False))))
        solver.add(z3_is_foreign_supplier   == BoolVal(bool(data.get("is_foreign_supplier", False))))
        solver.add(z3_is_ecommerce_platform == BoolVal(bool(data.get("is_ecommerce_platform", False))))
        solver.add(z3_days_overdue          == int(data.get("registration_days_overdue", 0)))
        solver.add(z3_update_on_time        == BoolVal(bool(data.get("update_on_time", False))))

    def get_violation_detail(self, data: dict[str, Any]) -> str:
        violations: list[str] = []

        if data.get("is_foreign_supplier") and not data.get("has_tax_code"):
            violations.append(
                "Căn cứ Điều 76 — Thông tư 90/2026/TT-BTC: "
                "Phát hiện tổ chức/cá nhân nước ngoài có hoạt động kinh doanh kỹ thuật số "
                "hoặc thương mại điện tử tại Việt Nam chưa thực hiện đăng ký mã số thuế "
                "theo cơ chế đăng ký điện tử dành cho nhà cung cấp nước ngoài.\n"
                "  → Hướng khắc phục: Đăng ký tài khoản trên Cổng thông tin điện tử của "
                "Tổng cục Thuế (thuedientu.gdt.gov.vn), hoàn thành hồ sơ đăng ký thuế "
                "theo mẫu dành cho nhà cung cấp nước ngoài và nộp trực tuyến trong vòng "
                f"{DEFAULT_REGISTRATION_DAYS_LIMIT} ngày kể từ khi phát sinh nghĩa vụ thuế tại Việt Nam."
            )

        if data.get("is_ecommerce_platform") and not data.get("has_tax_code"):
            violations.append(
                "Căn cứ Điều 78 — Thông tư 90/2026/TT-BTC: "
                "Sàn thương mại điện tử chưa đăng ký mã số thuế trong khi có nghĩa vụ "
                "kê khai, khấu trừ và nộp thuế thay cho các nhà cung cấp không có mã số thuế "
                "trên nền tảng của mình.\n"
                "  → Hướng khắc phục: Sàn TMĐT phải đăng ký mã số thuế cho chính mình "
                "và xây dựng cơ chế tự động kê khai thuế thay cho các đối tác bán hàng "
                "chưa có mã số thuế theo quy định tại Điều 78 Thông tư 90/2026."
            )

        days_overdue = data.get("registration_days_overdue", 0)
        if days_overdue > 0:
            violations.append(
                f"Căn cứ Điều 10 — Thông tư 90/2026/TT-BTC: "
                f"Doanh nghiệp/cá nhân chậm thực hiện đăng ký hoặc cập nhật thông tin "
                f"mã số thuế {days_overdue} ngày so với thời hạn luật định "
                f"({DEFAULT_REGISTRATION_DAYS_LIMIT} ngày kể từ ngày phát sinh nghĩa vụ).\n"
                f"  → Hướng khắc phục: Tiến hành đăng ký/cập nhật ngay lập tức qua cổng "
                f"dịch vụ thuế điện tử và chủ động liên hệ Chi cục Thuế để được hỗ trợ "
                f"hoàn thành thủ tục trong thời gian sớm nhất."
            )

        if violations:
            return "\n\n".join(violations)

        # SAT case — nhà cung cấp nước ngoài hoặc sàn TMĐT đã có MST
        if data.get("is_foreign_supplier"):
            return (
                "Nhà cung cấp nước ngoài đã hoàn thành đăng ký mã số thuế theo đúng "
                "quy trình điện tử của Thông tư 90/2026/TT-BTC. Hệ thống đã xác nhận "
                "đầy đủ nghĩa vụ thuế tại Việt Nam."
            )
        if data.get("is_ecommerce_platform"):
            return (
                "Sàn thương mại điện tử đã có mã số thuế và đáp ứng nghĩa vụ kê khai "
                "thay theo quy định Điều 78 Thông tư 90/2026/TT-BTC."
            )
        return "Không phát hiện vi phạm — Hoạt động đăng ký thuế tuân thủ đúng Thông tư 90/2026/TT-BTC."
