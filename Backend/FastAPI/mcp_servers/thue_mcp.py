# =============================================================================
# TaxLens-AI :: Thuế MCP Server — Tra Cứu Mã Số Thuế & Hóa Đơn Điện Tử
# Bản quyền: TaxLens-AI bởi Đoàn Hoàng Việt (Việt Gamer)
# =============================================================================
# Mô phỏng API Tổng cục Thuế (gdt.gov.vn) và hệ thống tra cứu hóa đơn
# (tracuuhoadon.gdt.gov.vn).
#
# Công cụ MCP:
#   - tra_cuu_mst      : Tra cứu tình trạng Mã số thuế
#   - kiem_tra_hoa_don  : Xác thực hóa đơn điện tử trên hệ thống TCT
#
# GHI CHÚ: Toàn bộ API đang dùng mock data. Thay thế hàm _mock_* bằng
# API thật của Tổng cục Thuế khi triển khai production.
# =============================================================================

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Any, Callable

from pydantic import BaseModel, Field, StrictStr, model_validator

logger = logging.getLogger("taxlens.mcp.thue")

# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------
THUE_TOOL_REGISTRY: dict[str, Callable] = {}


def mcp_tool(name: str):
    """Decorator đăng ký hàm async vào THUE_TOOL_REGISTRY."""
    def decorator(fn: Callable) -> Callable:
        THUE_TOOL_REGISTRY[name] = fn
        logger.debug("Đã đăng ký công cụ Thuế MCP: %s", name)
        return fn
    return decorator


# ---------------------------------------------------------------------------
# Audit helper
# ---------------------------------------------------------------------------
def _nhat_ky(tool: str, params: dict[str, Any]) -> None:
    """Ghi nhật ký kiểm toán cho mỗi lần gọi công cụ."""
    entry = {
        "su_kien": "goi_cong_cu_mcp",
        "thoi_gian": datetime.now(tz=timezone.utc).isoformat(),
        "may_chu": "thue_mcp",
        "cong_cu": tool,
        "tham_so": params,
    }
    logger.info(json.dumps(entry, ensure_ascii=False))


# ---------------------------------------------------------------------------
# Cơ sở dữ liệu Mã số thuế (Mock — mô phỏng API Tổng cục Thuế)
# ---------------------------------------------------------------------------

