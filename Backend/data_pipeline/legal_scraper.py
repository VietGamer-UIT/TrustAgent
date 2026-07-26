import os
import re
import time
import random
import requests
from bs4 import BeautifulSoup
from loguru import logger
from typing import List

# Đường dẫn lưu trữ dữ liệu pháp lý để Agent RAG đọc
OUTPUT_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "rag", "legal_data")

# Ví dụ về các URL VBPL thực tế (Người dùng sẽ cung cấp URL thật)
# Trong môi trường production, bạn có thể truyền list này từ config hoặc database
DEFAULT_URLS = [
    "https://vbpl.vn/tw/Pages/vbpq-toanvan.aspx?ItemID=141445", # Ví dụ Luật Doanh nghiệp 2020
    # Thêm các URL khác vào đây
]

class VBPLScraper:
    """
    Trình cào dữ liệu Văn bản pháp luật từ CSDL Quốc gia (vbpl.vn).
    Bắt buộc tuân thủ Polite Scraping để tránh bị block.
    """
    def __init__(self, urls: List[str] = None):
        self.urls = urls or DEFAULT_URLS
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept-Language': 'vi-VN,vi;q=0.9,en-US;q=0.8,en;q=0.7',
        }

    def _clean_text(self, text: str) -> str:
        """Loại bỏ khoảng trắng thừa"""
        return re.sub(r'\s+', ' ', text).strip()

    def _html_to_markdown(self, soup: BeautifulSoup) -> str:
        """
        Bóc tách phần nội dung toàn văn, nhận diện các thẻ <b>, <strong> 
        chứa chữ "Chương", "Điều" để chuyển đổi sang cấu trúc Markdown.
        """
        markdown_lines = []
        
        # Nội dung văn bản trên VBPL thường nằm trong div class 'toanvancontent'
        content_div = soup.find('div', class_='toanvancontent')
        if not content_div:
            # Fallback lấy body nếu cấu trúc đổi
            content_div = soup.body
            
        if not content_div:
            raise ValueError("Không tìm thấy nội dung văn bản trong HTML")

        # Duyệt qua tất cả các thẻ p, div có chứa text
        for tag in content_div.find_all(['p', 'div', 'b', 'strong', 'span']):
            # Bỏ qua các thẻ con nếu text của chúng đã được xử lý ở thẻ cha (tránh duplicate)
            # Tuy nhiên để đơn giản, ta sẽ quét các thẻ có nội dung và loại bỏ khoảng trắng.
            
            # Đối với <b>, <strong> chứa Chương/Điều
            if tag.name in ['b', 'strong'] or (tag.name == 'span' and tag.get('style') and 'bold' in tag.get('style')):
                text = self._clean_text(tag.get_text())
                if re.match(r'^Chương\s+[IVXLCDM]+', text, re.IGNORECASE):
                    markdown_lines.append(f"\n# {text}\n")
                    # Xóa nội dung tag để không bị append lại khi duyệt tag cha
                    tag.string = "" 
                    continue
                elif re.match(r'^Điều\s+\d+', text, re.IGNORECASE):
                    markdown_lines.append(f"\n## {text}\n")
                    tag.string = ""
                    continue
            
            # Nếu là thẻ p, div thông thường (và chưa bị xử lý ở trên)
            if tag.name in ['p', 'div']:
                text = self._clean_text(tag.get_text())
                if not text:
                    continue
                    
                # Xử lý các dạng list cơ bản
                if re.match(r'^\d+\.', text):
                    markdown_lines.append(f"### {text}")
                elif re.match(r'^[a-zđ]\)', text, re.IGNORECASE):
                    markdown_lines.append(f"- **{text.split(')')[0]})** {')'.join(text.split(')')[1:]).strip()}")
                else:
                    markdown_lines.append(text)
                    
        return "\n".join(markdown_lines)

    def scrape(self):
        """Thực thi cào dữ liệu qua danh sách URLs"""
        logger.info(f"Bắt đầu crawl {len(self.urls)} văn bản từ VBPL...")
        os.makedirs(OUTPUT_DIR, exist_ok=True)
        
        for index, url in enumerate(self.urls):
            logger.info(f"Đang xử lý URL [{index+1}/{len(self.urls)}]: {url}")
            
            try:
                # BẮT BUỘC: Polite Scraping
                delay = random.uniform(3, 7)
                logger.debug(f"Đợi {delay:.2f}s trước khi gọi request để tránh bị block...")
                time.sleep(delay)
                
                response = requests.get(url, headers=self.headers, timeout=30)
                
                if response.status_code != 200:
                    error_msg = f"Lỗi HTTP {response.status_code} khi truy cập {url}. Cấm fallback mock data."
                    logger.error(error_msg)
                    raise ConnectionError(error_msg)
                    
                soup = BeautifulSoup(response.content, 'html.parser', from_encoding='utf-8')
                
                # Trích xuất tiêu đề văn bản (để đặt tên file)
                title_tag = soup.find('title')
                doc_title = title_tag.get_text() if title_tag else f"VBPL_Document_{index}"
                doc_title = re.sub(r'[^a-zA-Z0-9_\-\s]', '', doc_title).strip().replace(' ', '_')
                
                md_content = self._html_to_markdown(soup)
                
                if not md_content.strip():
                    raise ValueError("Nội dung markdown rỗng sau khi parse. Cấu trúc web có thể đã thay đổi.")
                    
                file_path = os.path.join(OUTPUT_DIR, f"{doc_title}.md")
                
                with open(file_path, "w", encoding="utf-8") as f:
                    f.write(md_content)
                    
                logger.success(f"Đã lưu thành công: {file_path}")
                
            except Exception as e:
                logger.error(f"Lỗi khi crawl {url}: {e}")
                # Re-raise exception vì yêu cầu là tuyệt đối không dùng Mock data, lỗi phải văng ra.
                raise

if __name__ == "__main__":
    scraper = VBPLScraper()
    scraper.scrape()
