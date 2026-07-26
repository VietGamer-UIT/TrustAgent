# =============================================================================
# TrustAgent :: OCR MCP Server — Đọc Hóa Đơn / Chứng Từ bằng Gemini Vision
# Bản quyền: TrustAgent bởi Đoàn Hoàng Việt (Việt Gamer)
# =============================================================================
# Tích hợp google-generativeai (Gemini 1.5 Flash) để OCR hóa đơn thật.
#
# Công cụ MCP:
#   - doc_nhan_hoa_don : Đọc file hóa đơn thật (JPG/PNG/PDF) → bóc tách JSON
#   - doc_hop_dong     : Đọc file hợp đồng (mock — mở rộng tương tự)
#
# Kiến trúc bảo mật (Read-Only Guardrails):
#   1. Pydantic v2 strict validation trước khi gọi Gemini
#   2. Kiểm tra MIME type + whitelist định dạng cho phép
#   3. Audit log mọi lần gọi
#   4. Gemini chỉ ĐỌC, không ghi, không thực thi
#   5. Graceful error nếu file không phải hóa đơn hoặc file rác
# =============================================================================

from __future__ import annotations

import base64
import json
import logging
import mimetypes
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, StrictStr, field_validator

logger = logging.getLogger("trustagent.mcp.ocr")

# ---------------------------------------------------------------------------
# MCP Tool Registry
# ---------------------------------------------------------------------------
OCR_TOOL_REGISTRY: dict[str, Any] = {}


def mcp_tool(name: str):
    """Decorator dang ky ham async vao OCR_TOOL_REGISTRY."""
    def decorator(fn: Any) -> Any:
        OCR_TOOL_REGISTRY[name] = fn
        logger.debug("Da dang ky cong cu OCR MCP: %s", name)
        return fn
    return decorator


# ---------------------------------------------------------------------------
# Cấu hình Gemini Vision
# ---------------------------------------------------------------------------
_GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY", "")

# Định dạng file được chấp nhận (whitelist)
_DINH_DANG_HOP_LE: set[str] = {
    ".jpg", ".jpeg", ".png", ".webp", ".gif",
    ".pdf", ".tiff", ".tif", ".bmp",
}

# MIME type map
_MIME_MAP: dict[str, str] = {
    ".jpg":  "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png":  "image/png",
    ".webp": "image/webp",
    ".gif":  "image/gif",
    ".bmp":  "image/bmp",
    ".tiff": "image/tiff",
    ".tif":  "image/tiff",
    ".pdf":  "application/pdf",
}

# Prompt cho Gemini — chuyên gia kiểm toán OCR hóa đơn
_PROMPT_HOA_DON = """Bạn là một chuyên gia kiểm toán tài chính Việt Nam có nhiều năm kinh nghiệm.
Nhiệm vụ của bạn là đọc hình ảnh hóa đơn này và trích xuất thông tin.

QUAN TRỌNG: Trả lời CHÍNH XÁC dưới dạng JSON thuần túy, không có markdown, không có giải thích.

Nếu đây LÀ một hóa đơn/chứng từ tài chính hợp lệ, trả về:
{
  "is_valid": true,
  "so_hoa_don": "số hóa đơn (string)",
  "ngay_xuat": "YYYY-MM-DD",
  "ten_nguoi_ban": "tên công ty xuất hóa đơn (string)",
  "mst_nguoi_ban": "mã số thuế người bán (string, chỉ số)",
  "dia_chi_nguoi_ban": "địa chỉ người bán (string)",
  "ten_nguoi_mua": "tên công ty mua (string)",
  "mst_nguoi_mua": "mã số thuế người mua (string, chỉ số)",
  "hang_hoa": [{"ten": "tên hàng/dịch vụ", "don_gia": 0, "so_luong": 0, "thanh_tien": 0}],
  "tien_hang": 0,
  "thue_suat_vat": 10,
  "tien_thue_vat": 0,
  "tong_tien": 0,
  "don_vi_tien": "VNĐ",
  "ghi_chu": ""
}

Nếu file KHÔNG phải hóa đơn (hình ảnh chó mèo, phong cảnh, file rác, v.v.), trả về:
{
  "is_valid": false,
  "error_message": "Mô tả ngắn gọn lý do file không hợp lệ (ví dụ: Đây là ảnh chụp chó, không phải hóa đơn)"
}

Nếu là hóa đơn nhưng ảnh mờ/không đọc được một số trường, dùng null cho trường đó.
Tất cả giá trị tiền tệ phải là số nguyên (int), không có dấu phẩy hay đơn vị.
"""

