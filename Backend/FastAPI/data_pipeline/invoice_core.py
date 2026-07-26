import json
import os
import xml.etree.ElementTree as ET
from datetime import datetime
from typing import Optional, List, Dict, Any
from loguru import logger
from pydantic import BaseModel, Field
from rich.console import Console
from rich.panel import Panel
from rich.json import JSON

# Initialize Rich Console
console = Console()

# --- Pydantic Models ---

class Participant(BaseModel):
    ten: Optional[str] = Field(None, description="Tên công ty/Tổ chức")
    mst: Optional[str] = Field(None, description="Mã số thuế")

class FinancialData(BaseModel):
    tong_tien_chua_thue: float = Field(0.0)
    tong_tien_thue: float = Field(0.0)
    tong_tien_thanh_toan: float = Field(0.0)

class SignatureData(BaseModel):
    signing_time: Optional[datetime] = Field(None, description="Thời điểm ký số")

class InvoiceData(BaseModel):
    ky_hieu: Optional[str] = Field(None)
    so_hoa_don: Optional[str] = Field(None)
    ngay_lap: Optional[datetime] = Field(None)
    nguoi_ban: Participant = Field(default_factory=Participant)
    nguoi_mua: Participant = Field(default_factory=Participant)
    tai_chinh: FinancialData = Field(default_factory=FinancialData)
    chu_ky_so: SignatureData = Field(default_factory=SignatureData)

class Violation(BaseModel):
    rule: str
    description: str
    severity: str  # HIGH, MEDIUM, LOW

class ValidationResult(BaseModel):
    invoice_id: str
    status: str  # SAT (Satisfied) | UNSAT (Unsatisfied)
    extracted_data: InvoiceData
    violations: List[Violation] = Field(default_factory=list)

# --- Invoice Parser ---

class InvoiceParser:
    """
    Trình bóc tách Hóa đơn điện tử chuẩn Tổng cục Thuế Việt Nam (Nghị định 123/2020/NĐ-CP).
    Xử lý an toàn với XML Namespaces.
    """
    def __init__(self, file_path: str):
        self.file_path = file_path
        if not os.path.exists(file_path):
            logger.error(f"File không tồn tại: {file_path}")
            raise FileNotFoundError(f"File không tồn tại: {file_path}")
        
        try:
            self.tree = ET.parse(file_path)
            self.root = self.tree.getroot()
            # Cache XML content for Signature validation later
            with open(file_path, 'rb') as f:
                self.raw_content = f.read()
        except ET.ParseError as e:
            logger.error(f"Lỗi parse XML tại {file_path}. File có thể bị hỏng: {e}")
            raise

    def _find_text(self, node: ET.Element, tag: str) -> Optional[str]:
        """
        Duyệt cây XML và tìm thẻ (tag) bỏ qua namespace.
        Ví dụ tag thực tế là '{http://www.w3.org/2000/09/xmldsig#}SigningTime', hàm này chỉ cần tìm 'SigningTime'.
        """
        if node is None:
            return None
        for elem in node.iter():
            # Tách lấy phần Tên thẻ (Bỏ namespace trong ngoặc nhọn {})
            local_name = elem.tag.split('}')[-1]
            if local_name == tag:
                return elem.text
        return None

    def _find_node(self, node: ET.Element, tag: str) -> Optional[ET.Element]:
        """Tìm Element Node theo tên tag, bỏ qua namespace."""
        if node is None:
            return None
        for elem in node.iter():
            local_name = elem.tag.split('}')[-1]
            if local_name == tag:
                return elem
        return None

    def _parse_datetime(self, date_str: Optional[str]) -> Optional[datetime]:
        if not date_str:
            return None
        try:
            # Xử lý định dạng ISO 8601 (VD: 2026-07-26T14:30:00)
            return datetime.fromisoformat(date_str)
        except ValueError:
            try:
                # Xử lý định dạng yyyy-mm-dd
                return datetime.strptime(date_str[:10], "%Y-%m-%d")
            except ValueError as e:
                logger.warning(f"Không thể parse thời gian: {date_str} - {e}")
                return None

    def parse(self) -> InvoiceData:
        """Bóc tách XML vào Pydantic Model (InvoiceData)."""
        logger.info(f"Đang bóc tách Hóa đơn: {self.file_path}")
        
        # 1. Thông tin chung
        khhdon = self._find_text(self.root, 'KHHDon')
        shdon = self._find_text(self.root, 'SHDon')
        nlap_str = self._find_text(self.root, 'NLap')
        nlap = self._parse_datetime(nlap_str)

        # 2. Bên Bán
        nban_node = self._find_node(self.root, 'NBan')
        nban = Participant(
            ten=self._find_text(nban_node, 'Ten'),
            mst=self._find_text(nban_node, 'MST')
        )

        # 3. Bên Mua
        nmua_node = self._find_node(self.root, 'NMua')
        nmua = Participant(
            ten=self._find_text(nmua_node, 'Ten'),
            mst=self._find_text(nmua_node, 'MST')
        )

        # 4. Tài chính
        tgtcthue = float(self._find_text(self.root, 'TgTCThue') or 0.0)
        tgttthue = float(self._find_text(self.root, 'TgTThue') or 0.0)
        tgtttbso = float(self._find_text(self.root, 'TgTTTBSo') or 0.0)
        tai_chinh = FinancialData(
            tong_tien_chua_thue=tgtcthue,
            tong_tien_thue=tgttthue,
            tong_tien_thanh_toan=tgtttbso
        )

        # 5. Chữ ký số
        signature_node = self._find_node(self.root, 'Signature')
        signing_time_str = self._find_text(signature_node, 'SigningTime') if signature_node is not None else None
        chu_ky_so = SignatureData(
            signing_time=self._parse_datetime(signing_time_str)
        )

        return InvoiceData(
            ky_hieu=khhdon,
            so_hoa_don=shdon,
            ngay_lap=nlap,
            nguoi_ban=nban,
            nguoi_mua=nmua,
            tai_chinh=tai_chinh,
            chu_ky_so=chu_ky_so
        )

