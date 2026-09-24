# Information Retrieval (IR) Pipeline

TrustAgent's reusable IR pipeline handles complex multi-chunk document retrieval.

## Dense Retrieval & Embedding Workflow
- **Embeddings:** Documents are embedded using dual-encoder models.
- **Prefix Concept:** To improve semantic alignment, queries and passages are prepended with instructional tokens. This is model-dependent; generic implementations expect context strings. Where verified specifically (e.g., BQBBAO6 pipelines), the exact prefixes `query: ` and `passage: ` are used.

## Sparse Retrieval (BM25)
- Acts as a high-recall lexical safety net for exact-match keywords, dates, and ID strings.

## Candidate Union & Rank Fusion
- Dense and sparse retrieved candidate lists are fused. 
- A Reciprocal Rank Fusion (RRF) or normalized scoring strategy unifies scores to maximize candidate coverage.

## Multi-Chunk Document Aggregation
- Since long documents are chunked, the scores of multiple chunks belonging to the same document are aggregated.
- Strategies like `MAX` (taking the highest chunk score) or `TOP3AVG` (averaging the top 3 chunks) are used to compute the final document-level score.

## Oracle Ceiling
- The pipeline measures the "oracle ceiling" — the theoretical maximum performance if the reranker correctly places the true positive from the retrieved candidate list at rank 1.
