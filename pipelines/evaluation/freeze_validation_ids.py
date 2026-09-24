import json
import random
from pathlib import Path

def main():
    train_file = Path(r"data/task2\train.json")
    with open(train_file, "r", encoding="utf-8") as f:
        data = json.load(f)
        
    items = list(data.items())
    
    # EXACT same split logic as benchmark_legalqa.py
    random.seed(42)
    random.shuffle(items)
    
    split_idx = int(len(items) * 0.9)
    val_items = items[split_idx:]
    
    # Get top 200 IDs
    limit = 200
    val_items = val_items[:limit]
    
    question_ids = [k for k, v in val_items]
    
    out_file = r"data/scripts\validation_200_ids.json"
    result = {
        "seed": 42,
        "sample_count": len(question_ids),
        "question_ids": question_ids
    }
    
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=4)
        
    print(f"Saved {len(question_ids)} validation IDs to {out_file}")
    
    # While we're at it, let's verify leakage.
    train_items = items[:split_idx]
    train_ids = [k for k, v in train_items]
    
    intersection = set(train_ids).intersection(set(question_ids))
    print(f"Leakage check: Train IDs intersecting with Val IDs: {len(intersection)}")
    assert len(intersection) == 0, "DATA LEAKAGE DETECTED!"
    
if __name__ == "__main__":
    main()
