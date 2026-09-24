# Testing Guidelines

TrustAgent enforces strict testing standards to ensure logical stability and data safety.

## Unit Testing
- Located in `tests/`.
- Validates the Z3 forensics engine constraints mathematically.
- Tests RAG chunk retrieval logic using lightweight, generic fixtures (no external organizer datasets are used in tests).

## Pipeline Benchmarks
- Reusable benchmarking scripts (`pipelines/evaluation/`) are used to test dense retrieval and BM25 implementations locally.
- Do not run benchmarks against protected production data (`chroma_db`). Use isolated test fixtures.
