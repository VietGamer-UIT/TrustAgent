"""
TrustAgent — JSON Schemas cho Semantic Parser (Bộ Luật Việt Nam)

Hỗ trợ 5 bộ luật từ legal_data/:
  1. NghiDinh_356_2025_PDPD.md    — Bảo vệ dữ liệu cá nhân
  2. NghiDinh_165_2025.md         — Luật Dữ liệu (xử lý, bảo vệ dữ liệu quan trọng)
  3. NghiDinh_200_2026.md         — Trái phiếu doanh nghiệp / Chứng khoán
  4. NghiDinh_252_2026.md         — Quản lý Thuế
  5. ThongTu_90_2026_DangKyThue.md — Đăng ký Thuế

Kiến trúc:
  LLM (Gemini) → Trích xuất JSON → Pydantic validate → Z3 kiểm chứng tuân thủ
  LLM KHÔNG được phán quyết — Z3 mới là bên đưa ra kết luận.

Anti-hallucination: Mọi field boolean default = False, int default = worst-case
"""

from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


# =============================================================================
# Loại kịch bản — tương ứng với từng bộ luật
# =============================================================================

class ScenarioType(str, Enum):
    """Loại kịch bản, mỗi loại map tới 1 bộ luật trong legal_data/."""
    VN_DATA_PROTECTION  = "vn_data_protection"    # NghiDinh_356_2025_PDPD.md
    VN_DATA_LAW         = "vn_data_law"            # NghiDinh_165_2025.md
    VN_BOND             = "vn_bond"                # NghiDinh_200_2026.md
    VN_TAX_MGMT         = "vn_tax_mgmt"            # NghiDinh_252_2026.md
    VN_TAX_REGISTER     = "vn_tax_register"        # ThongTu_90_2026_DangKyThue.md
    UNKNOWN             = "unknown"


# =============================================================================
# Schema 1: Nghị định 356/2025 — Bảo vệ dữ liệu cá nhân
# =============================================================================

class ParsedVNDataProtection(BaseModel):
    """
    Trích xuất từ mô tả hoạt động xử lý/chuyển/sự cố dữ liệu cá nhân.
    Map tới NghiDinh_356_2025_PDPD.md.

    Anti-hallucination: Không đề cập rõ = False / 999
    """
    # Phân loại dữ liệu (Điều 3 & 4)
    is_sensitive_data: bool = Field(
        ...,
        description=(
            "True nếu dữ liệu nhạy cảm (Điều 4 NĐ356): sinh trắc, vị trí GPS, "
            "tài khoản ngân hàng, sức khỏe, tôn giáo, xu hướng tình dục. "
            "ANTI-HALLUCINATION: Không chắc = False"
        ),
    )
    data_type_location: bool = Field(
        default=False,
        description="True nếu có dữ liệu vị trí/GPS/định vị. Chỉ True khi đề cập RÕ RÀNG.",
    )
    data_type_biometric: bool = Field(
        default=False,
        description="True nếu có sinh trắc học (vân tay, khuôn mặt, mống mắt, ADN). Chỉ True khi RÕ RÀNG.",
    )

    # Kiểm soát truy cập (Khoản 2 Điều 4)
    has_access_control: bool = Field(
        default=False,
        description="True nếu ĐÃ thiết lập phân quyền/RBAC. ANTI-HALLUCINATION: Không đề cập = False",
    )
    has_security_measures: bool = Field(
        default=False,
        description="True nếu ĐÃ áp dụng bảo mật (mã hóa, firewall...). ANTI-HALLUCINATION: Không đề cập = False",
    )

    # Chuyển xuyên biên giới (Điều 17, 18)
    is_cross_border: bool = Field(
        default=False,
        description="True nếu dữ liệu chuyển ra nước ngoài (AWS/Azure/GCP/offshore). Không đề cập = False",
    )
    dossier_submitted_days: int = Field(
        default=999,
        description="Số ngày từ ngày chuyển đến ngày nộp hồ sơ. 999 = chưa nộp. Giới hạn ≤ 60 ngày.",
        ge=0,
    )
    basic_record_count: int = Field(
        default=0,
        description="Số bản ghi cơ bản chuyển xuyên biên giới. Ngưỡng AN ninh quốc gia: >100.000",
        ge=0,
    )
    sensitive_record_count: int = Field(
        default=0,
        description="Số bản ghi nhạy cảm chuyển xuyên biên giới. Ngưỡng AN ninh quốc gia: >10.000",
        ge=0,
    )
    national_security_assessed: bool = Field(
        default=False,
        description="True nếu đã đánh giá tác động an ninh quốc gia. Không đề cập = False",
    )

    # Sự cố lộ dữ liệu (Điều 29)
    is_breach: bool = Field(
        default=False,
        description="True nếu có sự cố lộ/rò rỉ/tấn công dữ liệu. Từ khóa: hack, breach, rò rỉ, mất dữ liệu.",
    )
    breach_notice_hours: int = Field(
        default=999,
        description="Số giờ từ phát hiện đến thông báo. 999 = chưa thông báo. Giới hạn ≤ 72 giờ.",
        ge=0,
    )
    breach_retention_years: int = Field(
        default=0,
        description="Số năm lưu hồ sơ sự cố. Giới hạn ≥ 5 năm (Điều 29).",
        ge=0,
    )

    # Metadata
    description: str = Field(default="", description="Mô tả ngắn hoạt động cần kiểm chứng")
    confidence: float = Field(default=1.0, description="Độ tin cậy LLM (0.0–1.0)", ge=0.0, le=1.0)
    raw_input: str = Field(default="", description="Câu nhập gốc")