# Prompt đọc hợp đồng
_PROMPT_HOP_DONG = """Bạn là chuyên gia kiểm toán hợp đồng.
Đọc tài liệu này và trích xuất thông tin dưới dạng JSON thuần túy:

Nếu ĐÂY LÀ hợp đồng hợp lệ:
{
  "is_valid": true,
  "so_hop_dong": "số hợp đồng",
  "ngay_ky": "YYYY-MM-DD",
  "ben_a": "tên bên A",
  "mst_ben_a": "MST bên A",
  "ben_b": "tên bên B",
  "mst_ben_b": "MST bên B",
  "gia_tri": 0,
  "noi_dung": "nội dung tóm tắt hợp đồng"
}

Nếu KHÔNG phải hợp đồng:
{
  "is_valid": false,
  "error_message": "lý do"
}
"""


# ---------------------------------------------------------------------------
# Audit helper
# ---------------------------------------------------------------------------
def _nhat_ky(tool: str, params: dict[str, Any]) -> None:
    """Ghi nhật ký kiểm toán cho mỗi lần gọi công cụ."""
    entry = {
        "su_kien": "goi_cong_cu_mcp",
        "thoi_gian": datetime.now(tz=timezone.utc).isoformat(),
        "may_chu": "ocr_mcp",
        "cong_cu": tool,
        "tham_so": params,
    }
    logger.info(json.dumps(entry, ensure_ascii=False))


# ---------------------------------------------------------------------------
# Kiểm tra định dạng file (security guardrail)
# ---------------------------------------------------------------------------
def _kiem_tra_dinh_dang(duong_dan: str) -> tuple[str, str]:
    """
    Kiểm tra file có tồn tại và có định dạng hợp lệ không.

    Returns:
        (duoi_file, mime_type) nếu hợp lệ

    Raises:
        ValueError nếu định dạng không được phép
        FileNotFoundError nếu file không tồn tại
    """
    path = Path(duong_dan)

    if not path.exists():
        raise FileNotFoundError(f"File không tồn tại: {duong_dan}")

    duoi = path.suffix.lower()
    if duoi not in _DINH_DANG_HOP_LE:
        raise ValueError(
            f"Định dạng '{duoi}' không được phép. "
            f"Chỉ chấp nhận: {', '.join(sorted(_DINH_DANG_HOP_LE))}"
        )

    mime = _MIME_MAP.get(duoi, "application/octet-stream")
    return duoi, mime