_CO_SO_DU_LIEU_MST: dict[str, dict[str, Any]] = {
    # ═══════════════════════════════════════════════════════
    # MST ĐANG HOẠT ĐỘNG — Doanh nghiệp hợp lệ
    # ═══════════════════════════════════════════════════════
    "0312345678": {
        "mst": "0312345678",
        "ten_doanh_nghiep": "Công ty TNHH Thương Mại Phúc Lộc",
        "dia_chi": "123 Nguyễn Huệ, Phường Bến Nghé, Quận 1, TP.HCM",
        "nguoi_dai_dien": "Nguyễn Văn An",
        "ngay_cap": "2015-03-20",
        "tinh_trang": "đang hoạt động",
        "co_quan_thue": "Chi cục Thuế Quận 1",
        "loai_hinh": "Công ty TNHH",
        "canh_bao": None,
    },
    "0309876543": {
        "mst": "0309876543",
        "ten_doanh_nghiep": "Công ty TNHH Dịch Vụ Hòa Bình",
        "dia_chi": "45 Trần Hưng Đạo, Quận 5, TP.HCM",
        "nguoi_dai_dien": "Trần Thị Bình",
        "ngay_cap": "2018-07-12",
        "tinh_trang": "đang hoạt động",
        "co_quan_thue": "Chi cục Thuế Quận 5",
        "loai_hinh": "Công ty TNHH",
        "canh_bao": None,
    },
    "0315678901": {
        "mst": "0315678901",
        "ten_doanh_nghiep": "Công ty CP Xây Dựng Tân Tiến",
        "dia_chi": "78 Lê Lợi, Quận 1, TP.HCM",
        "nguoi_dai_dien": "Lê Minh Cường",
        "ngay_cap": "2020-01-10",
        "tinh_trang": "đang hoạt động",
        "co_quan_thue": "Chi cục Thuế Quận 1",
        "loai_hinh": "Công ty cổ phần",
        "canh_bao": None,
    },
    "0314567890": {
        "mst": "0314567890",
        "ten_doanh_nghiep": "Công ty TNHH Vận Tải Minh Quang",
        "dia_chi": "200 Điện Biên Phủ, Quận Bình Thạnh, TP.HCM",
        "nguoi_dai_dien": "Phạm Quang Duy",
        "ngay_cap": "2019-05-15",
        "tinh_trang": "đang hoạt động",
        "co_quan_thue": "Chi cục Thuế Quận Bình Thạnh",
        "loai_hinh": "Công ty TNHH",
        "canh_bao": None,
    },
    "0101248141": {
        "mst": "0101248141",
        "ten_doanh_nghiep": "Công ty CP Phần Mềm FPT",
        "dia_chi": "Tòa nhà FPT, Phạm Văn Bạch, Cầu Giấy, Hà Nội",
        "nguoi_dai_dien": "Nguyễn Văn Khoa",
        "ngay_cap": "1999-09-13",
        "tinh_trang": "đang hoạt động",
        "co_quan_thue": "Cục Thuế TP. Hà Nội",
        "loai_hinh": "Công ty cổ phần",
        "canh_bao": None,
    },
    "0316789012": {
        "mst": "0316789012",
        "ten_doanh_nghiep": "Công ty TNHH Nội Thất Hoàng Gia",
        "dia_chi": "55 Nguyễn Văn Trỗi, Quận Phú Nhuận, TP.HCM",
        "nguoi_dai_dien": "Hoàng Gia Bảo",
        "ngay_cap": "2021-02-14",
        "tinh_trang": "đang hoạt động",
        "co_quan_thue": "Chi cục Thuế Quận Phú Nhuận",
        "loai_hinh": "Công ty TNHH",
        "canh_bao": None,
    },
    "0317890123": {
        "mst": "0317890123",
        "ten_doanh_nghiep": "Công ty TNHH Thiết Bị Y Tế Sài Gòn",
        "dia_chi": "102 Hai Bà Trưng, Quận 3, TP.HCM",
        "nguoi_dai_dien": "Ngô Thị Hương",
        "ngay_cap": "2022-06-01",
        "tinh_trang": "đang hoạt động",
        "co_quan_thue": "Chi cục Thuế Quận 3",
        "loai_hinh": "Công ty TNHH",
        "canh_bao": None,
    },
    "0318901234": {
        "mst": "0318901234",
        "ten_doanh_nghiep": "Công ty TNHH Quảng Cáo Sáng Tạo",
        "dia_chi": "10 Lý Tự Trọng, Quận 1, TP.HCM",
        "nguoi_dai_dien": "Đỗ Thanh Sơn",
        "ngay_cap": "2023-01-20",
        "tinh_trang": "đang hoạt động",
        "co_quan_thue": "Chi cục Thuế Quận 1",
        "loai_hinh": "Công ty TNHH",
        "canh_bao": None,
    },
    "0311111111": {
        "mst": "0311111111",
        "ten_doanh_nghiep": "Công ty CP Tư Vấn Luật An Khang",
        "dia_chi": "33 Pasteur, Quận 1, TP.HCM",
        "nguoi_dai_dien": "Vũ Đình Khang",
        "ngay_cap": "2017-08-25",
        "tinh_trang": "đang hoạt động",
        "co_quan_thue": "Chi cục Thuế Quận 1",
        "loai_hinh": "Công ty cổ phần",
        "canh_bao": None,
    },
    "0312222222": {
        "mst": "0312222222",
        "ten_doanh_nghiep": "Công ty TNHH Đào Tạo Nhân Lực Việt",
        "dia_chi": "67 Võ Văn Tần, Quận 3, TP.HCM",
        "nguoi_dai_dien": "Phan Thị Lan",
        "ngay_cap": "2020-11-30",
        "tinh_trang": "đang hoạt động",
        "co_quan_thue": "Chi cục Thuế Quận 3",
        "loai_hinh": "Công ty TNHH",
        "canh_bao": None,
    },
    "0301234567": {
        "mst": "0301234567",
        "ten_doanh_nghiep": "Công ty CP Đầu Tư ABC Việt Nam",
        "dia_chi": "88 Nguyễn Du, Quận 1, TP.HCM",
        "nguoi_dai_dien": "Trần Minh Tuấn",
        "ngay_cap": "2010-04-15",
        "tinh_trang": "đang hoạt động",
        "co_quan_thue": "Cục Thuế TP.HCM",
        "loai_hinh": "Công ty cổ phần",
        "canh_bao": None,
    },

    # ═══════════════════════════════════════════════════════
    # DANH SÁCH ĐEN — Công ty ma / đã bỏ trốn / ngừng hoạt động
    # ═══════════════════════════════════════════════════════
    "0399999001": {
        "mst": "0399999001",
        "ten_doanh_nghiep": "Công ty TNHH TM-DV Phát Đạt",
        "dia_chi": "Không xác định — đã bỏ địa chỉ kinh doanh",
        "nguoi_dai_dien": "Nguyễn Văn X (không liên lạc được)",
        "ngay_cap": "2022-01-05",
        "tinh_trang": "đã bỏ địa chỉ kinh doanh",
        "co_quan_thue": "Chi cục Thuế Quận 12",
        "loai_hinh": "Công ty TNHH",
        "canh_bao": "⚠️ CẢNH BÁO: Doanh nghiệp đã bỏ địa chỉ kinh doanh theo QĐ của Chi cục Thuế Quận 12. "
                    "Ngày thông báo: 2023-08-15. Hóa đơn từ DN này KHÔNG có giá trị pháp lý.",
    },
    "0399999002": {
        "mst": "0399999002",
        "ten_doanh_nghiep": "Công ty TNHH Xuất Nhập Khẩu Hải Vân",
        "dia_chi": "99 Nguyễn Thái Học, Quận 1, TP.HCM (ĐÃ ĐÓNG CỬA)",
        "nguoi_dai_dien": "Lê Thị Y (đã xuất cảnh)",
        "ngay_cap": "2021-06-10",
        "tinh_trang": "đã ngừng hoạt động",
        "co_quan_thue": "Chi cục Thuế Quận 1",
        "loai_hinh": "Công ty TNHH",
        "canh_bao": "⚠️ CẢNH BÁO: Doanh nghiệp ngừng hoạt động nhưng KHÔNG thông báo cơ quan thuế. "
                    "Người đại diện đã xuất cảnh. MST bị khóa từ ngày 2023-11-20. "
                    "Có dấu hiệu sử dụng hóa đơn bất hợp pháp.",
    },
    "0399999003": {
        "mst": "0399999003",
        "ten_doanh_nghiep": "Công ty TNHH MTV Đại Phong",
        "dia_chi": "Không xác định",
        "nguoi_dai_dien": "Trương Văn Z",
        "ngay_cap": "2023-03-01",
        "tinh_trang": "tạm ngừng hoạt động",
        "co_quan_thue": "Chi cục Thuế Quận Tân Bình",
        "loai_hinh": "Công ty TNHH MTV",
        "canh_bao": "⚠️ CẢNH BÁO: Doanh nghiệp tạm ngừng hoạt động có thời hạn. "
                    "Thời gian tạm ngừng: từ 2024-01-01 đến 2024-12-31. "
                    "Hóa đơn trong thời gian này KHÔNG hợp lệ.",
    },
}


