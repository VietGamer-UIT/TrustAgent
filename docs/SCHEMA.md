# TrustAgent Schema Reference

This document defines the core data schemas and interfaces used by the TrustAgent platform.

## 1. Request / Response Schema

### `AuditRequest`
Payload sent to `/api/audit`:
```json
{
  "document_text": "Clause 1. The company shall pay taxes by the 15th of the month...",
  "domain": "tax_compliance",
  "strict_mode": true
}
```

### `AuditResponse`
Returned by the API:
```json
{
  "status": "success",
  "audit_id": "aud_123abc",
  "is_compliant": false,
  "violations": [
    {
      "clause": "Tax payment deadline",
      "expected": "15th of the month",
      "found": "20th of the month"
    }
  ],
  "reasoning_trace": [
    "Parsed clause into constraint: deadline <= 15",
    "Evaluated constraint with Z3: 20 <= 15 -> FALSE"
  ]
}
```

## 2. Document & Chunk Metadata

Stored in ChromaDB for Retrieval Augmented Generation (RAG):
```json
{
  "id": "doc_987",
  "text": "Vietnamese Tax Management Law article 42...",
  "metadata": {
    "source_id": "law_2024",
    "chunk_index": 4,
    "effective_date": "2024-01-01",
    "domain": "tax"
  }
}
```

## 3. Agent Input / Output Structure

### LangGraph Agent State
```json
{
  "query": "Is a tax payment on the 20th valid?",
  "retrieved_context": ["Article 42 states the deadline is the 15th."],
  "current_step": "verification",
  "extracted_constraints": [
    "deadline_day <= 15"
  ],
  "verification_result": null
}
```

## 4. Forensic Verification (Z3 Solver) Result

Output of the internal Z3 Theorem Prover module:
```json
{
  "is_satisfiable": false,
  "model_counterexample": "deadline_day = 20",
  "proof_time_ms": 12,
  "rules_applied": ["vn_tax_mgmt_rule_v2"]
}
```