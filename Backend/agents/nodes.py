"""
TrustAgent.Forensics — Node Functions cho LangGraph Workflow (Phase 3.5)

Mỗi "node" là một bước trong workflow, nhận vào AgentState và trả về
dict để cập nhật state. LangGraph tự động merge dict vào state.

Các node (Phase 3.5):
    parse_node       — Gọi SemanticParser để hiểu câu yêu cầu
    legal_rag_node   — Lấy ngưỡng pháp lý từ văn bản luật qua RAG (mới)
    verify_node      — Gọi TrustAgentSolver Z3 với ngưỡng động từ RAG
    explain_node     — Tạo câu trả lời thân thiện cho người dùng
    route_after_parse — Quyết định: UNKNOWN → explain, known → legal_rag
"""

from __future__ import annotations

import logging
from typing import Any

from src.agents.state import AgentState
from src.rag.retriever import LegalRetriever
from src.rag.extractor import ThresholdExtractor, FALLBACK_THRESHOLDS
from src.semantic.parser import SemanticParser
from src.semantic.schemas import ScenarioType
from src.z3_engine.models import VerificationStatus
from src.z3_engine.solver import TrustAgentSolver
from src.z3_engine.rules.vn_dp_rule import VietnamDataProtectionRule
from src.z3_engine.rules.vn_bond_rule import VietnamBondRule
from src.z3_engine.rules.vn_tax_mgmt_rule import VietnamTaxMgmtRule
from src.z3_engine.rules.vn_tax_register_rule import VietnamTaxRegisterRule
from src.z3_engine.rules.vn_data_law_rule import VietnamDataLawRule

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Singletons — khởi tạo 1 lần, dùng lại xuyên request
# ---------------------------------------------------------------------------
_solver = TrustAgentSolver()
_solver.register_rule(VietnamDataProtectionRule())
_solver.register_rule(VietnamBondRule())
_solver.register_rule(VietnamTaxMgmtRule())
_solver.register_rule(VietnamTaxRegisterRule())
_solver.register_rule(VietnamDataLawRule())

_retriever = LegalRetriever()      # LegalRetriever: load docs + optional ChromaDB
_extractor = ThresholdExtractor()  # ThresholdExtractor: JSON > regex > fallback


def _get_parser(api_key: str = "") -> SemanticParser:
    """Tạo parser từ config hoặc dùng Mock nếu không có API key."""
    try:
        return SemanticParser.from_config()
    except Exception:
        return SemanticParser(api_key=api_key)


# ---------------------------------------------------------------------------
# Node 1: parse_node — Semantic Parsing (Neural Layer)
# ---------------------------------------------------------------------------
def parse_node(state: AgentState) -> dict[str, Any]:
    """
    Bước 1: Phân tích mô tả hoạt động xử lý dữ liệu bằng ngôn ngữ tự nhiên.

    Input  (từ state): user_input (str)
    Output (vào state): scenario_type, z3_data, applicable_rules,
                        parse_confidence, parse_error, parsed_dp

    Ví dụ:
        Input:  "Hệ thống xử lý vân tay nhân viên, chưa có phân quyền"
        Output: scenario_type="vn_data_protection",
                z3_data={"is_sensitive_data": True, "has_access_control": False, ...}
    """
    user_input = state.get("user_input", "")
    logger.info(f"[parse_node] Bắt đầu parse: '{user_input[:60]}...'")

    if not user_input or not user_input.strip():
        return {
            "scenario_type": ScenarioType.UNKNOWN.value,
            "z3_data": {},
            "applicable_rules": [],
            "parse_confidence": 0.0,
            "parse_error": "Input rỗng hoặc chỉ có khoảng trắng",
            "parsed_dp": None,
        }

    try:
        parser = _get_parser()
        result = parser.parse(user_input)

        # Trích xuất detail parsed_dp để explain_node dùng sau
        parsed_dp = result.vn_data_protection.model_dump() if result.vn_data_protection else None

        # Lấy confidence từ parsed data
        confidence = 0.0
        if result.vn_data_protection:
            confidence = result.vn_data_protection.confidence

        logger.info(
            f"[parse_node] Kết quả: scenario={result.scenario_type.value}, "
            f"confidence={confidence:.2f}"
        )

        return {
            "scenario_type": result.scenario_type.value,
            "z3_data": result.to_z3_data(),
            "applicable_rules": result.get_applicable_rules(),
            "parse_confidence": confidence,
            "parse_error": result.parse_error,
            "parsed_dp": parsed_dp,
        }

    except Exception as e:
        logger.error(f"[parse_node] Lỗi không mong muốn: {e}")
        return {
            "scenario_type": ScenarioType.UNKNOWN.value,
            "z3_data": {},
            "applicable_rules": [],
            "parse_confidence": 0.0,
            "parse_error": str(e),
            "parsed_dp": None,
        }


