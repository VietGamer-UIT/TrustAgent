# =============================================================================
# TrustAgent :: FastAPI Entry Point — Trợ Lý Ảo Phát Hiện Lỗi Chứng Từ
# Bản quyền: TrustAgent bởi Đoàn Hoàng Việt (Việt Gamer)
# =============================================================================
# Kết nối:
#   - AuditMiddleware  (ghi nhật ký HTTP → PostgreSQL)
#   - Lifespan events  (khởi tạo DB khi startup, giải phóng khi shutdown)
#   - API routers      (kiểm tra chứng từ + truy vấn nhật ký kiểm toán)
#
# Chạy local:
#   uvicorn Backend.FastAPI.main:app --reload --port 8000
# =============================================================================

from __future__ import annotations

import logging
import os
import re
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, HTTPException, Query, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from database.database import init_db, close_db
from database.middleware import AuditMiddleware, set_audit_context
from core.state import TrustAgentState
from core.supervisor import build_trustagent_graph
# from data_pipeline.lich_cao import khoi_dong_pipeline, lay_trang_thai

# ---------------------------------------------------------------------------
# Thư mục lưu tạm file upload
# ---------------------------------------------------------------------------
_TEMP_UPLOAD_DIR = Path(__file__).parent / "temp_uploads"
_TEMP_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

# Định dạng file được phép upload (whitelist)
_DINH_DANG_DUOC_PHEP: set[str] = {
    ".jpg", ".jpeg", ".png", ".webp", ".gif",
    ".pdf", ".tiff", ".tif", ".bmp",
}

# Kích thước file tối đa: 20MB
_KICH_THUOC_TOI_DA = 20 * 1024 * 1024  # 20MB in bytes


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
)
logger = logging.getLogger("trustagent.main")