# ---------------------------------------------------------------------------
# Gọi Gemini Vision
# ---------------------------------------------------------------------------
async def _goi_gemini_vision(duong_dan: str, prompt: str) -> dict[str, Any]:
    """
    Đọc file và gọi Gemini Vision để OCR.

    Returns:
        dict kết quả đã parse từ JSON response của Gemini

    Raises:
        RuntimeError nếu không có API key hoặc Gemini thất bại
        ValueError nếu response không parse được thành JSON
    """
    if not _GOOGLE_API_KEY:
        raise RuntimeError(
            "Biến môi trường GOOGLE_API_KEY chưa được thiết lập. "
            "Thêm GOOGLE_API_KEY vào file .env để sử dụng OCR thật."
        )

    # Import lazy để không bắt buộc khi chạy mock mode
    try:
        import google.generativeai as genai
    except ImportError:
        raise RuntimeError(
            "Thiếu thư viện google-generativeai. "
            "Chạy: pip install google-generativeai"
        )

    # Kiểm tra định dạng file
    duoi, mime_type = _kiem_tra_dinh_dang(duong_dan)

    # Đọc file và encode base64
    with open(duong_dan, "rb") as f:
        file_bytes = f.read()

    # Kiểm tra kích thước (tối đa 20MB)
    kich_thuoc_mb = len(file_bytes) / (1024 * 1024)
    if kich_thuoc_mb > 20:
        raise ValueError(
            f"File quá lớn ({kich_thuoc_mb:.1f}MB). "
            "Gemini Vision chỉ hỗ trợ tối đa 20MB."
        )

    # Cấu hình Gemini
    genai.configure(api_key=_GOOGLE_API_KEY)
    model = genai.GenerativeModel("gemini-1.5-flash")

    # Tạo phần nội dung multimodal
    image_part = {
        "mime_type": mime_type,
        "data": base64.b64encode(file_bytes).decode("utf-8"),
    }

    logger.info(
        "[OCR] Gọi Gemini Vision cho file: %s (%.1f KB, %s)",
        Path(duong_dan).name,
        len(file_bytes) / 1024,
        mime_type,
    )

    # Gọi Gemini
    response = model.generate_content(
        contents=[prompt, image_part],
        generation_config={
            "temperature": 0.0,       # Deterministic — quan trọng cho kiểm toán
            "max_output_tokens": 2048,
        },
    )

    # Lấy text response
    raw_text = response.text.strip()
    logger.debug("[OCR] Gemini raw response: %s", raw_text[:200])

    # Parse JSON — xử lý cả trường hợp Gemini bọc trong ```json ```
    json_match = re.search(r"```(?:json)?\s*([\s\S]*?)```", raw_text)
    if json_match:
        raw_text = json_match.group(1).strip()

    try:
        result = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"Gemini trả về dữ liệu không phải JSON hợp lệ: {exc}. "
            f"Raw response (200 ký tự đầu): {raw_text[:200]}"
        ) from exc

    return result


# ---------------------------------------------------------------------------
# Fallback: Mock data cho trường hợp không có API key (chế độ demo)
# ---------------------------------------------------------------------------
_DU_LIEU_MOCK_FALLBACK: dict[str, Any] = {
    "is_valid": True,
    "so_hoa_don": "HD-DEMO-001",
    "ngay_xuat": "2024-06-01",
    "ten_nguoi_ban": "Công ty TNHH Demo TrustAgent",
    "mst_nguoi_ban": "0312345678",
    "dia_chi_nguoi_ban": "123 Nguyễn Huệ, Quận 1, TP.HCM",
    "ten_nguoi_mua": "Công ty CP Kiểm Toán ABC",
    "mst_nguoi_mua": "0301234567",
    "hang_hoa": [
        {"ten": "Dịch vụ tư vấn kiểm toán (Demo)", "don_gia": 50_000_000, "so_luong": 1, "thanh_tien": 50_000_000},
    ],
    "tien_hang": 50_000_000,
    "thue_suat_vat": 10,
    "tien_thue_vat": 5_000_000,
    "tong_tien": 55_000_000,
    "don_vi_tien": "VNĐ",
    "ghi_chu": "[DEMO MODE - Không có GOOGLE_API_KEY]",
}

_DU_LIEU_HOP_DONG_FALLBACK: dict[str, Any] = {
    "is_valid": True,
    "so_hop_dong": "HĐ-DEMO-001",
    "ngay_ky": "2024-05-01",
    "ben_a": "Công ty CP Kiểm Toán ABC",
    "mst_ben_a": "0301234567",
    "ben_b": "Công ty TNHH Demo TrustAgent",
    "mst_ben_b": "0312345678",
    "gia_tri": 55_000_000,
    "noi_dung": "[DEMO MODE - Không có GOOGLE_API_KEY]",
}


