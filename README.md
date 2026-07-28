# TrustAgent

Nền tảng kiểm toán Neuro-Symbolic: kết hợp **LLM** và **Z3 Theorem Prover** để kiểm toán chứng từ và kiểm chứng pháp lý tại Việt Nam.

**Tác giả:** Đoàn Hoàng Việt (Việt Gamer)

---

## Kiến trúc

```plaintext
TrustAgent/
├── Frontend/          # Next.js — Workspace, Forensics, Audit Trail, Legal
├── Backend/           # FastAPI + LangGraph
│   ├── core/          # Pipeline kiểm toán chứng từ
│   ├── agents/        # Document / Tax / Legal agents
│   ├── forensics/     # Module Forensics (Z3 legal gatekeeper)
│   ├── z3_engine/     # Z3 cho luồng hợp đồng / hóa đơn
│   ├── rag/           # Legal RAG
│   └── data_pipeline/ # Data collection & caching
└── docker-compose.yml
```

### API (`:8000`)

| Tính năng | Endpoint |
|-----------|----------|
| Kiểm tra chứng từ | `POST /api/v1/kiem-tra/upload` |
| Tra cứu luật | `POST /api/v1/tra-cuu-luat` |
| Forensics Verify | `POST /api/v1/forensics/verify` |
| Forensics Audit | `GET /api/v1/forensics/audit` |

UI: `/` · `/forensics` · `/audit-trail` · `/investigate` · `/legal-knowledge`

---

## Chạy nhanh

```bash
docker compose up --build

# hoặc local
cd Backend && pip install -r requirements.txt
uvicorn main:app --reload --port 8000

cd Frontend && npm install && npm run dev
```

Cấu hình từ `.env.example` (`GOOGLE_API_KEY`). Thiếu key → Forensics dùng MockParser.

---

*TrustAgent — Đoàn Hoàng Việt (Việt Gamer)*