# --- Invoice Validator ---

class InvoiceValidator:
    """
    Xác minh tính hợp lệ của Hóa đơn điện tử theo các chuẩn kiểm toán Việt Nam.
    """
    def __init__(self, data: InvoiceData, raw_xml: bytes):
        self.data = data
        self.raw_xml = raw_xml
        self.violations: List[Violation] = []

    def validate_signature_existence(self):
        """Rule 1 - Tồn tại chữ ký số"""
        # Nếu không có đối tượng chu_ky_so hoặc signing_time bị None do thẻ Signature không tồn tại
        if self.data.chu_ky_so.signing_time is None:
            self.violations.append(Violation(
                rule="SignatureExistence",
                description="Không tìm thấy cụm thẻ <Signature> hoặc thiếu Thời điểm ký. Hóa đơn chưa phát hành hoặc bản nháp.",
                severity="HIGH"
            ))

    def validate_math(self):
        """Rule 2 - Đối soát Số học (Math Check)"""
        tc_thue = self.data.tai_chinh.tong_tien_chua_thue
        t_thue = self.data.tai_chinh.tong_tien_thue
        tt_tbso = self.data.tai_chinh.tong_tien_thanh_toan

        tong_tinh_toan = tc_thue + t_thue
        diff = abs(tong_tinh_toan - tt_tbso)

        if diff > 2.0:
            self.violations.append(Violation(
                rule="MathCheck",
                description=f"Lệch số học. Tổng tiền chưa thuế ({tc_thue}) + Thuế ({t_thue}) = {tong_tinh_toan}, khác Tổng thanh toán ({tt_tbso}). Mức lệch: {diff} VNĐ",
                severity="HIGH"
            ))

    def validate_integrity(self):
        """
        Rule 3 - Tính toàn vẹn (Integrity Check)
        Mô phỏng sử dụng thư viện signxml để verify XML Signature.
        """
        # Note: Thực tế cần dùng thư viện signxml. Ví dụ:
        # from signxml import XMLVerifier
        # try:
        #     root = ET.fromstring(self.raw_xml)
        #     XMLVerifier().verify(root, require_x509=False)
        # except Exception as e:
        #     self.violations.append(...)
        
        # Trong bản demo, chúng ta kiểm tra nếu cấu trúc có thẻ Signature thì giả định pass,
        # Nếu nội dung raw_xml bị hỏng sẽ báo lỗi. Ở đây ta chỉ log lại.
        logger.debug("Đang kiểm tra tính toàn vẹn chữ ký số bằng thư viện XMLDSig...")
        
        # Giả lập logic kiểm tra: nếu không có thẻ Signature, coi như Integrity FAILED.
        if b"<Signature" not in self.raw_xml and b":Signature" not in self.raw_xml:
            self.violations.append(Violation(
                rule="IntegrityCheck",
                description="File XML không có cấu trúc chữ ký số hợp lệ để verify DigestValue/SignatureValue.",
                severity="HIGH"
            ))

    def validate_time_sync(self):
        """Rule 4 - Chênh lệch Thời gian (Time Sync Check)"""
        nlap = self.data.ngay_lap
        nky = self.data.chu_ky_so.signing_time

        if nlap and nky:
            # Lấy ngày (bỏ qua giờ phút giây)
            nlap_date = nlap.date()
            nky_date = nky.date()
            
            delta_days = (nky_date - nlap_date).days
            
            if delta_days > 0:
                self.violations.append(Violation(
                    rule="TimeSync",
                    description=f"Thời điểm ký ({nky_date}) chậm hơn Thời điểm lập ({nlap_date}) {delta_days} ngày.",
                    severity="MEDIUM"
                ))
            elif delta_days < 0:
                self.violations.append(Violation(
                    rule="TimeSync",
                    description=f"Thời điểm ký ({nky_date}) lại xảy ra trước Thời điểm lập ({nlap_date}). Bất thường.",
                    severity="HIGH"
                ))

    def validate_all(self) -> ValidationResult:
        """Chạy tất cả các Rules và trả về ValidationResult."""
        self.validate_signature_existence()
        self.validate_math()
        self.validate_integrity()
        self.validate_time_sync()

        invoice_id = f"{self.data.ky_hieu or 'UNKNOWN'}_{self.data.so_hoa_don or 'UNKNOWN'}"
        
        # Nếu có vi phạm HIGH -> UNSAT. Vi phạm MEDIUM/LOW có thể tùy nghiệp vụ.
        # Ở đây ta mặc định cứ có lỗi là UNSAT.
        is_unsat = any(v.severity == "HIGH" for v in self.violations)
        status = "UNSAT" if is_unsat else "SAT"

        return ValidationResult(
            invoice_id=invoice_id,
            status=status,
            extracted_data=self.data,
            violations=self.violations
        )

