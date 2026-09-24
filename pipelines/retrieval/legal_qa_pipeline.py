import os

# CẤU HÌNH THƯ MỤC CACHE HUGGINGFACE ĐỂ CỨU Ổ C CỦA BẠN
os.environ["HF_HOME"] = "E:/data-hf_cache"

import json
import zipfile
import argparse
import time
import string
from pathlib import Path
from typing import List, Dict, Any
import traceback

import torch
from transformers import AutoModelForCausalLM, AutoTokenizer, pipeline
import chromadb
from sentence_transformers import SentenceTransformer, util

import nltk
from nltk.translate.meteor_score import meteor_score
from rouge_score import rouge_scorer
from rich.console import Console
from rich.table import Table

console = Console()

def preprocess_text(text: str) -> str:
    """Chuẩn hóa văn bản Tiếng Việt: lowercase, bỏ dấu câu, strip."""
    if not text:
        return ""
    # Chuyển về chữ thường
    text = text.lower()
    # Loại bỏ dấu câu
    translator = str.maketrans('', '', string.punctuation)
    text = text.translate(translator)
    # Xóa khoảng trắng thừa
    text = " ".join(text.split())
    return text

class LegalQAPipeline:
    def __init__(
        self,
        db_dir: str,
        warmup_file: str,
        model_name: str = "BAAI/bge-m3",
        llm_model: str = "Qwen/Qwen2.5-1.5B-Instruct"
    ):
        self.db_dir = Path(db_dir)
        self.warmup_file = Path(warmup_file)
        self.llm_model = llm_model
        
        # 1. Khởi tạo LLM Local (HuggingFace) < 4 Tỷ Tham số
        console.print(f"[bold blue][Info][/bold blue] Đang tải LLM Model {self.llm_model} (Local, Offline)...")
        console.print("[yellow]Quá trình này có thể mất vài phút nếu chưa tải weights...[/yellow]")
        
        try:
            from transformers import AutoTokenizer, AutoModelForCausalLM, pipeline
            import torch
            from transformers import BitsAndBytesConfig
            
            self.tokenizer = AutoTokenizer.from_pretrained(self.llm_model, trust_remote_code=True)
            
            bnb_config = BitsAndBytesConfig(
                load_in_4bit=True,
                bnb_4bit_compute_dtype=torch.float16
            )
            
            console.print(f"[bold blue][Info][/bold blue] Đang tải LLM Base Model (4-bit)...")
            self.model = AutoModelForCausalLM.from_pretrained(
                self.llm_model,
                device_map="auto",
                quantization_config=bnb_config,
                low_cpu_mem_usage=True,
                trust_remote_code=True
            )
            
            self.device = "cuda" if torch.cuda.is_available() else "cpu"
            console.print(f"[bold green]Thiết bị sử dụng cho LLM:[/bold green] {self.device}")

            self.text_generator = pipeline(
                "text-generation", 
                model=self.model, 
                tokenizer=self.tokenizer
            )
        except Exception as e:
            console.print(f"[bold red]Lỗi khi tải LLM:[/bold red] {e}")
            raise
        
        # 2. Khởi tạo ChromaDB Client (từ Task 1)
        console.print(f"[bold blue][Info][/bold blue] Kết nối ChromaDB tại {self.db_dir}...")
        self.chroma_client = chromadb.PersistentClient(path=str(self.db_dir))
        self.collection = self.chroma_client.get_or_create_collection(
            name="legal_ir",
            metadata={"hnsw:space": "cosine"}
        )
        
        # 3. Khởi tạo Embedding Model
        console.print(f"[bold blue][Info][/bold blue] Đang tải model embedding {model_name}...")
        self.embed_model = SentenceTransformer(model_name)
        
        # 4. Tải NLTK Data
        console.print("[bold blue][Info][/bold blue] Đang kiểm tra và tải các gói NLTK (wordnet, omw-1.4, punkt)...")
        try:
            nltk.download('wordnet', quiet=True)
            nltk.download('omw-1.4', quiet=True)
            nltk.download('punkt', quiet=True)
            nltk.download('punkt_tab', quiet=True)
        except Exception as e:
            console.print(f"[yellow]Cảnh báo khi tải NLTK:[/yellow] {e}")

        # Khởi tạo ROUGE scorer
        self.rouge = rouge_scorer.RougeScorer(['rougeL'], use_stemmer=False)

        # 5. Load Train Data for Dynamic Few-Shot
        train_file_path = Path("D:/TrustAgent/Data Science Challenge 2026 (Task 2)/train.json")
        console.print(f"[bold blue][Info][/bold blue] Đang tải train data để làm Dynamic Few-Shot ({train_file_path})...")
        try:
            with open(train_file_path, "r", encoding="utf-8") as f:
                self.train_data = json.load(f)
            
            # Extract questions and answers
            self.train_questions = []
            self.train_answers = []
            for k, v in self.train_data.items():
                if "question" in v and "answer" in v:
                    self.train_questions.append(v["question"])
                    self.train_answers.append(v["answer"])
            
            console.print(f"[bold blue][Info][/bold blue] Đang encode {len(self.train_questions)} câu hỏi train...")
            # Encode into tensor (on GPU if available)
            self.train_q_embeddings = self.embed_model.encode(self.train_questions, convert_to_tensor=True, show_progress_bar=True)
            console.print("[bold green][Xong][/bold green] Khởi tạo Dynamic Few-Shot index thành công.")
        except Exception as e:
            console.print(f"[bold red]Lỗi khi khởi tạo Dynamic Few-Shot:[/bold red] {e}")
            self.train_q_embeddings = None

    def retrieve_context(self, query: str, top_k: int = 3) -> str:
        """Truy vấn câu hỏi vào ChromaDB lấy top_k chunks và gộp thành 1 chuỗi string."""
        query_embedding = self.embed_model.encode([query], show_progress_bar=False).tolist()[0]
        
        results = self.collection.query(
            query_embeddings=[query_embedding],
            n_results=top_k
        )
        
        if not results['documents'] or not results['documents'][0]:
            return ""
            
        # Gộp các chunks trả về
        retrieved_chunks = results['documents'][0]
        context = "\n\n".join(retrieved_chunks)
        return context

    def generate_answer(self, query: str, context: str) -> str:
        """Gọi Local LLM để sinh câu trả lời với Dynamic Few-Shot."""
        # --- DYNAMIC FEW-SHOT RETRIEVAL ---
        few_shot_prompt = ""
        if hasattr(self, 'train_q_embeddings') and self.train_q_embeddings is not None:
            # Encode query
            query_emb = self.embed_model.encode(query, convert_to_tensor=True)
            # Tính cosine similarity
            cos_scores = util.cos_sim(query_emb, self.train_q_embeddings)[0]
            # Lọc bỏ các ví dụ quá giống (leakage)
            valid_mask = cos_scores < 0.9
            cos_scores[~valid_mask] = -1.0 # Loại bỏ
            # Lấy top 2
            top_results = torch.topk(cos_scores, k=2)
            
            few_shot_prompt = (
                "\n### VÍ DỤ THAM KHẢO VỀ CÁCH TRÌNH BÀY (HÃY HỌC THEO CÁCH HÀNH VĂN NÀY):\n"
                "LƯU Ý: Các ví dụ dưới đây CHỈ để tham khảo cách trình bày (format), "
                "KHÔNG được lấy nội dung/sự kiện pháp lý trong ví dụ để trả lời câu hỏi hiện tại. "
                "Nội dung câu trả lời phải lấy hoàn toàn từ 'Ngữ cảnh pháp lý thực tế' bên dưới.\n\n"
            )
            for i, idx in enumerate(top_results[1]):
                idx = int(idx)
                ex_q = self.train_questions[idx]
                ex_a = self.train_answers[idx]
                few_shot_prompt += f"Ví dụ {i+1}:\n- Câu hỏi: {ex_q}\n- Trả lời (Mẫu định dạng chuẩn):\n{ex_a}\n\n"

        # --- CONSTRUCT PROMPT ---
        sys_msg = (
            "Bạn là một trợ lý pháp lý chuyên nghiệp. Dựa vào NGỮ CẢNH PHÁP LÝ dưới đây, hãy trả lời câu hỏi của người dùng.\n\n"
            "YÊU CẦU QUAN TRỌNG:\n"
            "1. TRÍCH DẪN GẦN NGUYÊN VĂN: Hãy bám sát câu chữ trong ngữ cảnh, trích dẫn các khoản/điều một cách chính xác. Tuyệt đối hạn chế diễn giải lại bằng cách nói khác (abstractive).\n"
            "2. SAO CHÉP ĐỊNH DẠNG: Bạn bắt buộc phải trình bày câu trả lời của mình theo ĐÚNG CẤU TRÚC VÀ VĂN PHONG (văn xuôi, gạch đầu dòng, số thứ tự, v.v...) giống y hệt như các ví dụ tham khảo dưới đây. Nếu ví dụ dùng gạch đầu dòng, bạn phải dùng gạch đầu dòng. Nếu ví dụ viết liền, bạn phải viết liền. Độ dài câu trả lời của bạn cũng nên tương đương với cách trả lời trong ví dụ."
        )
        
        user_content = f"{few_shot_prompt}### Ngữ cảnh pháp lý thực tế:\n{context}\n\n### Câu hỏi của người dùng:\n{query}\n\n### Trả lời (Đảm bảo đúng định dạng như ví dụ):"
        
        messages = [
            {"role": "system", "content": sys_msg},
            {"role": "user", "content": user_content}
        ]
        
        prompt = self.tokenizer.apply_chat_template(
            messages, 
            tokenize=False, 
            add_generation_prompt=True
        )
        
        try:
            outputs = self.text_generator(
                prompt,
                max_new_tokens=600,
                temperature=0.1,  # Nhiệt độ thấp để tránh ảo giác pháp lý
                do_sample=False,
                top_p=0.9,
                repetition_penalty=1.05,
                pad_token_id=self.tokenizer.eos_token_id
            )
            
            # Trích xuất phần text được sinh ra (bỏ qua phần prompt)
            generated_text = outputs[0]["generated_text"]
            # Tách lấy phần câu trả lời cuối cùng sau token sinh
            if "<|im_start|>assistant\n" in generated_text:
                answer = generated_text.split("<|im_start|>assistant\n")[-1].strip()
            else:
                # Fallback nếu prompt format khác
                answer = generated_text[len(prompt):].strip()
                
            return answer
            
        except Exception as e:
            console.print(f"[bold red]Lỗi khi sinh câu trả lời nội bộ:[/bold red] {e}")
            return "Lỗi sinh câu trả lời từ mô hình cục bộ."
        finally:
            if torch.cuda.is_available():
                torch.cuda.empty_cache()

    def evaluate_and_submit(self, output_json: str = "submission.json", output_zip: str = "submission.zip", use_mock_context: bool = False):
        console.print("\n[bold yellow][Bắt đầu LegalQA Pipeline (Local LLM)][/bold yellow]")
        if not self.warmup_file.exists():
            console.print(f"[bold red]Lỗi:[/bold red] Không tìm thấy tập {self.warmup_file}.")
            return
            
        with open(self.warmup_file, "r", encoding="utf-8") as f:
            warmup_data = json.load(f)
            
        submission_dict = {}
        
        total_meteor = 0.0
        total_rougeL = 0.0
        count = 0
        
        # Bảng hiển thị kết quả trực tiếp
        table = Table(title="Tiến trình LegalQA (Task 2)", show_lines=True)
        table.add_column("Question ID", justify="center", style="cyan")
        table.add_column("Generated Answer (Truncated)", style="white")
        table.add_column("METEOR", justify="right", style="green")
        table.add_column("ROUGE-L", justify="right", style="magenta")
        
        for q_id, q_data in warmup_data.items():
            question = q_data.get("question", "")
            reference_answer = q_data.get("answer", "")
            
            # 1. Retrieval hoặc Mock Context
            if use_mock_context:
                context = reference_answer
            else:
                context = self.retrieve_context(question, top_k=3)
            
            # 2. Generation
            if use_mock_context:
                generated_answer = reference_answer
            else:
                generated_answer = self.generate_answer(question, context)
            
            # 3. Save for submission
            submission_dict[q_id] = {
                "answer": generated_answer
            }
            
            # 4. Evaluation
            norm_ref = preprocess_text(reference_answer)
            norm_gen = preprocess_text(generated_answer)
            
            meteor = 0.0
            rouge_l = 0.0
            if norm_ref and norm_gen:
                ref_tokens = nltk.word_tokenize(norm_ref)
                gen_tokens = nltk.word_tokenize(norm_gen)
                try:
                    meteor = meteor_score([ref_tokens], gen_tokens)
                except:
                    pass
                rouge_scores = self.rouge.score(norm_ref, norm_gen)
                rouge_l = rouge_scores['rougeL'].fmeasure
                
            total_meteor += meteor
            total_rougeL += rouge_l
            count += 1
            
            trunc_ans = generated_answer[:60] + "..." if len(generated_answer) > 60 else generated_answer
            table.add_row(
                str(q_id),
                trunc_ans,
                f"{meteor:.4f}",
                f"{rouge_l:.4f}"
            )

        console.print(table)
        
        # Điểm trung bình
        avg_meteor = total_meteor / count if count > 0 else 0
        avg_rougeL = total_rougeL / count if count > 0 else 0
        
        summary_table = Table(title="🏆 LegalQA Evaluation Summary (Local LLM) 🏆")
        summary_table.add_column("Metric", style="cyan")
        summary_table.add_column("Average Score", style="magenta")
        summary_table.add_row("METEOR (Primary)", f"{avg_meteor:.4f}")
        summary_table.add_row("ROUGE-L (Secondary)", f"{avg_rougeL:.4f}")
        console.print(summary_table)
        
        # 5. Ghi file Submission
        try:
            with open(output_json, "w", encoding="utf-8") as f:
                json.dump(submission_dict, f, ensure_ascii=False, indent=4)
            console.print(f"\nĐã xuất kết quả ra file: [bold]{output_json}[/bold]")
            
            # Nén ZIP chuẩn CodaLab
            with zipfile.ZipFile(output_zip, 'w', zipfile.ZIP_DEFLATED) as zipf:
                zipf.write(output_json, arcname="submission.json")
            console.print(f"Đã đóng gói thành công file: [bold green]{output_zip}[/bold green]")
            
        except Exception as e:
            console.print(f"[bold red]Lỗi khi ghi file submission: {e}[/bold red]")
            traceback.print_exc()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="UIT-DSC 2026 - Task 2: LegalQA Pipeline (Local LLM)")
    parser.add_argument("--db_dir", type=str, default="D:/TrustAgent/Data Science Challenge 2026/chroma_db_legal_ir", help="Directory of ChromaDB from Task 1")
    parser.add_argument("--warmup_file", type=str, default="D:/TrustAgent/Data Science Challenge 2026 (Task 2)/warmup.json", help="Path to warmup JSON file for Task 2")
    parser.add_argument("--model_name", type=str, default="BAAI/bge-m3", help="Embedding model name")
    parser.add_argument("--llm_model", type=str, default="Qwen/Qwen2.5-3B-Instruct", help="Local LLM model name (<4B Params)")
    
    parser.add_argument("--use_mock_context", action="store_true", help="Use reference answer as mock context to test generation speed")
    parser.add_argument("--output_json", type=str, default="D:/TrustAgent/Data Science Challenge 2026 (Task 2)/submission.json", help="Path to output JSON")
    parser.add_argument("--output_zip", type=str, default="D:/TrustAgent/Data Science Challenge 2026 (Task 2)/submission.zip", help="Path to output ZIP")
    
    args = parser.parse_args()
    
    try:
        pipeline = LegalQAPipeline(
            db_dir=args.db_dir,
            warmup_file=args.warmup_file,
            model_name=args.model_name,
            llm_model=args.llm_model
        )
        
        # Chạy query & đánh giá & xuất submission
        pipeline.evaluate_and_submit(
            output_json=args.output_json, 
            output_zip=args.output_zip, 
            use_mock_context=args.use_mock_context
        )
    except Exception as e:
        console.print(f"[bold red]Pipeline failed:[/bold red] {e}")
        traceback.print_exc()
