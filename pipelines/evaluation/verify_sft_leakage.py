import json

def main():
    val_file = r"data/scripts\validation_200_ids.json"
    with open(val_file, "r", encoding="utf-8") as f:
        val_ids = set(json.load(f)["question_ids"])
        
    train_file = r"data/scripts\train.jsonl"
    with open(train_file, "r", encoding="utf-8") as f:
        lines = f.readlines()
        
    sft_train_records = [json.loads(line) for line in lines]
    
    # We need to map sft_train_records back to question_id.
    # The original full train dataset is train.json
    full_train_file = r"data/task2\train.json"
    with open(full_train_file, "r", encoding="utf-8") as f:
        full_data = json.load(f)
        
    # Create mapping from question text -> question_id
    text_to_id = {}
    for q_id, v in full_data.items():
        text_to_id[v["question"]] = q_id
        
    sft_train_ids = set()
    for r in sft_train_records:
        user_msg = r["messages"][1]["content"]
        # Extract question part
        if "### Câu hỏi của người dùng:" in user_msg:
            question_text = user_msg.split("### Câu hỏi của người dùng:\n")[1].strip()
            if question_text in text_to_id:
                sft_train_ids.add(text_to_id[question_text])
                
    intersection = sft_train_ids.intersection(val_ids)
    print(f"Total SFT train records: {len(sft_train_records)}")
    print(f"Mapped to {len(sft_train_ids)} unique question IDs")
    print(f"Validation pool size: {len(val_ids)}")
    print(f"LEAKAGE (SFT Train Intersection Validation 200): {len(intersection)}")
    
    if len(intersection) > 0:
        print("CRITICAL LEAKAGE DETECTED!")
        print("Leaked IDs:")
        for q_id in intersection:
            print(f"- {q_id}")
    else:
        print("PASS: 0 leakage.")

if __name__ == "__main__":
    main()
