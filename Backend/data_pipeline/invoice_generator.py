import os
import random
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from faker import Faker
from loguru import logger

fake = Faker('vi_VN')
OUTPUT_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data_pipeline", "invoices")

# Danh sách MST mồi hợp lệ (Bắt đầu bằng 01 hoặc 03)
VALID_MSTS = [
    "0101248141", "0309532909", "0100109106", "0312771587", "0106774400"
]

ITEMS = [
    {"name": "Laptop Dell Latitude 7420", "price": 25000000},
    {"name": "Dịch vụ tư vấn phần mềm", "price": 150000000},
    {"name": "Giấy in A4 Double A", "price": 85000},
    {"name": "Bàn phím cơ Keychron", "price": 2500000},
    {"name": "Bản quyền Office 365", "price": 1200000}
]

def generate_random_mst() -> str:
    """Sinh MST ngẫu nhiên bắt đầu bằng 01 hoặc 03, dài 10 số"""
    prefix = random.choice(["01", "03"])
    suffix = "".join([str(random.randint(0, 9)) for _ in range(8)])
    return prefix + suffix

def generate_invoice_xml(filename: str, is_poisoned: bool = False) -> None:
    """
    Tạo file XML hóa đơn.
    Nếu is_poisoned = True, cố tình làm sai lệch toán học hoặc logic ngày tháng.
    """
    # Khởi tạo các node XML cơ bản (chuẩn TCHDon)
    root = ET.Element("HDon")
    tt_hdon = ET.SubElement(root, "TTHDon") # Thông tin hóa đơn
    nd_hdon = ET.SubElement(root, "NDHDon") # Nội dung hóa đơn
    
    # 1. Thông tin người bán & người mua
    nban = ET.SubElement(nd_hdon, "NBan")
    ET.SubElement(nban, "Ten").text = fake.company()
    ET.SubElement(nban, "MST").text = random.choice(VALID_MSTS)
    
    nmua = ET.SubElement(nd_hdon, "NMua")
    ET.SubElement(nmua, "Ten").text = fake.company()
    ET.SubElement(nmua, "MST").text = generate_random_mst()
    
    # 2. Chi tiết hàng hóa
    dshh = ET.SubElement(nd_hdon, "DSHHDVu")
    item = random.choice(ITEMS)
    quantity = random.randint(1, 10)
    unit_price = item["price"]
    total_amount_before_tax = quantity * unit_price
    tax_rate = random.choice([0.08, 0.10]) # 8% hoặc 10%
    tax_amount = int(total_amount_before_tax * tax_rate)
    total_amount = total_amount_before_tax + tax_amount
    
    # 3. Data Poisoning (20% bị sai lệch)
    sign_date = datetime.now() - timedelta(days=random.randint(1, 30))
    invoice_date = sign_date + timedelta(days=random.randint(1, 5))
    
    if is_poisoned:
        poison_type = random.choice(["math_error", "date_error"])
        if poison_type == "math_error":
            # Cộng sai tổng tiền hoặc tiền thuế
            tax_amount = tax_amount + random.randint(100000, 500000)
            total_amount = total_amount_before_tax + tax_amount - random.randint(50000, 200000)
            logger.debug(f"Đã tiêm độc (Toán học) vào file: {filename}")
        else:
            # Lỗi ngày: Ký hợp đồng sau khi xuất hóa đơn (Vô lý)
            sign_date = invoice_date + timedelta(days=random.randint(5, 15))
            logger.debug(f"Đã tiêm độc (Logic thời gian) vào file: {filename}")
            
    # Gắn vào XML
    ET.SubElement(tt_hdon, "NgayLap").text = invoice_date.strftime("%Y-%m-%d")
    ET.SubElement(tt_hdon, "NgayKy").text = sign_date.strftime("%Y-%m-%d")
    
    hh = ET.SubElement(dshh, "HHDVu")
    ET.SubElement(hh, "Ten").text = item["name"]
    ET.SubElement(hh, "SoLuong").text = str(quantity)
    ET.SubElement(hh, "DonGia").text = str(unit_price)
    ET.SubElement(hh, "ThanhTien").text = str(total_amount_before_tax)
    
    th_tien = ET.SubElement(nd_hdon, "THTTien")
    ET.SubElement(th_tien, "TienChuaThue").text = str(total_amount_before_tax)
    ET.SubElement(th_tien, "ThueSuat").text = f"{int(tax_rate*100)}%"
    ET.SubElement(th_tien, "TienThue").text = str(tax_amount)
    ET.SubElement(th_tien, "TongTien").text = str(total_amount)
    
    # Ghi file XML
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    tree = ET.ElementTree(root)
    tree.write(os.path.join(OUTPUT_DIR, filename), encoding="utf-8", xml_declaration=True)

def main():
    logger.info("Khởi chạy Module Synthetic Invoice Generator...")
    total_invoices = 1000
    poisoned_count = int(total_invoices * 0.20) # 20%
    normal_count = total_invoices - poisoned_count
    
    # Sinh hóa đơn chuẩn
    for i in range(normal_count):
        generate_invoice_xml(f"INV_{i+1:04d}.xml", is_poisoned=False)
        
    # Sinh hóa đơn lỗi
    for i in range(poisoned_count):
        generate_invoice_xml(f"ERR_INV_{normal_count+i+1:04d}.xml", is_poisoned=True)
        
    logger.success(f"Đã tạo thành công {total_invoices} hóa đơn (Gồm {poisoned_count} hóa đơn lỗi tại {OUTPUT_DIR})")

if __name__ == "__main__":
    main()
