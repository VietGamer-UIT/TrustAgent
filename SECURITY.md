# TrustAgent Security Guide

This document outlines the security policies for the TrustAgent repository, ensuring that sensitive data, credentials, and external datasets are handled safely.

## 1. Secrets Management

- **`.env` files:** The local `.env` file containing secrets (e.g., `GOOGLE_API_KEY`, database credentials) is strictly ignored by Git. Under no circumstances should secrets be printed to the console in production or committed to the repository.
- **`.env.example`:** Only safe placeholders should be committed. If a new environment variable is required, document it in `.env.example` without its actual value.
- **API Keys & Local Credentials:** Ensure that any scripts hitting third-party services load their keys from environment variables. Do not hard-code keys in Python or TypeScript files.

## 2. Data Separation and Protection

- **Production Database:** The production ChromaDB (`Backend/rag/chroma_db`) is the core knowledge base of TrustAgent. It should be backed up regularly but is excluded from version control to prevent data bloat and unintentional leakage of proprietary data.
- **External Datasets:** TrustAgent acts as an engine. External datasets (such as those from UIT DSC) are strictly classified as disposable input and are forbidden from being tracked in this repository.
- **Contest Artifact Exclusions:** To comply with competition rules, all historical contest artifacts (including datasets, embeddings, predictions, submissions, and caches) are explicitly banned from this repository.

## 3. Generated Artifact Handling

Temporary files generated during ML inference, retrieval, or model training (`.pkl`, `.json` dumps, `.csv` reports, `.safetensors` model weights) can quickly pollute the repository and pose data-leak risks. These files must remain confined to local scratch folders and are blocked from commits via `.gitignore`.
