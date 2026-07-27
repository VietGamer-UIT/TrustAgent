"""
TrustAgent — Bộ quy tắc Z3 cho Nghị định 356/2025/NĐ-CP
(Bảo vệ dữ liệu cá nhân Việt Nam)

Triển khai 5 ràng buộc Z3 tương ứng với 5 quy tắc pháp lý:
  - RULE 2: Xử lý dữ liệu nhạy cảm → BẮT BUỘC phân quyền + bảo mật
  - RULE 3: Chuyển xuyên biên giới → Nộp hồ sơ trong 60 ngày
  - RULE 4: Vượt ngưỡng an ninh quốc gia → Đánh giá tác động
  - RULE 5: Sự cố location/biometric → Thông báo ≤ 72 giờ + lưu 5 năm

Input  : DataProcessingActivity (từ SemanticParser)
Output : SAT ✅ (tuân thủ) hoặc UNSAT ❌ (vi phạm) + danh sách RuleViolation
"""

from __future__ import annotations

from typing import Any

from z3 import Bool, BoolVal, If, Int, Implies, Not, And, Or, Solver, sat

from .base_rule import BusinessRule

# =============================================================================
# Ngưỡng pháp lý mặc định (fallback khi RAG không trả về giá trị)
# =============================================================================

# Rule 3 — Chuyển dữ liệu xuyên biên giới (Khoản 4 Điều 18)
DEFAULT_CROSS_BORDER_DOSSIER_DAYS: int = 60

# Rule 4 — Ngưỡng an ninh quốc gia (Mẫu 09 Phụ lục)
DEFAULT_NATIONAL_SECURITY_BASIC_THRESHOLD: int = 100_000
DEFAULT_NATIONAL_SECURITY_SENSITIVE_THRESHOLD: int = 10_000

# Rule 5 — Sự cố lộ dữ liệu (Điều 29)
DEFAULT_BREACH_NOTICE_HOURS: int = 72
DEFAULT_BREACH_RETENTION_YEARS: int = 5


