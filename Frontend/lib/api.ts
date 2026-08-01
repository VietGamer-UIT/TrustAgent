// =============================================================================
// TrustAgent :: API Client
// Bản quyền: TrustAgent bởi Đoàn Hoàng Việt (Việt Gamer)
// =============================================================================

import axios, { AxiosError } from 'axios'

/**
 * Browser luôn gọi thẳng Backend qua cổng đã publish (localhost:8000),
 * tránh phụ thuộc Next.js rewrite (bị bake sai khi build Docker).
 */
function resolveApiBase(): string {
  if (typeof window !== 'undefined') {
    // Ưu tiên biến môi trường NEXT_PUBLIC_API_URL (bao gồm cả trường hợp rỗng để dùng relative proxy)
    if (process.env.NEXT_PUBLIC_API_URL !== undefined) {
      return process.env.NEXT_PUBLIC_API_URL === '/' 
        ? '' 
        : process.env.NEXT_PUBLIC_API_URL.replace(/\/$/, '')
    }

    const { protocol, hostname } = window.location
    if (hostname.includes('.app.github.dev')) {
      const backendHost = hostname.replace(
        /-3000\.app\.github\.dev$/,
        '-8000.app.github.dev'
      )
      return `${protocol}//${backendHost}`
    }
    // Cùng máy: Backend publish :8000
    return `${protocol}//${hostname === 'localhost' ? 'localhost' : hostname}:8000`
  }
  return (
    process.env.NEXT_PUBLIC_API_URL?.replace(/\/$/, '') ||
    process.env.BACKEND_URL?.replace(/\/$/, '') ||
    'http://127.0.0.1:8000'
  )
}

export const API_BASE = resolveApiBase()

const client = axios.create({
  baseURL: API_BASE,
  timeout: 180_000,
  headers: { 'Content-Type': 'application/json' },
})

if (process.env.NODE_ENV === 'development' && typeof window !== 'undefined') {
  console.info(`[TrustAgent] API base → ${API_BASE}`)
}

// ---------------------------------------------------------------------------
// Types — Kiểm Tra Chứng Từ
// ---------------------------------------------------------------------------

export interface CanhBao {
  loai: string
  so_hoa_don: string
  mo_ta: string
  muc_do: 'nghiêm trọng' | 'cao' | 'trung bình' | 'thấp'
  nguon: string
}

export interface KetQuaMST {
  mst: string
  ten_doanh_nghiep: string
  dia_chi: string
  nguoi_dai_dien: string
  ngay_cap: string | null
  tinh_trang: string
  co_quan_thue: string
  loai_hinh: string
  canh_bao: string | null
}

export interface BaoCaoKiemTra {
  ma_phien: string
  trang_thai: string
  muc_do_rui_ro: string
  tom_tat: string
  danh_sach_canh_bao: CanhBao[]
  ket_qua_mst: KetQuaMST[]
  khuyen_nghi: string[]
  agents_da_chay: string[]
  so_loi: number
  so_vong_lap: number
  hoan_tat_luc: string
}

export interface YeuCauKiemTra {
  ma_phien: string
  duong_dan_chung_tu: string[]
}

export interface KetQuaKiemTra {
  graph_run_id: string
  ma_phien: string
  trang_thai: string
  muc_do_rui_ro: string
  tom_tat: string
  so_vong_lap: number
  hoan_tat_luc: string
  bao_cao_kiem_tra: BaoCaoKiemTra
}

/** Kết quả từ endpoint upload file thật */
export interface KetQuaUpload extends KetQuaKiemTra {
  ten_file_goc?: string
  kich_thuoc_kb?: number
}

// ---------------------------------------------------------------------------
// Types — Audit
// ---------------------------------------------------------------------------

export interface AuditEvent {
  id: string
  event_type: string
  agent_name: string
  status: string
  tool_name: string | null
  retry_attempt: number
  duration_ms: number | null
  sha256_hash: string | null
  recorded_at: string | null
}

export interface AuditEventsResponse {
  incident_id: string
  count: number
  events: AuditEvent[]
}

export interface HealthResponse {
  status: string
  service: string
}

// ---------------------------------------------------------------------------
// Types — MST Cache (Local Data Caching Pipeline)
// ---------------------------------------------------------------------------

export interface ThongTinDoanNghiep {
  mst: string
  ten_doanh_nghiep: string
  dia_chi: string
  tinh_trang: string
  canh_bao: string | null
  nguon: string
  cap_nhat_luc: string
}

export interface TrangThaiPipeline {
  trang_thai: string
  lan_chay_cuoi: string | null
  so_ban_ghi: number
  so_den_hang_den: number
  so_ngung_hoat_dong: number
  thoi_gian_chay_tiep: string | null
}

// ---------------------------------------------------------------------------
// Error extraction
// ---------------------------------------------------------------------------
export function extractErrorMessage(err: unknown): string {
  if (err instanceof Error) {
    const maybeAxios = err as Error & {
      response?: { data?: { detail?: unknown }; status?: number }
      code?: string
    }
    const detail = maybeAxios.response?.data?.detail
    if (typeof detail === 'string') return detail
    if (Array.isArray(detail)) {
      return (detail as Array<{ msg?: string }>)
        .map((d) => d.msg ?? JSON.stringify(d))
        .join('; ')
    }
    if (maybeAxios.code === 'ERR_NETWORK' || maybeAxios.response?.status === 0) {
      return `Không thể kết nối tới backend (${API_BASE}). Kiểm tra backend đang chạy và CORS đúng.`
    }
    return err.message
  }
  if (typeof err === 'string') return err
  return 'Lỗi không xác định'
}

