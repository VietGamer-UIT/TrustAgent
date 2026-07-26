# =============================================================================
# TrustAgent :: Giám Sát Agent (Supervisor)
# Bản quyền: TrustAgent bởi Đoàn Hoàng Việt (Việt Gamer)
# =============================================================================
# Giám Sát là bộ điều phối trung tâm của luồng LangGraph kiểm tra chứng từ.
#
# Trách nhiệm:
#   1. TIẾP NHẬN : Nhận yêu cầu kiểm tra, khởi tạo giá trị mặc định.
#   2. ĐIỀU PHỐI : Quyết định agent chuyên trách nào chạy tiếp theo.
#   3. TỔNG HỢP : Khi tất cả agent đã báo cáo (hoặc hết vòng lặp),
#                  tạo báo cáo kiểm tra chứng từ cuối cùng.
#
# Điều kiện kết thúc (theo thứ tự ưu tiên):
#   A. Tất cả sub-agents đã trả về findings != None  → "hoàn tất"
#   B. iteration_count >= MAX_ITERATIONS (15)         → "một phần"
#   C. Lỗi không thể khắc phục ở tất cả agents      → "thất bại"
#
# Sử dụng router xác định (không LLM) để giữ tốc độ và kiểm toán được.
# =============================================================================

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from .state import TrangThaiKiemTra

logger = logging.getLogger("trustagent.agents.supervisor")

# ---------------------------------------------------------------------------
# Hằng số
# ---------------------------------------------------------------------------
MAX_ITERATIONS: int = 15
AGENTS_THEO_THU_TU: list[str] = [
    "chung_tu_agent",     # 1. Đọc & phân tích chứng từ
    "tuan_thu_agent",     # 2. Đối chiếu tuân thủ
]


# ---------------------------------------------------------------------------
# Node chính
# ---------------------------------------------------------------------------

async def supervisor_node(state: TrangThaiKiemTra) -> TrangThaiKiemTra:
    """
    LangGraph node: Giám Sát / Bộ Điều Phối Trung Tâm.

    Được gọi khi bắt đầu graph và sau mỗi sub-agent hoàn tất.
    """
    ma_phien: str = state.get("ma_phien", "UNKNOWN")
    iteration_count: int = state.get("iteration_count", 0) + 1

    logger.info(
        "[Giám Sát] Vòng #%d cho phiên=%s", iteration_count, ma_phien
    )

    # --- Ghi nhật ký ---
    messages: list[dict[str, Any]] = list(state.get("messages", []))
    messages.append({
        "role": "system",
        "agent": "supervisor",
        "content": f"Giám Sát vòng #{iteration_count} — đánh giá bước tiếp theo.",
        "timestamp": datetime.now(tz=timezone.utc).isoformat(),
    })

    # --- Giới hạn vòng lặp ---
    if iteration_count >= MAX_ITERATIONS:
        logger.warning(
            "[Giám Sát] Hết giới hạn %d vòng cho phiên=%s — tạo báo cáo một phần.",
            MAX_ITERATIONS, ma_phien,
        )
        report = _tao_bao_cao(state, trang_thai="một phần", so_vong_lap=iteration_count)
        return {
            **state,
            "messages": messages,
            "iteration_count": iteration_count,
            "current_agent": "XONG",
            "bao_cao_kiem_tra": report,
        }

    # --- Kiểm tra agent nào chưa chạy ---
    agent_tiep = _quyet_dinh_agent_tiep(state)

    if agent_tiep is None:
        # Tất cả đã hoàn tất → tổng hợp báo cáo
        logger.info("[Giám Sát] Tất cả agent hoàn tất — tổng hợp báo cáo.")
        report = _tao_bao_cao(state, trang_thai="hoàn tất", so_vong_lap=iteration_count)
        messages.append({
            "role": "assistant",
            "agent": "supervisor",
            "content": "Tất cả agent chuyên trách đã báo cáo. Đã tổng hợp báo cáo kiểm tra chứng từ.",
            "timestamp": datetime.now(tz=timezone.utc).isoformat(),
        })
        return {
            **state,
            "messages": messages,
            "iteration_count": iteration_count,
            "current_agent": "XONG",
            "bao_cao_kiem_tra": report,
        }

    # --- Điều phối tới agent tiếp theo ---
    logger.info("[Giám Sát] Điều phối tới: %s", agent_tiep)
    messages.append({
        "role": "assistant",
        "agent": "supervisor",
        "content": f"Điều phối tới {agent_tiep}.",
        "timestamp": datetime.now(tz=timezone.utc).isoformat(),
    })

    return {
        **state,
        "messages": messages,
        "iteration_count": iteration_count,
        "current_agent": agent_tiep,
        "retry_count": 0,
    }


# ---------------------------------------------------------------------------
# Logic điều phối
# ---------------------------------------------------------------------------

