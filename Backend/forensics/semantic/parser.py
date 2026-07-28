"""
TrustAgent — Semantic Parser (Bộ Luật Việt Nam)

Cầu nối giữa Neural Layer (Gemini LLM) và Symbolic Layer (Z3).

Hỗ trợ 5 bộ luật từ legal_data/:
  1. NghiDinh_356_2025_PDPD.md    → VN_DATA_PROTECTION  (bảo vệ dữ liệu cá nhân)
  2. NghiDinh_165_2025.md         → VN_DATA_LAW          (luật dữ liệu)
  3. NghiDinh_200_2026.md         → VN_BOND              (trái phiếu doanh nghiệp)
  4. NghiDinh_252_2026.md         → VN_TAX_MGMT          (quản lý thuế)
  5. ThongTu_90_2026_DangKyThue.md → VN_TAX_REGISTER     (đăng ký thuế)

Luồng xử lý:
  1. Nhận mô tả hoạt động bằng ngôn ngữ tự nhiên
  2. Phát hiện kịch bản pháp lý phù hợp
  3. Trích xuất biến boolean/int cần thiết cho Z3
  4. Validate bằng Pydantic
  5. Trả về ParseResult → Z3 kiểm chứng

Chế độ hoạt động:
  - Có GEMINI_API_KEY: GeminiSemanticParser (AI trích xuất)
  - Không có key:     MockSemanticParser (rule-based, dev/test)

Anti-hallucination: Mọi field boolean/int default = False/999 (worst-case)
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from .prompts import (
    SYSTEM_PROMPT,
    DETECT_SCENARIO_PROMPT,
    VN_DATA_PROTECTION_EXTRACT_PROMPT,
    EXPLAIN_RESULT_PROMPT,
)
from .schemas import (
    ParseResult,
    ParsedVNDataProtection,
    ParsedVNDataLaw,
    ParsedVNBond,
    ParsedVNTaxMgmt,
    ParsedVNTaxRegister,
    ScenarioType,
)

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Helper: trích xuất JSON từ text LLM
# ─────────────────────────────────────────────────────────────────────────────
def _extract_json(text: str) -> dict[str, Any]:
    """Trích xuất JSON từ chuỗi text của LLM (có thể wrap trong markdown)."""
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            pass
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            pass
    raise ValueError(f"Không thể trích xuất JSON từ: {text[:200]}")


# ─────────────────────────────────────────────────────────────────────────────
# Mock Parser — rule-based cho dev/test
# ─────────────────────────────────────────────────────────────────────────────
class MockSemanticParser:
    """
    Giả lập Gemini bằng keyword-based parsing.
    Dùng cho môi trường dev/test khi chưa có GEMINI_API_KEY.

    Anti-hallucination:
    - Chỉ set True khi từ khoá xuất hiện RÕ RÀNG trong câu
    - Mọi trường mặc định = False / 999 (worst-case)
    """

    # ── Từ khoá nhận diện kịch bản ────────────────────────────────────────

    _DP_KEYWORDS = [
        "vân tay", "khuôn mặt", "sinh trắc", "biometric", "fingerprint",
        "gps", "định vị", "location", "vị trí",
        "tài khoản ngân hàng", "lịch sử giao dịch",
        "sức khỏe", "bệnh án", "y tế", "hồ sơ y tế",
        "tôn giáo", "xu hướng tình dục",
        "dữ liệu cá nhân", "personal data", "gdpr", "pdpd",
        "mống mắt", "iris", "adn", "dna", "giọng nói",
        "lộ dữ liệu", "data breach", "rò rỉ", "bị tấn công", "bị hack",
        "mật khẩu", "cccd", "căn cước",
        "nghị định 356",
        # Dữ liệu cơ bản (Điều 3 NĐ356) — cũng thuộc phạm vi PDPD
        "họ tên", "số điện thoại", "sđt", "ngày sinh", "địa chỉ",
        "hình ảnh cá nhân", "tình trạng hôn nhân", "tài khoản số",
        "khách hàng", "người dùng", "nhân viên",
    ]

    _DATA_LAW_KEYWORDS = [
        "dữ liệu quan trọng", "dữ liệu cốt lõi", "trung tâm dữ liệu quốc gia",
        "luật dữ liệu", "nghị định 165", "nd 165",
        "lưu trữ nội địa", "data localization", "dữ liệu nhà nước",
        "quản trị dữ liệu", "data governance", "hạ tầng dữ liệu",
    ]

    _BOND_KEYWORDS = [
        "trái phiếu", "bond", "phát hành trái phiếu", "trái phiếu doanh nghiệp",
        "chào bán", "nhà đầu tư chuyên nghiệp", "bảo lãnh thanh toán",
        "nghị định 200", "nd 200", "thị trường trái phiếu",
    ]

    _TAX_MGMT_KEYWORDS = [
        "kê khai thuế", "nộp thuế", "hoàn thuế", "kiểm tra thuế", "thanh tra thuế",
        "nợ thuế", "chậm nộp thuế", "thuế thu nhập doanh nghiệp", "thuế gtgt",
        "nghị định 252", "nd 252", "luật quản lý thuế", "cơ quan thuế",
        "thuế tndn", "thuế tncn", "hóa đơn điện tử",
    ]

    _TAX_REGISTER_KEYWORDS = [
        "đăng ký thuế", "mã số thuế", "mst", "cấp mã số thuế",
        "thay đổi thông tin thuế", "chấm dứt mã số thuế",
        "thông tư 90", "tt 90", "nhà cung cấp nước ngoài",
        "sàn thương mại điện tử", "đăng ký mst", "khai thay",
    ]

    _SENSITIVE_KEYWORDS = [
        "vân tay", "khuôn mặt", "sinh trắc", "biometric", "fingerprint",
        "mống mắt", "iris", "adn", "dna", "giọng nói",
        "gps", "định vị", "location", "vị trí địa lý", "tọa độ",
        "tài khoản ngân hàng", "lịch sử giao dịch", "thông tin tín dụng",
        "sức khỏe", "bệnh án", "hồ sơ y tế",
        "tôn giáo", "xu hướng tình dục", "thông tin tội phạm",
        "mật khẩu", "cccd", "căn cước công dân",
    ]

    # ── Detect scenario ────────────────────────────────────────────────────

    def detect_scenario(self, user_input: str) -> ScenarioType:
        text = user_input.lower()

        # Ưu tiên kiểm tra từ khoá đặc trưng nhất trước
        if any(kw in text for kw in self._TAX_REGISTER_KEYWORDS):
            return ScenarioType.VN_TAX_REGISTER
        if any(kw in text for kw in self._TAX_MGMT_KEYWORDS):
            return ScenarioType.VN_TAX_MGMT
        if any(kw in text for kw in self._BOND_KEYWORDS):
            return ScenarioType.VN_BOND
        if any(kw in text for kw in self._DATA_LAW_KEYWORDS):
            return ScenarioType.VN_DATA_LAW
        if any(kw in text for kw in self._DP_KEYWORDS):
            return ScenarioType.VN_DATA_PROTECTION

        return ScenarioType.UNKNOWN

    # ── Parse từng kịch bản ───────────────────────────────────────────────

    def parse_vn_data_protection(self, user_input: str) -> ParsedVNDataProtection:
        """NghiDinh_356_2025_PDPD.md — Bảo vệ dữ liệu cá nhân."""
        text = user_input.lower()

        is_sensitive = any(kw in text for kw in self._SENSITIVE_KEYWORDS)
        data_type_biometric = any(kw in text for kw in [
            "vân tay", "khuôn mặt", "sinh trắc", "biometric", "fingerprint",
            "mống mắt", "iris", "adn", "dna", "giọng nói",
        ])
        data_type_location = any(kw in text for kw in [
            "gps", "định vị", "location", "vị trí", "tọa độ",
        ])

        # Anti-hallucination: chỉ True khi có từ khoá TÍCH CỰC, không có từ khoá PHỦ ĐỊNH
        _negative = ["chưa", "không có", "thiếu", "chưa thiết lập", "chưa có", "không thiết lập"]
        _has_negative_before = lambda kws: any(
            any(neg in text[max(0, text.find(kw)-20):text.find(kw)] for neg in _negative)
            for kw in kws if kw in text
        )

        _access_kws = ["phân quyền", "access control", "rbac", "giới hạn truy cập", "quyền truy cập"]
        _access_positive = any(kw in text for kw in _access_kws)
        _access_negated = _has_negative_before(_access_kws)
        has_access_ctrl = _access_positive and not _access_negated

        _sec_kws = ["mã hóa", "encrypt", "aes", "tls", "ssl", "firewall", "bảo mật", "security measures"]
        has_security = any(kw in text for kw in _sec_kws)

        is_cross_border = any(kw in text for kw in [
            "aws", "azure", "gcp", "google cloud", "máy chủ nước ngoài",
            "offshore", "nước ngoài", "cross-border", "singapore", "chuyển ra nước ngoài",
            "lưu trữ nước ngoài", "server nước ngoài",
        ])

        # Số ngày nộp hồ sơ — nhiều pattern hơn
        dossier_days = 999
        day_match = re.search(
            r"(?:sau|trong|nộp hồ sơ sau|hồ sơ sau)\s*(\d+)\s*ngày", text
        ) or re.search(
            r"(\d+)\s*ngày\s*(?:sau|kể từ|từ khi|nộp|hồ sơ)", text
        )
        if day_match:
            dossier_days = int(day_match.group(1))
        elif any(kw in text for kw in ["đã nộp hồ sơ", "nộp đúng hạn", "đã hoàn thành hồ sơ", "nộp ngay"]):
            dossier_days = 0

        # Số bản ghi
        basic_count = 0
        sensitive_count = 0
        count_matches = re.findall(r"([\d,\.]+)\s*(?:bản ghi|người dùng|khách hàng|nhân viên|record|user|người)", text)
        if count_matches:
            counts = [int(m.replace(",", "").replace(".", "")) for m in count_matches if m.replace(",", "").replace(".", "").isdigit()]
            if counts:
                if is_sensitive:
                    sensitive_count = counts[0]
                else:
                    basic_count = counts[0]

        ns_assessed = any(kw in text for kw in [
            "đánh giá an ninh quốc gia", "national security assessment", "an ninh quốc gia",
        ])

        is_breach = any(kw in text for kw in [
            "lộ dữ liệu", "rò rỉ", "data breach", "bị tấn công", "bị hack",
            "mất dữ liệu", "tấn công mạng", "unauthorized access", "sự cố bảo mật",
            "bị xâm nhập", "đánh cắp dữ liệu",
        ])

        notice_hours = 999
        if is_breach:
            # Pattern: "thông báo sau X giờ" hoặc "X giờ sau đó thông báo"
            hour_match = re.search(
                r"(?:thông báo sau|sau|báo cáo sau)\s*(\d+)\s*(?:giờ|tiếng|hours?)", text
            ) or re.search(
                r"(\d+)\s*(?:giờ|tiếng|hours?)\s*(?:sau|thông báo|notify|report)", text
            )
            if hour_match:
                notice_hours = int(hour_match.group(1))
            elif any(kw in text for kw in ["thông báo ngay", "thông báo trong vòng 24", "báo ngay"]):
                notice_hours = 24

        retention_match = re.search(
            r"(\d+)\s*năm\s*(?:lưu|giữ|bảo quản|retain|lưu trữ)"
            r"|(?:lưu trữ|giữ|lưu)\s*(?:trong|tối thiểu)?\s*(\d+)\s*năm",
            text
        )
        if retention_match:
            retention_years = int(retention_match.group(1) or retention_match.group(2))
        else:
            retention_years = 0

        return ParsedVNDataProtection(
            is_sensitive_data=is_sensitive,
            data_type_location=data_type_location,
            data_type_biometric=data_type_biometric,
            has_access_control=has_access_ctrl,
            has_security_measures=has_security,
            is_cross_border=is_cross_border,
            dossier_submitted_days=dossier_days,
            basic_record_count=basic_count,
            sensitive_record_count=sensitive_count,
            national_security_assessed=ns_assessed,
            is_breach=is_breach,
            breach_notice_hours=notice_hours,
            breach_retention_years=retention_years,
            description=user_input[:150],
            confidence=0.75,
            raw_input=user_input,
        )

    def parse_vn_data_law(self, user_input: str) -> ParsedVNDataLaw:
        """NghiDinh_165_2025.md — Luật Dữ liệu."""
        text = user_input.lower()
        return ParsedVNDataLaw(
            is_important_data=any(kw in text for kw in [
                "dữ liệu quan trọng", "dữ liệu cốt lõi", "hạ tầng quan trọng", "an ninh quốc gia",
            ]),
            is_core_data="dữ liệu cốt lõi" in text,
            is_stored_domestically=any(kw in text for kw in [
                "lưu tại việt nam", "máy chủ trong nước", "data center việt nam", "lưu nội địa",
            ]),
            has_data_governance=any(kw in text for kw in [
                "quản trị dữ liệu", "data governance", "chính sách dữ liệu",
            ]),
            has_audit_mechanism=any(kw in text for kw in [
                "kiểm toán", "audit", "nhật ký", "log hệ thống",
            ]),
            is_shared_to_foreign=any(kw in text for kw in [
                "chia sẻ nước ngoài", "cung cấp cho nước ngoài", "foreign", "quốc tế",
            ]),
            foreign_share_approved=any(kw in text for kw in [
                "đã được phê duyệt", "được chấp thuận", "có giấy phép",
            ]),
            description=user_input[:150],
            confidence=0.75,
            raw_input=user_input,
        )

    def parse_vn_bond(self, user_input: str) -> ParsedVNBond:
        """NghiDinh_200_2026.md — Trái phiếu doanh nghiệp."""
        text = user_input.lower()
        amount_match = re.search(r"([\d,\.]+)\s*(?:tỷ|triệu|billion|million)", text)
        amount = 0.0
        if amount_match:
            val = float(amount_match.group(1).replace(",", ""))
            amount = val if "tỷ" in text[amount_match.start():amount_match.end()+5] else val / 1000

        disc_match = re.search(r"(\d+)\s*ngày\s*(?:sau|công bố|thông báo)", text)
        disc_days = int(disc_match.group(1)) if disc_match else 999

        # Anti-hallucination: kiểm tra phủ định trước khi set True
        _negative = ["chưa", "không", "thiếu", "chưa được", "chưa có"]
        def _has_neg(kws: list[str]) -> bool:
            return any(
                any(neg in text[max(0, text.find(kw)-15):text.find(kw)] for neg in _negative)
                for kw in kws if kw in text
            )

        _audit_kws = ["kiểm toán", "audit", "bctc"]
        _audit_positive = any(kw in text for kw in _audit_kws)
        _audit_negated = _has_neg(_audit_kws)
        has_audited = _audit_positive and not _audit_negated

        return ParsedVNBond(
            is_issuance=any(kw in text for kw in ["phát hành", "chào bán", "issuance"]),
            is_domestic=not any(kw in text for kw in ["quốc tế", "international", "nước ngoài"]),
            has_audited_financial=has_audited,
            meets_equity_requirement=any(kw in text for kw in ["đủ vốn", "vốn chủ sở hữu đáp ứng", "đáp ứng điều kiện vốn"]),
            has_payment_guarantee=any(kw in text for kw in ["bảo lãnh", "tài sản đảm bảo", "guarantee"]),
            disclosure_done=any(kw in text for kw in ["đã công bố", "công bố thông tin", "disclosure"]),
            disclosure_days=disc_days,
            sold_to_professional_investors_only=any(kw in text for kw in [
                "nhà đầu tư chuyên nghiệp", "professional investor",
            ]),
            issuance_amount_billion_vnd=amount,
            description=user_input[:150],
            confidence=0.75,
            raw_input=user_input,
        )

    def parse_vn_tax_mgmt(self, user_input: str) -> ParsedVNTaxMgmt:
        """NghiDinh_252_2026.md — Quản lý Thuế."""
        text = user_input.lower()

        tax_type = "other"
        if any(kw in text for kw in ["thuế tndn", "thuế thu nhập doanh nghiệp"]):
            tax_type = "income_tax"
        elif any(kw in text for kw in ["thuế gtgt", "thuế giá trị gia tăng", "vat"]):
            tax_type = "vat"
        elif any(kw in text for kw in ["thuế tncn", "thu nhập cá nhân", "personal income"]):
            tax_type = "personal_income"
        elif any(kw in text for kw in ["xuất khẩu", "nhập khẩu", "hải quan", "customs"]):
            tax_type = "export_import"

        overdue_match = re.search(
            r"(\d+)\s*ngày\s*(?:chậm|quá hạn|trễ)"
            r"|(?:chậm|trễ|quá hạn)\s*(\d+)\s*ngày",
            text
        )
        if overdue_match:
            days_overdue = int(overdue_match.group(1) or overdue_match.group(2))
        else:
            days_overdue = 0

        def parse_vietnamese_tax_amounts(t: str):
            refund_amount = 0.0
            debt_amount = 0.0
            t_clean = t.lower().replace('.', '').replace(',', '')
            
            refund_match = re.search(r'(?:hoàn\s+thuế|hoàn|đề\s+nghị\s+hoàn)\s*(?:gtgt\s*)?(\d+)\s*(triệu|tỷ|đ|đồng|vnd)?', t_clean)
            if refund_match:
                val = int(refund_match.group(1))
                unit = refund_match.group(2)
                if unit == 'tỷ':
                    refund_amount = float(val * 1000)
                elif unit == 'triệu' or not unit:
                    refund_amount = float(val // 1000000 if val >= 1000000 else val)
            
            debt_match = re.search(r'(?:nợ\s+thuế|nợ|chưa\s+thanh\s+toán|nợ\s+chưa\s+thanh\s+toán)\s*(?:là\s*)?(\d+)\s*(triệu|tỷ|đ|đồng|vnd)?', t_clean)
            if debt_match:
                val = int(debt_match.group(1))
                unit = debt_match.group(2)
                if unit == 'tỷ':
                    debt_amount = float(val * 1000)
                elif unit == 'triệu' or not unit:
                    debt_amount = float(val // 1000000 if val >= 1000000 else val)
                    
            return refund_amount, debt_amount

        refund_amt, debt_amt = parse_vietnamese_tax_amounts(text)

        return ParsedVNTaxMgmt(
            tax_type=tax_type,
            declaration_on_time=any(kw in text for kw in ["kê khai đúng hạn", "nộp đúng hạn kê khai"]),
            payment_on_time=any(kw in text for kw in ["nộp đúng hạn", "thanh toán đúng hạn"]) and days_overdue == 0,
            days_overdue=days_overdue,
            is_refund_request=any(kw in text for kw in ["hoàn thuế", "refund", "xin hoàn"]),
            refund_amount_million_vnd=refund_amt,
            under_inspection=any(kw in text for kw in ["kiểm tra thuế", "thanh tra thuế", "đang bị kiểm tra"]),
            has_tax_debt=any(kw in text for kw in ["nợ thuế", "chậm nộp", "tax debt"]) or debt_amt > 0,
            tax_debt_million_vnd=debt_amt,
            description=user_input[:150],
            confidence=0.75,
            raw_input=user_input,
        )

    def parse_vn_tax_register(self, user_input: str) -> ParsedVNTaxRegister:
        """ThongTu_90_2026_DangKyThue.md — Đăng ký Thuế."""
        text = user_input.lower()

        action_type = "register"
        if any(kw in text for kw in ["cập nhật", "thay đổi thông tin", "update"]):
            action_type = "update"
        elif any(kw in text for kw in ["tạm ngừng", "suspend"]):
            action_type = "suspend"
        elif any(kw in text for kw in ["chấm dứt", "terminate", "đóng mst"]):
            action_type = "terminate"
        elif any(kw in text for kw in ["nhà cung cấp nước ngoài", "foreign supplier", "ncc nước ngoài"]):
            action_type = "foreign_supplier"

        overdue_match = re.search(r"(\d+)\s*ngày\s*(?:chậm|quá hạn|trễ)\s*(?:đăng ký)?", text)
        days_overdue = int(overdue_match.group(1)) if overdue_match else 0

        # Phát hiện nhà cung cấp nước ngoài / sàn TMĐT
        is_foreign_supplier = any(kw in text for kw in [
            "nhà cung cấp nước ngoài", "foreign supplier", "ncc ngoại",
            "shopee", "tiktok", "facebook", "google", "netflix", "amazon",
            "nền tảng số nước ngoài", "công ty nước ngoài",
        ])
        is_ecommerce_platform = any(kw in text for kw in [
            "sàn tmđt", "sàn thương mại điện tử", "e-commerce platform", "khai thay",
            "shopee", "tiktok shop", "lazada",
        ])

        # Xác định has_tax_code:
        # - "cần đăng ký", "đang đăng ký", "nộp hồ sơ đăng ký", "tiến hành đăng ký"
        #   → Tuân thủ đúng quy trình = có MST (đang trong quá trình hợp lệ)
        # - "chưa có mst", "chưa đăng ký", "không đăng ký", "từ chối đăng ký"
        #   → Vi phạm = không có MST
        # - "đã có mst", "có mã số thuế" → đã có rồi
        violation_keywords = ["chưa có mst", "chưa đăng ký", "không đăng ký",
                              "từ chối đăng ký", "bỏ qua đăng ký", "không có mã số thuế"]
        compliance_keywords = ["cần đăng ký", "đang đăng ký", "nộp hồ sơ đăng ký",
                               "tiến hành đăng ký", "thực hiện đăng ký", "đăng ký mã số thuế",
                               "đã có mst", "có mã số thuế", "mst hiện tại"]

        if any(kw in text for kw in violation_keywords) or days_overdue > 0:
            has_tax_code = False  # Vi phạm rõ ràng
        elif any(kw in text for kw in compliance_keywords):
            has_tax_code = True   # Đang tuân thủ quy trình
        else:
            has_tax_code = any(kw in text for kw in ["đã có mst", "có mã số thuế", "mst hiện tại"])

        return ParsedVNTaxRegister(
            action_type=action_type,
            has_tax_code=has_tax_code,
            is_foreign_supplier=is_foreign_supplier,
            is_ecommerce_platform=is_ecommerce_platform,
            registration_days_overdue=days_overdue,
            update_on_time=any(kw in text for kw in ["cập nhật đúng hạn", "thay đổi đúng hạn"]) and days_overdue == 0,
            description=user_input[:150],
            confidence=0.75,
            raw_input=user_input,
        )


    def explain_result(self, original_request: str, status: str, violations: list) -> str:
        """Tạo báo cáo Audit Trail bằng tiếng Việt (không dùng ANSI — dành cho UI web)."""
        text = original_request.lower()
        is_compliant = status == "SAT"

        if any(kw in text for kw in self._BOND_KEYWORDS):
            law_ref = "Nghị định 200/2026/NĐ-CP (Trái phiếu doanh nghiệp)"
            scenario = "Phát hành / giao dịch trái phiếu doanh nghiệp"
        elif any(kw in text for kw in self._TAX_REGISTER_KEYWORDS):
            law_ref = "Thông tư 90/2026/TT-BTC (Đăng ký thuế)"
            scenario = "Đăng ký / thay đổi mã số thuế"
        elif any(kw in text for kw in self._TAX_MGMT_KEYWORDS):
            law_ref = "Nghị định 252/2026/NĐ-CP (Quản lý thuế)"
            scenario = "Kê khai / nộp / hoàn thuế"
        elif any(kw in text for kw in self._DATA_LAW_KEYWORDS):
            law_ref = "Nghị định 165/2025/NĐ-CP (Luật Dữ liệu)"
            scenario = "Xử lý / lưu trữ / chia sẻ dữ liệu quan trọng"
        elif any(kw in text for kw in ["lộ", "rò rỉ", "breach", "hack"]):
            law_ref = "Nghị định 356/2025/NĐ-CP (Bảo vệ dữ liệu cá nhân)"
            scenario = "Xử lý sự cố vi phạm dữ liệu"
        elif any(kw in text for kw in ["vân tay", "khuôn mặt", "sinh trắc"]):
            law_ref = "Nghị định 356/2025/NĐ-CP (Bảo vệ dữ liệu cá nhân)"
            scenario = "Xử lý dữ liệu sinh trắc học"
        elif any(kw in text for kw in ["gps", "định vị", "location"]):
            law_ref = "Nghị định 356/2025/NĐ-CP (Bảo vệ dữ liệu cá nhân)"
            scenario = "Xử lý dữ liệu định vị"
        else:
            law_ref = "Nghị định / Thông tư liên quan (NĐ356, NĐ165, NĐ200, NĐ252, TT90)"
            scenario = "Hoạt động doanh nghiệp cần kiểm chứng pháp lý"

        lines: list[str] = [
            "🛡️ TRUSTAGENT — BÁO CÁO KIỂM CHỨNG",
            "",
            "1) Thông tin hoạt động",
            f"   • Nội dung: {scenario}",
            f"   • Khung pháp lý: {law_ref}",
            "",
            "2) Kết quả kiểm chứng (Z3)",
        ]

        if is_compliant:
            lines.append("   • Phán quyết: SAT — TUÂN THỦ")
            lines.append("   • Hành động: CHO PHÉP thực thi")
            lines.extend([
                "",
                "3) Nhận xét",
                "   Hệ thống không phát hiện vi phạm. Các biện pháp bảo vệ / "
                "điều kiện pháp lý yêu cầu đã được đáp ứng.",
                "",
                "4) Hành động của TrustAgent",
                "   Cho phép luồng xử lý tiếp tục.",
            ])
        else:
            lines.append("   • Phán quyết: UNSAT — VI PHẠM")
            lines.append("   • Hành động: CHẶN thực thi ngay")
            lines.extend(["", "3) Các vấn đề phát hiện"])
            bullets: list[str] = []
            for v in violations:
                raw = getattr(v, "violation_detail", None) or "Phát hiện vi phạm quy định pháp luật."
                for sub in [s.strip() for s in raw.replace("\\n", "\n").split("\n\n") if s.strip()]:
                    clean = " ".join(sub.replace("\n", " ").split())
                    # Bỏ prefix "Căn cứ ..." lặp lại nếu có nhiều lần
                    bullets.append(clean)
            if not bullets:
                bullets.append("Phát hiện vi phạm quy định pháp luật liên quan.")
            for i, b in enumerate(bullets, 1):
                lines.append(f"   {i}. {b}")
            lines.extend([
                "",
                "4) Hành động của TrustAgent",
                "   Đã chặn luồng dữ liệu / giao dịch để giảm rủi ro pháp lý "
                "và xử phạt hành chính cho doanh nghiệp.",
            ])

        return "\n".join(lines)


# ─────────────────────────────────────────────────────────────────────────────
# Gemini Parser — dùng khi có GEMINI_API_KEY
# ─────────────────────────────────────────────────────────────────────────────
class GeminiSemanticParser:
    """Parser thực sự dùng Gemini API. Tự động fallback sang MockParser nếu lỗi."""

    def __init__(self, api_key: str, model: str = "gemini-2.0-flash") -> None:
        self._model_name = model
        self._mock = MockSemanticParser()
        self._client = None
        try:
            import google.generativeai as genai
            genai.configure(api_key=api_key)
            self._client = genai.GenerativeModel(
                model_name=model,
                system_instruction=SYSTEM_PROMPT,
                generation_config={"temperature": 0.0, "response_mime_type": "application/json"},
            )
            logger.info(f"Gemini parser initialized: {model}")
        except ImportError:
            logger.warning("google-generativeai not installed. Using MockParser.")
        except Exception as e:
            logger.warning(f"Gemini init failed: {e}. Using MockParser.")

    def _call_gemini(self, prompt: str) -> dict[str, Any]:
        if self._client is None:
            raise RuntimeError("Gemini client not available")
        response = self._client.generate_content(prompt)
        return _extract_json(response.text)

    def detect_scenario(self, user_input: str) -> ScenarioType:
        if self._client is None:
            return self._mock.detect_scenario(user_input)
        try:
            prompt = DETECT_SCENARIO_PROMPT.format(user_input=user_input)
            data = self._call_gemini(prompt)
            return ScenarioType(data.get("scenario_type", "unknown"))
        except Exception as e:
            logger.warning(f"Gemini detect_scenario failed: {e}. Falling back.")
            return self._mock.detect_scenario(user_input)

    def parse_vn_data_protection(self, user_input: str) -> ParsedVNDataProtection:
        if self._client is None:
            return self._mock.parse_vn_data_protection(user_input)
        try:
            prompt = VN_DATA_PROTECTION_EXTRACT_PROMPT.format(user_input=user_input)
            data = self._call_gemini(prompt)
            data["raw_input"] = user_input
            return ParsedVNDataProtection(**data)
        except Exception as e:
            logger.warning(f"Gemini parse_dp failed: {e}. Falling back.")
            return self._mock.parse_vn_data_protection(user_input)

    def explain_result(self, original_request: str, status: str, violations: list) -> str:
        return self._mock.explain_result(original_request, status, violations)


# ─────────────────────────────────────────────────────────────────────────────
# SemanticParser — Public Interface
# ─────────────────────────────────────────────────────────────────────────────
class SemanticParser:
    """
    Public interface của Semantic Parsing Layer.

    Hỗ trợ 5 bộ luật từ bộ legal_data của TrustAgent.
    Tự động chọn GeminiSemanticParser hoặc MockSemanticParser.

    Sử dụng:
        parser = SemanticParser.from_config()
        result = parser.parse("Công ty phát hành trái phiếu 100 tỷ chưa kiểm toán")
        # result.scenario_type == ScenarioType.VN_BOND
        # result.to_z3_data() == {"is_issuance": True, "has_audited_financial": False, ...}
    """

    def __init__(self, api_key: str = "", model: str = "gemini-2.0-flash") -> None:
        if api_key:
            self._backend: GeminiSemanticParser | MockSemanticParser = GeminiSemanticParser(api_key, model)
        else:
            logger.info("No GEMINI_API_KEY — using MockSemanticParser for development")
            self._backend = MockSemanticParser()

    @classmethod
    def from_config(cls) -> "SemanticParser":
        try:
            from forensics.config import get_settings
            settings = get_settings()
            return cls(api_key=settings.gemini_api_key, model=settings.gemini_model)
        except Exception:
            return cls()

    def parse(self, user_input: str) -> ParseResult:
        """
        Pipeline chính: NL input → ParseResult → Z3 kiểm chứng.

        Input:  Mô tả hoạt động doanh nghiệp bằng tiếng Việt / Anh
        Output: ParseResult sẵn sàng đưa vào Z3
        """
        if not user_input or not user_input.strip():
            return ParseResult(
                scenario_type=ScenarioType.UNKNOWN,
                parse_error="Input rỗng — vui lòng mô tả hoạt động cần kiểm chứng",
            )

        try:
            scenario = self._backend.detect_scenario(user_input)
            mock = self._backend if isinstance(self._backend, MockSemanticParser) else self._backend._mock

            if scenario == ScenarioType.VN_DATA_PROTECTION:
                return ParseResult(
                    scenario_type=scenario,
                    vn_data_protection=mock.parse_vn_data_protection(user_input),
                )
            elif scenario == ScenarioType.VN_DATA_LAW:
                return ParseResult(
                    scenario_type=scenario,
                    vn_data_law=mock.parse_vn_data_law(user_input),
                )
            elif scenario == ScenarioType.VN_BOND:
                return ParseResult(
                    scenario_type=scenario,
                    vn_bond=mock.parse_vn_bond(user_input),
                )
            elif scenario == ScenarioType.VN_TAX_MGMT:
                return ParseResult(
                    scenario_type=scenario,
                    vn_tax_mgmt=mock.parse_vn_tax_mgmt(user_input),
                )
            elif scenario == ScenarioType.VN_TAX_REGISTER:
                return ParseResult(
                    scenario_type=scenario,
                    vn_tax_register=mock.parse_vn_tax_register(user_input),
                )
            else:
                return ParseResult(
                    scenario_type=ScenarioType.UNKNOWN,
                    parse_error=(
                        "Không nhận diện được kịch bản pháp lý. "
                        "Hệ thống hỗ trợ: bảo vệ dữ liệu cá nhân (NĐ356), "
                        "luật dữ liệu (NĐ165), trái phiếu DN (NĐ200), "
                        "quản lý thuế (NĐ252), đăng ký thuế (TT90)."
                    ),
                )

        except Exception as e:
            logger.error(f"SemanticParser.parse failed: {e}")
            return ParseResult(
                scenario_type=ScenarioType.UNKNOWN,
                parse_error=str(e),
            )

    def explain_result(self, original_request: str, status: str, violations: list) -> str:
        """Tạo AUDIT TRAIL LOG theo format nghiêm ngặt từ kết quả Z3."""
        return self._backend.explain_result(original_request, status, violations)
