import sys
import os
import traceback
from pathlib import Path

# Thêm đường dẫn để import
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from legal_ir_pipeline import LegalIRPipeline

def test():
    try:
        pipeline = LegalIRPipeline(
            data_dir="D:/TrustAgent/Data Science Challenge 2026 (Task 1)/selected-contexts",
            db_dir="D:/TrustAgent/Data Science Challenge 2026 (Task 1)/chroma_db_public",
            warmup_file="D:/TrustAgent/Data Science Challenge 2026 (Task 1)/train.json"
        )
        
        # Load BM25 from cache (since it's already built)
        pipeline.build_bm25_index()
        
        import torch
        pipeline.model.to('cpu')
        torch.cuda.empty_cache()
        
        from sentence_transformers import CrossEncoder
        pipeline.reranker = CrossEncoder("BAAI/bge-reranker-v2-m3", max_length=768, model_kwargs={"torch_dtype": torch.float16})
        
        print("Bắt đầu online_query...")
        query = "Cho mình hỏi về quy định xử phạt vi phạm hành chính trong lĩnh vực giao thông đường bộ."
        res = pipeline.online_query(query)
        print("Kết quả:", res)
        
    except Exception as e:
        print("Lỗi:")
        traceback.print_exc()

if __name__ == "__main__":
    test()
