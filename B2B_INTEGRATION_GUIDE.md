# TrustAgent — B2B Integration Guide
## Legal Audit API for Enterprise AI Agents

> **Base URL (Production):** `https://trustagent-qbrd.onrender.com`  
> **Version:** 1.0.0 · **Auth:** API Key (header `X-Api-Key`)

---

## 🎯 TrustAgent là gì?

TrustAgent là **Legal Firewall** — lớp kiểm toán pháp lý tự động cho AI Agent của doanh nghiệp.

Thay vì để AI Agent trực tiếp thực thi hành vi có thể vi phạm pháp luật, doanh nghiệp chỉ cần **gọi 1 API call** để TrustAgent kiểm tra trước. Nếu vi phạm → **chặn ngay**, nếu hợp lệ → **cho phép thực thi**.

```
AI Agent của bạn
      ↓ (Mô tả hành vi dự định thực hiện)
POST /api/v1/audit  ←── TrustAgent
      ↓
  SAT (✅ OK)  hoặc  UNSAT (🚫 Vi phạm → chi tiết điều khoản)
      ↓
Thực thi / Chặn lại
```

---

## 🔑 Xác thực

Gửi header `X-Api-Key` với API key được cấp:

```
X-Api-Key: trustagent_pilot
```

> **Pilot Integration (miễn phí):** Dùng key `trustagent_pilot`
> Key production sẽ được cấp riêng sau giai đoạn thử nghiệm.

---

## 📡 Endpoints

### 1. Kiểm tra kết nối

```http
GET /api/v1/audit/health
```

**Response:**
```json
{
  "status": "ok",
  "service": "TrustAgent Legal Audit API",
  "version": "1.0.0",
  "supported_scenarios": [
    "Bảo vệ dữ liệu cá nhân (NĐ 356/2025)",
    "Trái phiếu doanh nghiệp (NĐ 200/2026)",
    "Quản lý thuế (NĐ 252/2026)",
    "Đăng ký thuế (TT 90/2026)",
    "Luật Dữ liệu (NĐ 165/2025)"
  ]
}
```

---

### 2. Kiểm toán pháp lý (Main Endpoint)

```http
POST /api/v1/audit
Content-Type: application/json
X-Api-Key: trustagent_pilot
```

**Request Body:**
```json
{
  "description": "Mô tả hành vi/quyết định của AI Agent bằng tiếng Việt"
}
```

**Response — Tuân thủ (SAT ✅):**
```json
{
  "is_compliant": true,
  "z3_status": "SAT",
  "scenario": "vn_data_protection",
  "violations": [],
  "explanation": "✅ Hoạt động tuân thủ pháp luật. Không phát hiện vi phạm.",
  "duration_ms": 312.5
}
```

**Response — Vi phạm (UNSAT 🚫):**
```json
{
  "is_compliant": false,
  "z3_status": "UNSAT",
  "scenario": "vn_data_protection",
  "violations": [
    {
      "rule": "vn_data_protection_nd356",
      "detail": "Hệ thống đang xử lý dữ liệu sinh trắc học nhưng CHƯA thiết lập phân quyền truy cập (RBAC)...",
      "severity": "critical",
      "legal_ref": "Nghị định 356/2025/NĐ-CP về Bảo vệ Dữ liệu Cá nhân"
    }
  ],
  "explanation": "🛡️ TRUSTAGENT — BÁO CÁO KIỂM CHỨNG\n\n1) Thông tin hoạt động...",
  "duration_ms": 295.1
}
```

---

## 💡 Ví dụ tích hợp thực tế

### Python (dành cho FATS AI / AI Tài chính)

```python
import requests

TRUSTAGENT_URL = "https://trustagent-qbrd.onrender.com"
API_KEY = "trustagent_pilot"

def check_before_execute(action_description: str) -> dict:
    """
    Gọi TrustAgent trước khi AI Agent thực thi hành vi.
    Trả về dict với is_compliant, violations, explanation.
    """
    response = requests.post(
        f"{TRUSTAGENT_URL}/api/v1/audit",
        headers={
            "Content-Type": "application/json",
            "X-Api-Key": API_KEY,
        },
        json={"description": action_description},
        timeout=30,
    )
    response.raise_for_status()
    return response.json()


# Ví dụ: AI Tài chính xuất báo cáo → check pháp lý trước khi gửi khách
result = check_before_execute(
    "Phát hành trái phiếu doanh nghiệp 100 tỷ VNĐ, "
    "chưa có báo cáo tài chính được kiểm toán độc lập."
)

if result["is_compliant"]:
    print("✅ Hợp lệ — Cho phép thực thi")
    # ... tiếp tục luồng AI
else:
    print("🚫 VI PHẠM — Chặn thực thi ngay")
    for v in result["violations"]:
        print(f"  ❌ {v['detail'][:120]}")
        print(f"     Căn cứ: {v['legal_ref']}")
```

