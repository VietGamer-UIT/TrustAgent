import os
import json
import argparse
from pathlib import Path
from legal_ir_pipeline import LegalIRPipeline
from rich.console import Console
import torch

console = Console()

def main():
    parser = argparse.ArgumentParser(description="UIT-DSC 2026 - Error Analysis")
    parser.add_argument("--sample", type=int, default=300, help="Number of questions to test (default: 300)")
    parser.add_argument("--data_dir", type=str, default="D:/TrustAgent/Data Science Challenge 2026 (Task 1)/selected-contexts")
    parser.add_argument("--db_dir", type=str, default="D:/TrustAgent/Data Science Challenge 2026 (Task 1)/chroma_db_public")
    parser.add_argument("--train_file", type=str, default="D:/TrustAgent/Data Science Challenge 2026 (Task 1)/train.json")
    parser.add_argument("--use_llm", action="store_true", help="Use LLM for Query Expansion")
    args = parser.parse_args()

    pipeline = LegalIRPipeline(
        data_dir=args.data_dir,
        db_dir=args.db_dir,
        warmup_file=args.train_file,
        use_llm=args.use_llm
    )
    
    # Init BM25
    pipeline.build_bm25_index()
    
    # Init Reranker in FP16
    # Init Reranker
    pipeline.init_reranker()
    
    with open(args.train_file, "r", encoding="utf-8") as f:
        train_data = json.load(f)
        
    q_ids = list(train_data.keys())[:args.sample]
    
    stats = {
        'single_doc': {'total': 0, 'recall_30_hits': 0, 'recall_5_hits': 0, 'group_A': 0, 'group_B': 0},
        'multi_doc': {'total': 0, 'recall_30_hits': 0, 'recall_5_hits': 0, 'group_A': 0, 'group_B': 0}
    }
    
    examples = {
        'group_A': [],
        'group_B': []
    }
    
    processed_count = 0
    checkpoint_file = "error_analysis_checkpoint.json"
    
    console.print(f"[bold cyan]Bắt đầu phân tích {len(q_ids)} câu hỏi...[/bold cyan]")
    
    for q_id in q_ids:
        q_data = train_data[q_id]
        question = q_data.get("question", "")
        target_answers = [str(ans) for ans in q_data.get("answer", [])]
        if not target_answers:
            continue
            
        doc_type = 'single_doc' if len(target_answers) == 1 else 'multi_doc'
        stats[doc_type]['total'] += 1
        
        try:
            top_5, top_candidates = pipeline.online_query(question, top_k=150, return_candidates=True)
        except Exception as e:
            console.print(f"[red]Lỗi truy vấn câu {q_id}: {e}[/red]")
            continue
            
        # Check targets in top_candidates (Recall@30 - kept for compatibility)
        hits_30 = [ans for ans in target_answers if ans in top_candidates]
        is_recall_30 = len(hits_30) == len(target_answers) # Cần TẤT CẢ phải nằm trong top 150 (top_candidates)
        
        # Check targets in top_5 (Recall@5)
        hits_5 = [ans for ans in target_answers if ans in top_5]
        is_recall_5 = len(hits_5) == len(target_answers)
        
        if is_recall_30:
            stats[doc_type]['recall_30_hits'] += 1
        if is_recall_5:
            stats[doc_type]['recall_5_hits'] += 1
            
        if not is_recall_30:
            stats[doc_type]['group_A'] += 1
            if len(examples['group_A']) < 10:
                examples['group_A'].append({
                    "q_id": q_id,
                    "question": question,
                    "targets": target_answers,
                    "top_5": top_5,
                    "doc_type": doc_type
                })
        elif not is_recall_5:
            # Thuộc Top 30 nhưng bị văng khỏi Top 5
            stats[doc_type]['group_B'] += 1
            if len(examples['group_B']) < 10:
                examples['group_B'].append({
                    "q_id": q_id,
                    "question": question,
                    "targets": target_answers,
                    "top_candidates": top_candidates,
                    "top_5": top_5,
                    "doc_type": doc_type
                })
                
        processed_count += 1
        if processed_count % 50 == 0:
            with open(checkpoint_file, "w", encoding="utf-8") as f:
                json.dump({"stats": stats, "examples": examples}, f, ensure_ascii=False, indent=4)
            console.print(f"Đã xử lý {processed_count}/{len(q_ids)} câu...")
            
    # In báo cáo
    console.print("\n[bold green]BÁO CÁO PHÂN TÍCH LỖI (ERROR ANALYSIS)[/bold green]")
    for dtype in ['single_doc', 'multi_doc']:
        s = stats[dtype]
        t = s['total']
        if t == 0: continue
        console.print(f"\n[bold yellow]--- {dtype.upper()} (Tổng số: {t}) ---[/bold yellow]")
        console.print(f"Recall@30: {s['recall_30_hits']}/{t} ({(s['recall_30_hits']/t)*100:.2f}%)")
        console.print(f"Recall@5:  {s['recall_5_hits']}/{t} ({(s['recall_5_hits']/t)*100:.2f}%)")
        console.print(f"[red]Nhóm A (Lỗi Retrieval - Không lọt Top 30):[/red] {s['group_A']} ({(s['group_A']/t)*100:.2f}%)")
        console.print(f"[magenta]Nhóm B (Lỗi Reranking - Trong Top 30 nhưng rớt Top 5):[/magenta] {s['group_B']} ({(s['group_B']/t)*100:.2f}%)")
        
    with open("error_analysis_final.json", "w", encoding="utf-8") as f:
        json.dump({"stats": stats, "examples": examples}, f, ensure_ascii=False, indent=4)
    console.print(f"\nĐã lưu báo cáo chi tiết vào error_analysis_final.json")

if __name__ == "__main__":
    main()
