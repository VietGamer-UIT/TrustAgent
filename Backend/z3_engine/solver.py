import z3
from loguru import logger
from typing import Dict, Any, Tuple, List

class LegalSolver:
    def __init__(self):
        self.solver = z3.Solver()
        # Khai báo các biến Z3 đại diện cho các thông số hợp đồng
        self.tong_gia_tri = z3.Real('tong_gia_tri')
        self.phat_vi_pham = z3.Real('phat_vi_pham')
        self.thue_suat = z3.Real('thue_suat')
        
    def check_compliance(self, contract_data: Dict[str, Any], context_rules: str = "") -> Tuple[str, List[Dict[str, Any]]]:
        """
        Kiểm tra tính hợp lệ của hợp đồng bằng Z3 Solver.
        Trả về (Trạng thái SAT/UNSAT, danh sách lỗi).
        """
        self.solver.reset()
        violations = []
        
        # Lấy dữ liệu thực tế từ contract_data (Fallback về 0 nếu không có)
        val_tong_gia_tri = float(contract_data.get("tong_gia_tri", 0))
        val_phat_vi_pham = float(contract_data.get("phat_vi_pham", 0))
        val_thue_suat = float(contract_data.get("thue_suat", 0))

        # Thêm các ràng buộc thực tế (Facts)
        self.solver.add(self.tong_gia_tri == val_tong_gia_tri)
        self.solver.add(self.phat_vi_pham == val_phat_vi_pham)
        self.solver.add(self.thue_suat == val_thue_suat)

        # ---------------------------------------------------------
        # Các quy tắc pháp lý (Legal Constraints)
        # Có thể parse thêm từ context_rules, nhưng hardcode các luật cơ bản trước.
        # ---------------------------------------------------------

        # Rule 1: Mức phạt vi phạm hợp đồng thương mại không được vượt quá 8% giá trị phần nghĩa vụ hợp đồng bị vi phạm 
        # (Điều 301 Luật Thương mại 2005). Giả định phần bị vi phạm = tổng giá trị.
        self.solver.add(self.phat_vi_pham <= self.tong_gia_tri * 0.08)

        # Rule 2: Thuế suất VAT phải là số dương và hợp lý (0, 5, 8, 10, v.v...)
        self.solver.add(self.thue_suat >= 0)
        self.solver.add(self.thue_suat <= 100)

        # Kiểm tra tính khả thi (SAT)
        # Z3 đang tìm kiếm một model thỏa mãn CẢ giá trị thực tế VÀ quy định luật.
        result = self.solver.check()
        
        if result == z3.unsat:
            status = "UNSAT"
            # Logic fallback để xác định chính xác rule nào bị vi phạm
            if val_phat_vi_pham > val_tong_gia_tri * 0.08:
                violations.append({
                    "rule": "Luật Thương mại 2005 - Điều 301",
                    "description": f"Mức phạt vi phạm ({val_phat_vi_pham:,.0f}) vượt quá 8% tổng giá trị hợp đồng ({val_tong_gia_tri * 0.08:,.0f}).",
                    "severity": "high"
                })
            if val_thue_suat < 0 or val_thue_suat > 100:
                 violations.append({
                    "rule": "Luật Thuế",
                    "description": f"Thuế suất ({val_thue_suat}%) không hợp lệ.",
                    "severity": "high"
                })
            if not violations:
                violations.append({
                    "rule": "Quy tắc không xác định",
                    "description": "Các điều khoản hợp đồng mâu thuẫn với quy định pháp luật hoặc logic (Z3 UNSAT).",
                    "severity": "high"
                })
        else:
            status = "SAT"
            
        logger.info(f"[LegalSolver] Kết quả Z3: {status}. Số lỗi: {len(violations)}")
        return status, violations
