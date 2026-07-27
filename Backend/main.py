import os
import shutil
import uuid
import json
from typing import List, Optional

import google.generativeai as genai
from rag.retriever import get_legal_context

from fastapi import FastAPI, UploadFile, File, Form, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from loguru import logger

from core.graph_builder import build_trustagent_graph
from core.state import TrustAgentState

app = FastAPI(title="TrustAgent API", version="1.0.0")

# --- Configure CORS ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Adjust this in production to specific frontend domains
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Khởi tạo Graph
graph = build_trustagent_graph()

UPLOAD_DIR = os.path.join(os.path.dirname(__file__), "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

# --- Data Models for Frontend Match ---
class YeuCauKiemTra(BaseModel):
    ma_phien: str
    duong_dan_chung_tu: List[str] = []

class KetQuaKiemTra(BaseModel):
    graph_run_id: str = "run-123"
    ma_phien: str
    trang_thai: str
    muc_do_rui_ro: str
    tom_tat: str
    so_vong_lap: int
    hoan_tat_luc: str
    bao_cao_kiem_tra: dict

def format_frontend_response(incident_id: str, final_state: dict) -> dict:
    # Build standard response matching frontend KetQuaKiemTra
    audit_log = final_state.get("final_audit_log", {})
    tax_warnings = audit_log.get("tax_warnings", [])
    legal_violations = audit_log.get("legal_violations", [])
    
    canh_bao_list = []
    # Add tax warnings
    for warn in tax_warnings:
        canh_bao_list.append({
            "loai": warn.get("loai_loi", "Thuế"),
            "so_hoa_don": "N/A",
            "mo_ta": warn.get("chi_tiet", str(warn)),
            "muc_do": "cao",
            "nguon": "Tax Agent"
        })
    # Add legal violations
    for viol in legal_violations:
        canh_bao_list.append({
            "loai": "Pháp lý",
            "so_hoa_don": "N/A",
            "mo_ta": viol,
            "muc_do": "nghiêm trọng",
            "nguon": "Legal Agent"
        })
        
    # Check Z3 status
    z3_status = audit_log.get("z3_status", "UNKNOWN")
    if z3_status == "VIOLATION_DETECTED":
        canh_bao_list.append({
            "loai": "Toán học Z3",
            "so_hoa_don": "N/A",
            "mo_ta": "Z3 Engine phát hiện xung đột số học giữa hóa đơn và hợp đồng.",
            "muc_do": "nghiêm trọng",
            "nguon": "Z3 Engine"
        })
        
    muc_do_rui_ro = "nghiêm trọng" if canh_bao_list else "thấp"
    tom_tat = "Phát hiện sai phạm logic/toán học." if canh_bao_list else "Không phát hiện sai phạm nghiêm trọng."
    
    bao_cao = {
        "ma_phien": incident_id,
        "trang_thai": "Hoàn tất",
        "muc_do_rui_ro": muc_do_rui_ro,
        "tom_tat": tom_tat,
        "danh_sach_canh_bao": canh_bao_list,
        "ket_qua_mst": [],
        "khuyen_nghi": ["Gửi báo cáo cho CFO"] if canh_bao_list else ["Lưu trữ hồ sơ bình thường"],
        "agents_da_chay": ["document_agent", "tax_compliance_agent", "legal_agent", "supervisor"],
        "so_loi": 0,
        "so_vong_lap": final_state.get("iteration_count", 1),
        "hoan_tat_luc": audit_log.get("completed_at", "")
    }
    
    return {
        "graph_run_id": "graph-" + incident_id,
        "ma_phien": incident_id,
        "trang_thai": "Hoàn tất",
        "muc_do_rui_ro": muc_do_rui_ro,
        "tom_tat": tom_tat,
        "so_vong_lap": final_state.get("iteration_count", 1),
        "hoan_tat_luc": audit_log.get("completed_at", ""),
        "bao_cao_kiem_tra": bao_cao
    }

@app.post("/api/v1/kiem-tra/chung-tu")
async def kiem_tra_chung_tu_json(req: YeuCauKiemTra):
    incident_id = req.ma_phien or str(uuid.uuid4())
    logger.info(f"Bắt đầu DEMO kiểm toán: {incident_id}")
    
    initial_state: TrustAgentState = {
        "incident_id": incident_id,
        "evidence_paths": req.duong_dan_chung_tu,
        "extracted_data": {"contract_data": {}},
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
    final_state = await graph.ainvoke(initial_state)
    return format_frontend_response(incident_id, final_state)

@app.post("/api/v1/kiem-tra/upload")
async def upload_kiem_tra(
    request: Request,
    file: UploadFile = File(...),
):
    incident_id = request.query_params.get("ma_phien", str(uuid.uuid4()))
    logger.info(f"Bắt đầu UPLOAD kiểm toán: {incident_id}")
    
    file_path = os.path.join(UPLOAD_DIR, f"{incident_id}_{file.filename}")
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
        
    initial_state: TrustAgentState = {
        "incident_id": incident_id,
        "evidence_paths": [file_path],
        "extracted_data": {"contract_data": {}},
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
    final_state = await graph.ainvoke(initial_state)
    
    # Dọn file
    if os.path.exists(file_path):
        os.remove(file_path)
        
    resp = format_frontend_response(incident_id, final_state)
    # Add extra fields for Upload response
    resp["ten_file_goc"] = file.filename
    resp["kich_thuoc_kb"] = 0 # Dummy size
    return resp

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
            model = genai.GenerativeModel("gemini-2.0-flash-lite")
            prompt = f"Bạn là một chuyên gia pháp lý Việt Nam. Dựa vào ngữ cảnh sau để trả lời câu hỏi.\n\nNgữ cảnh:\n{context}\n\nCâu hỏi: {query}\n\nTrả lời ngắn gọn, chuyên nghiệp và có trích dẫn:"
            response = model.generate_content(prompt)
            answer = response.text
        except Exception as e:
            logger.error(f"Lỗi khi gọi Gemini: {e}")
            answer = f"⚠️ **Hệ thống AI đang tạm thời gián đoạn (Vượt quá hạn mức API/Quota Limit).**\n\nTuy nhiên, hệ thống RAG đã tìm thấy các tài liệu pháp lý thực tế liên quan đến truy vấn của bạn. Dưới đây là các trích đoạn nguyên bản từ kho dữ liệu (chưa qua tổng hợp của AI):\n\n---\n\n{context}"
    else:
        answer = f"⚠️ **Hệ thống chưa cấu hình GOOGLE_API_KEY.**\n\nDưới đây là các trích đoạn nguyên bản từ kho dữ liệu RAG:\n\n---\n\n{context}"
        
    return LegalQueryResponse(answer=answer, context=context)
