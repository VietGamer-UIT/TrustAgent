"""
TrustAgent — Legal RAG Retriever

Ưu tiên keyword search trên file markdown (ổn định).
Chroma/HuggingFace chỉ dùng khi sẵn sàng — không làm crash API.
"""

from __future__ import annotations

import os
import re
from typing import List

from loguru import logger

RAG_DATA_DIR = os.path.join(os.path.dirname(__file__), "legal_data")
EXTRA_LEGAL_DIR = os.path.join(
    os.path.dirname(__file__), "..", "data_pipeline", "legal_docs"
)
CHROMA_DB_DIR = os.path.join(os.path.dirname(__file__), "chroma_db")


def _load_markdown_corpus() -> list[tuple[str, str]]:
    """[(filename, content), ...]"""
    docs: list[tuple[str, str]] = []
    for folder in (RAG_DATA_DIR, EXTRA_LEGAL_DIR):
        if not os.path.isdir(folder):
            continue
        for name in sorted(os.listdir(folder)):
            if not name.lower().endswith(".md"):
                continue
            path = os.path.join(folder, name)
            try:
                with open(path, "r", encoding="utf-8", errors="ignore") as f:
                    docs.append((name, f.read()))
            except OSError as e:
                logger.warning(f"Không đọc được {path}: {e}")
    return docs


def _keyword_retrieve(query: str, k: int = 4) -> str:
    """Tìm đoạn liên quan bằng điểm từ khóa (luôn hoạt động)."""
    corpus = _load_markdown_corpus()
    if not corpus:
        return (
            "Chưa có tài liệu pháp lý trong kho. "
            "Thêm file .md vào Backend/rag/legal_data/."
        )

    tokens = [
        t for t in re.findall(r"[\wÀ-ỹ]{2,}", query.lower())
        if t not in {"và", "của", "cho", "với", "các", "một", "này", "khi", "là", "được", "trong"}
    ]
    if not tokens:
        tokens = [query.lower().strip()]

    scored: list[tuple[float, str, str]] = []
    for fname, content in corpus:
        lower = content.lower()
        score = sum(lower.count(t) for t in tokens)
        # boost filename matches
        score += sum(3 for t in tokens if t in fname.lower())
        if score <= 0:
            continue
        # Lấy đoạn chứa từ khóa đầu tiên
        snippet = content
        for t in tokens:
            idx = lower.find(t)
            if idx >= 0:
                start = max(0, idx - 200)
                end = min(len(content), idx + 900)
                snippet = content[start:end].strip()
                break
        scored.append((score, fname, snippet))

    scored.sort(key=lambda x: x[0], reverse=True)
    top = scored[:k] if scored else [
        (0, corpus[0][0], corpus[0][1][:1200])
    ]

    parts = []
    for score, fname, snippet in top:
        parts.append(f"### Nguồn: {fname}\n{snippet}")
    return "\n\n---\n\n".join(parts)


class LegalRetriever:
    def __init__(self) -> None:
        self.vector_store = None
        self._chroma_ready = False
        # Mặc định keyword RAG (ổn định). Bật Chroma bằng TRUSTAGENT_USE_CHROMA=1
        if os.getenv("TRUSTAGENT_USE_CHROMA", "").strip() in ("1", "true", "yes"):
            try:
                self._try_init_chroma()
            except Exception as e:
                logger.warning(f"Chroma/HF không khả dụng, dùng keyword RAG: {e}")
        else:
            logger.info("Legal RAG: chế độ keyword (ổn định).")

    def _try_init_chroma(self) -> None:
        if not (os.path.exists(CHROMA_DB_DIR) and os.listdir(CHROMA_DB_DIR)):
            return
        from langchain_community.vectorstores import Chroma
        from langchain_huggingface import HuggingFaceEmbeddings

        embeddings = HuggingFaceEmbeddings(model_name="keepitreal/vietnamese-sbert")
        self.vector_store = Chroma(
            persist_directory=CHROMA_DB_DIR,
            embedding_function=embeddings,
        )
        self._chroma_ready = True
        logger.info("Legal RAG: đã nạp ChromaDB.")

    def retrieve(self, query: str, k: int = 3) -> str:
        # Tầng 1: Lấy kết quả từ các file .md cục bộ (luật mới nhất)
        local_results = _keyword_retrieve(query, k=k)
        
        # Tầng 2: Lấy thêm kết quả từ ChromaDB (Pháp điển) nếu có
        chroma_results = ""
        if self._chroma_ready and self.vector_store is not None:
            try:
                results = self.vector_store.similarity_search(query, k=k)
                if results:
                    chroma_parts = []
                    for doc in results:
                        source = doc.metadata.get("source", "ChromaDB")
                        ten_dieu = doc.metadata.get("ten_dieu", "")
                        chroma_parts.append(f"### Nguồn: {source} ({ten_dieu})\n{doc.page_content}")
                    chroma_results = "\n\n---\n\n".join(chroma_parts)
            except Exception as e:
                logger.warning(f"Chroma search lỗi: {e}")
                
        # Gộp chung kết quả, ưu tiên luật mới (cục bộ) lên trên
        if chroma_results:
            return f"{local_results}\n\n---\n\n{chroma_results}"
        return local_results


# Lazy singleton — tránh load nặng lúc import module
_retriever: LegalRetriever | None = None


def get_retriever() -> LegalRetriever:
    global _retriever
    if _retriever is None:
        _retriever = LegalRetriever()
    return _retriever


def get_legal_context(query: str) -> str:
    return get_retriever().retrieve(query)
