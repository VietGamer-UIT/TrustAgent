"""
TrustAgent.Forensics — LangGraph Graph Builder (Phase 3.5)

Xây dựng và compile StateGraph với Legal RAG Node.

Sơ đồ graph (cập nhật Phase 3.5):

    START
      │
      ▼
    parse_node              ← Semantic parsing (Gemini/Mock)
      │
      ├─ [UNKNOWN] ──────────────────────────────────┐
      │                                              │
      ▼                                              │
    legal_rag_node  ← **MỚI** Tra cứu ngưỡng luật   │
      │                  từ văn bản pháp lý (RAG)    │
      ▼                                              │
    verify_node             ← Z3 với ngưỡng động     │
      │                                              │
      ▼                                              ▼
    explain_node            ← Phản hồi thân thiện
      │
      ▼
     END
"""

from __future__ import annotations

try:
    from langgraph.graph import StateGraph, END, START
    LANGGRAPH_AVAILABLE = True
except ImportError:
    LANGGRAPH_AVAILABLE = False

from src.agents.state import AgentState
from src.agents.nodes import (
    parse_node,
    legal_rag_node,
    verify_node,
    explain_node,
    route_after_parse,
)


def build_graph():
    """
    Tạo và compile LangGraph StateGraph cho TrustAgent workflow (Phase 3.5).

    Returns:
        CompiledGraph nếu langgraph đã cài, MockGraph nếu chưa cài.
    """
    if not LANGGRAPH_AVAILABLE:
        return _MockGraph()

    # Tạo graph với AgentState là schema
    graph = StateGraph(AgentState)

    # Thêm tất cả nodes
    graph.add_node("parse", parse_node)
    graph.add_node("rag", legal_rag_node)     # Legal RAG Node (Phase 3.5)
    graph.add_node("verify", verify_node)
    graph.add_node("explain", explain_node)

    # Edge bắt đầu
    graph.add_edge(START, "parse")

    # Conditional routing sau parse:
    # - known scenario → legal_rag (lấy ngưỡng) → verify (Z3) → explain
    # - UNKNOWN         → explain (skip rag+verify)
    graph.add_conditional_edges(
        "parse",
        route_after_parse,
        {
            "rag": "rag",          # known → legal_rag_node
            "explain": "explain",  # UNKNOWN → skip
        },
    )

    graph.add_edge("rag", "verify")       # Sau RAG → Z3 verify
    graph.add_edge("verify", "explain")   # Sau verify → explain
    graph.add_edge("explain", END)

    return graph.compile()


class _MockGraph:
    """
    Graph giả lập khi langgraph chưa được cài.
    Chạy các nodes tuần tự (không có state machine thực sự).
    Dùng cho dev/test khi chưa cài langgraph.
    """

    def invoke(self, initial_state: dict) -> AgentState:
        """Chạy workflow tuần tự: parse → route → (rag → verify) → explain."""
        state: AgentState = dict(initial_state)  # type: ignore

        # Bước 1: Parse
        state.update(parse_node(state))

        # Bước 2: Route
        next_step = route_after_parse(state)

        # Bước 3: Legal RAG + Verify (nếu scenario xác định)
        if next_step == "rag":
            state.update(legal_rag_node(state))   # Lấy ngưỡng từ luật
            state.update(verify_node(state))       # Z3 với ngưỡng động

        # Bước 4: Explain
        state.update(explain_node(state))

        return state  # type: ignore
