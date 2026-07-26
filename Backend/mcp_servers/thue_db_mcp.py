# =============================================================================
# TrustAgent :: Thuế DB MCP Server — Tra Cứu MST từ Local Cache
# Bản quyền: TrustAgent bởi Đoàn Hoàng Việt (Việt Gamer)
# =============================================================================
# MCP Server tra cứu MST từ PostgreSQL nội bộ (Local Data Cache).
# Thay vì gọi API Tổng cục Thuế qua mạng, agent tra cứu bảng
# `danh_muc_doanh_nghiep` trong database nội bộ → latency < 5ms.
#
# Công cụ MCP:
#   - tra_cuu_mst_local      : Tra cứu MST từ PostgreSQL local cache
#   - kiem_tra_mst_danh_sach : Kiểm tra nhiều MST cùng lúc
#
# Fallback: Nếu không tìm thấy trong local cache → fallback sang mock data
# (giống thue_mcp.py cũ) để đảm bảo hoạt động kể cả khi DB chưa có data.
# =============================================================================

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Any, Callable

from pydantic import BaseModel, Field, StrictStr, model_validator

logger = logging.getLogger("trustagent.mcp.thue_db")

# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------
THUE_DB_TOOL_REGISTRY: dict[str, Callable] = {}


def mcp_tool(name: str):
    """Decorator đăng ký hàm vào THUE_DB_TOOL_REGISTRY."""
    def decorator(fn: Callable) -> Callable:
        THUE_DB_TOOL_REGISTRY[name] = fn
        logger.debug("Đã đăng ký công cụ Thuế-DB MCP: %s", name)
        return fn
    return decorator


def _nhat_ky(tool: str, params: dict[str, Any]) -> None:
    entry = {
        "su_kien": "goi_cong_cu_mcp",
        "thoi_gian": datetime.now(tz=timezone.utc).isoformat(),
        "may_chu": "thue_db_mcp",
        "cong_cu": tool,
        "tham_so": params,
    }
    logger.info(json.dumps(entry, ensure_ascii=False))


# ---------------------------------------------------------------------------
# Database query helper
# ---------------------------------------------------------------------------

async def _query_mst_from_db(mst: str) -> dict[str, Any] | None:
    """
    Tra cứu MST từ PostgreSQL local cache.
    Trả None nếu không tìm thấy hoặc DB không khả dụng.
    """
    try:
        from ..database.database import AsyncSessionFactory
        from ..data_pipeline.models_pipeline import DoanNghiep
        from sqlalchemy import select

        async with AsyncSessionFactory() as session:
            stmt = select(DoanNghiep).where(DoanNghiep.mst == mst)
            result = await session.execute(stmt)
            dn = result.scalar_one_or_none()

            if dn is None:
                return None

            return {
                "mst":             dn.mst,
                "ten_doanh_nghiep": dn.ten_doanh_nghiep,
                "dia_chi":         dn.dia_chi,
                "nguoi_dai_dien":  dn.nguoi_dai_dien,
                "ngay_cap":        dn.ngay_cap,
                "tinh_trang":      dn.tinh_trang,
                "co_quan_thue":    dn.co_quan_thue,
                "loai_hinh":       dn.loai_hinh,
                "canh_bao":        dn.canh_bao,
                "nguon":           dn.nguon,
                "cap_nhat_luc":    dn.cap_nhat_luc.isoformat() if dn.cap_nhat_luc else None,
            }

    except Exception as exc:
        logger.warning("[ThueDB MCP] DB không khả dụng: %s. Dùng fallback.", exc)
        return None


async def _fallback_mock(mst: str) -> dict[str, Any]:
    """
    Fallback: nếu DB không có data → dùng mock cũ từ thue_mcp.
    Đảm bảo hệ thống hoạt động kể cả khi pipeline chưa chạy.
    """
    try:
        from .thue_mcp import _mock_tra_cuu_mst
        return await _mock_tra_cuu_mst(mst)
    except ImportError:
        return {
            "mst": mst,
            "ten_doanh_nghiep": "Không tìm thấy (DB chưa có data)",
            "dia_chi": "—",
            "nguoi_dai_dien": "—",
            "ngay_cap": None,
            "tinh_trang": "không tìm thấy",
            "co_quan_thue": "—",
            "loai_hinh": "—",
            "canh_bao": "⚠️ Local cache chưa được nạp dữ liệu. Chạy pipeline seed.",
            "nguon": "fallback_mock",
        }


# ---------------------------------------------------------------------------
# Input Schemas
# ---------------------------------------------------------------------------

