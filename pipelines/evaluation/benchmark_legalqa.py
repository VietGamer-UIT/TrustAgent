import os
import json
import time
import argparse
import traceback
import hashlib
from pathlib import Path
from collections import Counter
import gc

os.environ["HF_HOME"] = "E:/data-hf_cache"

import torch
import chromadb
from transformers import AutoModelForCausalLM, AutoTokenizer
from peft import PeftModel
from sentence_transformers import SentenceTransformer, util

import nltk
from nltk.translate.meteor_score import meteor_score
from rouge_score import rouge_scorer
from rich.console import Console
from rich.table import Table
from rich.progress import track
from tqdm import tqdm

import string

console = Console()

def preprocess_text(text: str) -> str:
    """Chuẩn hóa văn bản Tiếng Việt: lowercase, bỏ dấu câu, strip."""
    if not text:
        return ""
    text = text.lower()
    translator = str.maketrans('', '', string.punctuation)
    text = text.translate(translator)
    text = " ".join(text.split())
    return text

def calculate_repetition_metrics(text: str):
    tokens = text.split()
    if not tokens:
        return {
            "unique_unigram_ratio": 0.0, 
            "unique_bigram_ratio": 0.0, 
            "unique_trigram_ratio": 0.0, 
            "repeated_bigram_count": 0,
            "repeated_trigram_count": 0,
            "max_repeated_span": 0,
            "answer_length": 0
        }
    
    unigrams = tokens
    bigrams = list(zip(tokens, tokens[1:]))
    trigrams = list(zip(tokens, tokens[1:], tokens[2:]))
    
    bigram_counts = Counter(bigrams)
    trigram_counts = Counter(trigrams)
    
    repeated_bigrams = sum(1 for c in bigram_counts.values() if c > 1)
    repeated_trigrams = sum(1 for c in trigram_counts.values() if c > 1)
    
    # Calculate max repeated span
    max_span = 0
    n = len(tokens)
    for length in range(100, 3, -1):
        if length > n:
            continue
        spans = [tuple(tokens[i:i+length]) for i in range(n - length + 1)]
        if any(c > 1 for c in Counter(spans).values()):
            max_span = length
            break
            
    return {
        "answer_length": len(tokens),
        "unique_unigram_ratio": len(set(unigrams)) / len(unigrams) if unigrams else 0,
        "unique_bigram_ratio": len(set(bigrams)) / len(bigrams) if bigrams else 0,
        "unique_trigram_ratio": len(set(trigrams)) / len(trigrams) if trigrams else 0,
        "repeated_bigram_count": repeated_bigrams,
        "repeated_trigram_count": repeated_trigrams,
        "max_repeated_span": max_span
    }

