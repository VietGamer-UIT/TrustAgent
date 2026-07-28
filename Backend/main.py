import os
import shutil
import uuid
from typing import List
from contextlib import asynccontextmanager
from collections.abc import AsyncGenerator

from dotenv import load_dotenv

# Nạp .env từ thư mục Backend hoặc gốc TrustAgent
load_dotenv()
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

import google.generativeai as genai
from rag.retriever import get_legal_context

from fastapi import FastAPI, UploadFile, File, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from loguru import logger

from core.graph_builder import build_trustagent_graph
from core.state import TrustAgentState
from forensics.api.router import mount_forensics_routes
from forensics.database.session import create_tables, dispose_engine


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncGenerator[None, None]:
    """Startup: tạo bảng audit_logs (Forensics). Shutdown: đóng DB pool."""
    logger.info("[startup] TrustAgent API đang khởi động...")
    try:
        await create_tables()
        logger.info("[startup] TrustAgent audit DB sẵn sàng")
    except Exception as e:
        logger.error(f"[startup] Không khởi tạo được audit DB: {e}")
    yield
    await dispose_engine()
    logger.info("[shutdown] TrustAgent đã đóng kết nối database")


app = FastAPI(
    title="TrustAgent API",
    version="1.0.0",
    description=(
        "TrustAgent — nền tảng kiểm toán Neuro-Symbolic.\n\n"
        "**Tính năng:** Kiểm tra chứng từ | Tra cứu luật | "
        "**Forensics** (Z3 legal gatekeeper)"
    ),
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Forensics feature routes: /api/v1/forensics/verify, /api/v1/forensics/audit
mount_forensics_routes(app)

# Khởi tạo Graph kiểm toán chứng từ
graph = build_trustagent_graph()

UPLOAD_DIR = os.path.join(os.path.dirname(__file__), "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)


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
    audit_log = final_state.get("final_audit_log", {})
    tax_warnings = audit_log.get("tax_warnings", [])
    legal_violations = audit_log.get("legal_violations", [])

    canh_bao_list = []
    for warn in tax_warnings:
        canh_bao_list.append({
            "loai": warn.get("loai_loi", "Thuế"),
            "so_hoa_don": "N/A",
            "mo_ta": warn.get("chi_tiet", str(warn)),
            "muc_do": "cao",
            "nguon": "Tax Agent",
        })
    for viol in legal_violations:
        canh_bao_list.append({
            "loai": "Pháp lý",
            "so_hoa_don": "N/A",
            "mo_ta": viol,
            "muc_do": "nghiêm trọng",
            "nguon": "Legal Agent",
        })

    z3_status = audit_log.get("z3_status", "UNKNOWN")
    if z3_status == "VIOLATION_DETECTED":
        canh_bao_list.append({
            "loai": "Toán học Z3",
            "so_hoa_don": "N/A",
            "mo_ta": "Z3 Engine phát hiện xung đột số học giữa hóa đơn và hợp đồng.",
            "muc_do": "nghiêm trọng",
            "nguon": "Z3 Engine",
        })

    muc_do_rui_ro = "nghiêm trọng" if canh_bao_list else "thấp"
    tom_tat = (
        "Phát hiện sai phạm logic/toán học."
        if canh_bao_list
        else "Không phát hiện sai phạm nghiêm trọng."
    )

    bao_cao = {
        "ma_phien": incident_id,
        "trang_thai": "Hoàn tất",
        "muc_do_rui_ro": muc_do_rui_ro,
        "tom_tat": tom_tat,
        "danh_sach_canh_bao": canh_bao_list,
        "ket_qua_mst": [],
        "khuyen_nghi": (
            ["Gửi báo cáo cho CFO"] if canh_bao_list else ["Lưu trữ hồ sơ bình thường"]
        ),
        "agents_da_chay": [
            "document_agent",
            "tax_compliance_agent",
            "legal_agent",
            "supervisor",
        ],
        "so_loi": 0,
        "so_vong_lap": final_state.get("iteration_count", 1),
        "hoan_tat_luc": audit_log.get("completed_at", ""),
    }

    return {
        "graph_run_id": "graph-" + incident_id,
        "ma_phien": incident_id,
        "trang_thai": "Hoàn tất",
        "muc_do_rui_ro": muc_do_rui_ro,
        "tom_tat": tom_tat,
        "so_vong_lap": final_state.get("iteration_count", 1),
        "hoan_tat_luc": audit_log.get("completed_at", ""),
        "bao_cao_kiem_tra": bao_cao,
    }


@app.get("/health")
async def health():
    return {"status": "ok", "service": "trustagent", "forensics": True}


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
        "final_audit_log": {},
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
        "final_audit_log": {},
    }
    final_state = await graph.ainvoke(initial_state)

    if os.path.exists(file_path):
        os.remove(file_path)

    resp = format_frontend_response(incident_id, final_state)
    resp["ten_file_goc"] = file.filename
    resp["kich_thuoc_kb"] = 0
    return resp


class LegalQueryRequest(BaseModel):
    query: str


class LegalQueryResponse(BaseModel):
    answer: str
    context: str


@app.post("/api/v1/tra-cuu-luat", response_model=LegalQueryResponse)
async def tra_cuu_luat(request: LegalQueryRequest):
    query = (request.query or "").strip()
    if not query:
        return LegalQueryResponse(
            answer="Vui lòng nhập câu hỏi pháp lý.",
            context="",
        )

    logger.info(f"Tra cứu luật pháp: {query}")

    try:
        context = get_legal_context(query) or ""
    except Exception as e:
        logger.error(f"RAG lỗi: {e}")
        context = ""

    if not context.strip():
        context = (
            "Không tìm thấy đoạn luật khớp trực tiếp trong kho tài liệu hiện có "
            "(NĐ 356, 165, 200, 252, TT 90, Luật Thương mại, NĐ 123)."
        )

    api_key = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY") or ""
    answer = ""

    if api_key:
        try:
            genai.configure(api_key=api_key)
            model = genai.GenerativeModel("gemini-1.5-flash")
            prompt = (
                "Bạn là chuyên gia pháp lý Việt Nam của nền tảng TrustAgent.\n"
                "Chỉ dựa vào NGỮ CẢNH bên dưới để trả lời. "
                "Nếu ngữ cảnh thiếu, hãy nói rõ phần nào chưa đủ căn cứ.\n"
                "Trả lời bằng tiếng Việt, rõ ràng, có mục: Kết luận · Căn cứ · Lưu ý.\n\n"
                f"NGỮ CẢNH:\n{context[:8000]}\n\n"
                f"CÂU HỎI:\n{query}\n"
            )
            response = model.generate_content(prompt)
            answer = (response.text or "").strip()
        except Exception as e:
            logger.error(f"Lỗi khi gọi Gemini: {e}")
            answer = (
                "### Kết luận tạm thời (chế độ tra cứu tài liệu)\n\n"
                "Không gọi được mô hình AI lúc này. Dưới đây là các đoạn luật "
                "liên quan mà TrustAgent tìm được trong kho:\n\n"
                f"{context}"
            )
    else:
        answer = (
            "### Kết quả tra cứu tài liệu pháp lý\n\n"
            "Chưa cấu hình `GOOGLE_API_KEY` — TrustAgent trả về đoạn luật gốc "
            "khớp với câu hỏi của bạn:\n\n"
            f"{context}\n\n"
            "_Gợi ý: thêm GOOGLE_API_KEY vào `.env` để nhận câu trả lời tổng hợp "
            "bằng ngôn ngữ tự nhiên._"
        )

    return LegalQueryResponse(answer=answer, context=context)
