# Contributing to TrustAgent

Welcome to the TrustAgent repository! This document outlines the development workflow, repository structure, and safety expectations for contributors.

## 1. Repository Structure

TrustAgent is structured to separate concerns between production systems, experimental algorithms, and documentation:

- **`Backend/`**: Core API, FastAPI server, LangGraph agents, and the Z3 forensics engine.
- **`Frontend/`**: Next.js user interface.
- **`pipelines/`**: Reusable engineering logic for Retrieval, Reranking, Evaluation, and Training. (Experimental code should go here).
- **`docs/`**: Comprehensive project documentation.
- **`configs/`**: Configuration templates.

## 2. Development Workflow

- **Where to put new scripts**:
  - Production agent code goes into `Backend/agents/`.
  - Standalone evaluation, dense retrieval, or ranking scripts belong in `pipelines/`.
- **Where to put documentation**:
  - All detailed design, architecture, and historical docs belong in `docs/`.
  - Root should only contain high-level entry points (`README.md`, `ARCHITECTURE.md`).

## 3. Data Safety Expectations

TrustAgent operates in highly sensitive environments and has strict rules regarding what can be committed:

- **DO NOT commit generated artifacts:** Do not commit `*.pkl`, `*.bin`, `*.safetensors`, temporary `.json` prediction dumps, or massive log files.
- **DO NOT commit external datasets:** Any organizer datasets from external competitions (e.g., UIT DSC) must **never** be committed or reconstructed in this repository.
- **DO NOT commit secrets:** Never commit `.env` files or API keys. Always use `.env.example`.
- **DO NOT commit model weights:** Only configurations should be committed unless model artifacts are explicitly small and intended.

Thank you for helping keep TrustAgent clean, modular, and secure!
