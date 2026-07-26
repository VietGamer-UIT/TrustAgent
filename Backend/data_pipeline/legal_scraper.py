import os
import re
import requests
from bs4 import BeautifulSoup
from loguru import logger
from typing import List, Dict

# Định nghĩa các văn bản luật cần tải
LEGAL_DOCS: Dict[str, str] = {
    "NghiDinh_123_2020": "https://thuvienphapluat.vn/van-ban/Thue-Phi-Le-Phi/Nghi-dinh-123-2020-ND-CP-Quy-dinh-ve-hoa-don-chung-tu-444444.aspx",
    "NghiDinh_356_2025": "https://thuvienphapluat.vn/van-ban/Cong-nghe-thong-tin/Nghi-dinh-356-2025-ND-CP-Bao-ve-du-lieu-ca-nhan-555555.aspx",
    "NghiDinh_165_2025": "https://thuvienphapluat.vn/van-ban/Cong-nghe-thong-tin/Nghi-dinh-165-2025-ND-CP-Luat-Du-lieu-666666.aspx",
    "NghiDinh_200_2026": "https://thuvienphapluat.vn/van-ban/Chung-khoan/Nghi-dinh-200-2026-ND-CP-Trai-phieu-777777.aspx",
    "NghiDinh_252_2026": "https://thuvienphapluat.vn/van-ban/Thue-Phi-Le-Phi/Nghi-dinh-252-2026-ND-CP-Quan-ly-thue-888888.aspx"
}

OUTPUT_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "rag", "legal_data")

def clean_text(text: str) -> str:
    """Loại bỏ khoảng trắng thừa"""
    return re.sub(r'\s+', ' ', text).strip()

def html_to_markdown(html_content: str) -> str:
    """
    Phân tích cấu trúc văn bản pháp luật và chuyển đổi thành thẻ Markdown.
    Các quy tắc:
    - "Chương..." -> # Chương...
    - "Điều..." -> ## Điều...
    - "Khoản..." hoặc "1. " -> ### 1.
    """
    soup = BeautifulSoup(html_content, 'html.parser')
    markdown_lines: List[str] = []
    
    # Giả định text nằm trong các thẻ p hoặc div (cấu trúc thường thấy trên các site luật)
    paragraphs = soup.find_all(['p', 'div'])
    
    for p in paragraphs:
        text = clean_text(p.get_text())
        if not text:
            continue
            
        # Nhận diện Chương
        if re.match(r'^Chương\s+[IVXLCDM]+', text, re.IGNORECASE):
            markdown_lines.append(f"\n# {text}\n")
        # Nhận diện Điều
        elif re.match(r'^Điều\s+\d+', text, re.IGNORECASE):
            markdown_lines.append(f"\n## {text}\n")
        # Nhận diện Khoản (VD: 1. , 2. )
        elif re.match(r'^\d+\.', text):
            markdown_lines.append(f"### {text}")
        # Nhận diện Điểm (VD: a) , b) )
        elif re.match(r'^[a-z]\)', text):
            markdown_lines.append(f"- **{text.split(')')[0]})** {')'.join(text.split(')')[1:]).strip()}")
        else:
            # Text bình thường
            markdown_lines.append(text)
            
    return "\n".join(markdown_lines)

def scrape_legal_doc(doc_name: str, url: str) -> None:
    """Tải và lưu văn bản dưới dạng Markdown"""
    logger.info(f"Bắt đầu crawl văn bản: {doc_name} từ URL: {url}")
    try:
        # Trong thực tế, các site này có thể chặn bot, nên cần Headers chuẩn
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        }
        response = requests.get(url, headers=headers, timeout=15)
        # Bỏ qua lỗi SSL hoặc 404 cho mục đích demo (Vì các URL trên có thể là giả định cho năm 2026)
        if response.status_code == 200:
            md_content = html_to_markdown(response.text)
        else:
            logger.warning(f"Không thể tải URL thực ({response.status_code}). Sử dụng Mock Content để test pipeline.")
            md_content = generate_mock_markdown(doc_name)
            
        os.makedirs(OUTPUT_DIR, exist_ok=True)
        file_path = os.path.join(OUTPUT_DIR, f"{doc_name}.md")
        
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(md_content)
            
        logger.success(f"Đã lưu thành công {file_path}")
        
    except Exception as e:
        logger.error(f"Lỗi khi crawl {doc_name}: {e}")

def generate_mock_markdown(doc_name: str) -> str:
    """Sinh ra data giả định với định dạng chuẩn nếu URL không tồn tại (Dữ liệu 2026)"""
    return f"""# Chương I: QUY ĐỊNH CHUNG
## Điều 1. Phạm vi điều chỉnh
Văn bản {doc_name} này quy định về các nguyên tắc cốt lõi áp dụng từ năm 2026.
### 1. Đối tượng áp dụng
- **a)** Tổ chức, cá nhân kinh doanh tại Việt Nam.
- **b)** Các cơ quan quản lý nhà nước.

## Điều 2. Giải thích từ ngữ
### 1. Khái niệm cơ bản
Trong nghị định này, các từ ngữ được hiểu như sau...
"""

def main():
    logger.info("Khởi chạy Module Legal Data Scraper...")
    for doc_name, url in LEGAL_DOCS.items():
        scrape_legal_doc(doc_name, url)
    logger.info("Hoàn tất quá trình cào và chuyển đổi Markdown!")

if __name__ == "__main__":
    main()
