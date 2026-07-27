# =============================================================================
# TrustAgent :: Chứng Từ Agent (Document Agent)
# Bản quyền: TrustAgent bởi Đoàn Hoàng Việt (Việt Gamer)
# =============================================================================
# Agent chuyên trách đọc và phân tích hóa đơn chuẩn XML (Nghị định 123)
# =============================================================================

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any
import os

from core.state import TrustAgentState
from data_pipeline.invoice_core import (
    process_invoice, ValidationResult, 
    BatchInvoiceParser, InvoiceValidator
)

logger = logging.getLogger("trustagent.agents.chung_tu")
TEN_AGENT: str = "chung_tu_agent"

async def chung_tu_agent_node(state: TrustAgentState) -> dict:
    """
    LangGraph node: Chứng Từ Agent (Document Agent).
    Đọc hóa đơn XML bằng bộ parser chuẩn (invoice_core) và kiểm tra lỗi số học, chữ ký số.
    """
    messages = list(state.get("messages", []))
    error_log = list(state.get("error_log", []))
    duong_dan = state.get("evidence_paths", [])

    logger.info("[%s] Bắt đầu — %d chứng từ cần đọc", TEN_AGENT, len(duong_dan))
    messages.append({
        "role": "assistant",
        "agent": TEN_AGENT,
        "content": f"Bắt đầu đọc và phân tích {len(duong_dan)} file chứng từ bằng invoice_core.",
        "timestamp": datetime.now(tz=timezone.utc).isoformat(),
    })

    tat_ca_hoa_don: list[dict[str, Any]] = []
    loi_tong_hop: list[dict[str, Any]] = []
    bo_dem_so: dict[str, list[dict]] = {}

    def _append_invoice_result(res: ValidationResult, file_path: str):
        hd_dict = {
            "so_hoa_don": res.extracted_data.so_hoa_don,
            "ky_hieu": res.extracted_data.ky_hieu,
            "tien_hang": res.extracted_data.tai_chinh.tong_tien_chua_thue,
            "thue_suat_vat": 0, 
            "tien_thue_vat": res.extracted_data.tai_chinh.tong_tien_thue,
            "tong_tien": res.extracted_data.tai_chinh.tong_tien_thanh_toan,
            "mst_nguoi_ban": res.extracted_data.nguoi_ban.mst,
            "ten_nguoi_ban": res.extracted_data.nguoi_ban.ten,
            "mst_nguoi_mua": res.extracted_data.nguoi_mua.mst,
            "ngay_lap": res.extracted_data.ngay_lap.isoformat() if res.extracted_data.ngay_lap else None,
            "file_path": str(file_path)
        }
        tat_ca_hoa_don.append(hd_dict)

        for v in res.violations:
            loi_tong_hop.append({
                "so_hoa_don": hd_dict["so_hoa_don"],
                "loai_loi": v.rule,
                "mo_ta": v.description,
                "muc_do": v.severity.lower(),
            })
        
        key = f"{hd_dict.get('so_hoa_don', '')}_{hd_dict.get('ky_hieu', '')}"
        bo_dem_so.setdefault(key, []).append(hd_dict)

    for path in duong_dan:
        path_str = str(path).lower()
        
        try:
            if path_str.endswith('.xml'):
                # 1. Parse và Validate bằng process_invoice cho file đơn lẻ (REAL DATA PIPELINE)
                result: ValidationResult = process_invoice(path)
                _append_invoice_result(result, path)
                
            elif path_str.endswith(('.csv', '.tsv', '.txt', '.xls', '.xlsx')):
                # 2. Xử lý Bảng kê Hóa đơn
                logger.info(f"Đang xử lý bảng kê: {path}")
                parser = BatchInvoiceParser(path)
                inv_data_list = parser.parse()
                for inv_data in inv_data_list:
                    validator = InvoiceValidator(inv_data, b"")
                    res = validator.validate_all()
                    _append_invoice_result(res, path)
            else:
                logger.info("Bỏ qua file không hỗ trợ: %s", path)
                
        except Exception as e:
            error_msg = str(e)
            logger.exception("Lỗi xử lý file: %s", path)
            error_log.append({
                "agent": TEN_AGENT,
                "cong_cu": "invoice_core",
                "lan_thu": 1,
                "loai_loi": type(e).__name__,
                "thong_bao": error_msg,
                "thoi_gian": datetime.now(tz=timezone.utc).isoformat(),
            })

    # 3. Kiểm tra trùng số hóa đơn
    trung_so: list[dict[str, Any]] = []
    for key, nhom in bo_dem_so.items():
        if len(nhom) > 1:
            trung_so.append({
                "so_hoa_don": nhom[0].get("so_hoa_don"),
                "ky_hieu": nhom[0].get("ky_hieu"),
                "loai_loi": "trung_so",
                "so_lan_xuat_hien": len(nhom),
                "mo_ta": f"Hóa đơn số {nhom[0].get('so_hoa_don')} ký hiệu {nhom[0].get('ky_hieu')} xuất hiện {len(nhom)} lần",
                "muc_do": "nghiêm trọng",
            })

    loi_tong_hop.extend(trung_so)
    tat_ca_loi = len(loi_tong_hop)
    
    if not tat_ca_hoa_don and error_log:
        status = "error"
    else:
        status = "ok"

    findings = {
        "status": status,
        "agent": TEN_AGENT,
        "tong_hoa_don": len(tat_ca_hoa_don),
        "tong_loi": tat_ca_loi,
    }

    messages.append({
        "role": "assistant",
        "agent": TEN_AGENT,
        "content": (
            f"Phân tích XML hoàn tất. Trạng thái: {findings['status']}. "
            f"Đọc được {len(tat_ca_hoa_don)} hóa đơn. "
            f"Phát hiện {tat_ca_loi} lỗi/cảnh báo từ invoice_core."
        ),
        "timestamp": datetime.now(tz=timezone.utc).isoformat(),
    })
    logger.info("[%s] Hoàn tất — status=%s, lỗi=%d", TEN_AGENT, findings["status"], tat_ca_loi)

    extracted_data = state.get("extracted_data", {}).copy()
    extracted_data["document_agent"] = findings["status"]

    return {
        "messages": messages,
        "error_log": error_log,
        "hoa_don_list": tat_ca_hoa_don,
        "tax_warnings": loi_tong_hop,
        "extracted_data": extracted_data,
        "current_agent": "supervisor",
    }

