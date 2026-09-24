# TrustAgent

**TrustAgent** is a Neuro-Symbolic platform designed to combine Large Language Models (LLMs) and deterministic solvers (like the Z3 Theorem Prover) for document auditing, legal verification, and advanced decision-making pipelines.

*Author: Đoàn Hoàng Việt (Việt Gamer)*

---

## 📖 Project Overview

TrustAgent was originally built to automate and verify complex document reasoning (e.g., contracts, tax invoices) in the Vietnamese legal context. It uses a **RAG (Retrieval-Augmented Generation)** architecture integrated with autonomous agents and formal verification methods to ensure accuracy and compliance.

### Main Capabilities (CURRENT)
- **Document & Legal Auditing:** Uses specialized agents to parse and analyze documents against legal frameworks.
- **Forensics Gatekeeper:** A dedicated Z3-powered engine that formally verifies logic extracted by LLMs, ensuring constraints (like tax logic or contractual conditions) are mathematically sound.
- **Legal Retrieval (RAG):** Retrieves relevant legal clauses to ground LLM responses in actual law.

### Extended Capabilities (HISTORICAL / REUSABLE ENGINEERING)
During the UIT DSC 2026 development phase, TrustAgent was heavily extended with an advanced **LegalIR (Information Retrieval)** pipeline. While the competition-specific data and artifacts have been strictly excluded from this repository (see [Data Governance](DATA_GOVERNANCE.md)), the **reusable engineering components** have been retained. These include:
- Dense and BM25 lexical retrieval union.
- Multi-chunk document scoring aggregation.
- Cross-encoder reranking (e.g., using PEFT/LoRA).
- Candidate generation and rank fusion frameworks.
- Advanced evaluation utilities for retrieval performance.

For deep dives into these engineering milestones, see [UIT DSC 2026 Engineering](UIT_DSC_2026_ENGINEERING.md).

---

## 🏗️ Architecture

A complete conceptual breakdown is available in [ARCHITECTURE.md](ARCHITECTURE.md).

```plaintext
TrustAgent/
├── Frontend/          # Next.js — Workspace, Forensics, Audit Trail, Legal UI
├── Backend/           # FastAPI + LangGraph
│   ├── core/          # Document audit pipeline
│   ├── agents/        # Document / Tax / Legal agents
│   ├── forensics/     # Module Forensics (Z3 legal gatekeeper)
│   ├── z3_engine/     # Z3 for contract/invoice flow
│   ├── rag/           # Legal RAG (ChromaDB)
│   ├── data_pipeline/ # Data collection & caching
│   └── scripts/       # Reusable evaluation and inference utilities
└── docker-compose.yml
```

### High-Level Flow (CURRENT)
1. **User Query** → TrustAgent API
2. **Query Processing** → Analyzes intent and extracts constraints.
3. **Retrieval Layer** → Fetches relevant legal context from the production ChromaDB.
4. **Agent Analysis** → Synthesizes the retrieved data.
5. **Forensics Verification** → Z3 Theorem Prover validates the mathematical/logical claims.
6. **Decision Layer** → Final answer is returned to the user.

---

## 🚀 Local Development

### Prerequisites
- Docker & Docker Compose
- Python 3.12+
- Node.js 20+

### Quick Start (Docker)
```bash
docker compose up --build
```

### Quick Start (Local)
**Backend:**
```bash
cd Backend
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```
*Note: Configuration is loaded from `.env`. Ensure `GOOGLE_API_KEY` is set for LLM usage. If missing, the Forensics module will fallback to a MockParser.*

**Frontend:**
```bash
cd Frontend
npm install
npm run dev
```

---

## 🔐 Security & Data Separation

**Production vs. Experimental Data:**
TrustAgent strictly separates production data from experimental or historical contest artifacts. 
- The production database resides in `Backend/rag/chroma_db`. 
- **NO** third-party contest datasets (including UIT DSC 2026 test/train/public/private data) are distributed, stored, or reconstructed in this repository.

For more details on our strict data isolation and artifact policy, see [DATA_GOVERNANCE.md](DATA_GOVERNANCE.md).

---

*TrustAgent — Engineered for precision, verified by logic.*