// ---------------------------------------------------------------------------
// API Functions
// ---------------------------------------------------------------------------

export async function checkHealth(): Promise<HealthResponse> {
  const { data } = await client.get<HealthResponse>('/health')
  return data
}

/** Gửi yêu cầu kiểm tra chứng từ đa tác nhân */
export async function kiemTraChungTu(
  req: YeuCauKiemTra
): Promise<KetQuaKiemTra> {
  const { data } = await client.post<KetQuaKiemTra>(
    '/api/v1/kiem-tra/chung-tu',
    req,
    { headers: { 'X-Ma-Phien': req.ma_phien } }
  )
  return data
}

/** Backward-compat alias — vẫn chạy được với endpoint cũ */
export async function investigate(req: {
  incident_id: string
  evidence_paths: string[]
}): Promise<KetQuaKiemTra> {
  return kiemTraChungTu({
    ma_phien: req.incident_id,
    duong_dan_chung_tu: req.evidence_paths,
  })
}

/**
 * Upload file hóa đơn thật (JPG/PNG/PDF/WebP) và chạy Gemini Vision OCR.
 * Gọi endpoint POST /api/v1/kiem-tra/upload với FormData.
 */
export async function uploadHoaDon(
  file: File,
  maPhien?: string,
): Promise<KetQuaUpload> {
  const formData = new FormData()
  formData.append('file', file)

  const params = new URLSearchParams()
  if (maPhien?.trim()) params.set('ma_phien', maPhien.trim())

  const url = `/api/v1/kiem-tra/upload${params.toString() ? '?' + params.toString() : ''}`

  // Axios với FormData: không đặt Content-Type thủ công — để browser tự sinh boundary
  const { data } = await client.post<KetQuaUpload>(url, formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
    timeout: 300_000, // 5 phút — Gemini Vision có thể chậm hơn
  })
  return data
}

export async function getAuditEvents(
  incidentId: string,
  limit = 200
): Promise<AuditEventsResponse> {
  const { data } = await client.get<AuditEventsResponse>('/api/v1/audit/events', {
    params: { incident_id: incidentId, limit },
  })
  return data
}

/** Tra cứu MST từ Local Cache (PostgreSQL) */
export async function traCuuMST(mst: string): Promise<ThongTinDoanNghiep> {
  const { data } = await client.get<ThongTinDoanNghiep>(`/api/v1/mst/thong-tin`, {
    params: { mst },
  })
  return data
}

/** Lấy trạng thái Data Pipeline */
export async function getTrangThaiPipeline(): Promise<TrangThaiPipeline> {
  const { data } = await client.get<TrangThaiPipeline>('/api/v1/pipeline/trang-thai')
  return data
}

// ---------------------------------------------------------------------------
// Types — Forensics (Z3 Legal Gatekeeper)
// ---------------------------------------------------------------------------

export interface ForensicsViolation {
  rule_name: string
  rule_description: string
  severity: string
  violation_detail: string
  legal_reference: string
}

export interface ForensicsVerifyResponse {
  audit_id: string
  scenario_type: string
  z3_status: string
  is_compliant: boolean
  violations: ForensicsViolation[]
  legal_thresholds: Record<string, unknown>
  explanation: string
  duration_ms: number
}

export interface ForensicsAuditRecord {
  id: string
  created_at: string
  user_input: string
  scenario_type: string | null
  legal_thresholds: Record<string, unknown> | null
  z3_status: string | null
  is_compliant: boolean | null
  violations: Record<string, unknown>[]
  explanation: string | null
  duration_ms: number | null
}

export interface ForensicsAuditListResponse {
  items: ForensicsAuditRecord[]
  total: number
  limit: number
  offset: number
}

/** Forensics: kiểm chứng NL → RAG → Z3 */
export async function forensicsVerify(
  userInput: string
): Promise<ForensicsVerifyResponse> {
  const { data } = await client.post<ForensicsVerifyResponse>(
    '/api/v1/forensics/verify',
    { user_input: userInput }
  )
  return data
}

/** Forensics: danh sách audit trail */
export async function forensicsListAudits(params?: {
  limit?: number
  offset?: number
  scenario_type?: string
  is_compliant?: boolean
}): Promise<ForensicsAuditListResponse> {
  const { data } = await client.get<ForensicsAuditListResponse>(
    '/api/v1/forensics/audit',
    { params }
  )
  return data
}

/** Forensics: chi tiết một audit record */
export async function forensicsGetAudit(
  auditId: string
): Promise<ForensicsAuditRecord> {
  const { data } = await client.get<ForensicsAuditRecord>(
    `/api/v1/forensics/audit/${auditId}`
  )
  return data
}

/** Tra cứu / hỏi đáp pháp lý (Legal RAG) */
export async function traCuuLuat(
  query: string
): Promise<{ answer: string; context: string }> {
  const { data } = await client.post<{ answer: string; context: string }>(
    '/api/v1/tra-cuu-luat',
    { query }
  )
  return data
}

// Re-export
export { AxiosError }