# =============================================================================
# Schema 2: Nghị định 165/2025 — Luật Dữ liệu
# =============================================================================

class ParsedVNDataLaw(BaseModel):
    """
    Trích xuất từ mô tả hoạt động xử lý/bảo vệ/chia sẻ dữ liệu quan trọng.
    Map tới NghiDinh_165_2025.md (Luật Dữ liệu).

    Covers: dữ liệu quan trọng, dữ liệu cốt lõi, lưu trữ nội địa, chia sẻ cross-border.
    """
    # Phân loại dữ liệu (Điều 3)
    is_important_data: bool = Field(
        ...,
        description=(
            "True nếu dữ liệu quan trọng theo Điều 3 NĐ165: ảnh hưởng an ninh quốc gia, "
            "kinh tế, xã hội, y tế, hạ tầng quan trọng."
        ),
    )
    is_core_data: bool = Field(
        default=False,
        description="True nếu là dữ liệu cốt lõi (cấp cao hơn dữ liệu quan trọng). Chỉ True khi RÕ RÀNG.",
    )

    # Lưu trữ và xử lý
    is_stored_domestically: bool = Field(
        default=False,
        description="True nếu dữ liệu quan trọng được lưu trữ trong lãnh thổ Việt Nam.",
    )
    has_data_governance: bool = Field(
        default=False,
        description="True nếu có quy trình quản trị dữ liệu (data governance). Không đề cập = False",
    )
    has_audit_mechanism: bool = Field(
        default=False,
        description="True nếu có cơ chế kiểm toán/audit dữ liệu. Không đề cập = False",
    )

    # Chia sẻ / cung cấp dữ liệu
    is_shared_to_foreign: bool = Field(
        default=False,
        description="True nếu dữ liệu quan trọng được chia sẻ với tổ chức nước ngoài.",
    )
    foreign_share_approved: bool = Field(
        default=False,
        description="True nếu đã được cơ quan có thẩm quyền phê duyệt chia sẻ ra nước ngoài.",
    )

    # Metadata
    description: str = Field(default="", description="Mô tả ngắn hoạt động")
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    raw_input: str = Field(default="")


# =============================================================================
# Schema 3: Nghị định 200/2026 — Trái phiếu doanh nghiệp
# =============================================================================