def _quyet_dinh_agent_tiep(state: TrangThaiKiemTra) -> str | None:
    """
    Xác định sub-agent nào nên chạy tiếp.
    Chiến lược: chạy theo thứ tự cố định, bỏ qua agent đã có findings.
    """
    chung_tu_xong = _findings_da_co(state.get("chung_tu_findings"))
    tuan_thu_xong = _findings_da_co(state.get("tuan_thu_findings"))

    trang_thai = {
        "chung_tu_agent": chung_tu_xong,
        "tuan_thu_agent": tuan_thu_xong,
    }

    for agent in AGENTS_THEO_THU_TU:
        if not trang_thai[agent]:
            return agent

    return None


def _findings_da_co(findings: dict[str, Any] | None) -> bool:
    """Trả True nếu findings đã tồn tại và không cần chạy lại."""
    if findings is None:
        return False
    return findings.get("status") in {"ok", "exhausted_retries"}


# ---------------------------------------------------------------------------
# Tổng hợp báo cáo
# ---------------------------------------------------------------------------

def _tao_bao_cao(
    state: TrangThaiKiemTra,
    trang_thai: str,
    so_vong_lap: int,
) -> dict[str, Any]:
    """
    Tổng hợp báo cáo kiểm tra chứng từ cuối cùng từ findings của tất cả agents.
    """
    ma_phien = state.get("ma_phien", "UNKNOWN")
    chung_tu = state.get("chung_tu_findings") or {}
    tuan_thu = state.get("tuan_thu_findings") or {}
    error_log = state.get("error_log", [])

    # --- Tổng hợp tất cả cảnh báo ---
    danh_sach_canh_bao: list[dict[str, Any]] = []

    # Lỗi số học từ Chứng Từ Agent
    for loi in chung_tu.get("loi_so_hoc", []):
        danh_sach_canh_bao.append({
            "loai": "lỗi số học",
            "so_hoa_don": loi.get("so_hoa_don"),
            "mo_ta": loi.get("mo_ta"),
            "muc_do": loi.get("muc_do", "trung bình"),
            "nguon": "Chứng Từ Agent",
        })

    # Trùng số hóa đơn
    for loi in chung_tu.get("trung_so", []):
        danh_sach_canh_bao.append({
            "loai": "trùng số hóa đơn",
            "so_hoa_don": loi.get("so_hoa_don"),
            "mo_ta": loi.get("mo_ta"),
            "muc_do": loi.get("muc_do", "nghiêm trọng"),
            "nguon": "Chứng Từ Agent",
        })

    # Lỗi format
    for loi in chung_tu.get("loi_format", []):
        danh_sach_canh_bao.append({
            "loai": "lỗi format MST",
            "so_hoa_don": loi.get("so_hoa_don"),
            "mo_ta": loi.get("mo_ta"),
            "muc_do": loi.get("muc_do", "cao"),
            "nguon": "Chứng Từ Agent",
        })

    # MST trong danh sách đen
    for loi in tuan_thu.get("loi_danh_sach_den", []):
        for so_hd in loi.get("hoa_don_lien_quan", []):
            danh_sach_canh_bao.append({
                "loai": "MST danh sách đen",
                "so_hoa_don": so_hd,
                "mo_ta": (
                    f"MST {loi.get('mst')} — {loi.get('ten_doanh_nghiep')} — "
                    f"tình trạng: {loi.get('tinh_trang')}. {loi.get('canh_bao', '')}"
                ),
                "muc_do": "nghiêm trọng",
                "nguon": "Tuân Thủ Agent",
            })

    # Lỗi ngày logic
    for loi in tuan_thu.get("loi_ngay_logic", []):
        danh_sach_canh_bao.append({
            "loai": "lỗi ngày logic",
            "so_hoa_don": loi.get("so_hoa_don"),
            "mo_ta": loi.get("mo_ta"),
            "muc_do": loi.get("muc_do", "cao"),
            "nguon": "Tuân Thủ Agent",
        })

    # Hóa đơn không tồn tại trên TCT
    for hd in tuan_thu.get("hoa_don_khong_hop_le_tct", []):
        danh_sach_canh_bao.append({
            "loai": "hóa đơn không hợp lệ TCT",
            "so_hoa_don": hd.get("so_hoa_don"),
            "mo_ta": hd.get("thong_bao"),
            "muc_do": "nghiêm trọng",
            "nguon": "Tuân Thủ Agent",
        })

    # --- Đánh giá mức độ rủi ro tổng thể ---
    muc_do = _danh_gia_rui_ro(danh_sach_canh_bao)

    # --- Tạo khuyến nghị ---
    khuyen_nghi = _tao_khuyen_nghi(danh_sach_canh_bao, chung_tu, tuan_thu)

    # --- Kết quả MST cho bảng hiển thị ---
    ket_qua_mst = tuan_thu.get("ket_qua_mst", [])

    return {
        "ma_phien": ma_phien,
        "trang_thai": trang_thai,
        "muc_do_rui_ro": muc_do,
        "tom_tat": _tao_tom_tat(ma_phien, muc_do, trang_thai, danh_sach_canh_bao, error_log),
        "danh_sach_canh_bao": danh_sach_canh_bao,
        "ket_qua_mst": ket_qua_mst,
        "khuyen_nghi": khuyen_nghi,
        "agents_da_chay": AGENTS_THEO_THU_TU,
        "so_loi": len(error_log),
        "so_vong_lap": so_vong_lap,
        "hoan_tat_luc": datetime.now(tz=timezone.utc).isoformat(),
    }


