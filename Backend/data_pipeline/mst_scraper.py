import asyncio
import os
import random
from typing import List, Dict, Optional
from loguru import logger
from playwright.async_api import async_playwright, Page, BrowserContext
from playwright_stealth import stealth_async
from sqlalchemy.ext.asyncio import create_async_engine, AsyncEngine
from sqlalchemy import MetaData, Table, Column, String, Boolean
from sqlalchemy.dialects.postgresql import insert

# Cấu hình Database
# Lấy từ biến môi trường trong production, ví dụ: postgresql+asyncpg://user:pass@localhost/db
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql+asyncpg://postgres:postgres@localhost:5432/trustagent_db")

# Schema Definition
metadata = MetaData()
danh_muc_doanh_nghiep = Table(
    'danh_muc_doanh_nghiep', metadata,
    Column('mst', String, primary_key=True),
    Column('ten_doanh_nghiep', String),
    Column('nguoi_dai_dien', String),
    Column('dang_hoat_dong', Boolean)
)

class DatabaseManager:
    """Quản lý kết nối và các thao tác với PostgreSQL bằng SQLAlchemy Async."""
    
    def __init__(self, db_url: str = DATABASE_URL):
        self.engine: AsyncEngine = create_async_engine(db_url, echo=False)

    async def init_db(self):
        """Khởi tạo bảng nếu chưa có."""
        async with self.engine.begin() as conn:
            await conn.run_sync(metadata.create_all)
            
    async def upsert_companies(self, data: List[Dict[str, str]]):
        """UPSERT (Insert on conflict do update) dữ liệu doanh nghiệp."""
        if not data:
            return
            
        async with self.engine.begin() as conn:
            stmt = insert(danh_muc_doanh_nghiep).values(data)
            upsert_stmt = stmt.on_conflict_do_update(
                index_elements=['mst'],
                set_={
                    'ten_doanh_nghiep': stmt.excluded.ten_doanh_nghiep,
                    'nguoi_dai_dien': stmt.excluded.nguoi_dai_dien,
                    'dang_hoat_dong': stmt.excluded.dang_hoat_dong,
                }
            )
            await conn.execute(upsert_stmt)
            logger.success(f"Đã lưu/cập nhật {len(data)} doanh nghiệp vào DB.")

async def extract_mst_info(page: Page, mst: str) -> Dict[str, str]:
    """
    Hành vi người dùng:
    - Mở trang chủ masothue.com
    - Điền MST vào ô tìm kiếm
    - Chờ và click tìm kiếm
    - Trích xuất dữ liệu
    """
    logger.info(f"Đang xử lý MST: {mst}")
    try:
        # Điều hướng trang chủ
        await page.goto("https://masothue.com/", timeout=60000)
        
        # Đợi ô tìm kiếm xuất hiện (giả định id là search-box hoặc name là q)
        search_selector = "input[name='q']"
        await page.wait_for_selector(search_selector, timeout=15000)
        
        # Điền MST như người thật (gõ từng chữ)
        await asyncio.sleep(random.uniform(1.0, 2.5))
        await page.type(search_selector, mst, delay=random.randint(100, 300))
        
        # Nhấn Enter hoặc nút tìm kiếm
        await asyncio.sleep(random.uniform(0.5, 1.5))
        await page.keyboard.press("Enter")
        
        # Chờ kết quả tải xong (đợi bảng thông tin xuất hiện)
        # Giả định trang kết quả có thẻ chứa class table-taxinfo
        table_selector = "table.table-taxinfo"
        await page.wait_for_selector(table_selector, timeout=20000)
        
        # Bóc tách thông tin
        ten_dn = await page.locator("th[itemprop='name']").inner_text(timeout=5000)
        
        # Người đại diện (thường nằm trong thẻ có itemprop director)
        nguoi_dd = await page.locator("td a[itemprop='director']").inner_text(timeout=5000)
        
        # Trạng thái hoạt động
        tinh_trang_text = await page.locator("td a[href*='tinh-trang']").inner_text(timeout=5000)
        dang_hoat_dong = "Đang hoạt động" in tinh_trang_text
        
        return {
            "mst": mst,
            "ten_doanh_nghiep": ten_dn.strip(),
            "nguoi_dai_dien": nguoi_dd.strip(),
            "dang_hoat_dong": dang_hoat_dong
        }
    except Exception as e:
        logger.error(f"Lỗi khi tra cứu MST {mst}: {e}. Không fallback mock data.")
        raise

async def main():
    seed_file = os.path.join(os.path.dirname(__file__), "seed_mst.txt")
    if not os.path.exists(seed_file):
        logger.error(f"Không tìm thấy file seed MST tại: {seed_file}")
        # Tạo file mẫu để user biết cần điền gì nếu chưa có
        with open(seed_file, "w") as f:
            f.write("0101248141\n0309532909\n")
        logger.info(f"Đã tạo file {seed_file} mẫu. Vui lòng thêm các MST thật vào file này.")
        return

    with open(seed_file, "r") as f:
        mst_list = [line.strip() for line in f if line.strip()]

    if not mst_list:
        logger.warning("File seed_mst.txt trống.")
        return

    db_manager = DatabaseManager()
    await db_manager.init_db()
    
    scraped_data = []

    async with async_playwright() as p:
        # Chạy headful hoặc headless tùy cấu hình, dùng Chromium
        browser = await p.chromium.launch(headless=True)
        
        # Stealth Plugin yêu cầu context
        context: BrowserContext = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            viewport={"width": 1920, "height": 1080},
        )
        page: Page = await context.new_page()
        
        # Kích hoạt tàng hình (Stealth)
        await stealth_async(page)
        
        for mst in mst_list:
            try:
                info = await extract_mst_info(page, mst)
                scraped_data.append(info)
                
                # Lưu trữ từng đợt hoặc sau mỗi MST
                await db_manager.upsert_companies([info])
                
                # Nghỉ ngơi giữa các vòng lặp như người thật
                delay = random.uniform(3, 8)
                logger.debug(f"Nghỉ {delay:.1f}s trước MST tiếp theo...")
                await asyncio.sleep(delay)
                
            except Exception as e:
                logger.error(f"Dừng tiến trình tại MST {mst} do gặp lỗi nghiêm trọng: {e}")
                # Khi gặp lỗi chặn bot, raise ngoại lệ chứ không tiếp tục lặp để bị block IP hoàn toàn
                break

        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
