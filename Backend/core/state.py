import operator
from typing import Annotated, TypedDict, Any, List, Dict

class TrustAgentState(TypedDict):
    incident_id: str
    evidence_paths: List[str]
    extracted_data: Dict[str, Any]
    hoa_don_list: List[Dict[str, Any]]
    ket_qua_mst: List[Dict[str, Any]]
    tax_warnings: List[Dict[str, Any]]
    z3_status: str
    legal_violations: List[Dict[str, Any]]
    current_agent: str
    messages: Annotated[List[Dict[str, Any]], operator.add]
    error_log: Annotated[List[Dict[str, Any]], operator.add]
    final_audit_log: Dict[str, Any]
