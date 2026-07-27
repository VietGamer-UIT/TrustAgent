# =============================================================================
# TrustAgent :: Chứng Từ Agent (Document Agent)
# Bản quyền: TrustAgent bởi Đoàn Hoàng Việt (Việt Gamer)
# =============================================================================
# Agent chuyên trách đọc và phân tích hóa đơn/hợp đồng.
#
# Gọi MCP tools:
#   - doc_nhan_hoa_don : OCR đọc hóa đơn
#   - doc_hop_dong     : OCR đọc hợp đồng
#
# Kiểm tra:
#   - Lỗi số học: Tiền hàng + VAT ≠ Tổng tiền
#   - Lỗi VAT: Tiền thuế VAT ≠ Tiền hàng × thuế suất / 100
#   - Trùng số hóa đơn
#   - Lỗi format MST
#
# Tự sửa lỗi:
#   - Thử lại tối đa 3 lần nếu công cụ MCP thất bại
# =============================================================================

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from core.state import TrustAgentState
from mcp_servers.ocr_mcp import (
    doc_nhan_hoa_don, DocHoaDonInput,
)

logger = logging.getLogger("trustagent.agents.chung_tu")

MAX_THU_LAI: int = 3
TEN_AGENT: str = "chung_tu_agent"


async def chung_tu_agent_node(state: TrustAgentState) -> dict:
    """
    LangGraph node: Chứng Từ Agent (Document Agent).

    Đọc toàn bộ hóa đơn từ đường dẫn trong state, bóc tách thông tin
    và kiểm tra lỗi số học, lỗi format.
    """
    messages = list(state.get("messages", []))
    error_log = list(state.get("error_log", []))
    duong_dan = state.get("evidence_paths", [])

    logger.info("[%s] Bắt đầu — %d chứng từ cần đọc", TEN_AGENT, len(duong_dan))
    messages.append({
        "role": "assistant",
        "agent": TEN_AGENT,
        "content": f"Bắt đầu đọc và phân tích {len(duong_dan)} file chứng từ.",
        "timestamp": datetime.now(tz=timezone.utc).isoformat(),
    })

    # ------------------------------------------------------------------
    # Bước 1: OCR đọc tất cả hóa đơn
    # ------------------------------------------------------------------
    tat_ca_hoa_don: list[dict[str, Any]] = []

    for duong_dan_file in duong_dan:
        result = await _chay_voi_thu_lai(
            ham_cong_cu=doc_nhan_hoa_don,
            doi_tuong_input=DocHoaDonInput(duong_dan=duong_dan_file),
            ten_cong_cu=f"doc_nhan_hoa_don:{duong_dan_file}",
            error_log=error_log,
            messages=messages,
        )
        if result is not None:
            du_lieu = result.get("du_lieu", {})
            # Nếu trả về tất cả hóa đơn (demo mode)
            if du_lieu.get("che_do") == "demo_tat_ca":
                tat_ca_hoa_don.extend(du_lieu.get("hoa_don", []))
            else:
                tat_ca_hoa_don.append(du_lieu)

    # ------------------------------------------------------------------
    # Bước 2: Kiểm tra lỗi số học
    # ------------------------------------------------------------------
    loi_so_hoc: list[dict[str, Any]] = []

    for hd in tat_ca_hoa_don:
        so_hd = hd.get("so_hoa_don", "?")
        tien_hang = hd.get("tien_hang", 0)
        thue_suat = hd.get("thue_suat_vat", 0)
        tien_vat = hd.get("tien_thue_vat", 0)
        tong_tien = hd.get("tong_tien", 0)

        # Kiểm tra VAT đúng không
        vat_dung = round(tien_hang * thue_suat / 100)
        if tien_vat != vat_dung:
            chenh_lech_vat = tien_vat - vat_dung
            loi_so_hoc.append({
                "so_hoa_don": so_hd,
                "loai_loi": "sai_vat",
                "mo_ta": (
                    f"Tiền thuế VAT ghi {tien_vat:,.0f} VNĐ, "
                    f"đúng phải là {vat_dung:,.0f} VNĐ "
                    f"(tiền hàng {tien_hang:,.0f} × {thue_suat}%). "
                    f"Chênh lệch: {chenh_lech_vat:+,.0f} VNĐ"
                ),
                "chenh_lech": chenh_lech_vat,
                "muc_do": "cao" if abs(chenh_lech_vat) > 100_000 else "trung bình",
            })

        # Kiểm tra tổng tiền đúng không
        tong_dung = tien_hang + vat_dung
        if tong_tien != tong_dung:
            chenh_lech_tong = tong_tien - tong_dung
            loi_so_hoc.append({
                "so_hoa_don": so_hd,
                "loai_loi": "sai_tong",
                "mo_ta": (
                    f"Tổng tiền ghi {tong_tien:,.0f} VNĐ, "
                    f"đúng phải là {tong_dung:,.0f} VNĐ "
                    f"(tiền hàng + VAT). "
                    f"Chênh lệch: {chenh_lech_tong:+,.0f} VNĐ"
                ),
                "chenh_lech": chenh_lech_tong,
                "muc_do": "cao" if abs(chenh_lech_tong) > 100_000 else "trung bình",
            })

    # ------------------------------------------------------------------
    # Bước 3: Kiểm tra trùng số hóa đơn
    # ------------------------------------------------------------------
    trung_so: list[dict[str, Any]] = []
    bo_dem_so: dict[str, list[dict]] = {}

    for hd in tat_ca_hoa_don:
        key = f"{hd.get('so_hoa_don', '')}_{hd.get('ky_hieu', '')}"
        bo_dem_so.setdefault(key, []).append(hd)

    for key, nhom in bo_dem_so.items():
        if len(nhom) > 1:
            trung_so.append({
                "so_hoa_don": nhom[0].get("so_hoa_don"),
                "ky_hieu": nhom[0].get("ky_hieu"),
                "so_lan_xuat_hien": len(nhom),
                "mo_ta": (
                    f"Hóa đơn số {nhom[0].get('so_hoa_don')} ký hiệu "
                    f"{nhom[0].get('ky_hieu')} xuất hiện {len(nhom)} lần"
                ),
                "muc_do": "nghiêm trọng",
            })

    # ------------------------------------------------------------------
    # Bước 4: Kiểm tra format MST
    # ------------------------------------------------------------------
    loi_format: list[dict[str, Any]] = []

    for hd in tat_ca_hoa_don:
        mst = hd.get("mst_nguoi_ban", "")
        so_hd = hd.get("so_hoa_don", "?")
        mst_clean = mst.replace("-", "").strip()

        if not mst_clean.isdigit():
            loi_format.append({
                "so_hoa_don": so_hd,
                "loai_loi": "mst_khong_hop_le",
                "mo_ta": f"MST '{mst}' chứa ký tự không phải số",
                "muc_do": "cao",
            })
        elif len(mst_clean) not in (10, 13):
            loi_format.append({
                "so_hoa_don": so_hd,
                "loai_loi": "mst_sai_do_dai",
                "mo_ta": f"MST '{mst}' có {len(mst_clean)} ký tự (phải 10 hoặc 13)",
                "muc_do": "cao",
            })

    # ------------------------------------------------------------------
    # Đánh giá tổng thể
    # ------------------------------------------------------------------
    tat_ca_loi = len(loi_so_hoc) + len(trung_so) + len(loi_format)
    all_tools_failed = len(tat_ca_hoa_don) == 0

    if all_tools_failed:
        logger.error("[%s] Tất cả công cụ đã hết lần thử lại.", TEN_AGENT)
        findings: dict[str, Any] = {
            "status": "exhausted_retries",
            "agent": TEN_AGENT,
            "thong_bao": "Tất cả công cụ OCR MCP thất bại sau khi thử lại tối đa.",
        }
    else:
        findings = {
            "status": "ok",
            "agent": TEN_AGENT,
            "tong_hoa_don": len(tat_ca_hoa_don),
            "hoa_don": tat_ca_hoa_don,
            "loi_so_hoc": loi_so_hoc,
            "trung_so": trung_so,
            "loi_format": loi_format,
            "tong_loi": tat_ca_loi,
        }

    messages.append({
        "role": "assistant",
        "agent": TEN_AGENT,
        "content": (
            f"Phân tích chứng từ hoàn tất. Trạng thái: {findings['status']}. "
            f"Đọc được {len(tat_ca_hoa_don)} hóa đơn. "
            f"Phát hiện {len(loi_so_hoc)} lỗi số học, "
            f"{len(trung_so)} trùng số, "
            f"{len(loi_format)} lỗi format."
        ),
        "timestamp": datetime.now(tz=timezone.utc).isoformat(),
    })
    logger.info("[%s] Hoàn tất — status=%s, lỗi=%d", TEN_AGENT, findings["status"], tat_ca_loi)

    # Hợp nhất các lỗi thuế vào tax_warnings
    tax_warnings = loi_so_hoc + trung_so + loi_format
    
    # Đánh dấu đã hoàn thành
    extracted_data = state.get("extracted_data", {}).copy()
    extracted_data["document_agent"] = findings["status"]

    return {
        "messages": messages,
        "error_log": error_log,
        "hoa_don_list": tat_ca_hoa_don,
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
