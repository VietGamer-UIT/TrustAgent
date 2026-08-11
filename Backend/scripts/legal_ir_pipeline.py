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

import numpy as np
from rank_bm25 import BM25Okapi
from pyvi import ViTokenizer

import chromadb
from sentence_transformers import SentenceTransformer, CrossEncoder
from langchain_text_splitters import RecursiveCharacterTextSplitter
from rich.console import Console
from rich.table import Table
import re
import torch

console = Console()

class LegalIRPipeline:
    def __init__(
        self, 
        data_dir: str, 
        db_dir: str, 
        warmup_file: str,
        chunk_size: int = 2000,
        chunk_overlap: int = 400,
        model_name: str = "BAAI/bge-m3",
        use_llm: bool = False,
        reranker_max_length: int = 256
    ):
        self.data_dir = Path(data_dir)
        self.db_dir = Path(db_dir)
        self.warmup_file = Path(warmup_file)
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.reranker_max_length = reranker_max_length
        
        console.print(f"[bold blue][Info][/bold blue] Khởi tạo ChromaDB tại {self.db_dir}...")
        self.client = chromadb.PersistentClient(path=str(self.db_dir))
        self.collection = self.client.get_or_create_collection(
            name="legal_ir",
            metadata={"hnsw:space": "cosine"}
        )
        
        console.print(f"[bold blue][Info][/bold blue] Đang tải model embedding {model_name}...")
        import torch
        self.model = SentenceTransformer(model_name, model_kwargs={"torch_dtype": torch.float16})
        
        self.text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=self.chunk_size,
            chunk_overlap=self.chunk_overlap
        )
        
        self.bm25 = None
        self.bm25_doc_ids = []

    def embed_texts(self, texts: List[str]) -> List[List[float]]:
        # Chuyển văn bản thành vector. Tối đa hoá sức mạnh RTX 4060 bằng batch_size lớn (64)
        return self.model.encode(texts, batch_size=32, show_progress_bar=False).tolist()

    def offline_indexing(self):
        console.print("[bold yellow][Step 1][/bold yellow] Bắt đầu Offline Indexing...")
        
        json_files = glob.glob(os.path.join(self.data_dir, "*.json"))
        if not json_files:
            console.print("[red]Không tìm thấy file JSON nào trong thư mục data_dir![/red]")
            return
            
        console.print(f"Tìm thấy {len(json_files)} file văn bản. Đang tải danh sách file đã index...")
        
        # O(1) Skip Logic (Bypass ChromaDB limit)
        indexed_doc_ids = set()
        try:
            db_path = os.path.join(self.db_dir, 'chroma.sqlite3')
            if os.path.exists(db_path):
                conn = sqlite3.connect(db_path)
                cursor = conn.execute("SELECT string_value FROM embedding_metadata WHERE key = 'document_id'")
                for row in cursor:
                    if row[0]:
                        indexed_doc_ids.add(str(row[0]))
                conn.close()
            console.print(f"[green]Đã tìm thấy {len(indexed_doc_ids)} tài liệu cũ (đọc trực tiếp từ SQLite), sẽ tiến hành bỏ qua (fast-skip)![/green]")
        except Exception as e:
            console.print(f"[yellow]Không thể tải metadata bằng SQLite, sẽ chạy check tuần tự: {e}[/yellow]")
            
        console.print("Tiến hành phân mảnh (chunking) và indexing...")
        
        batch_ids = []
        batch_documents = []
        batch_metadatas = []
        
        chunk_counter = 0

        for file_path in json_files:
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    doc = json.load(f)
                    
                doc_id = str(doc.get("id"))
                passage = doc.get("passage", "")
                
                # Skip documents with no content - do NOT fabricate placeholder text
                if not passage:
                    continue
                    
                # Kiểm tra xem file này đã được index chưa để skip siêu tốc (O(1))
                if doc_id in indexed_doc_ids:
                    continue
                    
                name = doc.get("name", "Văn bản")
                
                chunks = []
                # Tách theo cấu trúc Điều/Chương
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
                    chunk_id = f"{doc_id}_chunk_{i}"
                    batch_ids.append(chunk_id)
                    batch_documents.append(chunk)
                    batch_metadatas.append({"document_id": doc_id})  # Ép kiểu string
                    
                    # Xử lý batch insertion để tối ưu tốc độ, đẩy vào ngay khi đủ mảng để không bị tràn RAM
                    if len(batch_ids) >= 500:
                        batch_embeddings = self.embed_texts(batch_documents)
                        self.collection.upsert(
                            ids=batch_ids,
                            documents=batch_documents,
                            metadatas=batch_metadatas,
                            embeddings=batch_embeddings
                        )
                        chunk_counter += len(batch_ids)
                        batch_ids.clear()
                        batch_documents.clear()
                        batch_metadatas.clear()
                        
                        if torch.cuda.is_available():
                            torch.cuda.empty_cache()
                        gc.collect()
                    
            except Exception as e:
                console.print(f"[red]Lỗi đọc file {file_path}: {e}[/red]")
                # Dọn mảng để tránh rác lây sang file sau
                batch_ids.clear()
                batch_documents.clear()
                batch_metadatas.clear()
                if torch.cuda.is_available():
                    torch.cuda.empty_cache()
                
        # Insert batch cuối cùng
        if batch_ids:
            batch_embeddings = self.embed_texts(batch_documents)
            self.collection.upsert(
                ids=batch_ids,
                documents=batch_documents,
                metadatas=batch_metadatas,
                embeddings=batch_embeddings
            )
            chunk_counter += len(batch_ids)
            gc.collect()
            
        console.print(f"[bold green]Indexing hoàn tất![/bold green] Đã index tổng cộng {chunk_counter} chunks.")

    def build_bm25_index(self):
        console.print("[bold cyan][BM25][/bold cyan] Đang xây dựng/tải Lexical Index (BM25) trên RAM...")
        json_files = glob.glob(os.path.join(self.data_dir, "*.json"))
        cache_path = os.path.join(self.db_dir, "bm25_cache.pkl")
        
        import pickle
        if os.path.exists(cache_path):
            try:
                with open(cache_path, "rb") as f:
                    cache_data = pickle.load(f)
                # Cho phép sai số nhỏ (vài file json bị lỗi thiếu text/doc_id)
                if len(cache_data["bm25_doc_ids"]) >= len(json_files) - 50:
                    self.bm25 = cache_data["bm25"]
                    self.bm25_doc_ids = cache_data["bm25_doc_ids"]
                    self.doc_passages = cache_data["doc_passages"]
                    self.doc_names = cache_data["doc_names"]
                    console.print(f"[bold green][BM25][/bold green] Đã tải BM25 Index từ cache cho {len(self.bm25_doc_ids)} tài liệu!")
                    return
            except Exception as e:
                console.print(f"[yellow]Lỗi tải BM25 cache: {e}. Sẽ build lại từ đầu...[/yellow]")

        corpus = []
        self.bm25_doc_ids = []
        
        self.doc_passages = {}
        self.doc_names = {}
        
        from rich.progress import track
        for file_path in track(json_files, description="Tokenizing BM25..."):
            with open(file_path, "r", encoding="utf-8") as f:
                doc = json.load(f)
                doc_id = str(doc.get("id"))
                passage = doc.get("passage", "")
                name = doc.get("name", "")
                
                # Skip documents with no content - do NOT fabricate placeholder text
                if not passage:
                    continue
                    
                tokenized = []
                import sys
                for line in passage.split('\n'):
                    if line.strip():
                        tokenized.extend([sys.intern(w) for w in ViTokenizer.tokenize(line).lower().split()])
                
                corpus.append(tokenized)
                self.bm25_doc_ids.append(doc_id)
                self.doc_passages[doc_id] = passage
                self.doc_names[doc_id] = name
        
        self.bm25 = BM25Okapi(corpus)
        
        try:
            with open(cache_path, "wb") as f:
                pickle.dump({
                    "bm25": self.bm25,
                    "bm25_doc_ids": self.bm25_doc_ids,
                    "doc_passages": self.doc_passages,
                    "doc_names": self.doc_names
                }, f)
            console.print(f"[bold green][BM25][/bold green] Đã lưu BM25 Index ra cache!")
        except Exception as e:
            console.print(f"[yellow]Lỗi lưu BM25 cache: {e}[/yellow]")
            
        console.print(f"[bold green][BM25][/bold green] Đã xây dựng xong BM25 Index cho {len(corpus)} tài liệu!")

    def init_reranker(self):
        from sentence_transformers import CrossEncoder
        import torch
        from rich.console import Console
        console = Console()
        model_name = "BAAI/bge-reranker-v2-m3"
        console.print(f"[bold blue][Info][/bold blue] Đang tải mô hình Reranker {model_name} với max_length={self.reranker_max_length}...")
        self.reranker = CrossEncoder(model_name, max_length=self.reranker_max_length, model_kwargs={"torch_dtype": torch.float16, "low_cpu_mem_usage": True})
        self.reranker.model.eval()
        console.print(f"[bold green][Reranker][/bold green] Đã tải xong Reranker!")

    def online_query(self, query: str, top_k: int = 150, return_candidates: bool = False):
        import re
        import sys
        
        # Tách/chuẩn hóa số hiệu văn bản trong Query
        boosted_doc_ids = set()
        pattern = r'\b(\d+[-/]\d+[-/a-zA-Z0-9]+)\b'
        matches = re.findall(pattern, query, re.IGNORECASE)
        for match in matches:
            for doc_id, name in getattr(self, 'doc_names', {}).items():
                if match.lower() in name.lower():
                    boosted_doc_ids.add(doc_id)

        # 1. Semantic Search
        query_embedding = self.embed_texts([query])[0]
        semantic_results = self.collection.query(
            query_embeddings=[query_embedding],
            n_results=1000,
            include=['metadatas', 'distances', 'documents']
        )
        
        semantic_scores = {}
        best_chunk_text_by_doc = {}
        if semantic_results['metadatas'] and semantic_results['metadatas'][0]:
            metadatas = semantic_results['metadatas'][0]
            distances = semantic_results['distances'][0]
            documents = semantic_results['documents'][0]
            for meta, dist, doc_text in zip(metadatas, distances, documents):
                doc_id = str(meta["document_id"])
                score = 1.0 / (1.0 + dist) 
                if doc_id not in semantic_scores or score > semantic_scores[doc_id]:
                    semantic_scores[doc_id] = score
                    best_chunk_text_by_doc[doc_id] = doc_text
                    
        sorted_semantic = sorted(semantic_scores.items(), key=lambda x: x[1], reverse=True)
        sorted_semantic = sorted_semantic[:top_k]
        semantic_ranks = {doc_id: rank+1 for rank, (doc_id, _) in enumerate(sorted_semantic)}
        
        # 2. Lexical Search (Keyword - BM25)
        lexical_ranks = {}
        if self.bm25 is not None:
            tokenized_query = [sys.intern(w) for w in ViTokenizer.tokenize(query).lower().split()]
            bm25_scores = self.bm25.get_scores(tokenized_query)
            top_n_indices = np.argsort(bm25_scores)[::-1][:top_k]
            
            rank = 1
            for idx in top_n_indices:
                if bm25_scores[idx] > 0:
                    doc_id = self.bm25_doc_ids[idx]
                    lexical_ranks[doc_id] = rank
                    rank += 1
                    
        # 3. Reciprocal Rank Fusion (RRF)
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
        top_candidates = [doc_id for doc_id, _ in sorted_rrf[:top_k]]
        
        if return_candidates and not hasattr(self, 'reranker'):
            return [], top_candidates

        # 4. Reranker
        if hasattr(self, 'reranker') and hasattr(self, 'doc_passages') and top_candidates:
            cross_inp = [[query, best_chunk_text_by_doc.get(doc_id, self.doc_passages.get(doc_id, "")[:2000])] for doc_id in top_candidates]
            
            if hasattr(self.reranker, 'predict'):
                cross_scores = self.reranker.predict(cross_inp)
            else:
                inputs = self.reranker_tokenizer(cross_inp, padding=True, truncation=True, max_length=self.reranker_max_length, return_tensors="pt").to("cuda")
                import torch
                with torch.no_grad():
                    outputs = self.reranker(**inputs)
                    cross_scores = outputs.logits.squeeze(-1).float().cpu().numpy()
            
            scored_candidates = list(zip(top_candidates, cross_scores))
            scored_candidates.sort(key=lambda x: x[1], reverse=True)
            
            top_5 = [doc_id for doc_id, _ in scored_candidates[:5]]
            
            if return_candidates:
                return top_5, top_candidates
            return top_5

        if return_candidates:
            return top_candidates[:5], top_candidates
        return top_candidates[:5]

    def evaluate_and_submit(self, mode: str = "eval", output_json: str = "submission.json", output_zip: str = "submission.zip"):
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
            # Xử lý trường hợp test data không có 'answer' (null)
            raw_ans = q_data.get("answer")
            target_answers = [str(ans) for ans in raw_ans] if raw_ans else []
            
            # Query pipeline Hybrid có bọc try/except chống crash
            try:
                predicted_doc_ids = self.online_query(question, top_k=100, return_candidates=False)
            except Exception as e:
                console.print(f"[bold red]Lỗi truy vấn ở câu {q_id}: {e}[/bold red]")
                predicted_doc_ids = []
            
            # ĐẢM BẢO CHỈ TRẢ VỀ TỐI ĐA 5 ĐỂ KHÔNG BỊ CHẤM 0 ĐIỂM
            if len(predicted_doc_ids) > 5:
                predicted_doc_ids = predicted_doc_ids[:5]
                
            # Save for submission
            submission_dict[q_id] = {
                "answer": predicted_doc_ids
            }
            
            # Tính điểm Precision và Recall cho câu này nếu ở mode eval
            if mode == "eval":
                predicted_set = set(predicted_doc_ids)
                target_set = set(target_answers)
                
                q_precision = 0.0
                q_recall = 0.0
                
                if predicted_set:
                    intersection = predicted_set.intersection(target_set)
                    q_precision = len(intersection) / len(predicted_set)
                
                if target_set:
                    intersection = predicted_set.intersection(target_set)
                    q_recall = len(intersection) / len(target_set)
                    
                precision_sum += q_precision
                recall_sum += q_recall
                
                detail_table.add_row(
                    str(q_id),
                    str(predicted_doc_ids),
                    str(target_answers),
                    f"{q_recall:.4f}",
                    f"{q_precision:.4f}"
                )
                
            processed_count += 1
            if processed_count % 50 == 0:
                with open("submission_partial.json", "w", encoding="utf-8") as f:
                    json.dump(submission_dict, f, ensure_ascii=False, indent=4)
                console.print(f"[Info] Đã lưu checkpoint {processed_count}/{total_questions} câu...")
                
        if mode == "eval":
            console.print(detail_table)
                    
        if mode == "eval":
            # Metric Toán học
            final_precision = precision_sum / total_questions if total_questions > 0 else 0
            final_recall = recall_sum / total_questions if total_questions > 0 else 0
            
            summary_table = Table(title="🏆 LegalIR Evaluation Results (Luật mới) 🏆")
            summary_table.add_column("Metric", style="cyan")
            summary_table.add_column("Score", style="magenta")
            summary_table.add_row("Recall (Primary)", f"{final_recall:.4f}")
            summary_table.add_row("Precision (Secondary)", f"{final_precision:.4f}")
            console.print(summary_table)
            
            output_json = "eval_debug.json"
        
        # Ghi file JSON
        try:
            with open(output_json, "w", encoding="utf-8") as f:
                json.dump(submission_dict, f, ensure_ascii=False, indent=4)
            console.print(f"Đã xuất kết quả ra file: [bold]{output_json}[/bold]")
            
            if mode == "submit":
                # Nén ZIP cực chuẩn (arcname giúp loại bỏ cây thư mục)
                with zipfile.ZipFile(output_zip, 'w', zipfile.ZIP_DEFLATED) as zipf:
                    zipf.write(output_json, arcname="submission.json")
                console.print(f"Đã đóng gói thành công file: [bold green]{output_zip}[/bold green] (Sẵn sàng nộp lên CodaLab!)")
            
        except Exception as e:
            console.print(f"[bold red]Lỗi khi ghi file submission: {e}[/bold red]")
            traceback.print_exc()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="UIT-DSC 2026 - Task 1: LegalIR Pipeline")
    parser.add_argument("--data_dir", type=str, default="D:/TrustAgent/Data Science Challenge 2026/selected-contexts", help="Directory containing context_*.json files")
    parser.add_argument("--db_dir", type=str, default="D:/TrustAgent/Data Science Challenge 2026/chroma_db_legal_ir", help="Directory to store ChromaDB vector database")
    parser.add_argument("--warmup_file", type=str, default="D:/TrustAgent/Data Science Challenge 2026/warmup.json", help="Path to warmup JSON file for evaluation")
    parser.add_argument("--chunk_size", type=int, default=2000, help="Chunk size for RecursiveCharacterTextSplitter")
    parser.add_argument("--chunk_overlap", type=int, default=400, help="Chunk overlap for RecursiveCharacterTextSplitter")
    parser.add_argument("--model_name", type=str, default="BAAI/bge-m3", help="Sentence-Transformers model name for embedding")
    parser.add_argument("--mode", choices=["eval", "submit"], default="eval", help="Run mode: 'eval' for internal testing, 'submit' for final output")
    
    args = parser.parse_args()
    
    pipeline = LegalIRPipeline(
        data_dir=args.data_dir,
        db_dir=args.db_dir,
        warmup_file=args.warmup_file,
        chunk_size=args.chunk_size,
        chunk_overlap=args.chunk_overlap,
        model_name=args.model_name
    )
    
    # Chạy index
    pipeline.offline_indexing()
    
    # Chạy query & đánh giá & xuất submission
    pipeline.evaluate_and_submit(
        mode=args.mode,
        output_json="D:/TrustAgent/Data Science Challenge 2026 (Task 1)/submission.json",
        output_zip="D:/TrustAgent/Data Science Challenge 2026 (Task 1)/submission.zip"
    )
