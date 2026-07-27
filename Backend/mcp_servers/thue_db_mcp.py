# =============================================================================
# TrustAgent :: Thuế DB MCP Server — Tra Cứu MST từ Local Cache
# Bản quyền: TrustAgent bởi Đoàn Hoàng Việt (Việt Gamer)
# =============================================================================
# MCP Server tra cứu MST từ PostgreSQL nội bộ (Local Data Cache).
# Thay vì gọi API Tổng cục Thuế qua mạng, agent tra cứu bảng
# `danh_muc_doanh_nghiep` trong database nội bộ → latency < 5ms.
#
# Dữ liệu được nạp vào DB từ module `data_pipeline/mst_scraper.py`.
# =============================================================================

from __future__ import annotations

import asyncio
import json
import logging
import os
from datetime import datetime, timezone
from typing import Any, Callable

from pydantic import BaseModel, Field, StrictStr, model_validator
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text

logger = logging.getLogger("trustagent.mcp.thue_db")

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql+asyncpg://postgres:postgres@localhost:5432/trustagent_db")

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
    Chỉ sử dụng Dữ liệu thực tế, KHÔNG DÙNG MOCK DATA.
    Trả None nếu không tìm thấy.
    """
    engine = create_async_engine(DATABASE_URL, echo=False)
    try:
        async with engine.connect() as conn:
            stmt = text("SELECT mst, ten_doanh_nghiep, nguoi_dai_dien, dang_hoat_dong FROM danh_muc_doanh_nghiep WHERE mst = :mst")
            result = await conn.execute(stmt, {"mst": mst})
            row = result.fetchone()

            if row is None:
                return None

            return {
                "mst": row[0],
                "ten_doanh_nghiep": row[1],
                "nguoi_dai_dien": row[2],
                "tinh_trang": "Đang hoạt động" if row[3] else "Ngừng hoạt động",
                "canh_bao": "Công ty đã ngừng hoạt động/Bỏ trốn" if not row[3] else None,
                "nguon": "local_db"
            }
    except Exception as exc:
        logger.error("[ThueDB MCP] Lỗi khi truy vấn DB: %s", exc)
        return None
    finally:
        await engine.dispose()


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
    Không dùng Mock data theo chuẩn Phase 3.1.
    """
    tool_name = "tra_cuu_mst_local"
    _nhat_ky(tool_name, params.model_dump())

    try:
        result = await _query_mst_from_db(params.mst)
        
        if result is None:
            return {
                "status": "not_found",
                "cong_cu": tool_name,
                "thong_bao": f"MST {params.mst} không tồn tại trong DB nội bộ."
            }

        return {
            "status": "ok",
            "cong_cu": tool_name,
            "nguon_tra_cuu": "local_db",
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
    """
    tool_name = "kiem_tra_mst_danh_sach"
    _nhat_ky(tool_name, {"so_mst": len(params.danh_sach_mst)})

    try:
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

        danh_sach_den = [
            r for r in ket_qua
            if r.get("canh_bao") or r.get("tinh_trang", "").lower() != "đang hoạt động"
        ]

        return {
            "status": "ok",
            "cong_cu": tool_name,
            "tong_kiem_tra": len(params.danh_sach_mst),
            "tim_thay_trong_db": len(ket_qua),
            "khong_co_data": len(cho_bo_sung),
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
