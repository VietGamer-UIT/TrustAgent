import json
import os
import torch
import chromadb
from pathlib import Path
from sentence_transformers import SentenceTransformer
from rich.progress import track
from rich.console import Console

console = Console()

def main():
    # Paths
    train_file = Path(r"data/sample\dataset.json")
    db_dir = Path(r"data/sample\chroma_db_bqbbao6")
    out_train = Path(r"data/scripts\dataset.jsonl")
    out_val = Path(r"data/scripts\val.jsonl")
    
    # Load data
    console.print("[bold blue]Loading train data...[/bold blue]")
    with open(train_file, "r", encoding="utf-8") as f:
        data = json.load(f)
        
    items = list(data.items())
    console.print(f"Loaded {len(items)} items.")
    
    # Split into train/val (e.g. 90% train, 10% val)
    import random
    random.seed(42)
    random.shuffle(items)
    
    split_idx = int(len(items) * 0.9)
    train_items = items[:split_idx]
    val_items = items[split_idx:]
    console.print(f"Train split: {len(train_items)} items")
    console.print(f"Val split: {len(val_items)} items")
    
    # Init ChromaDB
    console.print(f"[bold blue]Connecting to ChromaDB at {db_dir}...[/bold blue]")
    chroma_client = chromadb.PersistentClient(path=str(db_dir))
    collection = chroma_client.get_or_create_collection(
        name="legal_ir",
        metadata={"hnsw:space": "cosine"}
    )
    
    # Init Embedding Model
    console.print("[bold blue]Loading embedding model bqbbao6/vietnamese-legal-embedding...[/bold blue]")
    embed_model = SentenceTransformer("bqbbao6/vietnamese-legal-embedding")
    
    sys_msg = (
        "Bạn là một trợ lý pháp lý chuyên nghiệp. Dựa vào NGỮ CẢNH PHÁP LÝ dưới đây, hãy trả lời câu hỏi của người dùng.\n\n"
        "YÊU CẦU QUAN TRỌNG:\n"
        "1. TRÍCH DẪN GẦN NGUYÊN VĂN: Hãy bám sát câu chữ trong ngữ cảnh, trích dẫn các khoản/điều một cách chính xác. Tuyệt đối hạn chế diễn giải lại bằng cách nói khác (abstractive)."
    )
    
    def process_split(split_items, out_path, batch_size=128):
        out_f = open(out_path, "w", encoding="utf-8")
        
        for i in track(range(0, len(split_items), batch_size), description=f"Processing {out_path.name}..."):
            batch = split_items[i:i+batch_size]
            queries = [v["question"] for k, v in batch]
            answers = [v["answer"] for k, v in batch]
            ids = [k for k, v in batch]
            
            # Encode
            embeddings = embed_model.encode(queries, show_progress_bar=False, batch_size=batch_size)
            
            # Query ChromaDB
            results = collection.query(
                query_embeddings=embeddings.tolist(),
                n_results=3
            )
            
            for j in range(len(batch)):
                chunks = results['documents'][j]
                context = "\n\n".join(chunks)
                
                # Format into ChatML
                messages = [
                    {"role": "system", "content": sys_msg},
                    {"role": "user", "content": f"### Ngữ cảnh pháp lý thực tế:\n{context}\n\n### Câu hỏi của người dùng:\n{queries[j]}"},
                    {"role": "assistant", "content": answers[j]}
                ]
                
                record = {
                    "id": ids[j],
                    "messages": messages
                }
                out_f.write(json.dumps(record, ensure_ascii=False) + "\n")
                
        out_f.close()
        
    process_split(train_items, out_train)
    process_split(val_items, out_val)
    
    console.print("[bold green]Done! Dataset prepared.[/bold green]")

if __name__ == "__main__":
    main()
