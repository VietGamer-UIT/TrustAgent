# 🛡️ TrustAgent - The Neuro-Symbolic Audit & Legal Platform

![TrustAgent Banner](https://via.placeholder.com/1200x400/000000/FFFFFF/?text=TrustAgent+Enterprise)

**TrustAgent** là siêu nền tảng B2B SaaS đột phá, tiên phong kết hợp **LLM (Generative AI)** và **Z3 Theorem Prover (Symbolic AI)** để giải quyết dứt điểm các rủi ro pháp lý và sai phạm kế toán tại Việt Nam.

> **Tự hào tham dự: Data Science Challenge 2026** 🏆

---

## 🌟 Tại sao là TrustAgent? (USP)

Trong kiểm toán và pháp lý, **tính chính xác là sinh mệnh**. Các mô hình AI tạo sinh (như ChatGPT) thường xuyên bị ảo giác (Hallucination) dẫn đến rủi ro chết người trong kinh doanh. 

TrustAgent giải quyết vấn đề này bằng kiến trúc **Neuro-Symbolic AI**:
1. 🧠 **Neuro (LLM/RAG)**: Đọc hiểu hóa đơn, hợp đồng tự nhiên bằng tiếng Việt. Bóc tách dữ liệu từ file XML/PDF linh hoạt.
2. ⚙️ **Symbolic (Z3 Engine)**: Đưa các quy định pháp luật (Nghị định 123, Luật Doanh Nghiệp) vào các phương trình toán học chặt chẽ. Hệ thống Z3 sẽ chứng minh tính hợp lệ (SAT) hoặc bắt lỗi tuyệt đối (UNSAT). **Không thể sai sót!**

## 🏗️ Kiến trúc Hệ thống (Architecture)

Hệ thống được quy hoạch theo chuẩn Enterprise với kiến trúc Multi-Agent do **LangGraph** điều phối.

```plaintext
📂 TrustAgent
┃
┣ 📂 Frontend                # Next.js 14, TailwindCSS, Shadcn UI
┃
┣ 📂 Backend                 # FastAPI, LangGraph Multi-Agent, Z3 Prover
┃ ┣ 📂 core                  # LangGraph Supervisor & Unified State
┃ ┣ 📂 data_pipeline         # Xử lý Hóa đơn XML, Cào VBPL (Zero Mock Data)
┃ ┣ 📂 z3_engine             # Lõi Toán học kiểm chứng pháp lý
┃ ┣ 📂 agents                # Các Agent thi hành nhiệm vụ (Tax, Legal)
┃ ┗ 📂 mcp_servers           # Model Context Protocol Servers
┃
┣ 📂 Database_Migration      # Script SQL cho PostgreSQL/Supabase
┃
┗ 📂 Docker                  # Dockerfile & Compose triển khai thần tốc
```

## 🚀 Tính năng cốt lõi

- **Nhận diện và Xử lý Hóa đơn điện tử**: Đọc trực tiếp định dạng XML chuẩn Tổng Cục Thuế. Kiểm tra đối soát số liệu chuẩn xác đến từng đồng.
- **Truy vết Pháp lý (Legal RAG)**: Nối thẳng vào Cổng thông tin Quốc gia (vbpl.vn) lấy dữ liệu thật 100%. Rà soát điều khoản vi phạm bằng AI.
- **Báo cáo Audit Trail Toàn diện**: Xuất báo cáo rủi ro tài chính và pháp lý chi tiết dành cho CFO và Ban Giám Đốc.

## 🛠️ Công nghệ sử dụng (Tech Stack)
- **Backend:** Python 3.12+, FastAPI, LangGraph, Pydantic V2, Z3-Solver, Loguru
- **Frontend:** Next.js (App Router), React, TailwindCSS, Shadcn UI
- **Database:** PostgreSQL / Supabase
- **DevOps:** Docker, Docker Compose

---
*Developed with Passion for the Data Science Challenge 2026.* 💡
