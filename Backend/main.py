import os
import shutil
import uuid
import json
from typing import List, Optional

import google.generativeai as genai
from rag.retriever import get_legal_context

from fastapi import FastAPI, UploadFile, File, Form
from pydantic import BaseModel
from loguru import logger

from core.graph_builder import build_trustagent_graph
from core.state import TrustAgentState

app = FastAPI(title="TrustAgent API", version="1.0.0")

# Khởi tạo Graph
graph = build_trustagent_graph()

UPLOAD_DIR = os.path.join(os.path.dirname(__file__), "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

class AuditResponse(BaseModel):
    incident_id: str
    status: str
    final_audit_log: dict

@app.post("/api/v1/kiem-tra/chung-tu", response_model=AuditResponse)
async def kiem_tra_chung_tu(
    files: Optional[List[UploadFile]] = File(None),
    contract_data: Optional[str] = Form(None)
):
    incident_id = str(uuid.uuid4())
    logger.info(f"Bắt đầu phiên kiểm toán mới: {incident_id}")
    
    evidence_paths = []
    
    # Xử lý lưu file tạm thời
    if files:
        for file in files:
            file_path = os.path.join(UPLOAD_DIR, f"{incident_id}_{file.filename}")
            with open(file_path, "wb") as buffer:
                shutil.copyfileobj(file.file, buffer)
            evidence_paths.append(file_path)
            
    # Parse hợp đồng
    parsed_contract_data = {}
    if contract_data:
        try:
            parsed_contract_data = json.loads(contract_data)
        except json.JSONDecodeError:
            logger.warning("Không thể parse contract_data từ JSON.")

    # Khởi tạo state cho Graph
    initial_state: TrustAgentState = {
        "incident_id": incident_id,
        "evidence_paths": evidence_paths,
        "extracted_data": {"contract_data": parsed_contract_data},
        "hoa_don_list": [],
        "ket_qua_mst": [],
        "tax_warnings": [],
        "z3_status": "UNKNOWN",
        "legal_violations": [],
        "current_agent": "supervisor",
        "messages": [],
        "error_log": [],
        "final_audit_log": {}
    }

    # Kích hoạt luồng Graph
    logger.info("Đang kích hoạt LangGraph Supervisor...")
    final_state = await graph.ainvoke(initial_state)

    # Lấy kết quả cuối cùng từ compiler_node
    audit_log = final_state.get("final_audit_log", {})

    # Dọn dẹp file tạm
    for p in evidence_paths:
        if os.path.exists(p):
            try:
                os.remove(p)
            except OSError as e:
                logger.error(f"Lỗi khi xóa file tạm {p}: {e}")

    logger.info(f"Phiên kiểm toán hoàn tất: {incident_id}")

    return AuditResponse(
        incident_id=incident_id,
        status="COMPLETED",
        final_audit_log=audit_log
    )

class LegalQueryRequest(BaseModel):
    query: str

class LegalQueryResponse(BaseModel):
    answer: str
    context: str

@app.post("/api/v1/tra-cuu-luat", response_model=LegalQueryResponse)
async def tra_cuu_luat(request: LegalQueryRequest):
    query = request.query
    logger.info(f"Tra cứu luật pháp: {query}")
    
    context = get_legal_context(query)
    answer = ""
    
    api_key = os.getenv("GOOGLE_API_KEY")
    if api_key:
        try:
            genai.configure(api_key=api_key)
            model = genai.GenerativeModel("gemini-1.5-flash")
            prompt = f"Bạn là một chuyên gia pháp lý Việt Nam. Dựa vào ngữ cảnh sau để trả lời câu hỏi.\n\nNgữ cảnh:\n{context}\n\nCâu hỏi: {query}\n\nTrả lời ngắn gọn, chuyên nghiệp và có trích dẫn:"
            response = model.generate_content(prompt)
            answer = response.text
        except Exception as e:
            logger.error(f"Lỗi khi gọi Gemini: {e}")
            answer = f"Không thể kết nối AI (Lỗi API). Dưới đây là trích dẫn luật thô:\n\n{context}"
    else:
        answer = f"Hệ thống chưa cấu hình GOOGLE_API_KEY. Dưới đây là trích dẫn luật thô từ hệ thống RAG:\n\n{context}"
        
    return LegalQueryResponse(answer=answer, context=context)
