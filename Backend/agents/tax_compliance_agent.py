# =============================================================================
# TrustAgent :: Tuân Thủ Agent (Compliance Agent)
# Bản quyền: TrustAgent bởi Đoàn Hoàng Việt (Việt Gamer)
# =============================================================================
# Agent chuyên trách đối chiếu hóa đơn với cơ sở dữ liệu Tổng cục Thuế.
#
# Gọi MCP tools:
#   - tra_cuu_mst      : Tra cứu tình trạng Mã số thuế
#   - kiem_tra_hoa_don  : Xác thực hóa đơn trên hệ thống TCT
#
# Kiểm tra:
#   - MST có đang hoạt động hay không (danh sách đen)
#   - Hóa đơn có tồn tại trên hệ thống TCT không
#   - Ngày logic: hóa đơn xuất trước ngày ký hợp đồng
#   - Kiểm tra chéo: tần suất giao dịch bất thường
# =============================================================================

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from typing import Any

from core.state import TrustAgentState
from mcp_servers.thue_db_mcp import (
    tra_cuu_mst_local, TraCuuMSTLocalInput,
    kiem_tra_mst_danh_sach, KiemTraNhieuMSTInput,
)
from mcp_servers.thue_mcp import (
    kiem_tra_hoa_don, KiemTraHoaDonInput,
)


logger = logging.getLogger("trustagent.agents.tuan_thu")

MAX_THU_LAI: int = 3
TEN_AGENT: str = "tuan_thu_agent"


