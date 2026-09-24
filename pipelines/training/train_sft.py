import os
import torch
import json
from transformers import AutoTokenizer, AutoModelForCausalLM, BitsAndBytesConfig
from peft import LoraConfig, get_peft_model, prepare_model_for_kbit_training
from trl import SFTTrainer, SFTConfig
from datasets import load_dataset
from rich.console import Console

import os
os.environ["HF_HOME"] = "E:/data-hf_cache"

console = Console()

class CustomDataCollatorForChatML:
    def __init__(self, tokenizer, max_length=896):
        self.tokenizer = tokenizer
        self.max_length = max_length
        self.assistant_prompt = "<|im_start|>assistant\n"
        self.assistant_prompt_ids = self.tokenizer.encode(self.assistant_prompt, add_special_tokens=False)
        
    def __call__(self, features):
        input_ids_batch = []
        labels_batch = []
        attention_mask_batch = []
        
        for feature in features:
            if "messages" in feature:
                messages = feature["messages"]
                text = self.tokenizer.apply_chat_template(messages, tokenize=False)
            elif "text" in feature:
                text = feature["text"]
            else:
                text = ""
                
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
            
            seq_len = len(input_ids)
            prompt_len = len(self.assistant_prompt_ids)
            
            match_idx = -1
            for i in range(seq_len - prompt_len + 1):
                if input_ids[i:i+prompt_len].tolist() == self.assistant_prompt_ids:
                    match_idx = i + prompt_len
                    break
            
            if match_idx == -1:
                for i in range(seq_len):
                    decoded = self.tokenizer.decode(input_ids[:i])
                    if decoded.endswith(self.assistant_prompt):
                        match_idx = i
                        break
            
            if match_idx != -1:
                labels[:match_idx] = -100
            else:
                labels[:] = -100 
                
            input_ids_batch.append(input_ids)
            labels_batch.append(labels)
            attention_mask_batch.append(attention_mask)
            
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
    os.environ["HF_HOME"] = "E:/data-hf_cache"
    
    # Paths
    train_file = os.environ.get("SFT_TRAIN_FILE", "dataset.jsonl")
    output_dir = r"models\qwen1.5b-legalqa-sft-v3"
    model_id = "Qwen/Qwen2.5-1.5B-Instruct"
    
    console.print(f"[bold cyan]Output dir:[/bold cyan] {output_dir}")
    
    # Load dataset
    dataset = load_dataset("json", data_files={"train": train_file})["train"]
    
    # Tokenizer
    console.print("[bold blue]Loading tokenizer...[/bold blue]")
    tokenizer = AutoTokenizer.from_pretrained(model_id, trust_remote_code=True)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token
        
    console.print("[bold blue]Loading model...[/bold blue]")
    bnb_config = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_compute_dtype=torch.float16,
        bnb_4bit_quant_type="nf4",
        bnb_4bit_use_double_quant=True
    )
    
    model = AutoModelForCausalLM.from_pretrained(
        model_id,
        quantization_config=bnb_config,
        device_map="auto",
        torch_dtype=torch.float16,
        trust_remote_code=True
    )
    
    model = prepare_model_for_kbit_training(model)
    model.config.use_cache = False
    model.enable_input_require_grads()
    
    # LoRA config - Chỉ train Attention (q, k, v, o) để tiết kiệm VRAM tối đa!
    lora_config = LoraConfig(
        r=16,
        lora_alpha=32,
        target_modules=["q_proj", "k_proj", "v_proj", "o_proj"],
        lora_dropout=0.05,
        bias="none",
        task_type="CAUSAL_LM"
    )
    
    model = get_peft_model(model, lora_config)
    
    # Collator
    collator = CustomDataCollatorForChatML(tokenizer=tokenizer, max_length=896)
    
    # Training Arguments
    from transformers import TrainingArguments, Trainer
    training_args = TrainingArguments(
        output_dir=output_dir,
        max_steps=300,
        per_device_train_batch_size=1,
        gradient_accumulation_steps=16,
        per_device_eval_batch_size=1,
        eval_strategy="no",
        save_strategy="steps",
        save_steps=50,
        save_total_limit=10,
        logging_steps=10,
        learning_rate=2e-4,
        weight_decay=0.01,
        fp16=True,
        max_grad_norm=0.3,
        warmup_ratio=0.03,
        optim="adamw_8bit",
        report_to="none",
        remove_unused_columns=False,
        gradient_checkpointing=True,
    )
    
    # Trainer
    trainer = Trainer(
        model=model,
        args=training_args,
        train_dataset=dataset,
        data_collator=collator,
    )
    
    console.print("[bold green]Starting Training...[/bold green]")
    trainer.train()
    
    # Save final model
    trainer.save_model(output_dir)
    tokenizer.save_pretrained(output_dir)
    console.print("[bold green]Training complete![/bold green]")

if __name__ == "__main__":
    main()
