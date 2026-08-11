import os
import sys

# Thêm đường dẫn backend vào sys.path để import
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts.legal_ir_pipeline import LegalIRPipeline

if __name__ == "__main__":
    print("[Info] Khởi tạo pipeline dự đoán trên tập 1000 câu hỏi (public-official.json)...")
    
    # Sử dụng cấu hình mặc định như trong legal_ir_pipeline.py
    data_dir = "D:/TrustAgent/Data Science Challenge 2026/selected-contexts"
    db_dir = "D:/TrustAgent/Data Science Challenge 2026 (Task 1)/chroma_db_public"
    
    # File câu hỏi nộp bài
    test_file = "D:/TrustAgent/Data Science Challenge 2026 (Task 1)/public-official.json"
    
    # Đầu ra
    output_json = "D:/TrustAgent/Data Science Challenge 2026 (Task 1)/submission.json"
    output_zip = "D:/TrustAgent/Data Science Challenge 2026 (Task 1)/submission.zip"
    
    pipeline = LegalIRPipeline(
        data_dir=data_dir,
        db_dir=db_dir,
        warmup_file=test_file,
        chunk_size=2000,
        chunk_overlap=400,
        model_name="BAAI/bge-m3",
        reranker_max_length=768
    )
    
    # Chạy index (chỉ load cache nếu đã có)
    pipeline.offline_indexing()
    
    print(f"\n[Info] Bắt đầu chạy dự đoán 1000 câu hỏi và lưu vào {output_json}")
    # Chạy dự đoán ở chế độ 'submit' (không tính precision/recall)
    pipeline.evaluate_and_submit(
        mode="submit",
        output_json=output_json,
        output_zip=output_zip
    )
    
    print("\n[Thành công] Đã tạo xong file dự đoán!")
