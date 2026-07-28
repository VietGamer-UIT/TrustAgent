"""
TrustAgent — Trạng thái chia sẻ giữa các Agent Node (Nghị định 356/2025/NĐ-CP)

AgentState là "ký ức" trung tâm của workflow LangGraph.
Mỗi node đọc từ state và trả về dict để cập nhật state.

Luồng:
    START → parse_node → legal_rag_node → verify_node → explain_node → END
"""

from __future__ import annotations

from typing import Any, TypedDict


class AgentState(TypedDict, total=False):
    """
    Trạng thái chia sẻ giữa tất cả nodes trong LangGraph workflow.

    LangGraph tự động merge dict trả về từ mỗi node vào state này.
    Dùng total=False để các field đều optional.

    Cập nhật theo từng node:
        parse_node      → user_input, scenario_type, z3_data, applicable_rules,
                          parse_confidence, parse_error, parsed_dp
        legal_rag_node  → legal_thresholds
        verify_node     → z3_status, is_compliant, violations, verify_time_ms, verify_error
        explain_node    → explanation, final_error
    """

    # ── Input ─────────────────────────────────────────────────────────────
    user_input: str                      # Mô tả hoạt động xử lý dữ liệu của người dùng

    # ── Kết quả parse (Phase 2 — Semantic Parser) ─────────────────────────
    scenario_type: str                   # "vn_data_protection" | "unknown"
    z3_data: dict[str, Any]             # Dict data đưa vào Z3 (từ ParseResult.to_z3_data())
    applicable_rules: list[str]          # Danh sách rule_names → ["vn_data_protection_nd356"]
    parse_confidence: float              # Độ tin cậy của LLM (0.0 - 1.0)
    parse_error: str | None             # Lỗi nếu parse thất bại

    # Dữ liệu chi tiết đã parse (để explain_node dùng)
    parsed_dp: dict[str, Any] | None    # ParsedVNDataProtection.model_dump()

    # ── Legal RAG Module (Phase 3.5) ──────────────────────────────────────
    legal_thresholds: dict[str, int]    # Ngưỡng pháp lý từ RAG:
                                        # {"CROSS_BORDER_DOSSIER_DAYS": 60,
                                        #  "BREACH_NOTICE_HOURS": 72, ...}

    # ── Kết quả verify Z3 (Phase 1 — Z3 Engine) ──────────────────────────
    z3_status: str                       # "SAT" | "UNSAT" | "UNKNOWN"
    is_compliant: bool                   # True nếu SAT
    violations: list[dict[str, Any]]     # Danh sách vi phạm (từ RuleViolation.model_dump())
    verify_time_ms: float               # Thời gian Z3 kiểm tra (ms)
    verify_error: str | None            # Lỗi nếu verify thất bại

    # ── Kết quả explain — AUDIT TRAIL LOG format ──────────────────────────
    explanation: str                     # Báo cáo theo format nghiêm ngặt

    # ── Lỗi chung ─────────────────────────────────────────────────────────
    final_error: str | None             # Lỗi không mong muốn toàn cục