# ---------------------------------------------------------------------------
# Mock functions
# ---------------------------------------------------------------------------

async def _mock_tra_cuu_mst(mst: str) -> dict[str, Any]:
    """Mô phỏng tra cứu MST trên hệ thống Tổng cục Thuế."""
    await asyncio.sleep(0.15)  # Mô phỏng network latency

    if mst in _CO_SO_DU_LIEU_MST:
        return _CO_SO_DU_LIEU_MST[mst]

    # MST không tìm thấy
    return {
        "mst": mst,
        "ten_doanh_nghiep": "KHÔNG TÌM THẤY",
        "dia_chi": "Không có dữ liệu",
        "nguoi_dai_dien": "Không có dữ liệu",
        "ngay_cap": None,
        "tinh_trang": "không tìm thấy trong hệ thống",
        "co_quan_thue": "Không xác định",
        "loai_hinh": "Không xác định",
        "canh_bao": "⚠️ CẢNH BÁO: Mã số thuế không tồn tại trong cơ sở dữ liệu Tổng cục Thuế. "
                    "Có thể là MST giả hoặc đã bị xóa.",
    }


async def _mock_kiem_tra_hoa_don(
    mst_nguoi_ban: str,
    so_hoa_don: str,
    ngay_xuat: str,
) -> dict[str, Any]:
    """Mô phỏng xác thực hóa đơn trên tracuuhoadon.gdt.gov.vn."""
    await asyncio.sleep(0.1)

    # Hóa đơn từ công ty ma → không tìm thấy trên hệ thống
    if mst_nguoi_ban in ("0399999001", "0399999002", "0399999003"):
        return {
            "ket_qua": "không tìm thấy",
            "mst_nguoi_ban": mst_nguoi_ban,
            "so_hoa_don": so_hoa_don,
            "thong_bao": "Hóa đơn KHÔNG tồn tại trên hệ thống tra cứu hóa đơn điện tử của Tổng cục Thuế.",
            "muc_do_rui_ro": "nghiêm trọng",
        }

    # Hóa đơn hợp lệ
    return {
        "ket_qua": "hợp lệ",
        "mst_nguoi_ban": mst_nguoi_ban,
        "so_hoa_don": so_hoa_don,
        "ngay_xuat": ngay_xuat,
        "thong_bao": "Hóa đơn tồn tại và hợp lệ trên hệ thống Tổng cục Thuế.",
        "muc_do_rui_ro": "thấp",
    }


