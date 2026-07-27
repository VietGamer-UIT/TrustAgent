"""
TrustAgent — Data Models cho Z3 Verification Engine (Nghị định 356/2025/NĐ-CP)

Định nghĩa Pydantic models dùng trong toàn bộ pipeline kiểm chứng:
- DataProcessingActivity : Input mô tả hoạt động xử lý dữ liệu cá nhân
- RuleViolation          : Chi tiết một vi phạm pháp lý phát hiện bởi Z3
- VerificationResult     : Kết quả cuối cùng của quá trình kiểm chứng Z3
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Optional
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


# =============================================================================
# Enums
# =============================================================================

class VerificationStatus(str, Enum):
    """Kết quả trả về từ Z3 solver."""
    SAT = "SAT"         # Satisfiable — hành động tuân thủ pháp luật
    UNSAT = "UNSAT"     # Unsatisfiable — hành động vi phạm pháp luật
    UNKNOWN = "UNKNOWN" # Solver timeout hoặc thiếu thông tin


class DataSensitivity(str, Enum):
    """Phân loại dữ liệu theo Điều 3 & 4 — Nghị định 356/2025/NĐ-CP."""
    BASIC = "basic"         # Dữ liệu cơ bản (Điều 3): họ tên, CCCD, SĐT...
    SENSITIVE = "sensitive" # Dữ liệu nhạy cảm (Khoản 1 Điều 4): sinh trắc, tài khoản ngân hàng, định vị...
    UNKNOWN = "unknown"     # Chưa xác định


class ActivityType(str, Enum):
    """Loại hoạt động xử lý dữ liệu cần kiểm chứng."""
    SENSITIVE_PROCESSING = "sensitive_processing"       # Xử lý dữ liệu nhạy cảm (Rule 2)
    CROSS_BORDER_TRANSFER = "cross_border_transfer"     # Chuyển dữ liệu xuyên biên giới (Rule 3 & 4)
    BREACH_NOTIFICATION = "breach_notification"         # Sự cố lộ dữ liệu (Rule 5)
    UNKNOWN = "unknown"                                 # Chưa xác định


class RuleSeverity(str, Enum):
    """Mức độ nghiêm trọng của vi phạm."""
    CRITICAL = "critical"    # Phải chặn ngay — vi phạm pháp luật
    WARNING = "warning"      # Cần xem xét — rủi ro chính sách
    INFO = "info"            # Thông tin — gợi ý cải thiện


# =============================================================================
# Input Models
# =============================================================================

class DataProcessingActivity(BaseModel):
    """
    Dữ liệu mô tả hoạt động xử lý dữ liệu cá nhân — cầu nối giữa Neural Layer và Z3.

    Được Gemini Semantic Parser trích xuất từ câu mô tả của người dùng.
    Mỗi trường tương ứng với một biến Z3 trong VietnamDataProtectionRule.

    Ví dụ:
        Input: "Hệ thống AI xử lý dữ liệu vân tay nhân viên nhưng không có phân quyền"
        Output: DataProcessingActivity(
            is_sensitive_data=True,
            has_access_control=False,
            data_sensitivity=DataSensitivity.SENSITIVE,
            ...
        )
    """
    # --- Phân loại dữ liệu ---
    is_sensitive_data: bool = Field(
        ...,
        description=(
            "True nếu dữ liệu thuộc nhóm nhạy cảm theo Khoản 1 Điều 4 "
            "(sinh trắc, tài khoản ngân hàng, định vị, sức khỏe, tôn giáo...)"
        ),
    )
    data_sensitivity: DataSensitivity = Field(
        default=DataSensitivity.UNKNOWN,
        description="Phân loại chi tiết: basic / sensitive / unknown",
    )
    data_type_location: bool = Field(
        default=False,
        description="True nếu dữ liệu bao gồm định vị vị trí (GPS, location services)",
    )
    data_type_biometric: bool = Field(
        default=False,
        description="True nếu dữ liệu bao gồm sinh trắc học (vân tay, khuôn mặt, mống mắt, ADN)",
    )

    # --- Kiểm soát truy cập (Rule 2) ---
    has_access_control: bool = Field(
        default=False,
        description=(
            "True nếu đã thiết lập phân quyền giới hạn truy cập vào dữ liệu nhạy cảm "
            "(Khoản 2 Điều 4)"
        ),
    )
    has_security_measures: bool = Field(
        default=False,
        description="True nếu đã áp dụng biện pháp bảo mật phù hợp (Khoản 2 Điều 4)",
    )

    # --- Chuyển dữ liệu xuyên biên giới (Rule 3 & 4) ---
    is_cross_border: bool = Field(
        default=False,
        description=(
            "True nếu có chuyển dữ liệu ra nước ngoài "
            "(AWS/Azure/GCP, máy chủ nước ngoài, đối tác quốc tế...)"
        ),
    )
    dossier_submitted_days: int = Field(
        default=999,
        description=(
            "Số ngày kể từ ngày chuyển dữ liệu đến ngày nộp hồ sơ đánh giá tác động. "
            "999 = chưa nộp (mặc định worst-case)."
        ),
        ge=0,
    )
    basic_record_count: int = Field(
        default=0,
        description="Số bản ghi dữ liệu cơ bản được chuyển xuyên biên giới",
        ge=0,
    )
    sensitive_record_count: int = Field(
        default=0,
        description="Số bản ghi dữ liệu nhạy cảm được chuyển xuyên biên giới",
        ge=0,
    )
    national_security_assessed: bool = Field(
        default=False,
        description=(
            "True nếu đã thực hiện đánh giá tác động an ninh quốc gia "
            "(bắt buộc khi vượt ngưỡng Rule 4)"
        ),
    )

    # --- Sự cố lộ dữ liệu (Rule 5) ---
    is_breach: bool = Field(
        default=False,
        description="True nếu đây là sự cố lộ/rò rỉ dữ liệu cá nhân",
    )
    breach_notice_hours: int = Field(
        default=999,
        description=(
            "Số giờ từ lúc phát hiện sự cố đến lúc thông báo cho chủ thể dữ liệu. "
            "999 = chưa thông báo."
        ),
        ge=0,
    )
    breach_retention_years: int = Field(
        default=0,
        description="Số năm lưu trữ hồ sơ sự cố (tối thiểu 5 năm theo Điều 29)",
        ge=0,
    )

    # --- Metadata ---
    description: str = Field(
        default="",
        description="Mô tả gốc từ câu hỏi của người dùng",
    )
    confidence: float = Field(
        default=1.0,
        description="Độ tin cậy của LLM khi trích xuất (0.0–1.0)",
        ge=0.0,
        le=1.0,
    )


# =============================================================================
# Output Models (giữ nguyên cấu trúc — chỉ cập nhật mô tả)
# =============================================================================

class RuleViolation(BaseModel):
    """Chi tiết một vi phạm pháp lý phát hiện bởi Z3."""
    rule_name: str = Field(
        ...,
        description="Tên kỹ thuật của rule vi phạm",
        examples=["vn_dp_sensitive_access_control"],
    )
    rule_description: str = Field(
        ...,
        description="Mô tả rule bằng ngôn ngữ tự nhiên",
    )
    severity: RuleSeverity = Field(
        default=RuleSeverity.CRITICAL,
        description="Mức độ nghiêm trọng",
    )
    violation_detail: str = Field(
        ...,
        description="Giải thích cụ thể tại sao vi phạm (trích dẫn logic toán học)",
    )
    legal_reference: str = Field(
        default="",
        description="Trích dẫn Điều/Khoản trong Nghị định 356/2025/NĐ-CP",
        examples=["Khoản 2 Điều 4, Nghị định 356/2025/NĐ-CP"],
    )
    text_evidence: str = Field(
        default="",
        description="Trích dẫn chính xác nội dung từ văn bản pháp luật",
    )


class VerificationResult(BaseModel):
    """
    Kết quả đầy đủ từ quá trình kiểm chứng Z3 theo Nghị định 356/2025/NĐ-CP.

    Đây là output chính của Symbolic Layer.
    """
    id: UUID = Field(default_factory=uuid4, description="ID kiểm chứng duy nhất")
    status: VerificationStatus = Field(
        ...,
        description="SAT (tuân thủ), UNSAT (vi phạm), hoặc UNKNOWN (lỗi/thiếu thông tin)",
    )
    is_compliant: bool = Field(
        ...,
        description="True nếu hoạt động tuân thủ tất cả quy tắc Nghị định 356",
    )
    violations: list[RuleViolation] = Field(
        default_factory=list,
        description="Danh sách vi phạm phát hiện (rỗng nếu SAT)",
    )
    rules_checked: list[str] = Field(
        default_factory=list,
        description="Tên các rule đã kiểm tra",
    )
    verification_time_ms: float = Field(
        default=0.0,
        description="Thời gian Z3 kiểm tra (ms)",
    )
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Thời điểm kiểm chứng",
    )
    raw_input: dict = Field(
        default_factory=dict,
        description="Dữ liệu đầu vào gốc đã kiểm chứng",
    )
    explanation: str = Field(
        default="",
        description="Tóm tắt kết quả kiểm chứng dạng ngôn ngữ tự nhiên",
    )

    def to_audit_dict(self) -> dict:
        """Chuyển sang dict để lưu vào audit trail database."""
        return {
            "verification_id": str(self.id),
            "status": self.status.value,
            "is_compliant": self.is_compliant,
            "violations": [v.model_dump() for v in self.violations],
            "rules_checked": self.rules_checked,
            "verification_time_ms": self.verification_time_ms,
            "timestamp": self.timestamp.isoformat(),
            "raw_input": self.raw_input,
            "explanation": self.explanation,
        }
