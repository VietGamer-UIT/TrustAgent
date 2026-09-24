import os
import glob
import json
import zipfile
import argparse
from pathlib import Path
from typing import List, Dict, Any, Set
import traceback
import gc
import sqlite3
import pickle
import sys
import re
import unicodedata

import numpy as np
from rank_bm25 import BM25Okapi
from pyvi import ViTokenizer

import chromadb
from sentence_transformers import SentenceTransformer, CrossEncoder
from langchain_text_splitters import RecursiveCharacterTextSplitter
from rich.console import Console
from rich.table import Table
import torch
from rich.progress import track

console = Console()

class LegalIRPipeline:
    def __init__(
        self, 
        data_dir: str, 
        db_dir: str, 
        warmup_file: str,
        chunk_size: int = 2000,
        chunk_overlap: int = 400,
        model_name: str = "bqbbao6/vietnamese-legal-embedding",
        use_llm: bool = False,
        reranker_max_length: int = 512,  # Increased from 256
        disable_boost: bool = False,
        reranker_model_name: str = "BAAI/bge-reranker-v2-m3"
    ):
        self.data_dir = Path(data_dir)
        # Use the bqbbao6 DB by default since it has the valid HNSW index
        self.db_dir = Path("data/sample/chroma_db_bqbbao6")
        self.warmup_file = Path(warmup_file)
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.model_name = model_name
        self.use_llm = use_llm
        self.reranker_max_length = reranker_max_length
        self.disable_boost = disable_boost
        self.reranker_model_name = reranker_model_name
        
        self.model = None
        self.reranker = None
        self.bm25 = None
        
        console.print(f"[bold blue][Info][/bold blue] Khởi tạo ChromaDB tại {self.db_dir}...")
        self.client = chromadb.PersistentClient(path=str(self.db_dir))
        collection_name = "legal_ir" # Use the original fully indexed collection!
        self.collection = self.client.get_or_create_collection(
            name=collection_name,
            metadata={"hnsw:space": "cosine"}
        )
        
        console.print(f"[bold blue][Info][/bold blue] Đang tải model embedding {model_name}...")
        self.model = SentenceTransformer(model_name, model_kwargs={"torch_dtype": "float16"})
        
        self.text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=self.chunk_size,
            chunk_overlap=self.chunk_overlap
        )

    def embed_texts(self, texts: List[str]) -> List[List[float]]:
        return self.model.encode(texts, batch_size=64, show_progress_bar=False).tolist()

    def offline_indexing(self):
        console.print("[bold yellow][Step 1][/bold yellow] Bắt đầu Offline Indexing...")
        json_files = glob.glob(os.path.join(self.data_dir, "*.json"))
        if not json_files:
            console.print("[red]Không tìm thấy file JSON nào![/red]")
            return
            
        indexed_doc_ids = set()
        try:
            db_path = os.path.join(self.db_dir, 'chroma.sqlite3')
            if os.path.exists(db_path):
                conn = sqlite3.connect(db_path)
                collection_id_str = str(self.collection.id)
                query = '''
                    SELECT em.string_value 
                    FROM embedding_metadata em 
                    JOIN embeddings e ON em.id = e.id 
                    JOIN segments s ON e.segment_id = s.id 
                    WHERE em.key = 'document_id' AND s.collection = ?
                '''
                cursor = conn.execute(query, (collection_id_str,))
                for row in cursor:
                    if row[0]:
                        indexed_doc_ids.add(str(row[0]))
                conn.close()
            console.print(f"[green]Đã tìm thấy {len(indexed_doc_ids)} tài liệu cũ (đọc trực tiếp từ SQLite), sẽ tiến hành bỏ qua (fast-skip)![/green]")
        except Exception as e:
            pass
            
        batch_ids, batch_documents, batch_metadatas = [], [], []
        chunk_counter = 0

        for file_path in json_files:
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    doc = json.load(f)
                    
                doc_id = str(doc.get("id"))
                passage = doc.get("passage", "")
                if not passage or doc_id in indexed_doc_ids:
                    continue
                    
                name = doc.get("name", "Văn bản")
                chunks = []
                sections = re.split(r'(?=Điều \d+[:\.]|Chương \d+[:\.])', passage)
                for section in sections:
                    section = section.strip()
                    if not section:
                        continue
                    if len(section) > self.chunk_size:
                        sub_chunks = self.text_splitter.split_text(section)
                        for sub in sub_chunks:
                            chunks.append(f"Văn bản: {name}\nNội dung: {sub}")
                    else:
                        chunks.append(f"Văn bản: {name}\nNội dung: {section}")
                        
                for i, chunk in enumerate(chunks):
                    batch_ids.append(f"{doc_id}_chunk_{i}")
                    batch_documents.append(chunk)
                    batch_metadatas.append({"document_id": doc_id})
                    
                    if len(batch_ids) >= 500:
                        self.collection.upsert(
                            ids=batch_ids,
                            documents=batch_documents,
                            metadatas=batch_metadatas,
                            embeddings=self.embed_texts(batch_documents)
                        )
                        chunk_counter += len(batch_ids)
                        batch_ids.clear()
                        batch_documents.clear()
                        batch_metadatas.clear()
                        if torch.cuda.is_available():
                            torch.cuda.empty_cache()
                        gc.collect()
            except Exception as e:
                batch_ids.clear(); batch_documents.clear(); batch_metadatas.clear()
                
        if batch_ids:
            self.collection.upsert(
                ids=batch_ids,
                documents=batch_documents,
                metadatas=batch_metadatas,
                embeddings=self.embed_texts(batch_documents)
            )
            chunk_counter += len(batch_ids)
            
        console.print(f"[bold green]Indexing hoàn tất![/bold green] Đã index tổng cộng {chunk_counter} chunks mới.")

    def build_bm25_index(self):
        console.print("[bold cyan][BM25][/bold cyan] Đang xây dựng Lexical Index (BM25) theo dạng Chunks...")
        json_files = glob.glob(os.path.join(self.data_dir, "*.json"))
        cache_path = os.path.join(self.db_dir, "bm25_cache_chunked.pkl")
        
        if os.path.exists(cache_path):
            try:
                with open(cache_path, "rb") as f:
                    cache_data = pickle.load(f)
                if len(cache_data["doc_names"]) >= len(json_files) - 50:
                    self.bm25 = cache_data["bm25"]
                    self.bm25_chunk_doc_ids = cache_data["bm25_chunk_doc_ids"]
                    self.bm25_chunk_texts = cache_data["bm25_chunk_texts"]
                    self.doc_names = cache_data["doc_names"]
                    self.doc_numbers = cache_data.get("doc_numbers", {})
                    console.print(f"[bold green][BM25][/bold green] Đã tải BM25 Index từ cache với {len(self.bm25_chunk_texts)} chunks!")
                    return
            except Exception as e:
                console.print(f"[yellow]Lỗi tải BM25 cache: {e}. Sẽ build lại từ đầu...[/yellow]")

        corpus = []
        self.bm25_chunk_doc_ids = []
        self.bm25_chunk_texts = []
        self.doc_names = {}
        self.doc_numbers = {}
        
        for file_path in track(json_files, description="Chunking & Tokenizing BM25..."):
            with open(file_path, "r", encoding="utf-8") as f:
                doc = json.load(f)
                doc_id = str(doc.get("id"))
                passage = doc.get("passage", "")
                name = doc.get("name", "")
                
                if not passage:
                    continue
                    
                # Extract Doc Number
                doc_num = ""
                head_text = passage[:500]
                num_match = re.search(r'Số:\s*(\d+[-/]\d+[-/A-Za-z0-9Đđ]+)', head_text, re.IGNORECASE)
                if not num_match:
                    num_match = re.search(r'\b(\d+[-/]\d+[-/A-Za-z0-9Đđ]+)\b', head_text, re.IGNORECASE)
                if num_match:
                    doc_num = unicodedata.normalize("NFC", num_match.group(1).strip().lower())
                
                self.doc_names[doc_id] = name
                self.doc_numbers[doc_id] = doc_num

                # Split chunks EXACTLY like ChromaDB
                chunks = []
                sections = re.split(r'(?=Điều \d+[:\.]|Chương \d+[:\.])', passage)
                for section in sections:
                    section = section.strip()
                    if not section: continue
                    if len(section) > self.chunk_size:
                        sub_chunks = self.text_splitter.split_text(section)
                        for sub in sub_chunks:
                            chunks.append(f"Văn bản: {name}\nNội dung: {sub}")
                    else:
                        chunks.append(f"Văn bản: {name}\nNội dung: {section}")

                # Tokenize chunks
                for chunk in chunks:
                    tokenized = []
                    for line in chunk.split('\n'):
                        if line.strip():
                            tokenized.extend([sys.intern(w) for w in ViTokenizer.tokenize(line).lower().split()])
                    corpus.append(tokenized)
                    self.bm25_chunk_doc_ids.append(doc_id)
                    self.bm25_chunk_texts.append(sys.intern(chunk))
        
        self.bm25 = BM25Okapi(corpus)
        
        try:
            with open(cache_path, "wb") as f:
                pickle.dump({
                    "bm25": self.bm25,
                    "bm25_chunk_doc_ids": self.bm25_chunk_doc_ids,
                    "bm25_chunk_texts": self.bm25_chunk_texts,
                    "doc_names": self.doc_names,
                    "doc_numbers": self.doc_numbers
                }, f)
        except Exception as e:
            pass
            
        console.print(f"[bold green][BM25][/bold green] Xây dựng xong BM25 Index cho {len(corpus)} chunks!")

    def init_reranker(self):
        console.print(f"[bold blue][Info][/bold blue] Đang tải mô hình Reranker {self.reranker_model_name} với max_length={self.reranker_max_length}...")
        self.reranker = CrossEncoder(self.reranker_model_name, max_length=self.reranker_max_length, model_kwargs={"torch_dtype": torch.float16, "low_cpu_mem_usage": True})
        self.reranker.model.eval()

    def online_query(self, query: str, top_k: int = 5, return_candidates: bool = False):
        boosted_doc_ids = set()
        if not self.disable_boost:
            matches = re.findall(r'\b(\d+[-/]\d+[-/A-Za-z0-9Đđ]+)\b', query, re.IGNORECASE)
            for match in matches:
                query_num = unicodedata.normalize("NFC", match.strip().lower())
                for doc_id, doc_num in getattr(self, 'doc_numbers', {}).items():
                    if doc_num and doc_num == query_num:
                        boosted_doc_ids.add(doc_id)

        # 1. Semantic Search (ChromaDB)
        query_embedding = self.embed_texts([query])[0]
        semantic_results = self.collection.query(
            query_embeddings=[query_embedding],
            n_results=1500,
            include=['metadatas', 'distances', 'documents']
        )
        
        semantic_scores = {}
        best_semantic_chunk = {}
        if semantic_results['metadatas'] and semantic_results['metadatas'][0]:
            for meta, dist, doc_text in zip(semantic_results['metadatas'][0], semantic_results['distances'][0], semantic_results['documents'][0]):
                doc_id = str(meta["document_id"])
                score = 1.0 / (1.0 + dist) 
                if doc_id not in semantic_scores or score > semantic_scores[doc_id]:
                    semantic_scores[doc_id] = score
                    best_semantic_chunk[doc_id] = doc_text
                    
        sorted_semantic = sorted(semantic_scores.items(), key=lambda x: x[1], reverse=True)[:200]
        semantic_ranks = {doc_id: rank+1 for rank, (doc_id, _) in enumerate(sorted_semantic)}
        
        # 2. Lexical Search (BM25 on Chunks)
        lexical_ranks = {}
        best_lexical_chunk = {}
        if self.bm25 is not None:
            tokenized_query = [sys.intern(w) for w in ViTokenizer.tokenize(query).lower().split()]
            bm25_scores = self.bm25.get_scores(tokenized_query)
            top_n_indices = np.argsort(bm25_scores)[::-1][:1500]
            
            lexical_scores = {}
            for idx in top_n_indices:
                score = bm25_scores[idx]
                if score > 0:
                    doc_id = self.bm25_chunk_doc_ids[idx]
                    if doc_id not in lexical_scores or score > lexical_scores[doc_id]:
                        lexical_scores[doc_id] = score
                        best_lexical_chunk[doc_id] = self.bm25_chunk_texts[idx]
                        
            sorted_lexical = sorted(lexical_scores.items(), key=lambda x: x[1], reverse=True)[:200]
            lexical_ranks = {doc_id: rank+1 for rank, (doc_id, _) in enumerate(sorted_lexical)}
                    
        # 3. RRF Fusion
        k_rrf = 60
        rrf_scores = {}
        all_docs = set(semantic_ranks.keys()).union(set(lexical_ranks.keys()))
        for doc_id in all_docs:
            score = 0.0
            if doc_id in semantic_ranks:
                score += 1.0 / (k_rrf + semantic_ranks[doc_id])
            if doc_id in lexical_ranks:
                score += 1.0 / (k_rrf + lexical_ranks[doc_id])
            if doc_id in boosted_doc_ids:
                score += 2.0 
            rrf_scores[doc_id] = score
            
        sorted_rrf = sorted(rrf_scores.items(), key=lambda x: x[1], reverse=True)
        top_candidates = [doc_id for doc_id, _ in sorted_rrf[:80]] # Rerank top 80
        
        if return_candidates and not hasattr(self, 'reranker'):
            return [], top_candidates

        # 4. Reranking (Evaluate BOTH Semantic Best Chunk and Lexical Best Chunk per document)
        if hasattr(self, 'reranker') and top_candidates:
            # Prepare pairs: [query, chunk]
            candidate_chunks = []
            chunk_to_doc = []
            for doc_id in top_candidates:
                cands = set()
                if doc_id in best_semantic_chunk:
                    cands.add(best_semantic_chunk[doc_id])
                if doc_id in best_lexical_chunk:
                    cands.add(best_lexical_chunk[doc_id])
                
                for chunk_text in cands:
                    candidate_chunks.append([query, chunk_text])
                    chunk_to_doc.append(doc_id)
            
            if candidate_chunks:
                if hasattr(self.reranker, 'predict'):
                    cross_scores = self.reranker.predict(candidate_chunks)
                else:
                    import torch
                    inputs = self.reranker_tokenizer(candidate_chunks, padding=True, truncation=True, max_length=self.reranker_max_length, return_tensors="pt").to("cuda")
                    with torch.no_grad():
                        cross_scores = self.reranker(**inputs).logits.squeeze(-1).float().cpu().numpy()
                
                # Max score per doc
                final_doc_scores = {}
                for doc_id, score in zip(chunk_to_doc, cross_scores):
                    if doc_id not in final_doc_scores or score > final_doc_scores[doc_id]:
                        final_doc_scores[doc_id] = score
                
                scored_docs = list(final_doc_scores.items())
                scored_docs.sort(key=lambda x: x[1], reverse=True)
                
                # PAD with un-reranked if not enough
                top_final = [d[0] for d in scored_docs]
                if len(top_final) < top_k:
                    for doc_id in top_candidates:
                        if doc_id not in top_final:
                            top_final.append(doc_id)
                
                return_list = top_final[:top_k]
                if return_candidates:
                    return return_list, top_candidates
                return return_list

        fallback = top_candidates[:top_k]
        if return_candidates:
            return fallback, top_candidates
        return fallback

    def evaluate_and_submit(self, mode: str = "eval", output_json: str = "output_results.json", output_zip: str = "output_results.zip"):
        console.print(f"[bold yellow][Step 2][/bold yellow] Bắt đầu quá trình ({mode.upper()})...")
        self.init_reranker()
        self.build_bm25_index()
        
        if not self.warmup_file.exists():
            console.print(f"[bold red]Lỗi:[/bold red] Không tìm thấy tập {self.warmup_file}.")
            return
            
        with open(self.warmup_file, "r", encoding="utf-8") as f:
            warmup_data = json.load(f)
            
        total_questions = len(warmup_data)
        precision_sum = 0.0
        recall_sum = 0.0
        submission_dict = {}
        
        if mode == "eval":
            detail_table = Table(title="Chi tiết Đánh giá Từng câu hỏi (LegalIR)", show_lines=True)
            detail_table.add_column("Question ID", justify="center", style="cyan")
            detail_table.add_column("Predicted IDs", style="white")
            detail_table.add_column("Relevant IDs", style="white")
            detail_table.add_column("Recall", justify="right", style="green")
            detail_table.add_column("Precision", justify="right", style="magenta")
            
        processed_count = 0
        
        for q_id, q_data in warmup_data.items():
            question = q_data.get("question", "")
            raw_ans = q_data.get("answer")
            target_answers = [str(ans) for ans in raw_ans] if raw_ans else []
            
            try:
                predicted_doc_ids = self.online_query(question, top_k=5, return_candidates=False)
            except Exception as e:
                console.print(f"[bold red]Lỗi truy vấn ở câu {q_id}: {e}[/bold red]")
                predicted_doc_ids = []
            
            # Đảm bảo trả về đủ 5 nếu có thể (nhưng hàm online_query đã pad, nên ở đây cứ [:5] là được)
            predicted_doc_ids = predicted_doc_ids[:5]
                
            submission_dict[q_id] = {"answer": predicted_doc_ids}
            
            if mode == "eval":
                predicted_set = set(predicted_doc_ids)
                target_set = set(target_answers)
                
                q_precision, q_recall = 0.0, 0.0
                if predicted_set:
                    q_precision = len(predicted_set.intersection(target_set)) / len(predicted_set)
                if target_set:
                    q_recall = len(predicted_set.intersection(target_set)) / len(target_set)
                    
                precision_sum += q_precision
                recall_sum += q_recall
                
                detail_table.add_row(
                    str(q_id), str(predicted_doc_ids), str(target_answers),
                    f"{q_recall:.4f}", f"{q_precision:.4f}"
                )
                
            processed_count += 1
            if processed_count % 50 == 0:
                with open("submission_partial.json", "w", encoding="utf-8") as f:
                    json.dump(submission_dict, f, ensure_ascii=False, indent=4)
                console.print(f"[Info] Đã đánh giá {processed_count}/{total_questions} câu...")
            
            # Explicit garbage collection to prevent OOM over 1000 queries
            gc.collect()
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
                
        if mode == "eval":
            console.print(detail_table)
            final_precision = precision_sum / total_questions if total_questions > 0 else 0
            final_recall = recall_sum / total_questions if total_questions > 0 else 0
            
            summary_table = Table(title="🏆 LegalIR Evaluation Results (Luật mới) 🏆")
            summary_table.add_column("Metric", style="cyan")
            summary_table.add_column("Score", style="magenta")
            summary_table.add_row("Recall (Primary)", f"{final_recall:.4f}")
            summary_table.add_row("Precision (Secondary)", f"{final_precision:.4f}")
            console.print(summary_table)
            output_json = "eval_debug.json"
        
        try:
            with open(output_json, "w", encoding="utf-8") as f:
                json.dump(submission_dict, f, ensure_ascii=False, indent=4)
            console.print(f"Đã xuất kết quả ra file: [bold]{output_json}[/bold]")
            
            if mode == "submit":
                with zipfile.ZipFile(output_zip, 'w', zipfile.ZIP_DEFLATED) as zipf:
                    zipf.write(output_json, arcname="output_results.json")
                console.print(f"Đã đóng gói thành công file: [bold green]{output_zip}[/bold green]")
        except Exception as e:
            traceback.print_exc()

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--data_dir", type=str, default="data/sample/corpus")
    parser.add_argument("--db_dir", type=str, default="data/sample/chroma_db_legal_ir")
    parser.add_argument("--warmup_file", type=str, default="data/sample/warmup.json")
    parser.add_argument("--chunk_size", type=int, default=2000)
    parser.add_argument("--chunk_overlap", type=int, default=400)
    parser.add_argument("--model_name", type=str, default="BAAI/bge-m3")
    parser.add_argument("--mode", choices=["eval", "submit"], default="eval")
    parser.add_argument("--disable_boost", action="store_true")
    args = parser.parse_args()
    
    pipeline = LegalIRPipeline(
        data_dir=args.data_dir,
        db_dir=args.db_dir,
        warmup_file=args.warmup_file,
        chunk_size=args.chunk_size,
        chunk_overlap=args.chunk_overlap,
        model_name=args.model_name,
        disable_boost=args.disable_boost
    )
    
    # pipeline.offline_indexing() # Tạm thời tắt để không re-index lại ChromaDB
    pipeline.evaluate_and_submit(
        mode=args.mode,
        output_json="data/sample/output_results.json",
        output_zip="data/sample/output_results.zip"
    )
