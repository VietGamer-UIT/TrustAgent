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

from rag.retriever import get_legal_context

from fastapi import FastAPI, UploadFile, File, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from loguru import logger

from core.graph_builder import build_trustagent_graph
from core.state import TrustAgentState
from forensics.api.router import mount_forensics_routes
from forensics.database.session import create_tables, dispose_engine
from api.b2b import router as b2b_router


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

# B2B Enterprise API: /api/v1/audit
app.include_router(b2b_router)

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
            "(NĐ 356, 165, 200, 252, TT 90)."
        )

    api_key = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY") or ""
    answer = ""

    if api_key:
        try:
            import google.generativeai as genai
            genai.configure(api_key=api_key)
            # gemini-2.0-flash có quota pool riêng — thử trước
            _models = [
                "gemini-2.0-flash",
                "gemini-2.0-flash-lite",
                "gemini-1.5-flash-8b",
                "gemini-1.5-flash",
                "gemini-1.5-flash-latest",
                "gemini-pro",
            ]
            prompt = (
                "Bạn là chuyên gia pháp lý Việt Nam của nền tảng TrustAgent.\n"
                "Chỉ dựa vào NGỮ CẢNH bên dưới để trả lời câu hỏi.\n\n"
                "QUY TẮC:\n"
                "1. Trả lời NGẮN GỌN, TRỰC TIẾP, đúng trọng tâm câu hỏi (tối đa 5-7 câu).\n"
                "2. Bắt đầu bằng câu trả lời chính (số liệu, thời hạn, quy định cụ thể).\n"
                "3. In đậm (**) các số liệu, thời hạn, tên điều khoản quan trọng.\n"
                "4. Chỉ viết 'Theo Nghị định XX' hoặc 'Theo Thông tư YY' — KHÔNG nêu tên file .md.\n"
                "5. Nếu ngữ cảnh không đủ để trả lời, hãy nói rõ giới hạn đó.\n\n"
                f"NGỮ CẢNH:\n{context[:6000]}\n\n"
                f"CÂU HỎI: {query}\n"
            )
            for model_name in _models:
                try:
                    model = genai.GenerativeModel(model_name)
                    response = model.generate_content(prompt)
                    answer = (response.text or "").strip()
                    if answer:
                        logger.info(f"RAG OK với model: {model_name}")
                        break
                except Exception as model_err:
                    err_str = str(model_err).lower()
                    if any(k in err_str for k in ["quota", "429", "resource_exhausted", "rate"]):
                        logger.warning(f"Quota hết cho {model_name}, thử model khác...")
                        continue
                    logger.error(f"Lỗi model {model_name}: {model_err}")
                    break  # Lỗi khác (auth, network) → dừng ngay
        except Exception as e:
            logger.error(f"Lỗi khởi tạo Gemini: {e}")

    # ── Nếu AI không trả lời được → tạo câu trả lời ngôn ngữ tự nhiên từ context ──
    if not answer.strip():
        answer = _synthesize_natural_answer(query, context)

    return LegalQueryResponse(answer=answer, context=context)


def _synthesize_natural_answer(query: str, context: str) -> str:
    """
    Tạo câu trả lời ngôn ngữ tự nhiên từ context khi AI không khả dụng.
    Trích xuất các câu chứa từ khóa trực tiếp liên quan đến câu hỏi.
    """
    import re

    # Tách context thành các câu
    sentences = re.split(r"(?<=[.!?])\s+|(?<=\n)", context)
    sentences = [s.strip() for s in sentences if len(s.strip()) > 30]

    # Lấy từ khóa từ câu hỏi (bỏ stop words)
    stop = {"là", "bao", "lâu", "gì", "nào", "cần", "có", "theo", "thế", "như",
            "của", "và", "hoặc", "để", "với", "trong", "tại", "về", "các", "một",
            "được", "không", "khi", "cho", "sẽ", "đã", "đang", "này", "đó"}
    tokens = [t.lower() for t in re.findall(r"[\wÀ-ỹ]{2,}", query) if t.lower() not in stop]

    # Score từng câu
    scored = []
    for s in sentences:
        sl = s.lower()
        score = sum(sl.count(t) for t in tokens)
        # Boost câu có số liệu (thời hạn, %)
        if re.search(r"\d+\s*(ngày|giờ|năm|tháng|%|triệu|tỷ|khoản|điều)", sl):
            score += 3
        if score > 0:
            scored.append((score, s))

    scored.sort(key=lambda x: x[0], reverse=True)
    top_sentences = [s for _, s in scored[:5]]

    # Xác định nguồn luật từ context
    law_refs = []
    for pattern in [r"Nghị định \d+/\d+", r"Thông tư \d+/\d+", r"Điều \d+", r"Khoản \d+"]:
        found = re.findall(pattern, context)
        law_refs.extend(found[:2])
    law_ref_str = ", ".join(dict.fromkeys(law_refs)[:3]) if law_refs else "các quy định hiện hành"

    if not top_sentences:
        return (
            f"Chưa tìm thấy thông tin trực tiếp về câu hỏi này trong kho tài liệu pháp lý. "
            f"Vui lòng thử hỏi cụ thể hơn hoặc tham khảo trực tiếp {law_ref_str}."
        )

    body = " ".join(top_sentences)
    return (
        f"Căn cứ {law_ref_str}, TrustAgent tổng hợp thông tin liên quan:\n\n"
        f"{body}\n\n"
        f"_Lưu ý: Đây là trích dẫn trực tiếp từ văn bản pháp lý. "
        f"Để được tư vấn chuyên sâu, vui lòng tham khảo chuyên gia pháp lý._"
    )

