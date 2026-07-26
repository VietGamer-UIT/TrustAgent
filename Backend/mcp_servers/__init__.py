# =============================================================================
# TrustAgent :: MCP Servers Package
# =============================================================================
# Registry thống nhất cho tất cả MCP tool servers.
#
# Servers:
#   - ocr_mcp    : Đọc hóa đơn/hợp đồng bằng OCR (mock Tesseract/Google Vision)
#   - thue_mcp   : Tra cứu MST & xác thực hóa đơn (mock API Tổng cục Thuế)
#   - thue_db_mcp: Tra cứu MST từ Local PostgreSQL Cache (latency < 5ms)
# =============================================================================

from .ocr_mcp import OCR_TOOL_REGISTRY
from .thue_mcp import THUE_TOOL_REGISTRY
from .thue_db_mcp import THUE_DB_TOOL_REGISTRY

# Registry tổng hợp — tất cả công cụ MCP có thể gọi.
MCP_TOOL_REGISTRY: dict = {
    **OCR_TOOL_REGISTRY,
    **THUE_TOOL_REGISTRY,
    **THUE_DB_TOOL_REGISTRY,
}

__all__ = [
    "MCP_TOOL_REGISTRY",
    "OCR_TOOL_REGISTRY",
    "THUE_TOOL_REGISTRY",
    "THUE_DB_TOOL_REGISTRY",
]