class VietnamDataProtectionRule(BusinessRule):
    """
    Bộ quy tắc Z3 tổng hợp cho Nghị định 356/2025/NĐ-CP.

    Mỗi phương thức _check_* tương ứng với một ràng buộc Z3 độc lập.
    Tất cả ràng buộc được thêm vào cùng một Solver instance.

    Luồng kiểm chứng:
        data = DataProcessingActivity.model_dump()
        solver = Solver()
        rule.encode(solver, data)
        result = solver.check()  # sat hoặc unsat

    Bảng vi phạm:
        RULE 2: is_sensitive_data=True AND has_access_control=False  → UNSAT
        RULE 2: is_sensitive_data=True AND has_security_measures=False → UNSAT
        RULE 3: is_cross_border=True AND dossier_submitted_days > 60  → UNSAT
        RULE 4: is_cross_border=True AND (basic_count>100K OR sensitive_count>10K)
                AND national_security_assessed=False                  → UNSAT
        RULE 5: is_breach=True AND (location OR biometric) AND notice_hours > 72 → UNSAT
        RULE 5: is_breach=True AND (location OR biometric) AND retention_years < 5 → UNSAT
    """

    @property
    def name(self) -> str:
        return "vn_data_protection_nd356"

    @property
    def description(self) -> str:
        return (
            "Bảo vệ dữ liệu cá nhân theo Nghị định 356/2025/NĐ-CP — "
            "Kiểm chứng phân quyền, chuyển xuyên biên giới, và thông báo sự cố"
        )

    @property
    def legal_reference(self) -> str:
        return "Nghị định 356/2025/NĐ-CP về Bảo vệ Dữ liệu Cá nhân"

    @property
    def severity(self) -> str:
        return "critical"

    def encode(
        self,
        solver: Solver,
        data: dict[str, Any],
        dynamic_thresholds: dict[str, int] | None = None,
    ) -> None:
        """
        Mã hóa 5 ràng buộc Z3 tương ứng Nghị định 356 vào solver.

        Args:
            solver            : Z3 Solver instance
            data              : DataProcessingActivity.model_dump()
            dynamic_thresholds: Ngưỡng từ RAG (nếu có), fallback về hằng số

        Ví dụ:
            Input:  {"is_sensitive_data": True, "has_access_control": False, ...}
            Z3 adds: Implies(sensitive, access_control) + data binding
            Result: UNSAT ❌ (has_access_control=False vi phạm Khoản 2 Điều 4)
        """
        th = dynamic_thresholds or {}

        # Lấy ngưỡng từ RAG hoặc fallback
        dossier_limit       = th.get("CROSS_BORDER_DOSSIER_DAYS", DEFAULT_CROSS_BORDER_DOSSIER_DAYS)
        basic_ns_threshold  = th.get("NATIONAL_SECURITY_BASIC_THRESHOLD", DEFAULT_NATIONAL_SECURITY_BASIC_THRESHOLD)
        sensitive_ns_threshold = th.get("NATIONAL_SECURITY_SENSITIVE_THRESHOLD", DEFAULT_NATIONAL_SECURITY_SENSITIVE_THRESHOLD)
        breach_hour_limit   = th.get("BREACH_NOTICE_HOURS", DEFAULT_BREACH_NOTICE_HOURS)
        breach_retain_min   = th.get("BREACH_RETENTION_YEARS", DEFAULT_BREACH_RETENTION_YEARS)

        # ── Khai báo biến Z3 ──────────────────────────────────────────────
        z3_is_sensitive         = Bool("is_sensitive_data")
        z3_has_access_ctrl      = Bool("has_access_control")
        z3_has_security         = Bool("has_security_measures")
        z3_is_cross_border      = Bool("is_cross_border")
        z3_dossier_days         = Int("dossier_submitted_days")
        z3_basic_count          = Int("basic_record_count")
        z3_sensitive_count      = Int("sensitive_record_count")
        z3_ns_assessed          = Bool("national_security_assessed")
        z3_is_breach            = Bool("is_breach")
        z3_location             = Bool("data_type_location")
        z3_biometric            = Bool("data_type_biometric")
        z3_notice_hours         = Int("breach_notice_hours")
        z3_retention_years      = Int("breach_retention_years")

        # ── RULE 2: Dữ liệu nhạy cảm → Phân quyền + Bảo mật ─────────────
        # Khoản 2 Điều 4: is_sensitive → has_access_control
        solver.add(Implies(z3_is_sensitive, z3_has_access_ctrl))
        # Khoản 2 Điều 4: is_sensitive → has_security_measures
        solver.add(Implies(z3_is_sensitive, z3_has_security))

        # ── RULE 3: Chuyển xuyên biên giới → Nộp hồ sơ ≤ 60 ngày ─────────
        # Khoản 4 Điều 18: is_cross_border → dossier_days <= 60
        solver.add(Implies(z3_is_cross_border, z3_dossier_days <= dossier_limit))

        # ── RULE 4: Vượt ngưỡng an ninh quốc gia → Đánh giá tác động ──────
        # Mẫu 09 Phụ lục: cross_border AND (basic>100K OR sensitive>10K) → ns_assessed
        over_threshold = Or(
            z3_basic_count > basic_ns_threshold,
            z3_sensitive_count > sensitive_ns_threshold,
        )
        solver.add(
            Implies(
                And(z3_is_cross_border, over_threshold),
                z3_ns_assessed,
            )
        )

        # ── RULE 5: Sự cố location/biometric → Thông báo ≤ 72h + Lưu ≥ 5 năm ──
        # Điều 29: is_breach AND (location OR biometric) → notice_hours <= 72 AND retention_years >= 5
        location_or_biometric = Or(z3_location, z3_biometric)
        solver.add(
            Implies(
                And(z3_is_breach, location_or_biometric),
                And(z3_notice_hours <= breach_hour_limit, z3_retention_years >= breach_retain_min),
            )
        )

        # ── Bind dữ liệu thực tế vào Z3 ──────────────────────────────────
        solver.add(z3_is_sensitive    == BoolVal(bool(data.get("is_sensitive_data", False))))
        solver.add(z3_has_access_ctrl == BoolVal(bool(data.get("has_access_control", False))))
        solver.add(z3_has_security    == BoolVal(bool(data.get("has_security_measures", False))))
        solver.add(z3_is_cross_border == BoolVal(bool(data.get("is_cross_border", False))))
        solver.add(z3_dossier_days    == int(data.get("dossier_submitted_days", 999)))
        solver.add(z3_basic_count     == int(data.get("basic_record_count", 0)))
        solver.add(z3_sensitive_count == int(data.get("sensitive_record_count", 0)))
        solver.add(z3_ns_assessed     == BoolVal(bool(data.get("national_security_assessed", False))))
        solver.add(z3_is_breach       == BoolVal(bool(data.get("is_breach", False))))
        solver.add(z3_location        == BoolVal(bool(data.get("data_type_location", False))))
        solver.add(z3_biometric       == BoolVal(bool(data.get("data_type_biometric", False))))
        solver.add(z3_notice_hours    == int(data.get("breach_notice_hours", 999)))
        solver.add(z3_retention_years == int(data.get("breach_retention_years", 0)))

    def get_violation_detail(self, data: dict[str, Any]) -> str:
        """
        Phân tích dữ liệu và trả về mô tả vi phạm bằng ngôn ngữ tự nhiên thuần Việt.
        Không chứa tên biến lập trình. Được gọi khi Z3 trả về UNSAT.
        """
        violations: list[str] = []

        # Rule 2 — Dữ liệu nhạy cảm
        if data.get("is_sensitive_data") and not data.get("has_access_control"):
            violations.append(
                "Căn cứ Khoản 2 Điều 4 — Nghị định 356/2025/NĐ-CP:\n"
                "Hệ thống đang xử lý dữ liệu cá nhân nhạy cảm (sinh trắc học, vân tay, "
                "khuôn mặt...) nhưng CHƯA thiết lập cơ chế phân quyền truy cập. "
                "Theo quy định, mọi hoạt động xử lý dữ liệu nhạy cảm bắt buộc phải có "
                "hệ thống phân quyền theo vai trò (RBAC) để giới hạn người được phép truy cập.\n"
                "  Hướng khắc phục: Triển khai hệ thống quản lý phân quyền truy cập "
                "theo vai trò (RBAC), đảm bảo chỉ nhân sự được ủy quyền mới có thể "
                "đọc hoặc xử lý dữ liệu sinh trắc học này."
            )
        if data.get("is_sensitive_data") and not data.get("has_security_measures"):
            violations.append(
                "Căn cứ Khoản 2 Điều 4 — Nghị định 356/2025/NĐ-CP:\n"
                "Hệ thống xử lý dữ liệu sinh trắc học chưa áp dụng các biện pháp "
                "bảo mật kỹ thuật phù hợp như mã hóa dữ liệu lưu trữ và truyền tải.\n"
                "  Hướng khắc phục: Áp dụng mã hóa AES-256 hoặc tiêu chuẩn tương đương "
                "cho toàn bộ dữ liệu sinh trắc học khi lưu trữ và khi truyền qua mạng."
            )

        # Rule 3 — Chuyển xuyên biên giới
        dossier_days = data.get("dossier_submitted_days", 999)
        if data.get("is_cross_border") and dossier_days > DEFAULT_CROSS_BORDER_DOSSIER_DAYS:
            violations.append(
                f"Căn cứ Khoản 4 Điều 18 — Nghị định 356/2025/NĐ-CP:\n"
                f"Doanh nghiệp chuyển dữ liệu người dùng ra máy chủ nước ngoài nhưng "
                f"nộp hồ sơ đánh giá tác động bảo vệ dữ liệu sau {dossier_days} ngày "
                f"kể từ ngày tiến hành chuyển dữ liệu. Quy định yêu cầu hồ sơ phải "
                f"được nộp trong vòng {DEFAULT_CROSS_BORDER_DOSSIER_DAYS} ngày.\n"
                f"  Hướng khắc phục: Chuẩn bị và nộp hồ sơ đánh giá tác động chuyển "
                f"dữ liệu xuyên biên giới (Data Transfer Impact Assessment) tới Bộ Công "
                f"an trước hoặc trong vòng {DEFAULT_CROSS_BORDER_DOSSIER_DAYS} ngày kể từ "
                f"ngày bắt đầu chuyển dữ liệu ra nước ngoài."
            )

        # Rule 4 — An ninh quốc gia
        basic_count     = data.get("basic_record_count", 0)
        sensitive_count = data.get("sensitive_record_count", 0)
        if (
            data.get("is_cross_border")
            and (basic_count > DEFAULT_NATIONAL_SECURITY_BASIC_THRESHOLD
                 or sensitive_count > DEFAULT_NATIONAL_SECURITY_SENSITIVE_THRESHOLD)
            and not data.get("national_security_assessed")
        ):
            violations.append(
                f"Căn cứ Mẫu 09 Phụ lục — Nghị định 356/2025/NĐ-CP:\n"
                f"Lô dữ liệu chuyển ra nước ngoài vượt ngưỡng an ninh quốc gia "
                f"(trên {DEFAULT_NATIONAL_SECURITY_BASIC_THRESHOLD:,} bản ghi cơ bản hoặc "
                f"trên {DEFAULT_NATIONAL_SECURITY_SENSITIVE_THRESHOLD:,} bản ghi nhạy cảm) "
                f"nhưng chưa tiến hành đánh giá tác động an ninh quốc gia bắt buộc.\n"
                f"  Hướng khắc phục: Thực hiện đánh giá tác động an ninh quốc gia và "
                f"trình Bộ Công an phê duyệt trước khi chuyển dữ liệu vượt ngưỡng này."
            )

        # Rule 5 — Sự cố lộ dữ liệu
        is_sensitive_breach = (
            data.get("is_breach")
            and (data.get("data_type_location") or data.get("data_type_biometric"))
        )
        if is_sensitive_breach:
            notice_hours    = data.get("breach_notice_hours", 999)
            retention_years = data.get("breach_retention_years", 0)
            if notice_hours > DEFAULT_BREACH_NOTICE_HOURS:
                violations.append(
                    f"Căn cứ Điều 29 — Nghị định 356/2025/NĐ-CP:\n"
                    f"Sau khi phát hiện sự cố rò rỉ dữ liệu sinh trắc học hoặc vị trí, "
                    f"doanh nghiệp đã thông báo cho chủ thể dữ liệu sau {notice_hours} giờ. "
                    f"Điều 29 quy định bắt buộc phải thông báo trong vòng "
                    f"{DEFAULT_BREACH_NOTICE_HOURS} giờ kể từ khi phát hiện sự cố.\n"
                    f"  Hướng khắc phục: Xây dựng quy trình ứng phó sự cố (Incident "
                    f"Response Plan) với mục tiêu thông báo trong vòng {DEFAULT_BREACH_NOTICE_HOURS} "
                    f"giờ. Thông báo cần gửi tới cả chủ thể dữ liệu và Bộ Công an."
                )
            if retention_years < DEFAULT_BREACH_RETENTION_YEARS:
                violations.append(
                    f"Căn cứ Điều 29 — Nghị định 356/2025/NĐ-CP:\n"
                    f"Hồ sơ ghi nhận sự cố rò rỉ dữ liệu chỉ được lưu trữ "
                    f"{'chưa rõ thời hạn' if retention_years == 0 else str(retention_years) + ' năm'}, "
                    f"trong khi pháp luật yêu cầu lưu tối thiểu {DEFAULT_BREACH_RETENTION_YEARS} năm.\n"
                    f"  Hướng khắc phục: Thiết lập chính sách lưu trữ hồ sơ sự cố tối "
                    f"thiểu {DEFAULT_BREACH_RETENTION_YEARS} năm, bao gồm: nhật ký sự kiện, "
                    f"hành động xử lý, và kết quả điều tra."
                )

        if violations:
            return "\n\n".join(violations)
        return (
            "Không phát hiện vi phạm — Hệ thống xử lý dữ liệu cá nhân đáp ứng đầy đủ "
            "các yêu cầu của Nghị định 356/2025/NĐ-CP."
        )
