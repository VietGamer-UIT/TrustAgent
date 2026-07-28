import os
import sys
import argparse
from loguru import logger
from datasets import load_dataset
from langchain_community.vectorstores import Chroma
from langchain_huggingface import HuggingFaceEmbeddings

# Thiết lập đường dẫn tĩnh tương đối
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CHROMA_DB_DIR = os.path.join(BASE_DIR, "rag", "chroma_db")

def main():
    parser = argparse.ArgumentParser(description="Build ChromaDB from tmquan/phapdien-moj-gov-vn")
    parser.add_argument("--limit", type=int, default=0, help="Giới hạn số lượng điều luật để test (0 = Full)")
    args = parser.parse_args()

    logger.info("Khởi tạo Embedding Model (keepitreal/vietnamese-sbert)...")
    embeddings = HuggingFaceEmbeddings(model_name="keepitreal/vietnamese-sbert")

    logger.info("Tải dataset tmquan/phapdien-moj-gov-vn từ HuggingFace...")
    # Load bảng articles
    try:
        dataset = load_dataset("tmquan/phapdien-moj-gov-vn", "articles", split="train")
    except Exception as e:
        logger.error(f"Lỗi khi tải dataset: {e}")
        sys.exit(1)

    total_articles = len(dataset)
    logger.info(f"Đã tải thành công {total_articles} Điều luật từ Pháp điển.")

    if args.limit > 0:
        logger.info(f"⚠️ Chạy chế độ TEST: Chỉ index {args.limit} Điều luật đầu tiên.")
        dataset = dataset.select(range(min(args.limit, total_articles)))

    logger.info("Đang xử lý dữ liệu và tạo Vector Embeddings...")
    
    docs = []
    metadatas = []
    ids = []

    for i, row in enumerate(dataset):
        # Tạo metadata từ các field chuẩn của dataset
        chu_de = row.get("topic_title_vi", "Không rõ chủ đề")
        de_muc = row.get("subject_title_vi", "Không rõ đề mục")
        ten_dieu = row.get("article_title", f"Điều {i}")
        text = row.get("content_text", "")
        
        if not text or not text.strip():
            continue
            
        # Tạo đoạn văn bản đầy đủ ngữ cảnh để nhúng
        full_text = f"Chủ đề: {chu_de}\nĐề mục: {de_muc}\n{ten_dieu}\n\n{text}"
        
        docs.append(full_text)
        metadatas.append({
            "source": "Pháp điển Bộ Tư pháp",
            "chu_de": chu_de,
            "de_muc": de_muc,
            "ten_dieu": ten_dieu
        })
        ids.append(f"phapdien_{i}")

        if i > 0 and i % 1000 == 0:
            logger.info(f"Đã xử lý xong chunk {i} / {len(dataset)} ...")

    logger.info(f"Bắt đầu lưu {len(docs)} vectors vào ChromaDB tại: {CHROMA_DB_DIR}")
    
    # Chia nhỏ batch nếu quá lớn (Chroma có giới hạn batch size tuỳ cấu hình, thường là 5000-41666)
    batch_size = 5000
    vector_store = Chroma(
        persist_directory=CHROMA_DB_DIR,
        embedding_function=embeddings,
    )
    
    for i in range(0, len(docs), batch_size):
        end_idx = min(i + batch_size, len(docs))
        batch_docs = docs[i:end_idx]
        batch_metas = metadatas[i:end_idx]
        batch_ids = ids[i:end_idx]
        
        logger.info(f"Đang lưu batch {i} đến {end_idx} vào DB...")
        vector_store.add_texts(texts=batch_docs, metadatas=batch_metas, ids=batch_ids)

    logger.info("✅ HOÀN TẤT! ChromaDB đã sẵn sàng.")

if __name__ == "__main__":
    main()
