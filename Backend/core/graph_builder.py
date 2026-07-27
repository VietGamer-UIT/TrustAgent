import logging
from langgraph.graph import StateGraph, END
from typing import Literal

from .state import TrustAgentState
from .supervisor import supervisor_node
from agents.document_agent import chung_tu_agent_node as document_agent_node
from agents.tax_compliance_agent import tuan_thu_agent_node as tax_compliance_agent_node
from agents.legal_agent import legal_agent_node

logger = logging.getLogger("trustagent.graph")

NODE_GIAM_SAT     = "supervisor"
NODE_DOCUMENT     = "document_agent"
NODE_TAX          = "tax_compliance_agent"
NODE_LEGAL        = "legal_agent"

def dinh_tuyen_tu_giam_sat(state: TrustAgentState) -> Literal["document_agent", "tax_compliance_agent", "legal_agent", "__end__"]:
    dich = state.get("current_agent", "XONG")
    if dich == NODE_DOCUMENT:
        return NODE_DOCUMENT
    if dich == NODE_TAX:
        return NODE_TAX
    if dich == NODE_LEGAL:
        return NODE_LEGAL
    return END

def build_trustagent_graph() -> StateGraph:
    logger.info("[GraphBuilder] Đang xây dựng đồ thị TrustAgent hợp nhất...")
    graph = StateGraph(TrustAgentState)

    graph.add_node(NODE_GIAM_SAT, supervisor_node)
    graph.add_node(NODE_DOCUMENT, document_agent_node)
    graph.add_node(NODE_TAX, tax_compliance_agent_node)
    graph.add_node(NODE_LEGAL, legal_agent_node)

    graph.set_entry_point(NODE_GIAM_SAT)

    graph.add_conditional_edges(
        source=NODE_GIAM_SAT,
        path=dinh_tuyen_tu_giam_sat,
        path_map={
            NODE_DOCUMENT: NODE_DOCUMENT,
            NODE_TAX: NODE_TAX,
            NODE_LEGAL: NODE_LEGAL,
            END: END,
        },
    )

    graph.add_edge(NODE_DOCUMENT, NODE_GIAM_SAT)
    graph.add_edge(NODE_TAX, NODE_GIAM_SAT)
    graph.add_edge(NODE_LEGAL, NODE_GIAM_SAT)

    compiled = graph.compile()
    logger.info("[GraphBuilder] StateGraph biên dịch thành công.")
    return compiled

if __name__ == "__main__":
    import asyncio
    logging.basicConfig(level=logging.INFO)
    
    async def run_smoke_test():
        graph = build_trustagent_graph()
        
        scenarios = ["tax_audit", "legal_verify", "full_audit"]
        for s in scenarios:
            print(f"\n{'='*50}\nChạy Smoke Test với Kịch bản: {s}\n{'='*50}")
            initial_state = TrustAgentState(
                incident_id=f"TEST-{s.upper()}",
                scenario_type=s,
                evidence_paths=[],
                extracted_data={},
                hoa_don_list=[],
                ket_qua_mst=[],
                tax_warnings=[],
                legal_violations=[],
                messages=[],
                error_log=[]
            )
            
            result = await graph.ainvoke(initial_state)
            print(f"Kịch bản '{s}' hoàn tất! Agent cuối cùng: {result.get('current_agent')}")
            print(f"Số vòng lặp: {result.get('iteration_count')}")
            print(f"Final Audit Log: {result.get('final_audit_log')}")
            
    asyncio.run(run_smoke_test())
