# Evaluation Methodology

Evaluation in TrustAgent ensures robust retrieval and generation performance without dataset leakage.

## Validation Methodology & Leakage Prevention
- Validation splits are strictly isolated using frozen document IDs (`freeze_validation_ids.py`).
- Any overlap between training passages and validation queries is aggressively masked (`verify_sft_masking.py`, `verify_sft_leakage.py`) to prevent artificial metric inflation.

## Metrics
- **Recall@K:** Measures the proportion of relevant documents found in the top-K results. Used primarily to evaluate the candidate generation stage.
- **Precision@K:** Evaluates the density of relevant documents in the top-K.
- **NDCG@K:** Normalized Discounted Cumulative Gain penalizes correct documents that appear lower in the ranking.

## Oracle & Coverage
- **Candidate Coverage:** The percentage of queries where the true positive document exists *anywhere* in the candidate pool.
- **Oracle Ceiling:** The theoretical maximum NDCG@10 if the reranker were perfect (always selecting the true positive if it exists in the coverage pool).

## Audit Methodology
- Code changes require baseline comparisons (`run_baselines.bat`).
- Metric discrepancies are traced using schema validation and independent double checks.