def _danh_gia_rui_ro(canh_bao: list[dict]) -> str:
    """Đánh giá mức độ rủi ro dựa trên danh sách cảnh báo."""
    co_nghiem_trong = any(c.get("muc_do") == "nghiêm trọng" for c in canh_bao)
    co_cao = any(c.get("muc_do") == "cao" for c in canh_bao)
    co_trung_binh = any(c.get("muc_do") == "trung bình" for c in canh_bao)

    if co_nghiem_trong:
        return "nghiêm trọng"
    elif co_cao:
        return "cao"
    elif co_trung_binh:
        return "trung bình"
    return "thấp"


def _tao_khuyen_nghi(
    canh_bao: list[dict],
    chung_tu: dict,
    tuan_thu: dict,
) -> list[str]:
    """Tạo danh sách khuyến nghị cho kiểm toán viên."""
    kn: list[str] = []

    # Kiểm tra MST danh sách đen
    for c in canh_bao:
        if c.get("loai") == "MST danh sách đen":
            kn.append(
                f"LOẠI BỎ: Hóa đơn {c.get('so_hoa_don')} từ doanh nghiệp "
                f"trong danh sách đen — không được khấu trừ thuế GTGT."
            )

    # Kiểm tra lỗi số học
    loi_so_hoc = [c for c in canh_bao if c.get("loai") == "lỗi số học"]
    if loi_so_hoc:
        kn.append(
            f"KIỂM TRA: {len(loi_so_hoc)} hóa đơn có sai lệch số học — "
            "yêu cầu người bán xuất lại hóa đơn hoặc biên bản điều chỉnh."
        )

    # Kiểm tra trùng số
    trung = [c for c in canh_bao if c.get("loai") == "trùng số hóa đơn"]
    if trung:
        kn.append(
            f"CẢNH BÁO: {len(trung)} hóa đơn trùng số — "
            "có thể là hóa đơn giả hoặc khai trùng chi phí. Kiểm tra kỹ."
        )

    # Kiểm tra ngày logic
    ngay = [c for c in canh_bao if c.get("loai") == "lỗi ngày logic"]
    if ngay:
        kn.append(
            f"XÁC MINH: {len(ngay)} hóa đơn xuất TRƯỚC ngày ký hợp đồng — "
            "dấu hiệu hợp thức hóa chi phí. Yêu cầu giải trình từ khách hàng."
        )

    # Hóa đơn không tồn tại trên TCT
    khong_hop_le = [c for c in canh_bao if c.get("loai") == "hóa đơn không hợp lệ TCT"]
    if khong_hop_le:
        kn.append(
            f"NGHIÊM TRỌNG: {len(khong_hop_le)} hóa đơn không tồn tại trên "
            "hệ thống Tổng cục Thuế — nghi vấn hóa đơn giả."
        )

    if not kn:
        kn.append(
            "TIẾP TỤC GIÁM SÁT: Không phát hiện lỗi nghiêm trọng trong bộ chứng từ này. "
            "Khuyến nghị tiếp tục kiểm tra mẫu."
        )

    return kn


def _tao_tom_tat(
    ma_phien: str,
    muc_do: str,
    trang_thai: str,
    canh_bao: list[dict],
    error_log: list,
) -> str:
    """Tạo đoạn tóm tắt văn bản cho báo cáo."""
    ghi_chu_loi = (
        f" Có {len(error_log)} lỗi công cụ trong quá trình phân tích."
        if error_log else ""
    )

    so_nghiem_trong = sum(1 for c in canh_bao if c.get("muc_do") == "nghiêm trọng")
    so_cao = sum(1 for c in canh_bao if c.get("muc_do") == "cao")

    return (
        f"[TrustAgent] Phiên kiểm tra {ma_phien} đã {trang_thai.upper()}. "
        f"Mức độ rủi ro tổng thể: {muc_do.upper()}. "
        f"Phát hiện {len(canh_bao)} cảnh báo "
        f"({so_nghiem_trong} nghiêm trọng, {so_cao} cao). "
        f"Hai agent chuyên trách (Chứng Từ, Tuân Thủ) đã phân tích bộ chứng từ.{ghi_chu_loi}"
    )
