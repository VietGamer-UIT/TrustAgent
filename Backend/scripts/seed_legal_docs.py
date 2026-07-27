import os
from loguru import logger

def seed_legal_docs():
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    rag_dir = os.path.join(base_dir, "data_pipeline", "legal_docs")
    
    os.makedirs(rag_dir, exist_ok=True)
    
    # 1. Luật Thương mại 2005
    luat_thuong_mai = """# Luật Thương mại 2005
## Điều 301. Mức phạt vi phạm
Mức phạt đối với vi phạm nghĩa vụ hợp đồng hoặc tổng mức phạt đối với nhiều vi phạm do các bên thoả thuận trong hợp đồng, nhưng không quá 8% giá trị phần nghĩa vụ hợp đồng bị vi phạm, trừ trường hợp quy định tại Điều 266 của Luật này.
"""
    file1 = os.path.join(rag_dir, "luat_thuong_mai_2005.md")
    with open(file1, "w", encoding="utf-8") as f:
        f.write(luat_thuong_mai)
        
    # 2. Nghị định 123/2020/NĐ-CP
    nghi_dinh_123 = """# Nghị định 123/2020/NĐ-CP - Quy định về Hóa đơn, chứng từ
## Điều 9. Thời điểm lập hóa đơn
1. Thời điểm lập hóa đơn đối với bán hàng hóa là thời điểm chuyển giao quyền sở hữu hoặc quyền sử dụng hàng hóa cho người mua, không phân biệt đã thu được tiền hay chưa.
2. Thời điểm lập hóa đơn đối với cung cấp dịch vụ là thời điểm hoàn thành việc cung cấp dịch vụ.

## Điều 10. Nội dung của hóa đơn
7. Chữ ký của người bán, chữ ký của người mua. Thời điểm ký số trên hóa đơn điện tử là thời điểm người bán, người mua sử dụng chữ ký số để ký trên hóa đơn điện tử.
"""
    file2 = os.path.join(rag_dir, "nghi_dinh_123_2020.md")
    with open(file2, "w", encoding="utf-8") as f:
        f.write(nghi_dinh_123)
        
    logger.success(f"Đã tạo thành công dữ liệu RAG mẫu tại: {rag_dir}")

if __name__ == "__main__":
    seed_legal_docs()