### JavaScript / Node.js

```javascript
const TRUSTAGENT_URL = "https://trustagent-qbrd.onrender.com";
const API_KEY = "trustagent_pilot";

async function legalCheck(description) {
  const res = await fetch(`${TRUSTAGENT_URL}/api/v1/audit`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-Api-Key": API_KEY,
    },
    body: JSON.stringify({ description }),
  });
  if (!res.ok) throw new Error(`TrustAgent HTTP ${res.status}`);
  return res.json();
}

// Middleware tích hợp vào pipeline AI Agent
async function executeWithLegalGuard(agentAction, description) {
  const audit = await legalCheck(description);

  if (!audit.is_compliant) {
    // Log vi phạm và dừng luồng
    console.error("🚫 TrustAgent blocked:", audit.violations[0]?.detail);
    throw new Error(`LEGAL_VIOLATION: ${audit.z3_status}`);
  }

  // An toàn pháp lý → thực thi hành vi
  return agentAction();
}
```

---

## 📚 5 Bộ Luật Cốt Lõi

TrustAgent sử dụng kiến trúc Neuro-Symbolic (Gemini LLM + Z3 Solver) để kiểm chứng toán học theo 5 bộ luật mới nhất:

| # | Văn bản pháp lý | Phạm vi kiểm chứng | Kích thước |
|---|-----------------|-------------------|------------|
| 1 | **Nghị định 356/2025/NĐ-CP** — Bảo vệ dữ liệu cá nhân | Sinh trắc học, mã hóa, phân quyền RBAC, chuyển dữ liệu xuyên biên giới, thông báo sự cố 72h | 164KB |
| 2 | **Nghị định 200/2026/NĐ-CP** — Trái phiếu doanh nghiệp | Điều kiện phát hành, kiểm toán BCTC, công bố thông tin, nhà đầu tư chuyên nghiệp | 238KB |
| 3 | **Nghị định 252/2026/NĐ-CP** — Quản lý thuế | Quyết toán, thanh tra, gia hạn nộp thuế, phạt chậm nộp 0.03%/ngày | 418KB |
| 4 | **Thông tư 90/2026/TT-BTC** — Đăng ký thuế | Đăng ký mới, cập nhật thông tin, thời hạn 10 ngày | 242KB |
| 5 | **Nghị định 165/2025/NĐ-CP** — Luật Dữ liệu | Phân loại dữ liệu quan trọng, dữ liệu cốt lõi, quản lý dữ liệu quốc gia | 81KB |

> **Tại sao 5 bộ luật là ĐỦ?**
>
> 80% rủi ro pháp lý của doanh nghiệp công nghệ Việt Nam tập trung vào 3 nhóm:
> - **Dữ liệu** → NĐ 356 + NĐ 165
> - **Tài chính / Vốn** → NĐ 200
> - **Thuế** → NĐ 252 + TT 90
>
> Với AI Tài chính (FATS AI): NĐ 200 (trái phiếu) + NĐ 252 (thuế) + NĐ 356 (dữ liệu khách hàng) là 3 luật trực tiếp nhất.

---

## ⚡ Hiệu năng

| Chỉ số | Giá trị |
|--------|---------|
| Latency trung bình | 300–500ms |
| Latency tối đa | < 2 giây |
| Timeout khuyến nghị | 30 giây |
| Rate limit | Không giới hạn (Pilot) |

> **Lưu ý Free Tier Render.com:** Instance có thể ngủ sau 15 phút không hoạt động.
> Request đầu tiên sau khi ngủ có thể mất 30–50 giây để khởi động lại (cold start).
> → Có thể gọi `GET /api/v1/audit/health` định kỳ để giữ instance sống.

---

## 🔗 Tài liệu thêm

- **Swagger UI (Interactive):** `https://trustagent-qbrd.onrender.com/docs`
- **ReDoc:** `https://trustagent-qbrd.onrender.com/redoc`
- **GitHub:** `https://github.com/VietGamer-UIT/TrustAgent`

---

*TrustAgent · Neuro-Symbolic Legal Audit Platform*  
*Đoàn Hoàng Việt (Việt Gamer) · INNOSTAR Bán Kết 2 · 2026*
