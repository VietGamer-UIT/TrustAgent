"""
TrustAgent — Prompt Templates cho Gemini Semantic Parser (Nghị định 356/2025/NĐ-CP)

Hướng dẫn Gemini 2.0 Flash trích xuất thông tin hoạt động xử lý dữ liệu cá nhân
từ ngôn ngữ tự nhiên thành JSON có cấu trúc chính xác.

Nguyên tắc thiết kế:
- LLM CHỈ được phép TRÍCH XUẤT dữ liệu, KHÔNG được ra quyết định tuân thủ/vi phạm
- Mọi quyết định tuân thủ đều do Z3 Theorem Prover xử lý sau đó
- Anti-hallucination: Nếu không đề cập rõ ràng → mặc định False/999
"""

from __future__ import annotations


# ─────────────────────────────────────────────────────────────────────────────
# System Prompt — Bản sắc của Semantic Parser
# ─────────────────────────────────────────────────────────────────────────────
SYSTEM_PROMPT = """Bạn là TrustAgent Semantic Parser — bộ phân tích ngữ nghĩa chuyên nghiệp
cho hệ thống kiểm chứng tuân thủ Nghị định 356/2025/NĐ-CP về Bảo vệ Dữ liệu Cá nhân Việt Nam.

NHIỆM VỤ DUY NHẤT: Đọc mô tả hoạt động xử lý dữ liệu → Trích xuất thành JSON có cấu trúc.
KHÔNG được tự đánh giá hoạt động đó vi phạm hay tuân thủ — đó là việc của Z3 Theorem Prover.
Chỉ trả về JSON thuần túy, không giải thích, không markdown code block.

ANTI-HALLUCINATION PROTOCOL:
- Nếu người dùng KHÔNG đề cập rõ ràng việc có access control → has_access_control = false
- Nếu người dùng KHÔNG đề cập rõ ràng việc có biện pháp bảo mật → has_security_measures = false
- Nếu không nhắc đến hồ sơ đánh giá → dossier_submitted_days = 999 (chưa nộp)
- Nếu không nhắc đến thông báo sự cố → breach_notice_hours = 999 (chưa thông báo)
- Nguyên tắc: Thiếu thông tin = Chưa thực hiện = Giá trị worst-case"""


# ─────────────────────────────────────────────────────────────────────────────
# Prompt phát hiện kịch bản
# ─────────────────────────────────────────────────────────────────────────────
DETECT_SCENARIO_PROMPT = """Phân tích câu sau và xác định loại kịch bản bảo vệ dữ liệu cá nhân:
- "vn_data_protection": Liên quan đến xử lý dữ liệu cá nhân, chuyển dữ liệu xuyên biên giới,
  sự cố lộ dữ liệu, theo Nghị định 356/2025/NĐ-CP
- "unknown": Không liên quan đến bảo vệ dữ liệu cá nhân

Từ khoá nhận diện "vn_data_protection":
  Xử lý dữ liệu: vân tay, khuôn mặt, sinh trắc, định vị, GPS, sức khỏe, bệnh án,
    tài khoản ngân hàng, lịch sử giao dịch, tôn giáo, xu hướng tình dục, CCCD
  Chuyển xuyên biên giới: AWS, Azure, GCP, cloud nước ngoài, máy chủ nước ngoài,
    đối tác quốc tế, cross-border, offshore
  Sự cố: lộ dữ liệu, data breach, bị hack, rò rỉ, mất dữ liệu, tấn công

Câu: "{user_input}"

Trả về JSON: {{"scenario_type": "vn_data_protection" | "unknown"}}"""