class TraCuuMSTLocalInput(BaseModel):
    """Schema đầu vào — tra cứu 1 MST từ local cache."""
    mst: StrictStr = Field(..., description="Mã số thuế cần tra cứu (10 hoặc 13 ký tự)")

    @model_validator(mode="after")
    def kiem_tra_format(self) -> "TraCuuMSTLocalInput":
        mst_clean = self.mst.replace("-", "").strip()
        if not mst_clean.isdigit():
            raise ValueError(f"MST '{self.mst}' chứa ký tự không phải số")
        if len(mst_clean) not in (10, 13):
            raise ValueError(f"MST '{self.mst}' có {len(mst_clean)} ký tự (phải 10 hoặc 13)")
        return self


class KiemTraNhieuMSTInput(BaseModel):
    """Schema đầu vào — kiểm tra nhiều MST cùng lúc."""
    danh_sach_mst: list[StrictStr] = Field(
        ...,
        min_length=1,
        max_length=50,
        description="Danh sách MST cần kiểm tra (tối đa 50)",
    )


# ---------------------------------------------------------------------------
# MCP Tool Implementations
# ---------------------------------------------------------------------------

@mcp_tool("tra_cuu_mst_local")
async def tra_cuu_mst_local(params: TraCuuMSTLocalInput) -> dict[str, Any]:
    """
    Tra cứu MST từ Local Cache (PostgreSQL).

    Luồng:
      1. Query bảng danh_muc_doanh_nghiep trong PostgreSQL nội bộ
      2. Nếu không tìm thấy → fallback sang mock data
      3. Trả về thông tin đầy đủ kèm cảnh báo (nếu có)

    Lợi thế: Latency < 5ms (so với API Internet 200-2000ms).
    """
    tool_name = "tra_cuu_mst_local"
    _nhat_ky(tool_name, params.model_dump())

    try:
        # Ưu tiên 1: Query local PostgreSQL cache
        result = await _query_mst_from_db(params.mst)
        nguon = "local_db"

        # Ưu tiên 2: Fallback nếu DB không có
        if result is None:
            result = await _fallback_mock(params.mst)
            nguon = "fallback_mock"
            logger.info("[ThueDB MCP] MST %s không có trong local cache → dùng fallback", params.mst)

        return {
            "status": "ok",
            "cong_cu": tool_name,
            "nguon_tra_cuu": nguon,
            "du_lieu": result,
        }

    except Exception as exc:
        logger.exception("Lỗi không mong đợi trong %s", tool_name)
        return {
            "status": "error", "cong_cu": tool_name,
            "loai_loi": type(exc).__name__, "thong_bao": str(exc),
        }


@mcp_tool("kiem_tra_mst_danh_sach")
async def kiem_tra_mst_danh_sach(params: KiemTraNhieuMSTInput) -> dict[str, Any]:
    """
    Kiểm tra nhiều MST cùng lúc từ Local Cache.
    Tất cả queries chạy song song (asyncio.gather) → nhanh hơn sequential.
    """
    tool_name = "kiem_tra_mst_danh_sach"
    _nhat_ky(tool_name, {"so_mst": len(params.danh_sach_mst)})

    try:
        # Chạy song song tất cả queries
        tasks = [
            _query_mst_from_db(mst) for mst in params.danh_sach_mst
        ]
        raw_results = await asyncio.gather(*tasks, return_exceptions=False)

        ket_qua = []
        cho_bo_sung: list[str] = []

        for mst, result in zip(params.danh_sach_mst, raw_results):
            if result is None:
                cho_bo_sung.append(mst)
            else:
                ket_qua.append(result)

        # Fallback cho các MST không có trong DB
        if cho_bo_sung:
            fallback_tasks = [_fallback_mock(mst) for mst in cho_bo_sung]
            fallback_results = await asyncio.gather(*fallback_tasks)
            ket_qua.extend(fallback_results)

        # Phân loại
        danh_sach_den = [
            r for r in ket_qua
            if r.get("canh_bao") or r.get("tinh_trang", "").lower() not in (
                "đang hoạt động", ""
            )
        ]

        return {
            "status": "ok",
            "cong_cu": tool_name,
            "tong_kiem_tra": len(params.danh_sach_mst),
            "tim_thay_trong_db": len(params.danh_sach_mst) - len(cho_bo_sung),
            "dung_fallback": len(cho_bo_sung),
            "so_vi_pham": len(danh_sach_den),
            "ket_qua": ket_qua,
            "danh_sach_den": danh_sach_den,
        }

    except Exception as exc:
        logger.exception("Lỗi không mong đợi trong %s", tool_name)
        return {
            "status": "error", "cong_cu": tool_name,
            "loai_loi": type(exc).__name__, "thong_bao": str(exc),
        }
