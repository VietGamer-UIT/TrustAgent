# Legal RAG Layer

The Legal RAG (Retrieval-Augmented Generation) layer provides grounding for TrustAgent's LLM agents.

## Architecture
- Retrieves exact legal clauses, policies, and internal rules from `Backend/rag/chroma_db`.
- Operates on a structured vector database.
- Provides citations that agents can pass into the Z3 Theorem Prover or directly output to the user.

## Data Segregation
- The production ChromaDB is entirely distinct from external/experimental datasets.
- Context window engineering ensures that retrieved clauses fit effectively into generation prompts without overflow.
