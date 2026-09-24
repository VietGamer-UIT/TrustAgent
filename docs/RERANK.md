# Reranking Pipeline

After initial candidate generation via IR, the reranking pipeline refines the order of top candidates.

## Cross-Encoder Concept
- Uses a cross-encoder architecture where the query and document are tokenized as a single sequence (`[CLS] Query [SEP] Document [SEP]`).
- This allows deep attention interaction between query and document tokens, vastly improving precision over dual-encoders.

## PEFT & LoRA (Experimental)
- Experimental setups use Parameter-Efficient Fine-Tuning (PEFT) with Low-Rank Adaptation (LoRA) to adapt large language models into highly accurate rerankers without full-parameter training.

## Hard-Negative Mining
- The training datasets incorporate "hard negatives" — passages that have high BM25/Dense scores but are irrelevant.
- This forces the reranker to learn subtle semantic distinctions rather than relying on keyword overlap.

## Pointwise BCE Experimentation
- Rerankers are trained using Pointwise Binary Cross-Entropy (BCE) loss to predict independent relevance scores for each query-document pair.

## Document-Level vs Chunk-Level Scoring
- Similar to retrieval, reranking handles multi-chunk documents by scoring individual chunks and aggregating those scores to derive a final document-level ranking.
