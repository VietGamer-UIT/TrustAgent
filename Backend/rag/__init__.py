# TrustAgent.Forensics — RAG Module (Phase 3.5)
# Legal Retrieval-Augmented Generation for dynamic Z3 thresholds
from .retriever import LegalRetriever
from .extractor import ThresholdExtractor, FALLBACK_THRESHOLDS

__all__ = ["LegalRetriever", "ThresholdExtractor", "FALLBACK_THRESHOLDS"]