class ParsedVNBond(BaseModel):
    """
    Trích xuất từ mô tả hoạt động phát hành/giao dịch trái phiếu doanh nghiệp riêng lẻ.
    Map tới NghiDinh_200_2026.md.

    Covers: điều kiện phát hành, hồ sơ, công bố thông tin, mua lại, giao dịch.
    """
    # Loại hoạt động
    is_issuance: bool = Field(
        ...,
        description="True nếu là hoạt động PHÁT HÀNH trái phiếu. False nếu là giao dịch/mua bán.",
    )
    is_domestic: bool = Field(
        default=True,
        description="True nếu phát hành trong nước. False nếu phát hành ra thị trường quốc tế.",
    )

    # Điều kiện phát hành (Điều 5, 6)
    has_audited_financial: bool = Field(
        default=False,
        description="True nếu BCTC đã được kiểm toán độc lập theo quy định. Không đề cập = False",
    )
    meets_equity_requirement: bool = Field(
        default=False,
        description="True nếu vốn chủ sở hữu đáp ứng điều kiện phát hành. Không đề cập = False",
    )
    has_payment_guarantee: bool = Field(
        default=False,
        description="True nếu có bảo lãnh thanh toán hoặc tài sản đảm bảo. Không đề cập = False",
    )

    # Công bố thông tin (Điều 20–22)
    disclosure_done: bool = Field(
        default=False,
        description="True nếu đã thực hiện công bố thông tin theo quy định. Không đề cập = False",
    )
    disclosure_days: int = Field(
        default=999,
        description="Số ngày kể từ phát hành đến ngày công bố thông tin. 999 = chưa công bố.",
        ge=0,
    )

    # Nhà đầu tư chuyên nghiệp
    sold_to_professional_investors_only: bool = Field(
        default=False,
        description="True nếu chỉ bán cho nhà đầu tư chứng khoán chuyên nghiệp.",
    )

    # Giá trị phát hành
    issuance_amount_billion_vnd: float = Field(
        default=0.0,
        description="Tổng giá trị phát hành (tỷ VNĐ). 0 nếu không đề cập.",
        ge=0,
    )

    # Metadata
    description: str = Field(default="")
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    raw_input: str = Field(default="")


# =============================================================================
# Schema 4: Nghị định 252/2026 — Quản lý Thuế
# =============================================================================

class ParsedVNTaxMgmt(BaseModel):
    """
    Trích xuất từ mô tả hoạt động khai thuế, nộp thuế, hoàn thuế, kiểm tra thuế.
    Map tới NghiDinh_252_2026.md.

    Covers: kê khai, nộp thuế, gia hạn, hoàn thuế, kiểm tra, thanh tra.
    """
    # Loại nghĩa vụ thuế
    tax_type: str = Field(
        default="other",
        description=(
            "Loại thuế: 'income_tax' (TNDN), 'vat' (GTGT), 'personal_income' (TNCN), "
            "'export_import' (XNK), 'special_consumption' (TTĐB), 'other'."
        ),
    )

    # Kê khai và nộp thuế
    declaration_on_time: bool = Field(
        default=False,
        description="True nếu kê khai thuế đúng hạn. Không đề cập = False",
    )
    payment_on_time: bool = Field(
        default=False,
        description="True nếu nộp thuế đúng hạn. Không đề cập = False",
    )
    days_overdue: int = Field(
        default=0,
        description="Số ngày chậm nộp. 0 nếu đúng hạn.",
        ge=0,
    )

    # Hoàn thuế
    is_refund_request: bool = Field(
        default=False,
        description="True nếu là yêu cầu hoàn thuế.",
    )
    refund_amount_million_vnd: float = Field(
        default=0.0,
        description="Số tiền hoàn thuế đề nghị (triệu VNĐ).",
        ge=0,
    )

    # Kiểm tra / thanh tra
    under_inspection: bool = Field(
        default=False,
        description="True nếu đang bị kiểm tra/thanh tra thuế.",
    )
    has_tax_debt: bool = Field(
        default=False,
        description="True nếu có nợ thuế chưa thanh toán. Không đề cập = False",
    )
    tax_debt_million_vnd: float = Field(
        default=0.0,
        description="Số tiền nợ thuế (triệu VNĐ).",
        ge=0,
    )

    # Metadata
    description: str = Field(default="")
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    raw_input: str = Field(default="")


# =============================================================================
# Schema 5: Thông tư 90/2026 — Đăng ký Thuế
# =============================================================================

