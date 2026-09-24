import argparse
import json
import os
import torch
import chromadb
from pathlib import Path
from transformers import AutoTokenizer, AutoModelForCausalLM, BitsAndBytesConfig
from peft import PeftModel
from sentence_transformers import SentenceTransformer, util
import nltk
from nltk.translate.meteor_score import meteor_score
from rouge_score import rouge_scorer
from rich.console import Console
from rich.table import Table
from rich.progress import track
import gc

os.environ["HF_HOME"] = "E:/data-hf_cache"
console = Console()

def preprocess_text(text: str) -> str:
    import string
    if not text:
        return ""
    text = text.lower()
    translator = str.maketrans('', '', string.punctuation)
    text = text.translate(translator)
    text = " ".join(text.split())
    return text

class LegalQAEvaluator:
    def __init__(self, experiment_id, model_path, use_sft, top_k, fewshot_mask, max_new_tokens, do_sample, batch_size=1, limit_val=None, repetition_penalty=1.05, phase="all"):
        self.experiment_id = experiment_id
        self.model_path = model_path
        self.use_sft = use_sft
        self.top_k = top_k
        self.fewshot_mask = fewshot_mask
        self.max_new_tokens = max_new_tokens
        self.do_sample = do_sample
        self.batch_size = batch_size
        self.limit_val = limit_val
        self.repetition_penalty = repetition_penalty
        self.phase = phase
        
        # Load NLTK
        try:
            nltk.download('wordnet', quiet=True)
            nltk.download('omw-1.4', quiet=True)
            nltk.download('punkt', quiet=True)
            nltk.download('punkt_tab', quiet=True)
        except:
            pass
        self.rouge = rouge_scorer.RougeScorer(['rougeL'], use_stemmer=False)
        
        self.load_datasets()
        
        if self.phase in ["all", "retrieve"]:
            self.run_retrieval_phase()
        if self.phase in ["all", "generate"]:
            self.run_generation_phase()
        
    def load_datasets(self):
        train_file = Path(r"data/task2\train.json")
        with open(train_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        items = list(data.items())
        import random
        random.seed(42)
        random.shuffle(items)
        split_idx = int(len(items) * 0.9)
        val_items = items[split_idx:]
        if getattr(self, "limit_val", None) is not None:
            val_items = val_items[:self.limit_val]
        self.val_data = {k: v for k, v in val_items}
        self.train_items = items[:split_idx]
        self.train_questions = [v["question"] for k, v in self.train_items]
        console.print(f"[bold green]Loaded validation data: {len(self.val_data)} items[/bold green]")
        
    def retrieve_fewshot(self, query_emb, train_q_embs, k=2):
        cos_scores = util.cos_sim(query_emb, train_q_embs)[0]
        
        if self.fewshot_mask is not None:
            valid_mask = cos_scores < self.fewshot_mask
            cos_scores[~valid_mask] = -1.0
            
        top_results = torch.topk(cos_scores, k=k)
        
        few_shot_prompt = (
            "\n### VÍ DỤ THAM KHẢO VỀ CÁCH TRÌNH BÀY (HÃY HỌC THEO CÁCH HÀNH VĂN NÀY):\n"
            "LƯU Ý: Các ví dụ dưới đây CHỈ để tham khảo cách trình bày (format), "
            "KHÔNG được lấy nội dung/sự kiện pháp lý trong ví dụ để trả lời câu hỏi hiện tại. "
            "Nội dung câu trả lời phải lấy hoàn toàn từ 'Ngữ cảnh pháp lý thực tế' bên dưới.\n\n"
        )
        for i, idx in enumerate(top_results[1]):
            idx = int(idx)
            ex_q = self.train_items[idx][1]["question"]
            ex_a = self.train_items[idx][1]["answer"]
            few_shot_prompt += f"Ví dụ {i+1}:\n- Câu hỏi: {ex_q}\n- Trả lời (Mẫu định dạng chuẩn):\n{ex_a}\n\n"
        return few_shot_prompt

    def run_retrieval_phase(self):
        console.print("[bold blue]=== PHASE 1: RETRIEVAL ===[/bold blue]")
        db_dir = r"data/task1\chroma_db_bqbbao6"
        chroma_client = chromadb.PersistentClient(path=db_dir)
        collection = chroma_client.get_collection(name="legal_ir")
        
        console.print("Loading embedding model bqbbao6/vietnamese-legal-embedding...")
        embed_model = SentenceTransformer("bqbbao6/vietnamese-legal-embedding")
        
        console.print("Encoding train questions for few-shot...")
        train_q_embs = embed_model.encode(self.train_questions, batch_size=16, convert_to_tensor=True, show_progress_bar=True)
        
        self.retrieved_data = {}
        q_ids = list(self.val_data.keys())
        for q_id in track(q_ids, description="Retrieving..."):
            question = self.val_data[q_id]["question"]
            query_emb = embed_model.encode([question], convert_to_tensor=True, show_progress_bar=False)
            retrieval = collection.query(query_embeddings=query_emb.tolist(), n_results=self.top_k)
            
            # Extract documents (handling potential missing results)
            docs = retrieval['documents'][0] if retrieval['documents'] and len(retrieval['documents']) > 0 else []
            context = "\n\n".join(docs)
            
            few_shot = self.retrieve_fewshot(query_emb, train_q_embs, k=2)
            self.retrieved_data[q_id] = {"context": context, "few_shot": few_shot}
            
        with open(f"{self.experiment_id}_retrieved.json", "w", encoding="utf-8") as f:
            json.dump(self.retrieved_data, f, ensure_ascii=False)
        console.print("[yellow]Saved retrieved data and freeing RAM...[/yellow]")
        del embed_model
        del train_q_embs
        del chroma_client
        gc.collect()
        torch.cuda.empty_cache()

    def build_prompt(self, tokenizer, question, context, few_shot=""):
        sys_msg = (
            "Bạn là một trợ lý pháp lý chuyên nghiệp. Dựa vào NGỮ CẢNH PHÁP LÝ dưới đây, hãy trả lời câu hỏi của người dùng.\n\n"
            "YÊU CẦU QUAN TRỌNG:\n"
            "1. TRÍCH DẪN GẦN NGUYÊN VĂN: Hãy bám sát câu chữ trong ngữ cảnh, trích dẫn các khoản/điều một cách chính xác. Tuyệt đối hạn chế diễn giải lại bằng cách nói khác (abstractive)."
        )
        
        user_content = f"{few_shot}### Ngữ cảnh pháp lý thực tế:\n{context}\n\n### Câu hỏi của người dùng:\n{question}"
        
        messages = [
            {"role": "system", "content": sys_msg},
            {"role": "user", "content": user_content}
        ]
        
        return tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)

    def run_generation_phase(self):
        console.print("[bold blue]=== PHASE 2: GENERATION ===[/bold blue]")
        
        if self.phase == "generate":
            json_path = f"{self.experiment_id}_retrieved.json"
            if os.path.exists(json_path):
                with open(json_path, "r", encoding="utf-8") as f:
                    self.retrieved_data = json.load(f)
                console.print(f"Loaded retrieved data from {json_path}")
            else:
                console.print(f"[bold red]Error: {json_path} not found! Run retrieval phase first.[/bold red]")
                return

        base_id = "Qwen/Qwen2.5-1.5B-Instruct"
        tokenizer = AutoTokenizer.from_pretrained(base_id, trust_remote_code=True)
        tokenizer.padding_side = "left"
        if tokenizer.pad_token is None:
            tokenizer.pad_token = tokenizer.eos_token
            
        bnb_config = BitsAndBytesConfig(
            load_in_4bit=True,
            bnb_4bit_compute_dtype=torch.float16
        )
        model = AutoModelForCausalLM.from_pretrained(
            base_id,
            device_map="auto",
            quantization_config=bnb_config,
            low_cpu_mem_usage=True,
            trust_remote_code=True
        )
        if self.use_sft:
            console.print(f"Loading LoRA {self.model_path}...")
            model = PeftModel.from_pretrained(model, self.model_path)
            
        predictions = {}
        total_meteor = 0.0
        total_rougeL = 0.0
        q_ids = list(self.val_data.keys())
        if self.limit_val:
            q_ids = q_ids[:self.limit_val]
        
        from transformers import pipeline
        
        prompts = []
        for q_id in q_ids:
            q = self.val_data[q_id]["question"]
            r = self.retrieved_data[q_id]
            prompts.append((q_id, self.build_prompt(tokenizer, q, r["context"], r["few_shot"])))
            
        # Length bucketing to minimize padding waste
        prompts.sort(key=lambda x: len(x[1]))
        
        gen_kwargs = {
            "max_new_tokens": self.max_new_tokens,
            "pad_token_id": tokenizer.pad_token_id,
            "eos_token_id": [tokenizer.eos_token_id, tokenizer.convert_tokens_to_ids("<|im_end|>")],
            "do_sample": False,
        }
        if self.do_sample:
            gen_kwargs.update({"do_sample": True, "temperature": 0.1, "top_p": 0.9, "top_k": self.top_k, "repetition_penalty": self.repetition_penalty})
        else:
            gen_kwargs.update({"do_sample": False, "repetition_penalty": self.repetition_penalty})
            
        console.print("Generating with manual batching and bucketing...")
        
        # Batch generation
        for i in track(range(0, len(prompts), self.batch_size), description="Batch Generation"):
            batch = prompts[i:i + self.batch_size]
            batch_qids = [x[0] for x in batch]
            batch_texts = [x[1] for x in batch]
            
            inputs = tokenizer(batch_texts, return_tensors="pt", padding=True).to(model.device)
            prompt_len = inputs.input_ids.shape[1]
            
            with torch.no_grad():
                gen_out = model.generate(**inputs, **gen_kwargs)
            
            for j, q_id in enumerate(batch_qids):
                gen_ids = gen_out[j][prompt_len:]
                raw_ans = tokenizer.decode(gen_ids, skip_special_tokens=False)
                ans = raw_ans.replace("<|im_end|>", "").strip()
                predictions[q_id] = {"answer": ans}
                
        # Calculate metrics
        for q_id in q_ids:
            ans = predictions[q_id]["answer"]
            ref = self.val_data[q_id]["answer"]
            norm_ref = preprocess_text(ref)
            norm_gen = preprocess_text(ans)
            if norm_ref and norm_gen:
                try:
                    total_meteor += meteor_score([nltk.word_tokenize(norm_ref)], nltk.word_tokenize(norm_gen))
                except:
                    pass
                total_rougeL += self.rouge.score(norm_ref, norm_gen)['rougeL'].fmeasure
                
        total = len(q_ids)
        console.print(f"\n[bold magenta]Results for {self.experiment_id}[/bold magenta]")
        console.print(f"METEOR: {total_meteor/total:.4f}")
        console.print(f"ROUGE-L: {total_rougeL/total:.4f}")
        
        out_json = f"{self.experiment_id}_predictions.json"
        with open(out_json, "w", encoding="utf-8") as f:
            json.dump(predictions, f, ensure_ascii=False, indent=4)
        
        del model
        gc.collect()
        torch.cuda.empty_cache()

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--exp", type=str, required=True, help="Experiment ID (e.g. E00, E01)")
    parser.add_argument("--use_sft", action="store_true")
    parser.add_argument("--model_path", type=str, default=r"models\qwen1.5b-legalqa-sft-v2\checkpoint-150")
    parser.add_argument("--top_k", type=int, default=3)
    parser.add_argument("--fewshot_mask", type=float, default=0.9)
    parser.add_argument("--max_new_tokens", type=int, default=600)
    parser.add_argument("--do_sample", action="store_true")
    parser.add_argument("--batch_size", type=int, default=4)
    parser.add_argument("--limit_val", type=int, default=None, help="Limit number of validation items")
    parser.add_argument("--repetition_penalty", type=float, default=1.05)
    parser.add_argument("--phase", type=str, default="all", choices=["all", "retrieve", "generate"])
    args = parser.parse_args()
    
    LegalQAEvaluator(
        args.exp, 
        args.model_path, 
        args.use_sft, 
        args.top_k, 
        args.fewshot_mask, 
        args.max_new_tokens, 
        args.do_sample,
        args.batch_size,
        args.limit_val,
        args.repetition_penalty,
        args.phase
    )