# ─────────────────────────────────────────────────────────────────────────────
# Prompt trích xuất hoạt động bảo vệ dữ liệu (Nghị định 356)
# ─────────────────────────────────────────────────────────────────────────────
VN_DATA_PROTECTION_EXTRACT_PROMPT = """Trích xuất thông tin hoạt động xử lý dữ liệu cá nhân theo Nghị định 356/2025/NĐ-CP.

PHÂN LOẠI DỮ LIỆU NHẠY CẢM (is_sensitive_data = true nếu có BẤT KỲ loại sau):
  Sinh trắc học: vân tay, khuôn mặt, mống mắt, ADN, giọng nói
  Định vị: GPS, location, vị trí, định vị
  Tài chính: tài khoản ngân hàng, lịch sử giao dịch, thông tin tín dụng
  Sức khỏe: bệnh án, hồ sơ y tế, tình trạng bệnh
  Nhạy cảm khác: tôn giáo, xu hướng tình dục, thông tin tội phạm

ANTI-HALLUCINATION (CỰC KỲ QUAN TRỌNG):
  - Không đề cập access control → has_access_control: false
  - Không đề cập bảo mật → has_security_measures: false
  - Không đề cập hồ sơ/đánh giá tác động → dossier_submitted_days: 999
  - Không đề cập thông báo sự cố → breach_notice_hours: 999
  - Không đề cập lưu trữ hồ sơ → breach_retention_years: 0

VÍ DỤ:
Input: "Công ty xử lý dữ liệu vân tay 500 nhân viên. Hệ thống chưa có phân quyền."
Output: {{"is_sensitive_data": true, "data_type_biometric": true, "data_type_location": false,
  "has_access_control": false, "has_security_measures": false,
  "is_cross_border": false, "dossier_submitted_days": 999,
  "basic_record_count": 0, "sensitive_record_count": 500,
  "national_security_assessed": false,
  "is_breach": false, "breach_notice_hours": 999, "breach_retention_years": 0,
  "description": "Xử lý dữ liệu sinh trắc học nhân viên", "confidence": 0.95}}

Input: "Chúng tôi lưu GPS của 200.000 khách hàng lên AWS Singapore, đã nộp hồ sơ đánh giá sau 45 ngày."
Output: {{"is_sensitive_data": true, "data_type_biometric": false, "data_type_location": true,
  "has_access_control": false, "has_security_measures": false,
  "is_cross_border": true, "dossier_submitted_days": 45,
  "basic_record_count": 0, "sensitive_record_count": 200000,
  "national_security_assessed": false,
  "is_breach": false, "breach_notice_hours": 999, "breach_retention_years": 0,
  "description": "Chuyển dữ liệu GPS khách hàng lên AWS Singapore", "confidence": 0.92}}

Input: "Hệ thống bị tấn công, lộ dữ liệu khuôn mặt của 5.000 người. Chúng tôi thông báo sau 96 giờ."
Output: {{"is_sensitive_data": true, "data_type_biometric": true, "data_type_location": false,
  "has_access_control": false, "has_security_measures": false,
  "is_cross_border": false, "dossier_submitted_days": 999,
  "basic_record_count": 0, "sensitive_record_count": 5000,
  "national_security_assessed": false,
  "is_breach": true, "breach_notice_hours": 96, "breach_retention_years": 0,
  "description": "Sự cố lộ dữ liệu sinh trắc học khuôn mặt", "confidence": 0.97}}

Input: "Xử lý tên, số điện thoại của khách hàng. Có phân quyền và mã hóa AES-256."
Output: {{"is_sensitive_data": false, "data_type_biometric": false, "data_type_location": false,
  "has_access_control": true, "has_security_measures": true,
  "is_cross_border": false, "dossier_submitted_days": 999,
  "basic_record_count": 0, "sensitive_record_count": 0,
  "national_security_assessed": false,
  "is_breach": false, "breach_notice_hours": 999, "breach_retention_years": 0,
  "description": "Xử lý dữ liệu cơ bản với biện pháp bảo mật", "confidence": 0.90}}

Bây giờ trích xuất:
Input: "{user_input}"
Output:"""


# ─────────────────────────────────────────────────────────────────────────────
# Prompt tạo AUDIT TRAIL LOG (output cuối cùng theo định dạng nghiêm ngặt)
# ─────────────────────────────────────────────────────────────────────────────
AUDIT_LOG_EXPLAIN_PROMPT = """Dựa trên kết quả kiểm chứng Z3 bên dưới, hãy tạo báo cáo AUDIT TRAIL LOG
theo đúng format sau. Viết bằng tiếng Việt. KHÔNG thêm text nào ngoài format.

Yêu cầu gốc: "{original_request}"
Kịch bản: {scenario}
Thực thể: {entities}
Phân loại dữ liệu: {data_classification}
Kết quả Z3: {status}
Vi phạm: {violations}
Luật áp dụng: {legal_references}
Bằng chứng văn bản: {text_evidence}

==============================================================================
🛡️ TrustAgent AUDIT TRAIL LOG
==============================================================================
[TRANSACTION ANALYSIS]
- Extracted Scenario: {scenario}
- Target Entities: {entities}
- Data Classification: {data_classification}

[VERIFICATION ENGINE RESULT]
- Verification Status: {status}
- Operational Command: {"✅ ALLOW & AWAIT APPROVAL" if status == "SAT" else "🚫 BLOCK_IMMEDIATELY"}

[LEGAL CITATION & EVIDENCE]
- Citation Code: {legal_references}
- Text Evidence from Law: "{text_evidence}"
- Logic Violation Breakdown: [Giải thích logic toán học dựa trên violations: {violations}]

[GATEKEEPER PAYLOAD]
- System Action: {"AWAIT_CONFIRMATION: Dữ liệu hợp lệ pháp lý. Chờ phê duyệt thực thi." if status == "SAT" else "DISALLOW_EXECUTION: Đã ngắt kết nối API, chặn luồng dữ liệu để tránh vi phạm pháp luật."}
=============================================================================="""


# ─────────────────────────────────────────────────────────────────────────────
# Giải thích đơn giản (fallback khi không dùng audit log format)
# ─────────────────────────────────────────────────────────────────────────────
EXPLAIN_RESULT_PROMPT = """Dựa trên kết quả kiểm chứng Nghị định 356/2025/NĐ-CP bên dưới,
viết báo cáo ngắn gọn bằng tiếng Việt (2-4 câu).

Yêu cầu gốc: "{original_request}"
Kết quả: {status}
Chi tiết vi phạm: {violations}

Nếu SAT ✅: Xác nhận hoạt động tuân thủ và điểm tuân thủ cụ thể.
Nếu UNSAT ❌: Giải thích rõ điều khoản vi phạm (trích dẫn Nghị định 356) và biện pháp khắc phục."""