class ParsedVNTaxRegister(BaseModel):
    """
    Trích xuất từ mô tả hoạt động đăng ký mã số thuế, thay đổi thông tin, chấm dứt MST.
    Map tới ThongTu_90_2026_DangKyThue.md.

    Covers: cấp MST, thay đổi thông tin, tạm ngừng, chấm dứt, MST nhà cung cấp nước ngoài.
    """
    # Loại hoạt động đăng ký
    action_type: str = Field(
        default="register",
        description=(
            "Loại hành động: 'register' (đăng ký mới), 'update' (cập nhật thông tin), "
            "'suspend' (tạm ngừng), 'terminate' (chấm dứt), 'foreign_supplier' (NCCNgNgoài)."
        ),
    )

    # Thông tin đăng ký
    has_tax_code: bool = Field(
        default=False,
        description="True nếu đã có mã số thuế (MST). Không đề cập = False",
    )
    is_foreign_supplier: bool = Field(
        default=False,
        description="True nếu là nhà cung cấp nước ngoài (e-commerce/digital platform).",
    )
    is_ecommerce_platform: bool = Field(
        default=False,
        description="True nếu là sàn thương mại điện tử phải kê khai thay.",
    )

    # Thời hạn và tuân thủ
    registration_days_overdue: int = Field(
        default=0,
        description="Số ngày chậm đăng ký so với quy định. 0 = đúng hạn.",
        ge=0,
    )
    update_on_time: bool = Field(
        default=False,
        description="True nếu cập nhật thông tin MST đúng hạn. Không đề cập = False",
    )

    # Metadata
    description: str = Field(default="")
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    raw_input: str = Field(default="")


# =============================================================================
# ParseResult — Kết quả tổng hợp
# =============================================================================

class ParseResult(BaseModel):
    """
    Kết quả tổng hợp từ Semantic Parser.
    Chứa loại kịch bản và dữ liệu tương ứng đã parse.
    Sẵn sàng chuyển cho Z3 Verification Engine.
    """
    scenario_type: ScenarioType = Field(
        ...,
        description="Loại kịch bản phát hiện được từ input",
    )

    # Chỉ 1 trong 5 field sau được điền, tương ứng với scenario_type
    vn_data_protection: Optional[ParsedVNDataProtection] = Field(
        default=None,
        description="Dữ liệu bảo vệ DLCN (NĐ356) — khi scenario=VN_DATA_PROTECTION",
    )
    vn_data_law: Optional[ParsedVNDataLaw] = Field(
        default=None,
        description="Dữ liệu Luật Dữ liệu (NĐ165) — khi scenario=VN_DATA_LAW",
    )
    vn_bond: Optional[ParsedVNBond] = Field(
        default=None,
        description="Dữ liệu trái phiếu DN (NĐ200) — khi scenario=VN_BOND",
    )
    vn_tax_mgmt: Optional[ParsedVNTaxMgmt] = Field(
        default=None,
        description="Dữ liệu quản lý thuế (NĐ252) — khi scenario=VN_TAX_MGMT",
    )
    vn_tax_register: Optional[ParsedVNTaxRegister] = Field(
        default=None,
        description="Dữ liệu đăng ký thuế (TT90) — khi scenario=VN_TAX_REGISTER",
    )

    parse_error: Optional[str] = Field(
        default=None,
        description="Thông báo lỗi nếu parse thất bại",
    )

    def to_z3_data(self) -> dict:
        """Chuyển kết quả parse thành dict để đưa vào Z3 verification."""
        _exclude = {"confidence", "raw_input", "description"}
        mapping = {
            ScenarioType.VN_DATA_PROTECTION: self.vn_data_protection,
            ScenarioType.VN_DATA_LAW: self.vn_data_law,
            ScenarioType.VN_BOND: self.vn_bond,
            ScenarioType.VN_TAX_MGMT: self.vn_tax_mgmt,
            ScenarioType.VN_TAX_REGISTER: self.vn_tax_register,
        }
        obj = mapping.get(self.scenario_type)
        if obj:
            return obj.model_dump(exclude=_exclude)
        return {}

    def get_applicable_rules(self) -> list[str]:
        """Trả về danh sách rule names cần kiểm tra cho kịch bản này."""
        mapping = {
            ScenarioType.VN_DATA_PROTECTION: ["vn_data_protection_nd356"],
            ScenarioType.VN_DATA_LAW:        ["vn_data_law_nd165"],
            ScenarioType.VN_BOND:            ["vn_bond_nd200"],
            ScenarioType.VN_TAX_MGMT:        ["vn_tax_mgmt_nd252"],
            ScenarioType.VN_TAX_REGISTER:    ["vn_tax_register_tt90"],
            ScenarioType.UNKNOWN:            [],
        }
        return mapping.get(self.scenario_type, [])
