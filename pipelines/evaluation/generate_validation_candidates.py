import json
import numpy as np
from pathlib import Path
import chromadb
from sentence_transformers import SentenceTransformer
from rank_bm25 import BM25Okapi

def main():
    base_dir = Path(r"data/competition")
    results_dir = base_dir / "experiments" / "legalir" / "autonomous" / "results"
    
    val_file = base_dir / "configs" / "validation_manifest.json"
    with open(val_file, "r", encoding="utf-8") as f:
        val_qids = set(json.load(f))
        
    train_file = base_dir.parent.parent / "Data Science Challenge 2026 (Task 1)" / "train.json"
    with open(train_file, "r", encoding="utf-8") as f:
        train_data = json.load(f)
        
    val_queries = {}
    for qid, item in train_data.items():
        if qid in val_qids:
            val_queries[qid] = item["question"]
            
    print(f"Loaded {len(val_queries)} validation queries.")
    
    # Dense retrieval
    print("Loading embedding model...")
    embed_model = SentenceTransformer("bqbbao6/vietnamese-legal-embedding")
    
    print("Loading ChromaDB...")
    db_dir = r"data/task1\chroma_db_bqbbao6"
    client = chromadb.PersistentClient(path=db_dir)
    collection = client.get_collection(name="legal_ir")
    
    raw_cands = {}
    
    # Query Chroma
    qids_list = list(val_queries.keys())
    q_texts = [val_queries[qid] for qid in qids_list]
    
    batch_size = 32
    print("Running dense retrieval...")
    for i in range(0, len(qids_list), batch_size):
        batch_qids = qids_list[i:i+batch_size]
        batch_texts = q_texts[i:i+batch_size]
        
        embs = embed_model.encode(batch_texts).tolist()
        results = collection.query(query_embeddings=embs, n_results=500)
        
        for j, qid in enumerate(batch_qids):
            dense_docs = results['ids'][j]
            raw_cands[qid] = {"dense_500": dense_docs}
            
    # BM25 retrieval
    print("Loading BM25 index...")
    # Read corpus
    corpus_file = base_dir.parent.parent / "Data Science Challenge 2026 (Task 1)" / "corpus.json"
    with open(corpus_file, "r", encoding="utf-8") as f:
        corpus_data = json.load(f)
        
    corpus_ids = []
    corpus_texts = []
    for doc in corpus_data:
        corpus_ids.append(doc["article_id"])
        text = doc["title"] + " " + doc["text"]
        corpus_texts.append(text.lower().split())
        
    print("Building BM25Okapi...")
    bm25 = BM25Okapi(corpus_texts)
    
    print("Running BM25 retrieval...")
    for i, qid in enumerate(qids_list):
        if i % 100 == 0:
            print(f"BM25 query {i}/{len(qids_list)}")
        q_text = val_queries[qid].lower().split()
        scores = bm25.get_scores(q_text)
        top500_idx = np.argsort(scores)[::-1][:500]
        bm25_docs = [corpus_ids[idx] for idx in top500_idx]
        raw_cands[qid]["bm25_500"] = bm25_docs
        
    print("Applying RRF...")
    k_rrf = 60
    for qid, cands in raw_cands.items():
        dense_docs = cands["dense_500"]
        bm25_docs = cands["bm25_500"]
        
        scores_dict = {}
        for rank, doc in enumerate(dense_docs):
            scores_dict[doc] = scores_dict.get(doc, 0.0) + 1.0 / (k_rrf + rank + 1)
        for rank, doc in enumerate(bm25_docs):
            scores_dict[doc] = scores_dict.get(doc, 0.0) + 1.0 / (k_rrf + rank + 1)
            
        rrf_docs = sorted(scores_dict.keys(), key=lambda x: scores_dict[x], reverse=True)
        cands["rrf_500"] = rrf_docs[:500]
        
    out_file = base_dir / "experiments" / "legalir" / "autonomous" / "raw_candidates_validation.json"
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(raw_cands, f, indent=4)
        
    print(f"Saved candidates to {out_file}")

if __name__ == "__main__":
    main()
