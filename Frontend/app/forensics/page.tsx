'use client'

import { useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import {
  Shield, Play, Loader2, CheckCircle2, XCircle, AlertTriangle,
  Sparkles, Zap, Scale, Clock, Database,
} from 'lucide-react'
import {
  forensicsVerify,
  ForensicsVerifyResponse,
  ForensicsViolation,
  extractErrorMessage,
} from '@/lib/api'

const EXAMPLES = [
  {
    label: 'Sinh trắc học',
    text: 'Hệ thống xử lý vân tay 500 nhân viên, chưa có phân quyền truy cập',
  },
  {
    label: 'Chuyển biên giới',
    text: 'Chuyển dữ liệu GPS nhân viên lên AWS, nộp hồ sơ sau 80 ngày',
  },
  {
    label: 'Tuân thủ',
    text: 'Lưu tên và SĐT khách hàng, có mã hóa AES-256 và RBAC',
  },
  {
    label: 'Trái phiếu',
    text: 'Phát hành trái phiếu 100 tỷ, chưa kiểm toán BCTC',
  },
]

const RULE_LABELS: Record<string, string> = {
  vn_data_protection_nd356: 'Bảo vệ dữ liệu cá nhân (NĐ 356/2025)',
  vn_data_law_nd165: 'Luật dữ liệu (NĐ 165/2025)',
  vn_bond_nd200: 'Trái phiếu doanh nghiệp (NĐ 200/2026)',
  vn_tax_mgmt_nd252: 'Quản lý thuế (NĐ 252/2026)',
  vn_tax_register_tt90: 'Đăng ký thuế (TT 90/2026)',
}

const THRESHOLD_LABELS: Record<string, string> = {
  CROSS_BORDER_DOSSIER_DAYS: 'Thời hạn nộp hồ sơ chuyển dữ liệu xuyên biên giới',
  NATIONAL_SECURITY_BASIC_THRESHOLD: 'Ngưỡng bản ghi dữ liệu cơ bản (an ninh quốc gia)',
  NATIONAL_SECURITY_SENSITIVE_THRESHOLD: 'Ngưỡng bản ghi dữ liệu nhạy cảm (an ninh quốc gia)',
  BREACH_NOTICE_HOURS: 'Thời hạn thông báo sự cố lộ dữ liệu (giờ)',
  BREACH_RETENTION_YEARS: 'Thời gian lưu hồ sơ sự cố (năm)',
  IMPORTANT_DATA_REVIEW_DAYS: 'Thời hạn rà soát dữ liệu quan trọng (ngày)',
  DISCLOSURE_DAYS_LIMIT: 'Thời hạn công bố thông tin trái phiếu (ngày)',
  MIN_EQUITY_BILLION_VND: 'Vốn chủ sở hữu tối thiểu (tỷ VNĐ)',
  LATE_PAYMENT_PENALTY_RATE_PERMILLE: 'Lãi chậm nộp thuế (‰/ngày)',
  INSPECTION_STATUTE_OF_LIMITATIONS_YEARS: 'Thời hiệu thanh tra thuế (năm)',
}

function stripAnsi(s: string): string {
  return s
    .replace(/\u001b\[[0-9;]*m/g, '')
    .replace(/\x1b\[[0-9;]*m/g, '')
    .replace(/\[(?:\d{1,3}(?:;\d{1,3})*)?m/g, '')
}

function ruleTitle(name: string): string {
  if (RULE_LABELS[name]) return RULE_LABELS[name]
  // heuristic: vn_data_protection_nd356 → đọc được hơn
  return name
    .replace(/^vn_/, '')
    .replace(/_/g, ' ')
    .replace(/\bnd(\d+)/i, 'NĐ $1')
    .replace(/\btt(\d+)/i, 'TT $1')
}

function splitViolationPoints(detail: string): string[] {
  const clean = stripAnsi(detail)
  return clean
    .split(/\n\n+|(?=Căn cứ )/g)
    .map((s) => s.replace(/\s+/g, ' ').trim())
    .filter(Boolean)
}

function ViolationCards({ violations }: { violations: ForensicsViolation[] }) {
  const points: { title: string; body: string; ref: string }[] = []
  for (const v of violations) {
    const parts = splitViolationPoints(v.violation_detail)
    const title = ruleTitle(v.rule_name)
    for (const p of parts) {
      points.push({
        title,
        body: p,
        ref: v.legal_reference || '',
      })
    }
  }

  if (points.length === 0) return null

  return (
    <div>
      <p className="mb-3 text-[11px] font-semibold uppercase tracking-[0.16em] text-slate-500">
        Đã phát hiện {points.length} vấn đề cần xử lý
      </p>
      <ul className="space-y-3">
        {points.map((p, i) => (
          <motion.li
            key={`${p.title}-${i}`}
            initial={{ opacity: 0, x: -10 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ delay: 0.06 + i * 0.05 }}
            className="rounded-xl border border-red-500/25 bg-red-950/30 px-4 py-3.5"
          >
            <p className="text-sm font-semibold text-red-300">
              Vấn đề {i + 1}: {p.title}
            </p>
            <p className="mt-2 text-sm leading-relaxed text-slate-300">{p.body}</p>
            {p.ref && (
              <p className="mt-2 text-xs text-slate-500">Căn cứ: {p.ref}</p>
            )}
          </motion.li>
        ))}
      </ul>
    </div>
  )
}

function ThresholdHuman({ data }: { data: Record<string, unknown> }) {
  const entries = Object.entries(data)
  if (!entries.length) return null
  return (
    <div className="surface-glass rounded-xl p-4">
      <p className="mb-3 text-[10px] font-semibold uppercase tracking-[0.16em] text-slate-500">
        Ngưỡng pháp lý đang áp dụng
      </p>
      <ul className="space-y-2">
        {entries.map(([k, v]) => (
          <li
            key={k}
            className="flex flex-wrap items-baseline justify-between gap-2 border-b border-white/5 pb-2 text-sm last:border-0 last:pb-0"
          >
            <span className="text-slate-400">
              {THRESHOLD_LABELS[k] || k}
            </span>
            <span className="font-mono text-teal-300/90">
              {typeof v === 'number' ? v.toLocaleString('vi-VN') : String(v)}
            </span>
          </li>
        ))}
      </ul>
    </div>
  )
}

export default function ForensicsPage() {
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState<ForensicsVerifyResponse | null>(null)
  const [error, setError] = useState<string | null>(null)

  const runVerify = async () => {
    if (input.trim().length < 3) {
      setError('Vui lòng nhập mô tả hoạt động (ít nhất 3 ký tự).')
      return
    }
    setLoading(true)
    setError(null)
    setResult(null)
    try {
      const data = await forensicsVerify(input.trim())
      setResult(data)
    } catch (err) {
      setError(extractErrorMessage(err))
    } finally {
      setLoading(false)
    }
  }

  const isSat = result?.z3_status === 'SAT'
  const isUnsat = result?.z3_status === 'UNSAT'

  return (
    <div className="relative mx-auto max-w-5xl px-6 py-10 md:px-10 md:py-14">
      <motion.header
        initial={{ opacity: 0, y: 18 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.55, ease: [0.22, 1, 0.36, 1] }}
        className="mb-10"
      >
        <div className="mb-4 inline-flex items-center gap-2 rounded-full border border-teal-400/20 bg-teal-400/10 px-3 py-1 text-[11px] font-medium uppercase tracking-[0.18em] text-teal-300">
          <Sparkles className="h-3.5 w-3.5" />
          TrustAgent · Forensics
        </div>
        <h1 className="font-display text-4xl font-bold tracking-tight text-white md:text-5xl">
          Kiểm chứng pháp lý
          <span className="block bg-gradient-to-r from-teal-300 via-cyan-300 to-sky-400 bg-clip-text text-transparent">
            bằng toán học Z3
          </span>
        </h1>
        <p className="mt-4 max-w-2xl text-base leading-relaxed text-slate-400">
          Mô tả hoạt động bằng tiếng Việt. TrustAgent hiểu ngữ nghĩa → tra ngưỡng luật →
          Z3 chứng minh tuân thủ (SAT) hoặc vi phạm (UNSAT).
        </p>

        <div className="mt-4 flex items-start gap-2 rounded-xl border border-sky-400/15 bg-sky-500/5 px-3.5 py-3 text-xs leading-relaxed text-slate-400">
          <Database className="mt-0.5 h-3.5 w-3.5 shrink-0 text-sky-400" />
          <span>
            Sắp tới Forensics sẽ tự quét cơ sở dữ liệu doanh nghiệp — hiện tại đang mô phỏng
            bằng mô tả + ngữ cảnh trong ô nhập liệu bên dưới.
          </span>
        </div>

        <div className="mt-5 flex flex-wrap gap-4 text-xs text-slate-500">
          {[
            { icon: Zap, t: 'Hiểu ngôn ngữ' },
            { icon: Scale, t: 'Tra cứu luật' },
            { icon: Shield, t: 'Chứng minh Z3' },
          ].map(({ icon: Icon, t }) => (
            <span
              key={t}
              className="inline-flex items-center gap-1.5 rounded-lg border border-white/5 bg-white/[0.03] px-2.5 py-1.5"
            >
              <Icon className="h-3.5 w-3.5 text-teal-400/80" />
              {t}
            </span>
          ))}
        </div>
      </motion.header>

      <motion.section
        initial={{ opacity: 0, y: 16 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.08, duration: 0.5 }}
        className="surface-glass relative overflow-hidden rounded-2xl p-5 md:p-7"
      >
        <label className="mb-2 block text-[11px] font-semibold uppercase tracking-[0.16em] text-slate-500">
          Mô tả hoạt động cần kiểm chứng
        </label>
        <textarea
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) runVerify()
          }}
          rows={4}
          placeholder="Ví dụ: Hệ thống xử lý vân tay nhân viên, chưa có phân quyền truy cập…"
          className="w-full resize-none rounded-xl border border-white/10 bg-ink-950/70 px-4 py-3.5 text-sm leading-relaxed text-slate-100 placeholder:text-slate-600 outline-none transition focus:border-teal-400/40 focus:ring-2 focus:ring-teal-400/20"
        />

        <div className="mt-4 flex flex-wrap gap-2">
          {EXAMPLES.map((ex, i) => (
            <motion.button
              key={ex.label}
              type="button"
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.12 + i * 0.04 }}
              onClick={() => setInput(ex.text)}
              className="rounded-lg border border-white/8 bg-white/[0.03] px-3 py-1.5 text-left text-xs text-slate-400 transition hover:border-teal-400/30 hover:bg-teal-400/5 hover:text-teal-200"
            >
              <span className="mr-1.5 font-medium text-teal-500/80">{ex.label}</span>
              {ex.text.length > 42 ? `${ex.text.slice(0, 42)}…` : ex.text}
            </motion.button>
          ))}
        </div>

        <div className="mt-6 flex flex-wrap items-center gap-3">
          <button
            type="button"
            onClick={runVerify}
            disabled={loading}
            className="group relative inline-flex items-center gap-2 overflow-hidden rounded-xl bg-gradient-to-r from-teal-500 to-cyan-500 px-6 py-3 text-sm font-semibold text-ink-950 shadow-[0_0_28px_rgba(45,212,191,0.25)] transition hover:brightness-110 disabled:opacity-60"
          >
            {loading ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <Play className="h-4 w-4 transition group-hover:translate-x-0.5" />
            )}
            {loading ? 'Đang kiểm chứng…' : 'Kiểm chứng ngay'}
          </button>
          <span className="text-[11px] text-slate-600">Ctrl / ⌘ + Enter</span>
        </div>
      </motion.section>

      <AnimatePresence mode="wait">
        {error && (
          <motion.div
            key="err"
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0 }}
            className="mt-5 flex items-start gap-3 rounded-xl border border-red-500/30 bg-red-950/40 px-4 py-3 text-sm text-red-300"
          >
            <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
            {error}
          </motion.div>
        )}

        {result && (
          <motion.div
            key="res"
            initial={{ opacity: 0, y: 20, scale: 0.98 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.45, ease: [0.22, 1, 0.36, 1] }}
            className="mt-6 space-y-4"
          >
            <div
              className={`surface-glass relative overflow-hidden rounded-2xl p-6 ${
                isSat
                  ? 'ring-1 ring-emerald-400/25 shadow-[0_0_40px_rgba(16,185,129,0.12)]'
                  : isUnsat
                    ? 'ring-1 ring-red-400/25 shadow-[0_0_40px_rgba(239,68,68,0.12)]'
                    : ''
              }`}
            >
              <div
                className={`absolute -right-8 -top-8 h-40 w-40 rounded-full blur-3xl ${
                  isSat ? 'bg-emerald-500/20' : isUnsat ? 'bg-red-500/20' : 'bg-amber-500/15'
                }`}
              />

              <div className="relative flex flex-wrap items-center gap-4">
                {result.is_compliant ? (
                  <CheckCircle2 className="h-10 w-10 text-emerald-400" />
                ) : (
                  <XCircle className="h-10 w-10 text-red-400" />
                )}
                <div>
                  <p
                    className={`font-display text-2xl font-bold tracking-tight ${
                      isSat
                        ? 'text-emerald-400'
                        : isUnsat
                          ? 'text-red-400'
                          : 'text-amber-400'
                    }`}
                  >
                    {isSat
                      ? 'SAT — Tuân thủ pháp luật'
                      : isUnsat
                        ? 'UNSAT — Vi phạm pháp luật'
                        : 'Chưa đủ thông tin để kết luận'}
                  </p>
                  <p className="mt-1 flex flex-wrap items-center gap-3 text-xs text-slate-500">
                    <span className="inline-flex items-center gap-1">
                      <Clock className="h-3 w-3" />
                      {result.duration_ms.toFixed(0)} ms
                    </span>
                    <span className="font-mono">#{result.audit_id.slice(0, 8)}</span>
                  </p>
                </div>
                <span
                  className={`ml-auto rounded-lg px-3 py-1.5 text-xs font-bold tracking-wider ${
                    result.is_compliant
                      ? 'bg-emerald-500/15 text-emerald-300 ring-1 ring-emerald-400/30'
                      : 'bg-red-500/15 text-red-300 ring-1 ring-red-400/30'
                  }`}
                >
                  {result.is_compliant ? 'CHO PHÉP' : 'CHẶN NGAY'}
                </span>
              </div>

              <div className="relative mt-5 rounded-xl border border-white/5 bg-ink-950/50 p-4">
                <p className="mb-2 text-[10px] font-semibold uppercase tracking-[0.16em] text-slate-500">
                  Báo cáo kiểm chứng
                </p>
                <pre
                  className={`whitespace-pre-wrap font-sans text-sm leading-relaxed ${
                    isSat ? 'text-emerald-100/90' : isUnsat ? 'text-red-100/90' : 'text-slate-300'
                  }`}
                >
                  {stripAnsi(result.explanation)}
                </pre>
              </div>
            </div>

            <ViolationCards violations={result.violations} />
            <ThresholdHuman data={result.legal_thresholds} />
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}
