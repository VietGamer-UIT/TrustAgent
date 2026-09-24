import torch
from transformers import AutoTokenizer
import json
from rich.console import Console

console = Console()

class CustomDataCollatorForChatML:
    def __init__(self, tokenizer, max_length=1024):
        self.tokenizer = tokenizer
        self.max_length = max_length
        
        # We need to find the token sequence that denotes the start of assistant response
        # In Qwen2.5, the assistant's turn starts with: <|im_start|>assistant\n
        self.assistant_prompt = "<|im_start|>assistant\n"
        self.assistant_prompt_ids = self.tokenizer.encode(self.assistant_prompt, add_special_tokens=False)
        
    def __call__(self, features):
        input_ids_batch = []
        labels_batch = []
        attention_mask_batch = []
        
        for feature in features:
            messages = feature["messages"]
            text = self.tokenizer.apply_chat_template(messages, tokenize=False)
            
            encoded = self.tokenizer(
                text, 
                truncation=True, 
                max_length=self.max_length,
                return_tensors="pt",
                add_special_tokens=False
            )
            
            input_ids = encoded["input_ids"][0]
            attention_mask = encoded["attention_mask"][0]
            labels = input_ids.clone()
            
            # Find the assistant prompt in the input_ids
            # We search for self.assistant_prompt_ids
            seq_len = len(input_ids)
            prompt_len = len(self.assistant_prompt_ids)
            
            match_idx = -1
            for i in range(seq_len - prompt_len + 1):
                if input_ids[i:i+prompt_len].tolist() == self.assistant_prompt_ids:
                    match_idx = i + prompt_len
                    break
            
            if match_idx == -1:
                # If we didn't find the exact token match, we might have tokenization boundary issues.
                # Let's decode progressively to find the exact boundary
                for i in range(seq_len):
                    decoded = self.tokenizer.decode(input_ids[:i])
                    if decoded.endswith(self.assistant_prompt):
                        match_idx = i
                        break
            
            if match_idx != -1:
                # Mask everything before the assistant's actual text
                labels[:match_idx] = -100
            else:
                print("WARNING: Could not find assistant prompt in sequence.")
                labels[:] = -100 # Mask everything if we fail
                
            input_ids_batch.append(input_ids)
            labels_batch.append(labels)
            attention_mask_batch.append(attention_mask)
            
        # Pad sequences
        input_ids = torch.nn.utils.rnn.pad_sequence(
            [i.flip(0) for i in input_ids_batch], 
            batch_first=True, 
            padding_value=self.tokenizer.pad_token_id
        ).flip(1)
        
        labels = torch.nn.utils.rnn.pad_sequence(
            [l.flip(0) for l in labels_batch], 
            batch_first=True, 
            padding_value=-100
        ).flip(1)
        
        attention_mask = torch.nn.utils.rnn.pad_sequence(
            [a.flip(0) for a in attention_mask_batch], 
            batch_first=True, 
            padding_value=0
        ).flip(1)
        
        return {
            "input_ids": input_ids,
            "labels": labels,
            "attention_mask": attention_mask
        }

def main():
    model_id = "Qwen/Qwen2.5-1.5B-Instruct"
    tokenizer = AutoTokenizer.from_pretrained(model_id, trust_remote_code=True)
    
    if not tokenizer.pad_token:
        tokenizer.pad_token = tokenizer.eos_token
        
    # Read a sample from dataset.jsonl
    with open(r"data/dataset.jsonl", "r", encoding="utf-8") as f:
        sample_json = json.loads(f.readline())
        
    messages = sample_json["messages"]
    
    # Instantiate custom collator
    collator = CustomDataCollatorForChatML(tokenizer=tokenizer, max_length=1024)
    
    batch = [sample_json]
    collated = collator(batch)
    
    input_ids = collated["input_ids"][0]
    labels = collated["labels"][0]
    
    unmasked_indices = labels != -100
    unmasked_input_ids = input_ids[unmasked_indices]
    
    unmasked_text = tokenizer.decode(unmasked_input_ids)
    
    console.print("[bold green]=== ORIGINAL ASSISTANT MESSAGE ===[/bold green]")
    console.print(messages[-1]["content"][:200] + "...")
    
    console.print("\n[bold yellow]=== UNMASKED TEXT (Should match exactly) ===[/bold yellow]")
    console.print(unmasked_text[:200] + "...")
    
    console.print("\n[bold cyan]=== IS IT A MATCH? ===[/bold cyan]")
    expected = messages[-1]["content"] + "<|im_end|>"
    if unmasked_text == expected:
        console.print("✅ PERFECT MATCH! The masking is 100% correct.")
    else:
        console.print("❌ MISMATCH DETECTED! Look closely at the extra tokens.")
        console.print(f"Unmasked ends with: {repr(unmasked_text[-20:])}")
        console.print(f"Expected ends with: {repr(expected[-20:])}")

if __name__ == "__main__":
    main()
