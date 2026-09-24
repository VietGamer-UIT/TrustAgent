import os
import json
import time
import torch
from transformers import AutoTokenizer, AutoModelForCausalLM, BitsAndBytesConfig
from rich.console import Console
from rich.table import Table

console = Console()
os.environ["HF_HOME"] = "E:/data-hf_cache"

def load_diag_data():
    with open("diag_retrieved.json", "r", encoding="utf-8") as f:
        d = json.load(f)
    return d["val"], d["ret"]

def main():
    val_data, retrieved = load_diag_data()
    q_ids = list(val_data.keys())
    
    console.print("Loading model...")
    base_id = "Qwen/Qwen2.5-1.5B-Instruct"
    tokenizer = AutoTokenizer.from_pretrained(base_id, trust_remote_code=True)
    tokenizer.padding_side = "left"
    
    quant_config = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_quant_type="nf4",
        bnb_4bit_compute_dtype=torch.float16
    )
    model = AutoModelForCausalLM.from_pretrained(base_id, quantization_config=quant_config, device_map="cuda")
    
    # Prepare all prompts
    prompts = []
    for q_id in q_ids:
        ctx = retrieved[q_id]["context"]
        fs = retrieved[q_id]["few_shot"]
        user_content = f"{fs}### Ngữ cảnh pháp lý thực tế:\n{ctx}\n\n### Câu hỏi của người dùng:\n{val_data[q_id]['question']}"
        sys_msg = "Bạn là một trợ lý pháp lý chuyên nghiệp. Dựa vào NGỮ CẢNH PHÁP LÝ dưới đây, hãy trả lời câu hỏi của người dùng."
        messages = [{"role": "system", "content": sys_msg}, {"role": "user", "content": user_content}]
        prompts.append(tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True))
    
    batch_sizes = [1, 2, 4, 8]
    results = []
    
    for bs in batch_sizes:
        console.print(f"\n--- Benchmarking Batch Size: {bs} ---")
        torch.cuda.empty_cache()
        t0 = time.time()
        
        total_gen_tokens = 0
        total_prompt_tokens = 0
        
        # Batching loop
        for i in range(0, len(prompts), bs):
            batch_prompts = prompts[i:i+bs]
            inputs = tokenizer(batch_prompts, return_tensors="pt", padding=True).to("cuda")
            
            prompt_len = inputs.input_ids.shape[1]
            total_prompt_tokens += prompt_len * len(batch_prompts)
            
            gen_out = model.generate(
                **inputs,
                max_new_tokens=600,
                pad_token_id=tokenizer.pad_token_id,
                eos_token_id=[tokenizer.eos_token_id, tokenizer.convert_tokens_to_ids("<|im_end|>")],
                do_sample=False,
                repetition_penalty=1.05
            )
            
            # Count generated tokens
            for j in range(len(batch_prompts)):
                gen_toks = len(gen_out[j]) - prompt_len
                total_gen_tokens += gen_toks
                
        t1 = time.time()
        runtime = t1 - t0
        
        results.append({
            "batch_size": bs,
            "runtime": runtime,
            "q_per_sec": len(prompts) / runtime,
            "tok_per_sec": total_gen_tokens / runtime
        })
        
        console.print(f"BS={bs}: {runtime:.2f}s | {len(prompts)/runtime:.2f} q/s | {total_gen_tokens/runtime:.2f} tok/s")

if __name__ == '__main__':
    main()