# ---------------------------------------------------------------------------
# Node 2 (mới): legal_rag_node — Legal RAG: lấy ngưỡng từ văn bản luật
# ---------------------------------------------------------------------------
def legal_rag_node(state: AgentState) -> dict[str, Any]:
    """
    Bước 2: Lấy ngưỡng pháp lý từ cơ sở dữ liệu văn bản luật (RAG).

    Thay thế việc hardcode hằng số như VN_CASH_THRESHOLD = 20_000_000.
    Legal RAG Node trậtự tắt cả từ cơ sở dữ liệu luật động .

    Input  (từ state): scenario_type
    Output (vào state): legal_thresholds

    Luồng xử lý:
        1. LegalRetriever.get_legal_text(scenario_type) → văn bản luật
        2. ThresholdExtractor.extract(scenario_type, text) → dict ngưỡng
        3. Nếu fail → fallback defaults (không bao giờ raise)

    Ví dụ:
        Input:  scenario_type="vn_payment"
        Output: legal_thresholds={"VN_CASH_THRESHOLD": 20000000}

        Input:  scenario_type="kr_tax_refund"
        Output: legal_thresholds={"KR_MIN_RECEIPT_AMOUNT": 30000,
                                   "KR_CUSTOMS_CHECK_THRESHOLD": 75000}
    """
    scenario_type = state.get("scenario_type", "unknown")
    logger.info(f"[legal_rag_node] Tra cứu luật cho scenario: {scenario_type}")

    # Fallback an toàn nếu scenario không xác định
    if scenario_type not in FALLBACK_THRESHOLDS:
        logger.warning(f"[legal_rag_node] Không có luật cho scenario: {scenario_type}")
        return {"legal_thresholds": {}}

    try:
        # Tầng 1: Lấy văn bản luật từ RAG
        legal_text = _retriever.get_legal_text(scenario_type)

        # Tầng 2: Trích xuất ngưỡng từ văn bản
        thresholds = _extractor.extract(scenario_type, legal_text)

        logger.info(f"[legal_rag_node] Ngưỡng đã lấy: {thresholds}")
        return {"legal_thresholds": thresholds}

    except Exception as e:
        # Tầng 3: Fallback nếu RAG thất bại hoàn toàn
        logger.error(f"[legal_rag_node] Lỗi RAG: {e} → dùng fallback defaults")
        fallback = dict(FALLBACK_THRESHOLDS.get(scenario_type, {}))
        return {"legal_thresholds": fallback}


# ---------------------------------------------------------------------------
# Node 3: verify_node — Z3 Formal Verification (Symbolic Layer) [Updated]
# ---------------------------------------------------------------------------
def verify_node(state: AgentState) -> dict[str, Any]:
    """
    Bước 3: Kiểm chứng dữ liệu bằng Z3 Theorem Prover.

    Cập nhật Phase 3.5: Nhận dynamic_thresholds từ state["legal_thresholds"]
    và truyền vào TrustAgentSolver.verify() thay vì dùng hằng số.

    Input  (từ state): z3_data, applicable_rules, legal_thresholds
    Output (vào state): z3_status, is_compliant, violations, verify_time_ms, verify_error

    Ví dụ:
        Input:  z3_data={"amount": 25000000, "is_cash_payment": True},
                legal_thresholds={"VN_CASH_THRESHOLD": 20000000}
        Output: z3_status="UNSAT", is_compliant=False, violations=[...]
    """
    z3_data = state.get("z3_data", {})
    applicable_rules = state.get("applicable_rules", [])
    scenario_type = state.get("scenario_type", "unknown")
    # Lấy ngưỡng từ RAG state (None nếu legal_rag_node chưa chạy)
    dynamic_thresholds = state.get("legal_thresholds") or None

    logger.info(
        f"[verify_node] Kiểm chứng scenario={scenario_type}, "
        f"rules={applicable_rules}, thresholds={dynamic_thresholds}"
    )

    # Nếu không có data để verify → skip
    if not z3_data or not applicable_rules:
        return {
            "z3_status": VerificationStatus.UNKNOWN.value,
            "is_compliant": False,
            "violations": [],
            "verify_time_ms": 0.0,
            "verify_error": "Không có dữ liệu hoặc rule để kiểm chứng",
        }

    try:
        # Truyền dynamic_thresholds từ RAG vào solver
        verify_result = _solver.verify(
            data=z3_data,
            rule_names=applicable_rules,
            dynamic_thresholds=dynamic_thresholds,  # ← Từ Legal RAG Node
        )

        violations_dicts = [v.model_dump() for v in verify_result.violations]

        logger.info(
            f"[verify_node] Kết quả: status={verify_result.status.value}, "
            f"compliant={verify_result.is_compliant}, "
            f"time={verify_result.verification_time_ms:.2f}ms"
        )

        return {
            "z3_status": verify_result.status.value,
            "is_compliant": verify_result.is_compliant,
            "violations": violations_dicts,
            "verify_time_ms": verify_result.verification_time_ms,
            "verify_error": None,
        }

    except Exception as e:
        logger.error(f"[verify_node] Lỗi không mong muốn: {e}")
        return {
            "z3_status": VerificationStatus.UNKNOWN.value,
            "is_compliant": False,
            "violations": [],
            "verify_time_ms": 0.0,
            "verify_error": str(e),
        }