async def tuan_thu_agent_node(state: TrustAgentState) -> dict:
    """
    LangGraph node: Tuân Thủ Agent (Compliance Agent).

    Đối chiếu kết quả từ Chứng Từ Agent với cơ sở dữ liệu Tổng cục Thuế.
    """
    messages = list(state.get("messages", []))
    error_log = list(state.get("error_log", []))
    hoa_don_list = state.get("hoa_don_list", [])

    logger.info("[%s] Bắt đầu — %d hóa đơn cần đối chiếu", TEN_AGENT, len(hoa_don_list))
    messages.append({
        "role": "assistant",
        "agent": TEN_AGENT,
        "content": f"Bắt đầu đối chiếu tuân thủ cho {len(hoa_don_list)} hóa đơn.",
        "timestamp": datetime.now(tz=timezone.utc).isoformat(),
    })

    # ------------------------------------------------------------------
    # Bước 1: Thu thập tất cả MST người bán (unique)
    # ------------------------------------------------------------------
    mst_set: set[str] = set()
    for hd in hoa_don_list:
        mst = hd.get("mst_nguoi_ban", "")
        if mst:
            mst_set.add(mst)

    # ------------------------------------------------------------------
    # Bước 2: Batch tra cứu MST từ Local PostgreSQL Cache
    # ------------------------------------------------------------------
    ket_qua_mst: list[dict[str, Any]] = []
    loi_danh_sach_den: list[dict[str, Any]] = []

    if mst_set:
        batch_result = await _chay_voi_thu_lai(
            ham_cong_cu=kiem_tra_mst_danh_sach,
            doi_tuong_input=KiemTraNhieuMSTInput(danh_sach_mst=sorted(mst_set)),
            ten_cong_cu="kiem_tra_mst_danh_sach",
            error_log=error_log,
            messages=messages,
        )
        if batch_result is not None:
            ket_qua_mst = batch_result.get("ket_qua", [])

            messages.append({
                "role": "assistant",
                "agent": TEN_AGENT,
                "content": (
                    f"Tra cứu {len(mst_set)} MST từ PostgreSQL local cache. "
                    f"Tìm thấy {batch_result.get('tim_thay_trong_db', 0)} trong DB, "
                    f"{batch_result.get('khong_co_data', 0)} không có data."
                ),
                "timestamp": datetime.now(tz=timezone.utc).isoformat(),
            })

            # Xử lý danh sách đen từ kết quả batch
            for r in batch_result.get("danh_sach_den", []):
                tinh_trang = (r.get("tinh_trang") or "").lower()
                mst = r.get("mst", "")
                hd_lien_quan = [
                    hd.get("so_hoa_don") for hd in hoa_don_list
                    if hd.get("mst_nguoi_ban") == mst
                ]
                loi_danh_sach_den.append({
                    "mst": mst,
                    "ten_doanh_nghiep": r.get("ten_doanh_nghiep"),
                    "tinh_trang": tinh_trang,
                    "canh_bao": r.get("canh_bao", ""),
                    "hoa_don_lien_quan": hd_lien_quan,
                    "muc_do": "nghiêm trọng",
                })


    # ------------------------------------------------------------------
    # Bước 3: Xác thực hóa đơn trên hệ thống TCT
    # ------------------------------------------------------------------
    ket_qua_xac_thuc: list[dict[str, Any]] = []

    for hd in hoa_don_list:
        mst_ban = hd.get("mst_nguoi_ban", "")
        so_hd = hd.get("so_hoa_don", "")
        ngay = hd.get("ngay_xuat", "")

        if mst_ban and so_hd and ngay:
            result = await _chay_voi_thu_lai(
                ham_cong_cu=kiem_tra_hoa_don,
                doi_tuong_input=KiemTraHoaDonInput(
                    mst_nguoi_ban=mst_ban,
                    so_hoa_don=so_hd,
                    ngay_xuat=ngay,
                ),
                ten_cong_cu=f"kiem_tra_hoa_don:{so_hd}",
                error_log=error_log,
                messages=messages,
            )
            if result is not None:
                ket_qua_xac_thuc.append(result.get("du_lieu", {}))

    # ------------------------------------------------------------------
    # Bước 4: Kiểm tra ngày logic (hóa đơn xuất trước ngày ký hợp đồng)
    # ------------------------------------------------------------------
    loi_ngay_logic: list[dict[str, Any]] = []

    for hd in hoa_don_list:
        ghi_chu = hd.get("ghi_chu", "") or ""
        ngay_xuat_str = hd.get("ngay_xuat", "")

        # Tìm ngày ký hợp đồng trong ghi chú
        match = re.search(r"ký ngày (\d{4}-\d{2}-\d{2})", ghi_chu)
        if match and ngay_xuat_str:
            try:
                ngay_xuat = datetime.strptime(ngay_xuat_str, "%Y-%m-%d")
                ngay_ky_hd = datetime.strptime(match.group(1), "%Y-%m-%d")

                if ngay_xuat < ngay_ky_hd:
                    so_ngay_truoc = (ngay_ky_hd - ngay_xuat).days
                    loi_ngay_logic.append({
                        "so_hoa_don": hd.get("so_hoa_don"),
                        "ngay_xuat_hoa_don": ngay_xuat_str,
                        "ngay_ky_hop_dong": match.group(1),
                        "chenh_lech_ngay": so_ngay_truoc,
                        "mo_ta": (
                            f"Hóa đơn {hd.get('so_hoa_don')} xuất ngày {ngay_xuat_str} "
                            f"nhưng hợp đồng ký ngày {match.group(1)} — "
                            f"hóa đơn xuất TRƯỚC hợp đồng {so_ngay_truoc} ngày"
                        ),
                        "muc_do": "nghiêm trọng" if so_ngay_truoc > 30 else "cao",
                    })
            except ValueError:
                pass  # Bỏ qua lỗi parse ngày

    # ------------------------------------------------------------------
    # Tổng hợp kết quả
    # ------------------------------------------------------------------
    tat_ca_loi = len(loi_danh_sach_den) + len(loi_ngay_logic)
    hoa_don_khong_hop_le = [
        x for x in ket_qua_xac_thuc
        if x.get("ket_qua") == "không tìm thấy"
    ]

    findings: dict[str, Any] = {
        "status": "ok",
        "agent": TEN_AGENT,
        "ket_qua_mst": ket_qua_mst,
        "loi_danh_sach_den": loi_danh_sach_den,
        "loi_ngay_logic": loi_ngay_logic,
        "ket_qua_xac_thuc_hd": ket_qua_xac_thuc,
        "hoa_don_khong_hop_le_tct": hoa_don_khong_hop_le,
        "tong_loi": tat_ca_loi + len(hoa_don_khong_hop_le),
    }

    messages.append({
        "role": "assistant",
        "agent": TEN_AGENT,
        "content": (
            f"Đối chiếu tuân thủ hoàn tất. "
            f"Tra cứu {len(ket_qua_mst)} MST. "
            f"Phát hiện {len(loi_danh_sach_den)} MST trong danh sách đen, "
            f"{len(loi_ngay_logic)} lỗi ngày logic, "
            f"{len(hoa_don_khong_hop_le)} hóa đơn không tồn tại trên TCT."
        ),
        "timestamp": datetime.now(tz=timezone.utc).isoformat(),
    })
    logger.info("[%s] Hoàn tất — lỗi=%d", TEN_AGENT, findings["tong_loi"])

    # Gộp tất cả lỗi thuế
    tax_warnings = loi_danh_sach_den + loi_ngay_logic + hoa_don_khong_hop_le
    
    # Đánh dấu hoàn thành
    extracted_data = state.get("extracted_data", {}).copy()
    extracted_data["tax_compliance_agent"] = findings["status"]

    return {
        "messages": messages,
        "error_log": error_log,
        "ket_qua_mst": ket_qua_mst,
        "tax_warnings": tax_warnings,
        "extracted_data": extracted_data,
        "current_agent": "supervisor",
    }


