"""
TrustAgent — Legal RAG Retriever

Nhiệm vụ: Lấy đúng văn bản luật từ legal_data/ dựa trên ScenarioType.

Bộ legal_data hiện tại (5 văn bản):
  vn_data_protection  → NghiDinh_356_2025_PDPD.md   (Bảo vệ dữ liệu cá nhân)
  vn_data_law         → NghiDinh_165_2025.md         (Luật Dữ liệu)
  vn_bond             → NghiDinh_200_2026.md         (Trái phiếu doanh nghiệp)
  vn_tax_mgmt         → NghiDinh_252_2026.md         (Quản lý Thuế)
  vn_tax_register     → ThongTu_90_2026_DangKyThue.md (Đăng ký Thuế)

Chiến lược fallback 3 tầng:
  1. ChromaDB semantic search (nếu cài chromadb)
  2. Keyword-based in-memory search (luôn hoạt động)
  3. Hardcoded defaults (không bao giờ fail)
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path

logger = logging.getLogger(__name__)

# Đường dẫn tới thư mục chứa văn bản luật
_LEGAL_DATA_DIR = Path(__file__).parent / "legal_data"

# Map ScenarioType → filename trong legal_data/
_SCENARIO_TO_FILE: dict[str, str] = {
    "vn_data_protection": "NghiDinh_356_2025_PDPD.md",
    "vn_data_law":        "NghiDinh_165_2025.md",
    "vn_bond":            "NghiDinh_200_2026.md",
    "vn_tax_mgmt":        "NghiDinh_252_2026.md",
    "vn_tax_register":    "ThongTu_90_2026_DangKyThue.md",
}

# Default thresholds — fallback khi RAG fail hoàn toàn
DEFAULT_THRESHOLDS: dict[str, dict[str, int]] = {
    "vn_data_protection": {
        "CROSS_BORDER_DOSSIER_DAYS": 60,
        "NATIONAL_SECURITY_BASIC_THRESHOLD": 100_000,
        "NATIONAL_SECURITY_SENSITIVE_THRESHOLD": 10_000,
        "BREACH_NOTICE_HOURS": 72,
        "BREACH_RETENTION_YEARS": 5,
    },
    "vn_data_law": {
        "IMPORTANT_DATA_REVIEW_DAYS": 30,
    },
    "vn_bond": {
        "DISCLOSURE_DAYS_LIMIT": 3,
        "MIN_EQUITY_BILLION_VND": 30,
    },
    "vn_tax_mgmt": {
        "LATE_PAYMENT_PENALTY_RATE_PERMILLE": 3,
        "INSPECTION_STATUTE_OF_LIMITATIONS_YEARS": 5,
    },
    "vn_tax_register": {
        "REGISTRATION_DAYS_LIMIT": 10,
        "UPDATE_DEADLINE_DAYS": 10,
    },
}


class LegalRetriever:
    """
    Lấy văn bản luật phù hợp từ legal_data/ dựa trên ScenarioType.

    Chiến lược fallback 3 tầng:
    1. ChromaDB semantic search (nếu đã cài: pip install chromadb)
    2. Full-document in-memory retrieval (luôn hoạt động)
    3. Trả về chuỗi rỗng nếu không có doc

    Ví dụ:
        retriever = LegalRetriever()
        text = retriever.get_legal_text("vn_data_protection")
        # → "...không quá 60 ngày kể từ ngày tiến hành chuyển..."
    """

    def __init__(self, data_dir: Path | str | None = None) -> None:
        self._data_dir = Path(data_dir) if data_dir else _LEGAL_DATA_DIR
        self._docs: dict[str, str] = {}
        self._collection = None
        self._chromadb_available = False

        self._load_all_docs()
        self._try_init_chromadb()

    def _load_all_docs(self) -> None:
        """Load tất cả 5 văn bản luật từ legal_data/ vào memory."""
        for scenario, filename in _SCENARIO_TO_FILE.items():
            filepath = self._data_dir / filename
            if filepath.exists():
                self._docs[scenario] = filepath.read_text(encoding="utf-8")
                size_kb = len(self._docs[scenario]) // 1024
                logger.info(f"[RAG] Loaded: {filename} ({size_kb}KB) → scenario={scenario}")
            else:
                logger.warning(f"[RAG] Không tìm thấy: {filepath}")

    def _try_init_chromadb(self) -> None:
        """Thử khởi tạo ChromaDB. Nếu fail → dùng keyword search."""
        try:
            import chromadb
            client = chromadb.PersistentClient(
                path=str(self._data_dir / ".chroma_cache")
            )
            self._collection = client.get_or_create_collection(
                name="legal_documents",
                metadata={"hnsw:space": "cosine"},
            )
            self._index_docs_to_chromadb()
            self._chromadb_available = True
            logger.info("[RAG] ChromaDB initialized successfully")
        except ImportError:
            logger.info("[RAG] ChromaDB not installed → using keyword-based retrieval (OK for dev)")
        except Exception as e:
            short_msg = str(e).split('\n')[0]
            logger.warning(f"[RAG] ChromaDB init failed: {short_msg} → using keyword-based retrieval")

    def _index_docs_to_chromadb(self) -> None:
        """Index các legal docs vào ChromaDB với chunking đơn giản."""
        if self._collection is None or self._collection.count() > 0:
            return
        chunks, metadatas, ids = [], [], []
        for scenario, doc_text in self._docs.items():
            paragraphs = [p.strip() for p in doc_text.split("\n\n") if len(p.strip()) > 50]
            for i, para in enumerate(paragraphs):
                chunks.append(para)
                metadatas.append({"scenario": scenario, "chunk_id": i})
                ids.append(f"{scenario}_{i}")
        if chunks:
            self._collection.add(documents=chunks, metadatas=metadatas, ids=ids)
            logger.info(f"[RAG] Indexed {len(chunks)} chunks to ChromaDB")

    # ─────────────────────────────────────────────────────────────────────────
    # Public API
    # ─────────────────────────────────────────────────────────────────────────

    def get_legal_text(self, scenario_type: str, n_chunks: int = 5) -> str:
        """
        Lấy văn bản luật liên quan đến scenario_type.

        Args:
            scenario_type: "vn_data_protection" | "vn_data_law" | "vn_bond" |
                           "vn_tax_mgmt" | "vn_tax_register"
            n_chunks: Số chunks ChromaDB trả về (chỉ dùng khi có ChromaDB)

        Returns:
            Văn bản luật, hoặc "" nếu không tìm thấy.
        """
        if scenario_type not in self._docs:
            logger.warning(f"[RAG] No legal doc for scenario: {scenario_type}")
            return ""

        # Tầng 1: ChromaDB semantic search
        if self._chromadb_available and self._collection:
            try:
                results = self._collection.query(
                    query_texts=[scenario_type],
                    n_results=min(n_chunks, self._collection.count()),
                    where={"scenario": scenario_type},
                )
                if results["documents"] and results["documents"][0]:
                    return "\n\n".join(results["documents"][0])
            except Exception as e:
                logger.warning(f"[RAG] ChromaDB query failed: {e} → fallback")

        # Tầng 2 & 3: Trả về toàn bộ document
        return self._docs[scenario_type]

    def get_threshold_json(self, scenario_type: str) -> str:
        """
        Lấy JSON block chứa threshold từ văn bản luật.
        Ưu tiên JSON block cuối cùng (thường là bảng tổng hợp).

        Returns: JSON string hoặc "" nếu không tìm thấy.
        """
        text = self._docs.get(scenario_type, "")
        if not text:
            return ""
        # Lấy tất cả JSON blocks, ưu tiên block cuối (bảng tổng hợp)
        blocks = re.findall(r"```json\s*(\{.*?\})\s*```", text, re.DOTALL)
        if blocks:
            return blocks[-1].strip()  # Block cuối = bảng tổng hợp
        return ""

    def is_available(self, scenario_type: str) -> bool:
        """Kiểm tra có legal doc cho scenario này không."""
        return scenario_type in self._docs

    def get_all_scenarios(self) -> list[str]:
        """Trả về danh sách các scenario type đã load được."""
        return list(self._docs.keys())
