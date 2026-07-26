# =============================================================================
# TrustAgent :: LangGraph Xây Dựng Đồ Thị Kiểm Tra Chứng Từ
# Bản quyền: TrustAgent bởi Đoàn Hoàng Việt (Việt Gamer)
# =============================================================================
# Xây dựng và biên dịch StateGraph cho luồng kiểm tra chứng từ đa tác nhân.
#
# Topology:
#
#   START
#     │
#     ▼
#   [supervisor] ──► dinh_tuyen()
#                         │
#                         ├── "chung_tu_agent" ──► [Chứng Từ Agent] ──┐
#                         ├── "tuan_thu_agent" ──► [Tuân Thủ Agent]  ──┤
#                         │                                             │
#                         │        ◄────────────────────────────────────┘
#                         │        (tất cả sub-agents quay lại supervisor)
#                         │
#                         └── KẾT THÚC  (khi current_agent == "XONG")
# =============================================================================

from __future__ import annotations

import logging
from typing import Literal

from langgraph.graph import StateGraph, END

from .state import TrangThaiKiemTra
from .supervisor import supervisor_node
from .chung_tu_agent import chung_tu_agent_node
from .tuan_thu_agent import tuan_thu_agent_node

logger = logging.getLogger("trustagent.graph")

# ---------------------------------------------------------------------------
# Tên node (nguồn chân lý duy nhất — tránh lỗi chính tả)
# ---------------------------------------------------------------------------
NODE_GIAM_SAT     = "supervisor"
NODE_CHUNG_TU     = "chung_tu_agent"
NODE_TUAN_THU     = "tuan_thu_agent"


# ---------------------------------------------------------------------------
# Hàm định tuyến có điều kiện
# ---------------------------------------------------------------------------

def dinh_tuyen_tu_giam_sat(
    state: TrangThaiKiemTra,
) -> Literal["chung_tu_agent", "tuan_thu_agent", "__end__"]:
    """
    Hàm edge có điều kiện: đọc state.current_agent và trả về
    tên node tiếp theo hoặc '__end__' để kết thúc graph.
    """
    dich = state.get("current_agent", "XONG")

    if dich == NODE_CHUNG_TU:
        logger.debug("[Router] supervisor → chung_tu_agent")
        return NODE_CHUNG_TU

    if dich == NODE_TUAN_THU:
        logger.debug("[Router] supervisor → tuan_thu_agent")
        return NODE_TUAN_THU

    # "XONG" hoặc giá trị bất kỳ → kết thúc graph
    logger.info("[Router] supervisor → KẾT THÚC (current_agent=%s)", dich)
    return END


# ---------------------------------------------------------------------------
# Xây dựng đồ thị
# ---------------------------------------------------------------------------

def build_ir_graph() -> StateGraph:
    """
    Xây dựng, cấu hình và biên dịch StateGraph kiểm tra chứng từ.

    Các bước:
      1. Khởi tạo StateGraph với TrangThaiKiemTra.
      2. Thêm tất cả agent nodes.
      3. Đặt điểm vào là supervisor.
      4. Thêm conditional edges từ supervisor.
      5. Thêm unconditional return edges.
      6. Biên dịch và trả về.

    Returns:
        StateGraph đã biên dịch, sẵn sàng cho .invoke() / .ainvoke().
    """
    logger.info("[GraphBuilder] Đang xây dựng đồ thị TrustAgent...")

    # 1. Khởi tạo graph
    graph = StateGraph(TrangThaiKiemTra)

    # 2. Đăng ký nodes
    graph.add_node(NODE_GIAM_SAT, supervisor_node)
    graph.add_node(NODE_CHUNG_TU, chung_tu_agent_node)
    graph.add_node(NODE_TUAN_THU, tuan_thu_agent_node)

    logger.debug("[GraphBuilder] Nodes: %s", [
        NODE_GIAM_SAT, NODE_CHUNG_TU, NODE_TUAN_THU,
    ])

    # 3. Điểm vào
    graph.set_entry_point(NODE_GIAM_SAT)

    # 4. Conditional edges: supervisor → agents hoặc END
    graph.add_conditional_edges(
        source=NODE_GIAM_SAT,
        path=dinh_tuyen_tu_giam_sat,
        path_map={
            NODE_CHUNG_TU: NODE_CHUNG_TU,
            NODE_TUAN_THU: NODE_TUAN_THU,
            END:           END,
        },
    )

    # 5. Unconditional return edges: agent → supervisor
    graph.add_edge(NODE_CHUNG_TU, NODE_GIAM_SAT)
    graph.add_edge(NODE_TUAN_THU, NODE_GIAM_SAT)

    logger.debug("[GraphBuilder] Edges đã cấu hình.")

    # 6. Biên dịch
    compiled = graph.compile()

    logger.info("[GraphBuilder] StateGraph biên dịch thành công.")
    return compiled


# ---------------------------------------------------------------------------
# Test nhanh (chạy: python -m Backend.FastAPI.ir_agents.graph_builder)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import asyncio
    import json
    import logging

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    )

    async def _chay_demo():
        """Smoke test toàn bộ luồng kiểm tra chứng từ."""
        print("\n" + "=" * 70)
        print("  TrustAgent — Kiểm Thử Hệ Thống Đa Tác Nhân")
        print("=" * 70)

        do_thi = build_ir_graph()

        # Trạng thái khởi tạo — mô phỏng kiểm toán viên gửi hóa đơn
        trang_thai_ban_dau: TrangThaiKiemTra = {
            "ma_phien": "KT-2024-DEMO-001",
            "duong_dan_chung_tu": [
                "/hoa_don/tat_ca.pdf",  # Demo mode → trả tất cả hóa đơn
            ],
            "messages":       [],
            "error_log":      [],
            "retry_count":    0,
            "iteration_count": 0,
        }

        print(f"\n[+] Khởi động kiểm tra phiên: {trang_thai_ban_dau['ma_phien']}")
        print(f"[+] Đường dẫn chứng từ: {trang_thai_ban_dau['duong_dan_chung_tu']}\n")

        ket_qua = await do_thi.ainvoke(trang_thai_ban_dau)

        print("\n" + "=" * 70)
        print("  BÁO CÁO KIỂM TRA CHỨNG TỪ")
        print("=" * 70)
        print(json.dumps(ket_qua.get("bao_cao_kiem_tra"), indent=2, ensure_ascii=False))

        print("\n" + "=" * 70)
        print(f"  Tổng vòng lặp: {ket_qua.get('iteration_count')}")
        print(f"  Số lỗi ghi nhận: {len(ket_qua.get('error_log', []))}")
        print(f"  Số tin nhắn: {len(ket_qua.get('messages', []))}")
        print("=" * 70 + "\n")

    asyncio.run(_chay_demo())