# ---------------------------------------------------------------------------
# Helper thử lại tự sửa lỗi
# ---------------------------------------------------------------------------

async def _chay_voi_thu_lai(
    ham_cong_cu,
    doi_tuong_input,
    ten_cong_cu: str,
    error_log: list,
    messages: list,
) -> dict[str, Any] | None:
    """Gọi MCP tool tối đa MAX_THU_LAI lần. Trả None nếu hết lần thử."""
    for lan in range(1, MAX_THU_LAI + 1):
        try:
            result: dict[str, Any] = await ham_cong_cu(doi_tuong_input)

            if not isinstance(result, dict):
                raise ValueError(f"Kỳ vọng dict, nhận được {type(result).__name__}")
            if result.get("status") == "error":
                raise RuntimeError(
                    f"Công cụ trả lỗi: {result.get('loai_loi')} — {result.get('thong_bao')}"
                )

            logger.debug("[%s] '%s' thành công lần thử %d.", TEN_AGENT, ten_cong_cu, lan)
            return result

        except Exception as exc:
            error_log.append({
                "agent": TEN_AGENT,
                "cong_cu": ten_cong_cu,
                "lan_thu": lan,
                "loai_loi": type(exc).__name__,
                "thong_bao": str(exc),
                "thoi_gian": datetime.now(tz=timezone.utc).isoformat(),
            })
            messages.append({
                "role": "system",
                "agent": TEN_AGENT,
                "content": (
                    f"[Tự sửa lỗi] '{ten_cong_cu}' thất bại lần {lan}/{MAX_THU_LAI}: "
                    f"{type(exc).__name__}: {str(exc)[:120]}"
                ),
                "timestamp": datetime.now(tz=timezone.utc).isoformat(),
            })
            logger.warning(
                "[%s] '%s' lần %d/%d thất bại: %s",
                TEN_AGENT, ten_cong_cu, lan, MAX_THU_LAI, exc
            )

    logger.error("[%s] '%s' đã hết %d lần thử.", TEN_AGENT, ten_cong_cu, MAX_THU_LAI)
    return None