# ---------------------------------------------------------------------------
# Node 3: explain_node — Tạo phản hồi thân thiện cho người dùng
# ---------------------------------------------------------------------------
def explain_node(state: AgentState) -> dict[str, Any]:
    """
    Bước 3: Tạo câu giải thích thân thiện dựa trên kết quả Z3.

    Input  (từ state): user_input, z3_status, violations, scenario_type, parse_error
    Output (vào state): explanation, final_error

    Ví dụ:
        Input:  z3_status="UNSAT", violations=[{rule: "vn_cash_payment_threshold", ...}]
        Output: explanation="❌ Giao dịch bị từ chối. Số tiền 25,000,000 VNĐ..."
    """
    user_input = state.get("user_input", "")
    z3_status = state.get("z3_status", "UNKNOWN")
    violations = state.get("violations", [])
    scenario_type = state.get("scenario_type", "UNKNOWN")
    parse_error = state.get("parse_error")
    verify_error = state.get("verify_error")

    logger.info(f"[explain_node] Tạo giải thích: status={z3_status}")

    # Trường hợp lỗi nghiêm trọng — không parse được
    if scenario_type == ScenarioType.UNKNOWN.value:
        if parse_error:
            explanation = (
                f"⚠️ Xin lỗi, tôi không nhận diện được hoạt động bảo vệ dữ liệu cá nhân.\n"
                f"Lý do: {parse_error}\n\n"
                f"Gợi ý: Hãy mô tả rõ hoạt động xử lý dữ liệu.\n"
                f"Ví dụ: 'Hệ thống AI của chúng tôi xử lý dữ liệu vân tay của 500 nhân viên, "
                f"chưa thiết lập phân quyền truy cập.'"
            )
        else:
            explanation = (
                "⚠️ Yêu cầu không liên quan đến bảo vệ dữ liệu cá nhân theo Nghị định 356/2025/NĐ-CP.\n"
                "Hệ thống kiểm chứng: Xử lý dữ liệu nhạy cảm, chuyển xuyên biên giới, sự cố lộ dữ liệu."
            )
        return {"explanation": explanation, "final_error": None}

    # Trường hợp lỗi Z3
    if verify_error:
        explanation = (
            f"⚠️ Có lỗi khi kiểm tra quy định. Chi tiết: {verify_error}"
        )
        return {"explanation": explanation, "final_error": verify_error}

    # Tạo giải thích dựa trên kết quả Z3
    try:
        parser = _get_parser()

        # Chuyển violations dict → objects tương tự để explain
        class _FakeViolation:
            """Adapter để explain_result() dùng được violations từ dict."""
            def __init__(self, d: dict):
                self.violation_detail = d.get("violation_detail", "Vi phạm quy định")
                self.legal_reference = d.get("legal_reference", "")
                self.text_evidence = d.get("text_evidence", "")

        fake_violations = [_FakeViolation(v) for v in violations]
        explanation = parser.explain_result(user_input, z3_status, fake_violations)

        return {"explanation": explanation, "final_error": None}

    except Exception as e:
        logger.error(f"[explain_node] Lỗi: {e}")
        # Fallback đơn giản nếu parser.explain_result thất bại
        if z3_status == "SAT":
            fallback = "✅ AWAIT_CONFIRMATION: Hoạt động xử lý dữ liệu hợp lệ pháp lý."
        elif z3_status == "UNSAT":
            fallback = f"🚫 BLOCK_IMMEDIATELY: Phát hiện {len(violations)} vi phạm Nghị định 356/2025/NĐ-CP."
        else:
            fallback = "⚠️ UNKNOWN: Không đủ thông tin để kiểm chứng."
        return {"explanation": fallback, "final_error": str(e)}


# ---------------------------------------------------------------------------
# Route Function — quyết định đường đi trong graph
# ---------------------------------------------------------------------------
def route_after_parse(state: AgentState) -> str:
    """
    Sau parse_node, quyết định bước tiếp theo:
    - Nếu scenario UNKNOWN → nhảy thẳng sang explain_node
    - Nếu scenario xác định → đi qua legal_rag_node (mới) rồi verify_node
    """
    scenario_type = state.get("scenario_type", "unknown")
    if scenario_type == ScenarioType.UNKNOWN.value:
        logger.info("[route] Scenario UNKNOWN → skip rag+verify, đi thẳng explain")
        return "explain"
    logger.info(f"[route] Scenario={scenario_type} → đi qua legal_rag")
    return "rag"  # ← Đổi từ 'verify' sang 'rag' (Phase 3.5)
