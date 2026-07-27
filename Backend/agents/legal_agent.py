import logging
import os
import json
from datetime import datetime, timezone

from core.state import TrustAgentState
from rag.retriever import get_legal_context
from z3_engine.solver import LegalSolver
import google.generativeai as genai

logger = logging.getLogger("trustagent.agents.legal")
TEN_AGENT = "legal_agent"

def _extract_contract_data(contract_text: str) -> dict:
    """Sử dụng LLM để trích xuất các thông số hợp đồng (Loại bỏ hoàn toàn Mock Data)"""
    default_data = {"tong_gia_tri": 0, "phat_vi_pham": 0, "thue_suat": 0}
    if not contract_text or not isinstance(contract_text, str):
        return default_data

    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        logger.warning("Không có GOOGLE_API_KEY, fallback về data rỗng.")
        return default_data

    try:
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel("gemini-1.5-flash")
        
        prompt = f"""Bạn là hệ thống trích xuất dữ liệu hợp đồng chuyên nghiệp.
Hãy đọc nội dung hợp đồng dưới đây và trả về định dạng JSON thuần túy.
Các trường bắt buộc:
- "tong_gia_tri": (số nguyên) Tổng giá trị hợp đồng (VND).
- "phat_vi_pham": (số nguyên) Tiền phạt vi phạm (VND). Nếu là %, hãy tính ra số tiền theo tong_gia_tri.
- "thue_suat": (số nguyên) Thuế suất (%). VD: 8 hoặc 10.

Nội dung hợp đồng:
{contract_text}
"""
        response = model.generate_content(prompt)
        result_text = response.text.strip()
        if result_text.startswith("```json"):
            result_text = result_text[7:-3].strip()
        elif result_text.startswith("```"):
            result_text = result_text[3:-3].strip()
            
        data = json.loads(result_text)
        return {
            "tong_gia_tri": data.get("tong_gia_tri", 0),
            "phat_vi_pham": data.get("phat_vi_pham", 0),
            "thue_suat": data.get("thue_suat", 0)
        }
    except Exception as e:
        logger.error(f"Lỗi khi trích xuất dữ liệu bằng LLM: {e}")
        return default_data

async def legal_agent_node(state: TrustAgentState) -> dict:
    """
    LangGraph node: Pháp lý Agent (Legal Agent).
    """
    messages = list(state.get("messages", []))
    legal_violations = list(state.get("legal_violations", []))
    incident_id = state.get("incident_id", "UNKNOWN")
    
    extracted_data = state.get("extracted_data", {})
    raw_contract = extracted_data.get("contract_data", "")
    
    if isinstance(raw_contract, dict):
        raw_contract = json.dumps(raw_contract, ensure_ascii=False)
        
    logger.info(f"[{TEN_AGENT}] Trích xuất thông tin hợp đồng bằng LLM (Real Data)...")
    contract_data = _extract_contract_data(raw_contract)
    
    logger.info(f"[{TEN_AGENT}] Kiểm tra pháp lý cho phiên {incident_id}")
    
    # 1. RAG Retrieval
    query = "Quy định về mức phạt vi phạm hợp đồng thương mại và thuế suất."
    legal_context = get_legal_context(query)
    logger.debug(f"[{TEN_AGENT}] Lấy ngữ cảnh RAG: {len(legal_context)} ký tự.")
    
    # 2. Z3 Solver Proof
    solver = LegalSolver()
    z3_status, violations = solver.check_compliance(contract_data, context_rules=legal_context)
    
    legal_violations.extend(violations)
    
    messages.append({
        "role": "assistant",
        "agent": TEN_AGENT,
        "content": (
            f"Kiểm tra pháp lý hoàn tất. Dữ liệu trích xuất LLM: {contract_data}. "
            f"Trạng thái Z3: {z3_status}. Vi phạm: {len(violations)}. "
            f"Ngữ cảnh RAG: {len(legal_context)} ký tự."
        ),
        "timestamp": datetime.now(tz=timezone.utc).isoformat(),
    })
    
    extracted_data_out = extracted_data.copy()
    extracted_data_out["legal_agent"] = z3_status
    extracted_data_out["parsed_contract"] = contract_data
    
    return {
        "messages": messages,
        "z3_status": z3_status,
        "legal_violations": legal_violations,
        "extracted_data": extracted_data_out,
        "current_agent": "supervisor"
    }
