# TrustAgent API Documentation

The TrustAgent backend exposes endpoints for interacting with the neuro-symbolic engine.

## Core Endpoints
- `POST /api/audit`: Submits a document (e.g., invoice, contract) for auditing against Z3 logic rules.
- `POST /api/query`: Submits a free-form query that the Agent Swarm processes via Legal RAG.

## Data Structures
- All requests and responses use strict JSON schemas validated via Pydantic on the FastAPI backend.

*(Note: API is subject to change based on ongoing development.)*