# ---------------------------------------------------------------------------
# Pydantic v2 Input Schemas
# ---------------------------------------------------------------------------

class TraCuuMSTInput(BaseModel):
    """Schema đầu vào cho công cụ tra cứu Mã số thuế."""
    mst: StrictStr = Field(
        ...,
        description="Mã số thuế cần tra cứu (10 hoặc 13 ký tự số)",
    )

    @model_validator(mode="after")
    def kiem_tra_format_mst(self) -> "TraCuuMSTInput":
        """Kiểm tra MST đúng format: chỉ chứa số, 10 hoặc 13 ký tự."""
        mst_clean = self.mst.replace("-", "").strip()
        if not mst_clean.isdigit():
            raise ValueError(f"MST '{self.mst}' chứa ký tự không phải số")
        if len(mst_clean) not in (10, 13):
            raise ValueError(
                f"MST '{self.mst}' có {len(mst_clean)} ký tự — phải là 10 hoặc 13"
            )
        return self


class KiemTraHoaDonInput(BaseModel):
    """Schema đầu vào cho công cụ xác thực hóa đơn điện tử."""
    mst_nguoi_ban: StrictStr = Field(
        ...,
        description="MST người bán trên hóa đơn",
    )
    so_hoa_don: StrictStr = Field(
        ...,
        description="Số hóa đơn cần xác thực",
    )
    ngay_xuat: StrictStr = Field(
        ...,
        description="Ngày xuất hóa đơn (YYYY-MM-DD)",
    )


# ---------------------------------------------------------------------------
# MCP Tool Implementations
# ---------------------------------------------------------------------------

@mcp_tool("tra_cuu_mst")
async def tra_cuu_mst(params: TraCuuMSTInput) -> dict[str, Any]:
    """
    Tra cứu tình trạng Mã số thuế trên hệ thống Tổng cục Thuế.

    Trả về thông tin: tên DN, địa chỉ, người đại diện, tình trạng hoạt động,
    và cảnh báo nếu DN nằm trong danh sách đen.
    """
    tool_name = "tra_cuu_mst"
    _nhat_ky(tool_name, params.model_dump())

    try:
        result = await _mock_tra_cuu_mst(params.mst)
        return {"status": "ok", "cong_cu": tool_name, "du_lieu": result}
    except Exception as exc:
        logger.exception("Lỗi không mong đợi trong %s", tool_name)
        return {
            "status": "error", "cong_cu": tool_name,
            "loai_loi": type(exc).__name__, "thong_bao": str(exc),
        }


@mcp_tool("kiem_tra_hoa_don")
async def kiem_tra_hoa_don(params: KiemTraHoaDonInput) -> dict[str, Any]:
    """
    Xác thực hóa đơn điện tử trên hệ thống tracuuhoadon.gdt.gov.vn.

    Kiểm tra hóa đơn có tồn tại trên hệ thống Tổng cục Thuế hay không.
    """
    tool_name = "kiem_tra_hoa_don"
    _nhat_ky(tool_name, params.model_dump())

    try:
        result = await _mock_kiem_tra_hoa_don(
            params.mst_nguoi_ban,
            params.so_hoa_don,
            params.ngay_xuat,
        )
        return {"status": "ok", "cong_cu": tool_name, "du_lieu": result}
    except Exception as exc:
        logger.exception("Lỗi không mong đợi trong %s", tool_name)
        return {
            "status": "error", "cong_cu": tool_name,
            "loai_loi": type(exc).__name__, "thong_bao": str(exc),
        }