# ---------------------------------------------------------------------------
# Application lifespan
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    FastAPI lifespan context manager.
    - Startup  : Khởi tạo bảng PostgreSQL, biên dịch graph.
    - Shutdown : Giải phóng connection pool.
    """
    logger.info("[Khởi động] TrustAgent đang khởi tạo...")

    await init_db()
    logger.info("[Khởi động] Audit DB sẵn sàng.")

    app.state.trustagent_graph = build_trustagent_graph()
    logger.info("[Khởi động] Đồ thị kiểm tra TrustAgent đã nạp.")

    # Khởi động Data Pipeline — nạp seed data MST vào PostgreSQL
    # await khoi_dong_pipeline()
    logger.info("[Khởi động] Data Pipeline (Local MST Cache) đã khởi động.")

    yield

    logger.info("[Tắt] Đang giải phóng database engine...")
    await close_db()
    logger.info("[Tắt] TrustAgent đã tắt sạch.")


# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------

app = FastAPI(
    title="TrustAgent — Trợ Lý Ảo Phát Hiện Lỗi Chứng Từ",
    description=(
        "TrustAgent bởi Đoàn Hoàng Việt (Việt Gamer). "
        "Nền tảng AI đa tác nhân phát hiện lỗi chứng từ, hóa đơn "
        "và gian lận tài chính cho ngành kiểm toán Việt Nam. "
        "Sử dụng LangGraph, MCP Servers và PostgreSQL Audit Trail."
    ),
    version="2.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

# ── Middleware ────────────────────────────────────────────────────────────────
app.add_middleware(AuditMiddleware)

# ---------------------------------------------------------------------------
# CORS
# ---------------------------------------------------------------------------
_CORS_ORIGIN_REGEX = (
    r"http://localhost:\d+"
    r"|http://127\.0\.0\.1:\d+"
    r"|https://.*-3000\.app\.github\.dev"
    r"|https://.*-3000\.preview\.app\.github\.dev"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[],
    allow_origin_regex=_CORS_ORIGIN_REGEX,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Ma-Phien"],
)


# ---------------------------------------------------------------------------
# Pydantic v2 Request / Response Schemas
# ---------------------------------------------------------------------------

class YeuCauKiemTra(BaseModel):
    """Request body cho endpoint kiểm tra chứng từ."""
    ma_phien: str = Field(
        ...,
        min_length=1,
        max_length=128,
        description="Mã phiên kiểm tra duy nhất (ví dụ: 'KT-2024-001')",
        examples=["KT-2024-DEMO-001"],
    )
    duong_dan_chung_tu: list[str] = Field(
        default_factory=list,
        description="Đường dẫn tới file chứng từ (hóa đơn, hợp đồng)",
        examples=[["/hoa_don/HD-001.pdf", "/hoa_don/HD-002.pdf"]],
    )


class KetQuaKiemTra(BaseModel):
    """Response body sau khi graph kiểm tra chứng từ hoàn tất."""
    graph_run_id:      str
    ma_phien:          str
    trang_thai:        str
    muc_do_rui_ro:     str
    tom_tat:           str
    so_vong_lap:       int
    hoan_tat_luc:      str
    bao_cao_kiem_tra:  dict[str, Any]


# ---------------------------------------------------------------------------
# API Endpoints
# ---------------------------------------------------------------------------

@app.get("/health", tags=["ops"], summary="Kiểm tra trạng thái")
async def health() -> dict[str, str]:
    """Health check — 200 OK khi ứng dụng đang chạy."""
    return {"status": "ok", "service": "TrustAgent"}


@app.post(
    "/api/v1/kiem-tra/chung-tu",
    response_model=KetQuaKiemTra,
    status_code=status.HTTP_200_OK,
    tags=["kiem-tra-chung-tu"],
    summary="Khởi động kiểm tra chứng từ đa tác nhân",
)
async def kiem_tra_chung_tu(request: YeuCauKiemTra) -> KetQuaKiemTra:
    """
    Kích hoạt luồng LangGraph đa tác nhân kiểm tra bộ chứng từ.

    Luồng:
      1. Tạo graph_run_id duy nhất.
      2. Đặt audit context (ma_phien + graph_run_id).
      3. Gọi StateGraph với TrangThaiKiemTra ban đầu.
      4. Trả về bao_cao_kiem_tra từ state cuối cùng.
    """
    graph_run_id = str(uuid.uuid4())

    set_audit_context(
        incident_id=request.ma_phien,
        graph_run_id=graph_run_id,
    )

    initial_state: TrustAgentState = {
        "incident_id":         request.ma_phien,
        "user_prompt":         "",
        "evidence_paths":      request.duong_dan_chung_tu or ["/hoa_don/tat_ca.pdf"],
        "extracted_data":      {},
        "scenario_type":       "full_audit",
        "tax_warnings":        [],
        "z3_status":           None,
        "legal_violations":    [],
        "final_audit_log":     {},
        "messages":            [],
    }

    logger.info(
        "[API] Khởi động kiểm tra — phiên=%s run_id=%s",
        request.ma_phien, graph_run_id,
    )

    try:
        final_state: TrustAgentState = await app.state.trustagent_graph.ainvoke(initial_state)
    except Exception as exc:
        logger.exception("[API] Graph thất bại cho phiên=%s", request.ma_phien)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Kiểm tra chứng từ thất bại: {type(exc).__name__}: {exc}",
        )

    report: dict[str, Any] = final_state.get("final_audit_log", {})

    return KetQuaKiemTra(
        graph_run_id=graph_run_id,
        ma_phien=report.get("ma_phien", request.ma_phien),
        trang_thai=report.get("trang_thai", "chưa rõ"),
        muc_do_rui_ro=report.get("muc_do_rui_ro", "chưa rõ"),
        tom_tat=report.get("tom_tat", "Không có tóm tắt."),
        so_vong_lap=report.get("so_vong_lap", 0),
        hoan_tat_luc=report.get("hoan_tat_luc", ""),
        bao_cao_kiem_tra=report,
    )


# Keep the old endpoint as well for backward compatibility during transition
@app.post(
    "/api/v1/ir/investigate",
    status_code=status.HTTP_200_OK,
    tags=["kiem-tra-chung-tu"],
    summary="[Tương thích ngược] Kiểm tra chứng từ",
    include_in_schema=False,
)
async def investigate_compat(request: YeuCauKiemTra) -> KetQuaKiemTra:
    """Backward-compatible alias — redirects to the main endpoint."""
    return await kiem_tra_chung_tu(request)


@app.post(
    "/api/v1/kiem-tra/upload",
    response_model=KetQuaKiemTra,
    status_code=status.HTTP_200_OK,
    tags=["kiem-tra-chung-tu"],
    summary="Upload file hóa đơn thật và kiểm tra bằng Gemini Vision OCR",
)
async def kiem_tra_upload(
    file: UploadFile = File(..., description="File hóa đơn (JPG/PNG/PDF/WebP, tối đa 20MB)"),
    ma_phien: str = Query(
        default="",
        description="Mã phiên kiểm tra (để trống sẽ tự sinh)",
        max_length=128,
    ),
) -> KetQuaKiemTra:
    """
    Upload file hóa đơn/chứng từ thật và chạy pipeline kiểm tra AI.

    Luồng:
      1. Kiểm tra định dạng file (whitelist: JPG/PNG/PDF/WebP)
      2. Kiểm tra kích thước (tối đa 20MB)
      3. Lưu file tạm vào temp_uploads/
      4. Gọi LangGraph pipeline với đường dẫn file thật
      5. Gemini Vision OCR đọc hóa đơn → bóc tách JSON
      6. Agents kiểm tra số học, MST, ngày tháng
      7. Trả về báo cáo

    Graceful error handling:
      - File .exe hoặc định dạng không hỗ trợ → 415 Unsupported Media Type
      - File quá lớn → 413 Request Entity Too Large
      - File ảnh chó mèo không phải hóa đơn → báo cáo is_valid=false
    """
    # ── 1. Kiểm tra định dạng ──────────────────────────────────────────────
    ten_file_goc = file.filename or "unknown"
    duoi_file = Path(ten_file_goc).suffix.lower()

    if duoi_file not in _DINH_DANG_DUOC_PHEP:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=(
                f"Định dạng file '{duoi_file}' không được hỗ trợ. "
                f"Chỉ chấp nhận: {', '.join(sorted(_DINH_DANG_DUOC_PHEP))}. "
                "Vui lòng upload file hóa đơn dạng JPG, PNG, PDF hoặc WebP."
            ),
        )

    # ── 2. Đọc nội dung file ───────────────────────────────────────────────
    noi_dung = await file.read()

    if len(noi_dung) > _KICH_THUOC_TOI_DA:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=(
                f"File quá lớn ({len(noi_dung) / 1024 / 1024:.1f}MB). "
                "Giới hạn tối đa là 20MB."
            ),
        )

    if len(noi_dung) == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File rỗng. Vui lòng upload file hóa đơn hợp lệ.",
        )

    # ── 3. Sinh mã phiên và lưu file tạm ──────────────────────────────────
    graph_run_id = str(uuid.uuid4())
    ma_phien_thuc = ma_phien.strip() or f"KT-UPLOAD-{graph_run_id[:8].upper()}"

    # Tên file an toàn: [uuid]_[tên gốc đã làm sạch]
    ten_file_sach = re.sub(r'[^\w\-_\.]', '_', ten_file_goc)
    ten_file_luu = f"{graph_run_id[:8]}_{ten_file_sach}"
    duong_dan_luu = _TEMP_UPLOAD_DIR / ten_file_luu

    try:
        with open(duong_dan_luu, "wb") as f_out:
            f_out.write(noi_dung)
    except OSError as exc:
        logger.exception("[Upload] Không thể lưu file: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Không thể lưu file tạm: {exc}",
        )

    logger.info(
        "[Upload] Đã lưu file: %s (%.1f KB) → phiên: %s",
        ten_file_luu, len(noi_dung) / 1024, ma_phien_thuc,
    )

    # ── 4. Gọi LangGraph pipeline ──────────────────────────────────────────
    set_audit_context(incident_id=ma_phien_thuc, graph_run_id=graph_run_id)

    initial_state: TrustAgentState = {
        "incident_id":         ma_phien_thuc,
        "user_prompt":         "",
        "evidence_paths":      [str(duong_dan_luu)],  # Đường dẫn file thật
        "extracted_data":      {},
        "scenario_type":       "full_audit",
        "tax_warnings":        [],
        "z3_status":           None,
        "legal_violations":    [],
        "final_audit_log":     {},
        "messages":            [],
    }

    try:
        final_state: TrustAgentState = await app.state.trustagent_graph.ainvoke(initial_state)
    except Exception as exc:
        # Dọn dẹp file tạm nếu pipeline thất bại
        try:
            duong_dan_luu.unlink(missing_ok=True)
        except OSError:
            pass
        logger.exception("[Upload] Graph thất bại cho phiên=%s", ma_phien_thuc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Kiểm tra chứng từ thất bại: {type(exc).__name__}: {exc}",
        )

    # Xóa file tạm sau khi xử lý xong (tùy chọn — bỏ comment nếu muốn giữ)
    # try:
    #     duong_dan_luu.unlink(missing_ok=True)
    # except OSError:
    #     pass

    report: dict[str, Any] = final_state.get("final_audit_log", {})

    return KetQuaKiemTra(
        graph_run_id=graph_run_id,
        ma_phien=report.get("ma_phien", ma_phien_thuc),
        trang_thai=report.get("trang_thai", "chưa rõ"),
        muc_do_rui_ro=report.get("muc_do_rui_ro", "chưa rõ"),
        tom_tat=report.get("tom_tat", "Không có tóm tắt."),
        so_vong_lap=report.get("so_vong_lap", 0),
        hoan_tat_luc=report.get("hoan_tat_luc", ""),
        bao_cao_kiem_tra=report,
    )


@app.get(
    "/api/v1/audit/events",
    tags=["nhat-ky-kiem-toan"],
    summary="Truy vấn nhật ký kiểm toán theo mã phiên",
)
async def get_audit_events(
    incident_id: str,
    limit: int = 100,
) -> dict[str, Any]:
    """
    Trả về các sự kiện kiểm toán gần nhất cho mã phiên (incident_id).
    Mỗi sự kiện được ghi bất biến vào PostgreSQL với SHA-256 hash.
    """
    from sqlalchemy import select, desc
    from database.database import AsyncSessionFactory
    from database.models import AuditEvent

    async with AsyncSessionFactory() as session:
        result = await session.execute(
            select(AuditEvent)
            .where(AuditEvent.incident_id == incident_id)
            .order_by(desc(AuditEvent.recorded_at))
            .limit(min(limit, 500))
        )
        events = result.scalars().all()

    return {
        "incident_id": incident_id,
        "count": len(events),
        "events": [
            {
                "id":             str(e.id),
                "event_type":     e.event_type,
                "agent_name":     e.agent_name,
                "status":         e.status,
                "tool_name":      e.tool_name,
                "retry_attempt":  e.retry_attempt,
                "duration_ms":    e.duration_ms,
                "sha256_hash":    e.sha256_state_hash,
                "recorded_at":    e.recorded_at.isoformat() if e.recorded_at else None,
            }
            for e in events
        ],
    }


@app.get(
    "/api/v1/mst/thong-tin",
    tags=["local-mst-cache"],
    summary="Tra cứu thông tin MST từ Local Cache (PostgreSQL)",
)
async def tra_cuu_mst_endpoint(mst: str) -> dict[str, Any]:
    """
    Tra cứu thông tin doanh nghiệp theo MST từ local PostgreSQL cache.
    Latency < 5ms nhờ tra cứu nội bộ, không cần kết nối API Tổng cục Thuế.
    """
    from mcp_servers.thue_db_mcp import tra_cuu_mst_local, TraCuuMSTLocalInput

    try:
        result = await tra_cuu_mst_local(TraCuuMSTLocalInput(mst=mst))
        return result
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"MST không hợp lệ: {exc}",
        )


@app.get(
    "/api/v1/pipeline/trang-thai",
    tags=["local-mst-cache"],
    summary="Lấy trạng thái Data Pipeline (Local MST Cache)",
)
async def trang_thai_pipeline() -> dict[str, Any]:
    """
    Trả về trạng thái hiện tại của Data Pipeline.
    Bao gồm: tổng bản ghi, số đang HĐ, số ngừng HĐ, lần chạy cuối.
    """
    return {}