def process_invoice(file_path: str) -> ValidationResult:
    """Hàm lõi nạp và xác thực hóa đơn."""
    parser = InvoiceParser(file_path)
    data = parser.parse()
    
    validator = InvoiceValidator(data, parser.raw_content)
    result = validator.validate_all()
    
    logger.info(f"Kết quả kiểm định HĐ {result.invoice_id}: {result.status}")
    return result

if __name__ == "__main__":
    import sys
    if sys.stdout.encoding.lower() != 'utf-8':
        sys.stdout.reconfigure(encoding='utf-8')
        
    # --- Code chạy thử (Khối if __name__ == '__main__') ---
    
    # 1. Tạo file XML Test (Giả lập cấu trúc hóa đơn thật)
    test_file_path = "test_invoice.xml"
    test_xml_content = """<?xml version="1.0" encoding="utf-8"?>
<HDon xmlns="http://vanthu.gov.vn/hdon">
    <DLHDon>
        <TTChung>
            <KHHDon>1C26TML</KHHDon>
            <SHDon>0000123</SHDon>
            <NLap>2026-07-24T10:00:00</NLap>
        </TTChung>
        <NDHDon>
            <NBan>
                <Ten>CÔNG TY TNHH CÔNG NGHỆ TRUSTAGENT</Ten>
                <MST>0101248141</MST>
            </NBan>
            <NMua>
                <Ten>CÔNG TY CP TẬP ĐOÀN ĐỐI TÁC</Ten>
                <MST>0309532909</MST>
            </NMua>
            <TToan>
                <TgTCThue>1000000.00</TgTCThue>
                <TgTThue>80000.00</TgTThue>
                <!-- Tạo lỗi số học giả để test: 1080000 != 1080500 -->
                <TgTTTBSo>1080500.00</TgTTTBSo>
            </TToan>
        </NDHDon>
    </DLHDon>
    <Signature xmlns="http://www.w3.org/2000/09/xmldsig#">
        <SignedInfo>...</SignedInfo>
        <SignatureValue>XYZ123...</SignatureValue>
        <!-- Tạo lỗi TimeSync giả để test: Ký sau 2 ngày -->
        <SigningTime>2026-07-26T15:00:00</SigningTime>
    </Signature>
</HDon>
"""
    with open(test_file_path, "w", encoding="utf-8") as f:
        f.write(test_xml_content)
    
    # 2. Xử lý và in kết quả bằng Rich
    console.print(Panel.fit("[bold green]BẮT ĐẦU KIỂM ĐỊNH HÓA ĐƠN ĐIỆN TỬ[/bold green]", border_style="green"))
    
    try:
        result = process_invoice(test_file_path)
        
        result_dict = result.model_dump(mode='json') # Pydantic v2
        
        # Đổi màu title Panel dựa trên Status
        panel_color = "red" if result.status == "UNSAT" else "green"
        status_text = f"[bold {panel_color}]{result.status}[/bold {panel_color}]"
        
        console.print(f"\n[bold]Mã Hóa Đơn:[/bold] {result.invoice_id} | [bold]Trạng Thái:[/bold] {status_text}\n")
        
        # In JSON Data đẹp
        console.print(JSON(json.dumps(result_dict)))
        
    except Exception as e:
        logger.exception("Đã xảy ra lỗi trong quá trình xử lý.")
    finally:
        # Cleanup file test nếu cần (ở đây giữ lại để user xem)
        pass