class BenchmarkLegalQA:
    def __init__(self, args):
        self.args = args
        self.experiment = args.experiment
        self.limit = args.limit
        self.batch_size = args.batch_size
        self.do_sample = args.do_sample
        self.top_k_retrieval = args.top_k_retrieval
        
        # Original Baseline Prompt Semantic exact match
        self.sys_msg = (
            "Bạn là một trợ lý pháp lý chuyên nghiệp. Dựa vào NGỮ CẢNH PHÁP LÝ dưới đây, hãy trả lời câu hỏi của người dùng.\n\n"
            "YÊU CẦU QUAN TRỌNG:\n"
            "1. TRÍCH DẪN GẦN NGUYÊN VĂN: Hãy bám sát câu chữ trong ngữ cảnh, trích dẫn các khoản/điều một cách chính xác. Tuyệt đối hạn chế diễn giải lại bằng cách nói khác (abstractive).\n"
            "2. SAO CHÉP ĐỊNH DẠNG: Bạn bắt buộc phải trình bày câu trả lời của mình theo ĐÚNG CẤU TRÚC VÀ VĂN PHONG (văn xuôi, gạch đầu dòng, số thứ tự, v.v...) giống y hệt như các ví dụ tham khảo dưới đây. Nếu ví dụ dùng gạch đầu dòng, bạn phải dùng gạch đầu dòng. Nếu ví dụ viết liền, bạn phải viết liền. Độ dài câu trả lời của bạn cũng nên tương đương với cách trả lời trong ví dụ."
        )

        try:
            nltk.download('wordnet', quiet=True)
            nltk.download('omw-1.4', quiet=True)
            nltk.download('punkt', quiet=True)
            nltk.download('punkt_tab', quiet=True)
        except:
            pass
        self.rouge = rouge_scorer.RougeScorer(['rougeL'], use_stemmer=False)
        self.load_datasets()
        
        # Create output dirs
        os.makedirs("prompt_cache", exist_ok=True)
        os.makedirs("benchmark_results", exist_ok=True)

    def load_datasets(self):
        train_file = Path(r"data/task2\train.json")
        with open(train_file, "r", encoding="utf-8") as f:
            data = json.load(f)
            
        items = list(data.items())
        # Validate schema
        for k, v in items[:5]:
            assert isinstance(v.get("answer"), str), f"Dataset schema error: answer is not a string for {k}"
            
        import random
        random.seed(42)
        random.shuffle(items)
        split_idx = int(len(items) * 0.9)
        val_items = items[split_idx:]
        
        if self.args.validation_ids:
            with open(self.args.validation_ids, "r", encoding="utf-8") as f:
                valid_ids_data = json.load(f)
                target_ids = set(valid_ids_data["question_ids"])
            val_items = [item for item in val_items if item[0] in target_ids]
            console.print(f"Loaded {len(val_items)} validation samples from {self.args.validation_ids}")
        elif self.limit is not None:
            val_items = val_items[:self.limit]
            
        self.val_data = {k: v for k, v in val_items}
        self.train_items = items[:split_idx]
        self.train_questions = [v["question"] for k, v in self.train_items]
        console.print(f"[bold green]Loaded {len(self.val_data)} validation samples for benchmark.[/bold green]")

    def run_retrieval(self):
        # We define E00_FUNCTIONAL using bqbbao6 as the functional baseline DB
        db_dir = r"data/task1\chroma_db_bqbbao6"
        embed_model_name = "bqbbao6/vietnamese-legal-embedding"
        
        # Rigorous Cache ID based on exact metadata
        # Read the exact validation IDs
        val_ids_list = list(self.val_data.keys())
        val_ids_hash = hashlib.sha256(json.dumps(val_ids_list, sort_keys=True).encode("utf-8")).hexdigest()[:8]
        
        cache_state = {
            "dataset": "train.json",
            "embed_model": embed_model_name,
            "database": db_dir,
            "top_k_retrieval": self.top_k_retrieval,
            "val_ids_hash": val_ids_hash,
            "fewshot_k": len(self.train_items),
            "prompt_version": 2
        }
        cache_hash = hashlib.sha256(json.dumps(cache_state, sort_keys=True).encode("utf-8")).hexdigest()[:16]
        
        cache_id = f"retrieval_v2_{cache_hash}"
        cache_path = os.path.join("prompt_cache", f"{cache_id}.json")
        
        if os.path.exists(cache_path) and not self.args.force_retrieval:
            console.print(f"[bold blue]Loading retrieval cache from {cache_path}[/bold blue]")
            with open(cache_path, "r", encoding="utf-8") as f:
                self.retrieved_data = json.load(f)
            # Verify cache has exact 200 IDs
            cache_keys = set(self.retrieved_data.keys())
            val_keys = set(self.val_data.keys())
            if cache_keys != val_keys:
                console.print(f"[bold red]CRITICAL: Cache keys do not match validation IDs. Rebuilding...[/bold red]")
            else:
                console.print(f"[bold green]Verified cache contains exact {len(cache_keys)} target IDs.[/bold green]")
                return

        console.print(f"[bold blue]=== PHASE 1: RETRIEVAL ({embed_model_name}) ===[/bold blue]")
        chroma_client = chromadb.PersistentClient(path=db_dir)
        collection = chroma_client.get_collection(name="legal_ir")
        
        console.print(f"Loading embedding model {embed_model_name}...")
        embed_model = SentenceTransformer(embed_model_name)
        
        console.print("Encoding train questions for dynamic few-shot...")
        
        # VERIFY FEW-SHOT LEAKAGE
        train_ids = set([k for k, v in self.train_items])
        val_ids = set(self.val_data.keys())
        leakage = train_ids.intersection(val_ids)
        if len(leakage) > 0:
            raise ValueError(f"CRITICAL LEAKAGE DETECTED: {len(leakage)} validation samples found in few-shot train pool!")
        console.print("[bold green]Verified 0 leakage between few-shot pool and validation set.[/bold green]")
        
        train_q_embs = embed_model.encode(self.train_questions, batch_size=16, convert_to_tensor=True, show_progress_bar=True)
        
        self.retrieved_data = {}
        # Iterate over self.val_data directly so we only retrieve what we need!
        for q_id, val_info in tqdm(self.val_data.items(), desc="Retrieving context and few-shot"):
            question = val_info["question"]
            
            # Retrieval
            query_emb = embed_model.encode([question], convert_to_tensor=True, show_progress_bar=False)
            retrieval = collection.query(query_embeddings=query_emb.tolist(), n_results=self.top_k_retrieval)
            docs = retrieval['documents'][0] if retrieval['documents'] and len(retrieval['documents']) > 0 else []
            context = "\n\n".join(docs)
            
            # Few-shot
            cos_scores = util.cos_sim(query_emb, train_q_embs)[0]
            # Exclude highly similar to prevent data leakage in case it's in training set
            valid_mask = cos_scores < 0.9
            cos_scores[~valid_mask] = -1.0
            top_results = torch.topk(cos_scores, k=2)
            
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
                
            self.retrieved_data[q_id] = {
                "context": context,
                "few_shot_prompt": few_shot_prompt
            }
            
        # Save cache
        with open(cache_path, "w", encoding="utf-8") as f:
            json.dump(self.retrieved_data, f, indent=4, ensure_ascii=False)
        console.print(f"[bold green]Saved retrieval cache to {cache_path}[/bold green]")
        
        del embed_model
        del train_q_embs
        del chroma_client
        gc.collect()
        if torch.cuda.is_available():
            torch.cuda.empty_cache()

    def build_prompt(self, tokenizer, question, context, few_shot_prompt):
        user_content = f"{few_shot_prompt}### Ngữ cảnh pháp lý thực tế:\n{context}\n\n### Câu hỏi của người dùng:\n{question}\n\n### Trả lời (Đảm bảo đúng định dạng như ví dụ):"
        messages = [
            {"role": "system", "content": self.sys_msg},
            {"role": "user", "content": user_content}
        ]
        return tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)

    def run_generation(self):
        total_tokens_generated = 0
        total_input_tokens = 0
        input_lengths = []
        output_lengths = []
        
        console.print(f"[bold blue]=== PHASE 2: GENERATION ({self.experiment}) ===[/bold blue]")
        start_time = time.time()
        self.model_id = "Qwen/Qwen2.5-1.5B-Instruct"
        tokenizer = AutoTokenizer.from_pretrained(self.model_id, trust_remote_code=True)
        tokenizer.padding_side = "left"
        if tokenizer.pad_token is None:
            tokenizer.pad_token = tokenizer.eos_token
            
        from transformers import BitsAndBytesConfig
        bnb_config = BitsAndBytesConfig(
            load_in_4bit=True,
            bnb_4bit_compute_dtype=torch.float16
        )
        
        console.print(f"Loading Base Model {self.model_id}...")
        model = AutoModelForCausalLM.from_pretrained(
            self.model_id,
            device_map="auto",
            quantization_config=bnb_config,
            low_cpu_mem_usage=True,
            trust_remote_code=True
        )
        
        # Handle SFT if requested
        if self.args.sft_path:
            console.print(f"Loading LoRA from {self.args.sft_path}...")
            model = PeftModel.from_pretrained(model, self.args.sft_path)
            
        # Prepare Prompts
        prompts = []
        for q_id in self.val_data.keys():
            q = self.val_data[q_id]["question"]
            r = self.retrieved_data.get(q_id, {"context": "", "few_shot_prompt": ""})
            full_prompt = self.build_prompt(tokenizer, q, r["context"], r["few_shot_prompt"])
            prompts.append((q_id, full_prompt))
            
        if self.args.length_bucketing:
            prompts.sort(key=lambda x: len(x[1]))
            
        predictions = {}
        
        torch.cuda.reset_peak_memory_stats()
        
        i = 0
        pbar = tqdm(total=len(prompts), desc=f"Batch Gen (bs={self.batch_size})")
        
        current_batch_size = self.batch_size
        truncate_next = False
        
        while i < len(prompts):
            actual_batch_size = min(current_batch_size, len(prompts) - i)
            batch = prompts[i:i + actual_batch_size]
            batch_qids = [x[0] for x in batch]
            batch_prompts = [x[1] for x in batch]
            
            try:
                if truncate_next:
                    inputs = tokenizer(batch_prompts, return_tensors="pt", padding=True, truncation=True, max_length=1536).to(model.device)
                else:
                    inputs = tokenizer(batch_prompts, return_tensors="pt", padding=True).to(model.device)
                
                batch_input_tokens = inputs.input_ids.shape[1]
                total_input_tokens += batch_input_tokens * len(batch_prompts)
                for _ in range(len(batch_prompts)):
                    input_lengths.append(batch_input_tokens)
                    
                outputs = model.generate(
                    **inputs,
                    max_new_tokens=512,
                    temperature=0.1,
                    repetition_penalty=1.05,
                    pad_token_id=tokenizer.eos_token_id,
                    do_sample=False
                )
                
                for j in range(len(batch_prompts)):
                    gen_len = outputs[j].shape[0] - inputs.input_ids.shape[1]
                    output_lengths.append(gen_len)
                    total_tokens_generated += gen_len
                    
                    gen_ids = outputs[j][inputs.input_ids.shape[1]:]
                    raw_ans = tokenizer.decode(gen_ids, skip_special_tokens=False)
                    ans = raw_ans.replace("<|im_end|>", "").strip()
                    predictions[batch_qids[j]] = ans
                    
                del inputs
                del outputs
                import gc
                gc.collect()
                
                i += actual_batch_size
                pbar.update(actual_batch_size)
                
                # Reset for next batch
                current_batch_size = self.batch_size
                truncate_next = False
                
            except RuntimeError as e:
                if "out of memory" in str(e):
                    import gc
                    gc.collect()
                    torch.cuda.empty_cache()
                    
                    if current_batch_size > 1:
                        current_batch_size = max(1, current_batch_size // 2)
                        console.print(f"\n[yellow]OOM encountered, reducing batch size to {current_batch_size}[/yellow]")
                    else:
                        if not truncate_next:
                            console.print(f"\n[red]OOM encountered at batch size 1! Truncating prompt...[/red]")
                            truncate_next = True
                        else:
                            console.print(f"\n[bold red]FATAL OOM even after truncation![/bold red]")
                            raise e
                else:
                    raise e
                    
        pbar.close()
        
        # Coverage assertion
        expected_ids = set(self.val_data.keys())
        actual_ids = set(predictions.keys())
        missing = expected_ids - actual_ids
        extra = actual_ids - expected_ids
        assert not missing, f"Missing predictions for IDs: {missing}"
        assert not extra, f"Extra predictions for IDs: {extra}"
        assert len(predictions) == len(expected_ids)
        end_time = time.time()
        
        # Calculate metrics
        total_meteor = 0.0
        total_rougeL = 0.0
        meteor_valid_count = 0
        meteor_failed_count = 0
        
        rep_unigram_ratio_sum = 0
        rep_bigram_ratio_sum = 0
        rep_trigram_ratio_sum = 0
        rep_bigram_count_sum = 0
        rep_trigram_count_sum = 0
        max_repeated_span_sum = 0
        answer_length_sum = 0
        
        per_sample_metrics = []
        
        # Block-level metrics
        blocks = {}
        block_size = 50
        frozen_order = list(self.val_data.keys())
        for i, q_id in enumerate(frozen_order):
            block_idx = i // block_size
            block_name = f"Block_{chr(65 + block_idx)}"
            if block_name not in blocks:
                blocks[block_name] = {"meteor": 0.0, "rougeL": 0.0, "count": 0}
            
            ans = predictions.get(q_id, "")
            ref = self.val_data[q_id]["answer"]
            
            norm_ref = preprocess_text(ref)
            norm_gen = preprocess_text(ans)
            
            m_score = 0.0
            r_score = 0.0
            
            if norm_ref and norm_gen:
                try:
                    m_score = meteor_score([nltk.word_tokenize(norm_ref)], nltk.word_tokenize(norm_gen))
                    total_meteor += m_score
                    blocks[block_name]["meteor"] += m_score
                    meteor_valid_count += 1
                except Exception as e:
                    console.print(f"[yellow]METEOR error on q_id {q_id}: {e}[/yellow]")
                    meteor_failed_count += 1
                
                try:
                    r_score = self.rouge.score(norm_ref, norm_gen)['rougeL'].fmeasure
                    total_rougeL += r_score
                    blocks[block_name]["rougeL"] += r_score
                except Exception as e:
                    console.print(f"[yellow]ROUGE error on q_id {q_id}: {e}[/yellow]")
            else:
                meteor_failed_count += 1
                
            blocks[block_name]["count"] += 1
                
            rep_stats = calculate_repetition_metrics(norm_gen)
            rep_unigram_ratio_sum += rep_stats["unique_unigram_ratio"]
            rep_bigram_ratio_sum += rep_stats["unique_bigram_ratio"]
            rep_trigram_ratio_sum += rep_stats["unique_trigram_ratio"]
            rep_bigram_count_sum += rep_stats["repeated_bigram_count"]
            rep_trigram_count_sum += rep_stats["repeated_trigram_count"]
            max_repeated_span_sum += rep_stats["max_repeated_span"]
            answer_length_sum += rep_stats["answer_length"]
            
            per_sample_metrics.append({
                "question_id": q_id,
                "meteor": m_score,
                "rougeL": r_score,
                "reference_length": len(norm_ref.split()),
                "prediction_length": rep_stats["answer_length"],
                "repetition_ratio": rep_stats["unique_bigram_ratio"]
            })

        # Finalize block metrics
        block_metrics = {}
        for b_name, b_data in blocks.items():
            cnt = b_data["count"]
            block_metrics[f"{b_name}_METEOR"] = b_data["meteor"] / cnt if cnt else 0
            block_metrics[f"{b_name}_ROUGE-L"] = b_data["rougeL"] / cnt if cnt else 0

        n_samples = len(self.val_data)
        import numpy as np
        
        metrics = {
            "experiment": self.experiment,
            "base_model": self.model_id,
            "adapter_path": self.args.sft_path,
            "total_samples": n_samples,
            "meteor_valid_count": meteor_valid_count,
            "meteor_failed_count": meteor_failed_count,
            "avg_meteor": total_meteor / n_samples if n_samples > 0 else 0,
            "avg_rougeL": total_rougeL / n_samples if n_samples > 0 else 0,
            "runtime_seconds": round(end_time - start_time, 2),
            "questions_per_second": round(n_samples / (end_time - start_time), 2) if end_time != start_time else 0,
            "tokens_per_second": round(total_tokens_generated / (end_time - start_time), 2) if end_time != start_time else 0,
            "average_input_tokens": float(np.mean(input_lengths)) if input_lengths else 0,
            "p50_input_tokens": float(np.percentile(input_lengths, 50)) if input_lengths else 0,
            "p90_input_tokens": float(np.percentile(input_lengths, 90)) if input_lengths else 0,
            "average_output_tokens": float(np.mean(output_lengths)) if output_lengths else 0,
            "p50_output_tokens": float(np.percentile(output_lengths, 50)) if output_lengths else 0,
            "p90_output_tokens": float(np.percentile(output_lengths, 90)) if output_lengths else 0,
            "peak_vram_gb": round(torch.cuda.max_memory_allocated() / (1024**3), 2) if torch.cuda.is_available() else 0,
            "ROUGE-L": total_rougeL / n_samples if n_samples else 0,
            "rep_unique_unigram": rep_unigram_ratio_sum / n_samples if n_samples else 0,
            "rep_unique_bigram": rep_bigram_ratio_sum / n_samples if n_samples else 0,
            "rep_unique_trigram": rep_trigram_ratio_sum / n_samples if n_samples else 0,
            "rep_bigram_count": rep_bigram_count_sum / n_samples if n_samples else 0,
            "rep_trigram_count": rep_trigram_count_sum / n_samples if n_samples else 0,
            "max_repeated_span": max_repeated_span_sum / n_samples if n_samples else 0,
            "avg_answer_length": answer_length_sum / n_samples if n_samples else 0,
            "runtime_seconds": runtime,
            "questions_per_second": n_samples / runtime if runtime else 0,
            "tokens_per_second": total_tokens_generated / runtime if runtime else 0,
            "peak_vram_gb": peak_vram
        }
        metrics.update(block_metrics)
        
        # Also store prompt hashes to verify identical inputs
        prompt_hashes = {}
        for q_id, full_prompt in prompts:
            prompt_hashes[q_id] = hashlib.sha256(full_prompt.encode("utf-8")).hexdigest()
        
        out_json = f"benchmark_results/{self.experiment}_limit{self.limit}.json"
        with open(out_json, "w", encoding="utf-8") as f:
            json.dump(metrics, f, indent=4)
            
        hash_json = f"benchmark_results/{self.experiment}_limit{self.limit}_hashes.json"
        with open(hash_json, "w", encoding="utf-8") as f:
            json.dump(prompt_hashes, f, indent=4)
            
        # Write predictions for inspection
        pred_json = f"benchmark_results/{self.experiment}_limit{self.limit}_predictions.json"
        with open(pred_json, "w", encoding="utf-8") as f:
            json.dump(predictions, f, ensure_ascii=False, indent=4)
            
        # Write per-sample metrics
        per_sample_json = f"benchmark_results/{self.experiment}_limit{self.limit}_persample.json"
        with open(per_sample_json, "w", encoding="utf-8") as f:
            json.dump(per_sample_metrics, f, ensure_ascii=False, indent=4)
            
        console.print(f"[bold green]Saved metrics to {out_json}, predictions to {pred_json}, per-sample to {per_sample_json}[/bold green]")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--experiment", type=str, required=True, help="Experiment name (e.g. E00_FUNCTIONAL)")
    parser.add_argument("--limit", type=int, default=20, help="Number of validation samples")
    parser.add_argument("--batch_size", type=int, default=8, help="Batch size")
    parser.add_argument("--do_sample", action="store_true", help="Enable sampling")
    parser.add_argument("--temperature", type=float, default=0.1)
    parser.add_argument("--top_p", type=float, default=0.9)
    parser.add_argument("--top_k_retrieval", type=int, default=3, help="Top K context retrieval")
    parser.add_argument("--max_new_tokens", type=int, default=512)
    parser.add_argument("--repetition_penalty", type=float, default=1.05)
    parser.add_argument("--length_bucketing", action="store_true", help="Sort prompts by length to minimize padding")
    parser.add_argument("--sft_path", type=str, default=None, help="Path to LoRA weights for E01")
    parser.add_argument("--force_retrieval", action="store_true", help="Ignore cache and retrieve again")
    parser.add_argument("--validation_ids", type=str, default=None, help="Path to json specifying explicit validation IDs")
    
    args = parser.parse_args()
    
    bench = BenchmarkLegalQA(args)
    bench.run_retrieval()
    bench.run_generation()
