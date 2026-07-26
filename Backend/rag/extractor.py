"""
TrustAgent.Forensics — Threshold Extractor từ văn bản luật (RAG Module)

Nhiệm vụ: Đọc văn bản luật và trích xuất các con số ngưỡng (threshold)
thành dict Python để đưa vào Z3 BusinessRule.

Hỗ trợ 5 bộ luật:
  vn_data_protection  → NghiDinh_356_2025_PDPD.md
  vn_data_law         → NghiDinh_165_2025.md
  vn_bond             → NghiDinh_200_2026.md
  vn_tax_mgmt         → NghiDinh_252_2026.md
  vn_tax_register     → ThongTu_90_2026_DangKyThue.md

Chiến lược extraction 3 tầng:
  1. JSON block extraction (regex từ markdown) — nhanh, reliable
  2. Pattern-based extraction (regex từ text thường) — fallback
  3. Hardcoded defaults — không bao giờ fail
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Fallback thresholds — dùng khi extraction fail ở mọi tầng
# ─────────────────────────────────────────────────────────────────────────────
FALLBACK_THRESHOLDS: dict[str, dict[str, int]] = {
    # Nghị định 356/2025/NĐ-CP — Bảo vệ dữ liệu cá nhân
    "vn_data_protection": {
        "CROSS_BORDER_DOSSIER_DAYS": 60,               # Khoản 4 Điều 18
        "NATIONAL_SECURITY_BASIC_THRESHOLD": 100_000,  # Mẫu 09 Phụ lục
        "NATIONAL_SECURITY_SENSITIVE_THRESHOLD": 10_000,
        "BREACH_NOTICE_HOURS": 72,                     # Điều 29
        "BREACH_RETENTION_YEARS": 5,                   # Điều 29
    },
    # Nghị định 165/2025/NĐ-CP — Luật Dữ liệu
    "vn_data_law": {
        "IMPORTANT_DATA_REVIEW_DAYS": 30,
    },
    # Nghị định 200/2026/NĐ-CP — Trái phiếu doanh nghiệp
    "vn_bond": {
        "DISCLOSURE_DAYS_LIMIT": 3,
        "MIN_EQUITY_BILLION_VND": 30,
    },
    # Nghị định 252/2026/NĐ-CP — Quản lý Thuế
    "vn_tax_mgmt": {
        "LATE_PAYMENT_PENALTY_RATE_PERMILLE": 3,
        "INSPECTION_STATUTE_OF_LIMITATIONS_YEARS": 5,
    },
    # Thông tư 90/2026/TT-BTC — Đăng ký Thuế
    "vn_tax_register": {
        "REGISTRATION_DAYS_LIMIT": 10,
        "UPDATE_DEADLINE_DAYS": 10,
    },
}

# Regex patterns để extract threshold từ text thường
_REGEX_PATTERNS: dict[str, list[tuple[str, str]]] = {
    "vn_data_protection": [
        (r"CROSS_BORDER_DOSSIER_DAYS\s*:\s*(\d+)", "CROSS_BORDER_DOSSIER_DAYS"),
        # Khớp chính xác: "không quá 60 ngày kể từ ngày tiến hành chuyển"
        (r"không quá\s*(\d+)\s*ngày.*?chuyển", "CROSS_BORDER_DOSSIER_DAYS"),
        (r"nộp hồ sơ.*?không quá\s*(\d+)\s*ngày", "CROSS_BORDER_DOSSIER_DAYS"),
        (r"thời hạn nộp hồ sơ.*?(\d+)\s*ngày", "CROSS_BORDER_DOSSIER_DAYS"),
        (r"BREACH_NOTICE_HOURS\s*:\s*(\d+)", "BREACH_NOTICE_HOURS"),
        (r"không quá\s*(\d+)\s*giờ.*?(?:thông báo|phát hiện)", "BREACH_NOTICE_HOURS"),
        (r"BREACH_RETENTION_YEARS\s*:\s*(\d+)", "BREACH_RETENTION_YEARS"),
        (r"tối thiểu\s*(\d+)\s*năm.*?lưu trữ", "BREACH_RETENTION_YEARS"),
        (r"NATIONAL_SECURITY_BASIC_THRESHOLD\s*:\s*([\d,]+)", "NATIONAL_SECURITY_BASIC_THRESHOLD"),
        (r"([\d\.]+)\.000\s*(?:bản ghi)?.*?dữ liệu cơ bản", "NATIONAL_SECURITY_BASIC_THRESHOLD"),
        (r"NATIONAL_SECURITY_SENSITIVE_THRESHOLD\s*:\s*([\d,]+)", "NATIONAL_SECURITY_SENSITIVE_THRESHOLD"),
        (r"([\d\.]+)\.000\s*(?:bản ghi)?.*?dữ liệu nhạy cảm", "NATIONAL_SECURITY_SENSITIVE_THRESHOLD"),
    ],
    "vn_bond": [
        (r"DISCLOSURE_DAYS_LIMIT\s*:\s*(\d+)", "DISCLOSURE_DAYS_LIMIT"),
        (r"công bố thông tin.*?(\d+)\s*ngày", "DISCLOSURE_DAYS_LIMIT"),
    ],
    "vn_tax_mgmt": [
        (r"LATE_PAYMENT_PENALTY_RATE_PERMILLE\s*:\s*(\d+)", "LATE_PAYMENT_PENALTY_RATE_PERMILLE"),
    ],
    "vn_tax_register": [
        (r"REGISTRATION_DAYS_LIMIT\s*:\s*(\d+)", "REGISTRATION_DAYS_LIMIT"),
        (r"(\d+)\s*ngày.*?đăng ký thuế", "REGISTRATION_DAYS_LIMIT"),
    ],
}

# Keys được lookup từ JSON block — mỗi scenario
_JSON_KEYS: dict[str, list[str]] = {
    "vn_data_protection": [
        "CROSS_BORDER_DOSSIER_DAYS",
        "NATIONAL_SECURITY_BASIC_THRESHOLD",
        "NATIONAL_SECURITY_SENSITIVE_THRESHOLD",
        "BREACH_NOTICE_HOURS",
        "BREACH_RETENTION_YEARS",
    ],
    "vn_data_law": [
        "IMPORTANT_DATA_REVIEW_DAYS",
    ],
    "vn_bond": [
        "DISCLOSURE_DAYS_LIMIT",
        "MIN_EQUITY_BILLION_VND",
    ],
    "vn_tax_mgmt": [
        "LATE_PAYMENT_PENALTY_RATE_PERMILLE",
        "INSPECTION_STATUTE_OF_LIMITATIONS_YEARS",
    ],
    "vn_tax_register": [
        "REGISTRATION_DAYS_LIMIT",
        "UPDATE_DEADLINE_DAYS",
    ],
}


class ThresholdExtractor:
    """
    Trích xuất các giá trị ngưỡng từ văn bản luật đã được RAG retrieve.

    Input:  Văn bản luật (str) + scenario_type (str)
    Output: dict[str, int] — ví dụ: {"CROSS_BORDER_DOSSIER_DAYS": 60}

    Sử dụng:
        extractor = ThresholdExtractor()
        thresholds = extractor.extract("vn_data_protection", legal_text)
        # → {"CROSS_BORDER_DOSSIER_DAYS": 60, "BREACH_NOTICE_HOURS": 72, ...}
    """

    def extract(self, scenario_type: str, legal_text: str) -> dict[str, int]:
        """
        Trích xuất threshold từ văn bản luật.

        Luôn trả về dict hợp lệ (dùng fallback nếu cần).
        Không bao giờ raise Exception.
        """
        if not legal_text or not legal_text.strip():
            logger.warning(f"[Extractor] Văn bản rỗng cho {scenario_type} → dùng fallback")
            return self._get_fallback(scenario_type)

        try:
            # Tầng 1: JSON block extraction (ưu tiên block cuối — bảng tổng hợp)
            result = self._extract_from_json_block(legal_text, scenario_type)
            if result:
                logger.info(f"[Extractor] JSON extraction OK cho {scenario_type}: {result}")
                return result

            # Tầng 2: Pattern-based regex extraction
            result = self._extract_from_patterns(legal_text, scenario_type)
            if result:
                logger.info(f"[Extractor] Regex extraction OK cho {scenario_type}: {result}")
                return result

        except Exception as e:
            logger.error(f"[Extractor] Lỗi extraction cho {scenario_type}: {e}")

        # Tầng 3: Hardcoded fallback
        logger.warning(f"[Extractor] Không extract được → dùng fallback cho {scenario_type}")
        return self._get_fallback(scenario_type)

    # ─────────────────────────────────────────────────────────────────────────
    # Tầng 1: JSON block extraction
    # ─────────────────────────────────────────────────────────────────────────

    def _extract_from_json_block(self, text: str, scenario_type: str) -> dict[str, int] | None:
        """
        Tìm tất cả ```json {...} ``` blocks trong markdown.
        Duyệt ngược (block cuối trước — thường là bảng tổng hợp).
        """
        json_blocks = re.findall(r"```json\s*(\{.*?\})\s*```", text, re.DOTALL)
        target_keys = _JSON_KEYS.get(scenario_type, [])
        if not target_keys:
            return None

        # Duyệt ngược để ưu tiên block tổng hợp cuối trang
        for block_str in reversed(json_blocks):
            try:
                data: dict[str, Any] = json.loads(block_str)
            except json.JSONDecodeError:
                continue

            extracted: dict[str, int] = {}
            for key in target_keys:
                value = self._find_nested_value(data, key)
                if value is not None:
                    try:
                        extracted[key] = int(value)
                    except (ValueError, TypeError):
                        pass

            if extracted:
                return extracted

        return None

    # ─────────────────────────────────────────────────────────────────────────
    # Tầng 2: Pattern-based regex extraction
    # ─────────────────────────────────────────────────────────────────────────

    def _extract_from_patterns(self, text: str, scenario_type: str) -> dict[str, int] | None:
        """Dùng regex patterns để extract threshold từ text thường."""
        patterns = _REGEX_PATTERNS.get(scenario_type, [])
        extracted: dict[str, int] = {}

        for pattern, key in patterns:
            match = re.search(pattern, text, re.IGNORECASE | re.UNICODE | re.DOTALL)
            if match:
                raw = match.group(1).replace(",", "").replace(".", "").strip()
                try:
                    extracted[key] = int(raw)
                except ValueError:
                    continue

        return extracted if extracted else None

    # ─────────────────────────────────────────────────────────────────────────
    # Tầng 3: Fallback defaults
    # ─────────────────────────────────────────────────────────────────────────

    def _get_fallback(self, scenario_type: str) -> dict[str, int]:
        """Trả về hardcoded defaults. Không bao giờ raise Exception."""
        defaults = FALLBACK_THRESHOLDS.get(scenario_type, {})
        if not defaults:
            logger.error(f"[Extractor] Không có fallback cho scenario: {scenario_type}")
        return dict(defaults)

    # ─────────────────────────────────────────────────────────────────────────
    # Helpers
    # ─────────────────────────────────────────────────────────────────────────

    @staticmethod
    def _find_nested_value(obj: dict | Any, key: str) -> int | None:
        """Tìm key trong dict, hỗ trợ nested dict."""
        if isinstance(obj, dict):
            if key in obj:
                return obj[key]
            for v in obj.values():
                result = ThresholdExtractor._find_nested_value(v, key)
                if result is not None:
                    return result
        return None
