import os
import json
import time
from legal_ir_pipeline import LegalIRPipeline

data_dir = "D:/TrustAgent/Data Science Challenge 2026 (Task 1)/test_selected-contexts"
db_dir = "D:/TrustAgent/Data Science Challenge 2026 (Task 1)/test_db"
warmup_file = "D:/TrustAgent/Data Science Challenge 2026 (Task 1)/train.json"

pipeline = LegalIRPipeline(
    data_dir=data_dir,
    db_dir=db_dir,
    warmup_file=warmup_file
)

print("\n--- STEP 1: TEST OFFLINE INDEXING (50 FILES) ---")
pipeline.offline_indexing()
print("Offline indexing completed.")

print("\n--- STEP 2: TEST ONLINE QUERY (10 QUESTIONS) ---")
pipeline.build_bm25_index()

import torch
from sentence_transformers import CrossEncoder

if hasattr(pipeline, 'model'):
    pipeline.model.to('cpu')
if torch.cuda.is_available():
    torch.cuda.empty_cache()

pipeline.reranker = CrossEncoder("BAAI/bge-reranker-v2-m3", max_length=768)

with open(warmup_file, "r", encoding="utf-8") as f:
    warmup_data = json.load(f)

print(f"Loaded {len(warmup_data)} questions from train.json.")
questions = list(warmup_data.items())[:10]

for q_id, q_data in questions:
    question = q_data.get("question", "")
    print(f"\nQ[{q_id}]: {question[:50]}...")
    start = time.time()
    try:
        predicted = pipeline.online_query(question, top_k=100)
        end = time.time()
        print(f"-> Time: {end-start:.2f}s | Predicted: {predicted}")
    except Exception as e:
        print(f"-> ERROR: {e}")