# ---------------------------------------------------------------------------
# Pydantic v2 Input Schemas
# ---------------------------------------------------------------------------

class DocHoaDonInput(BaseModel):
    """Schema dau vao cho cong cu doc hoa don that."""
    duong_dan: StrictStr = Field(
        ...,
        description="Duong dan tuyet doi toi file hoa don (JPG/PNG/PDF/WebP)",
    )

    @field_validator("duong_dan", mode="after")
    @classmethod
    def kiem_tra_duong_dan(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Duong dan file khong duoc de trong.")
        if ".." in v:
            raise ValueError("Duong dan khong duoc chua '..' (path traversal bi chan).")
        return v


class DocHopDongInput(BaseModel):
    """Schema dau vao cho cong cu doc hop dong."""
    duong_dan: StrictStr = Field(
        ...,
        description="Duong dan tuyet doi toi file hop dong PDF",
    )

    @field_validator("duong_dan", mode="after")
    @classmethod
    def kiem_tra_duong_dan(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Duong dan file khong duoc de trong.")
        if ".." in v:
            raise ValueError("Duong dan khong duoc chua '..' (path traversal bi chan).")
        return v


# ---------------------------------------------------------------------------
# MCP Tool Implementations
# ---------------------------------------------------------------------------

@mcp_tool("doc_nhan_hoa_don")
async def doc_nhan_hoa_don(params: DocHoaDonInput) -> dict[str, Any]:
    """
    Đọc hóa đơn thật bằng Gemini Vision OCR và bóc tách thông tin.

    Luồng xử lý:
      1. Validate input (Pydantic + path traversal check)
      2. Kiểm tra định dạng file (whitelist)
      3. Gọi Gemini 1.5 Flash với prompt kiểm toán chuyên nghiệp
      4. Parse JSON response
      5. Trả về kết quả có cấu trúc

    Nếu file không phải hóa đơn → Gemini trả về is_valid=false + error_message.
    Nếu không có GOOGLE_API_KEY → fallback sang demo data.

    Guardrails:
      - Không cho phép path traversal (..)
      - Chỉ chấp nhận định dạng ảnh/PDF
      - Gemini chỉ đọc, không ghi/thực thi
      - Audit log mọi lần gọi
    """
    tool_name = "doc_nhan_hoa_don"
    _nhat_ky(tool_name, {"duong_dan": params.duong_dan})

    try:
        # Nếu không có API key → fallback demo mode
        if not _GOOGLE_API_KEY:
            logger.warning(
                "[OCR] GOOGLE_API_KEY chưa thiết lập → chạy fallback demo mode"
            )
            return {
                "status": "ok",
                "cong_cu": tool_name,
                "che_do": "demo_fallback",
                "canh_bao": "Chưa có GOOGLE_API_KEY. Đặt biến môi trường để dùng OCR thật.",
                "du_lieu": _DU_LIEU_MOCK_FALLBACK,
            }

        ket_qua = await _goi_gemini_vision(params.duong_dan, _PROMPT_HOA_DON)

        # Kiểm tra is_valid từ Gemini
        if not ket_qua.get("is_valid", True):
            logger.warning(
                "[OCR] File không hợp lệ: %s — Lý do: %s",
                params.duong_dan,
                ket_qua.get("error_message", "Không rõ"),
            )
            return {
                "status": "khong_hop_le",
                "cong_cu": tool_name,
                "che_do": "gemini_vision",
                "loi": ket_qua.get("error_message", "File không phải hóa đơn hợp lệ"),
                "du_lieu": None,
            }

        # Bổ sung trường so_hoa_don nếu Gemini bỏ qua
        if "so_hoa_don" not in ket_qua or not ket_qua.get("so_hoa_don"):
            ten_file = Path(params.duong_dan).stem
            ket_qua["so_hoa_don"] = ten_file

        logger.info(
            "[OCR] ✅ OCR thành công: %s — HD: %s, Người bán: %s, MST: %s, Tổng: %s",
            Path(params.duong_dan).name,
            ket_qua.get("so_hoa_don"),
            ket_qua.get("ten_nguoi_ban"),
            ket_qua.get("mst_nguoi_ban"),
            ket_qua.get("tong_tien"),
        )

        return {
            "status": "ok",
            "cong_cu": tool_name,
            "che_do": "gemini_vision",
            "du_lieu": ket_qua,
        }

    except FileNotFoundError as exc:
        logger.error("[OCR] File không tìm thấy: %s", exc)
        return {
            "status": "error",
            "cong_cu": tool_name,
            "loai_loi": "FileNotFoundError",
            "thong_bao": str(exc),
        }

    except ValueError as exc:
        # Bao gồm: định dạng sai, JSON parse lỗi, path traversal
        logger.warning("[OCR] Lỗi validation: %s", exc)
        return {
            "status": "error",
            "cong_cu": tool_name,
            "loai_loi": "ValidationError",
            "thong_bao": str(exc),
        }

    except RuntimeError as exc:
        # API key thiếu, thư viện thiếu
        logger.error("[OCR] Lỗi cấu hình: %s", exc)
        return {
            "status": "error",
            "cong_cu": tool_name,
            "loai_loi": "ConfigError",
            "thong_bao": str(exc),
        }

    except Exception as exc:
        logger.exception("[OCR] Lỗi không mong đợi trong %s", tool_name)
        return {
            "status": "error",
            "cong_cu": tool_name,
            "loai_loi": type(exc).__name__,
            "thong_bao": str(exc),
        }


@mcp_tool("doc_hop_dong")
async def doc_hop_dong(params: DocHopDongInput) -> dict[str, Any]:
    """
    Đọc hợp đồng bằng Gemini Vision OCR.

    Trả về JSON chứa: ngày ký, bên A, bên B, giá trị hợp đồng.
    Nếu file không phải hợp đồng → is_valid=false.
    """
    tool_name = "doc_hop_dong"
    _nhat_ky(tool_name, {"duong_dan": params.duong_dan})

    try:
        if not _GOOGLE_API_KEY:
            logger.warning("[OCR] GOOGLE_API_KEY chưa thiết lập → fallback demo mode")
            return {
                "status": "ok",
                "cong_cu": tool_name,
                "che_do": "demo_fallback",
                "canh_bao": "Chưa có GOOGLE_API_KEY.",
                "du_lieu": _DU_LIEU_HOP_DONG_FALLBACK,
            }

        ket_qua = await _goi_gemini_vision(params.duong_dan, _PROMPT_HOP_DONG)

        if not ket_qua.get("is_valid", True):
            return {
                "status": "khong_hop_le",
                "cong_cu": tool_name,
                "che_do": "gemini_vision",
                "loi": ket_qua.get("error_message", "File không phải hợp đồng hợp lệ"),
                "du_lieu": None,
            }

        return {
            "status": "ok",
            "cong_cu": tool_name,
            "che_do": "gemini_vision",
            "du_lieu": ket_qua,
        }

    except FileNotFoundError as exc:
        return {
            "status": "error", "cong_cu": tool_name,
            "loai_loi": "FileNotFoundError", "thong_bao": str(exc),
        }
    except ValueError as exc:
        return {
            "status": "error", "cong_cu": tool_name,
            "loai_loi": "ValidationError", "thong_bao": str(exc),
        }
    except RuntimeError as exc:
        return {
            "status": "error", "cong_cu": tool_name,
            "loai_loi": "ConfigError", "thong_bao": str(exc),
        }
    except Exception as exc:
        logger.exception("[OCR] Lỗi không mong đợi trong %s", tool_name)
        return {
            "status": "error", "cong_cu": tool_name,
            "loai_loi": type(exc).__name__, "thong_bao": str(exc),
        }
