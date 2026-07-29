'use client'

import { useCallback, useEffect, useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import {
  RefreshCw, ScrollText, CheckCircle2, XCircle, AlertTriangle,
  Loader2, Filter, ChevronDown, ChevronUp, Clock, Hash, Shield,
} from 'lucide-react'
import {
  forensicsListAudits,
  ForensicsAuditRecord,
  extractErrorMessage,
} from '@/lib/api'

/** Xóa ANSI color codes khỏi chuỗi */
function stripAnsi(s: string): string {
  return s
    .replace(/\u001b\[[0-9;]*m/g, '')
    .replace(/\x1b\[[0-9;]*m/g, '')
}

/** Format timestamp sang múi giờ Việt Nam GMT+7 */
function formatVNTime(isoString: string | null | undefined): string {
  if (!isoString) return '—'
  try {
    const d = new Date(isoString)
    return d.toLocaleString('vi-VN', {
      timeZone: 'Asia/Ho_Chi_Minh',
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
      day: '2-digit',
      month: '2-digit',
      year: 'numeric',
    })
  } catch {
    return isoString
  }
}

/** Parse explanation text thành danh sách vấn đề theo section */
function parseExplanation(raw: string): {
  header: string
  issues: Array<{ label: string; text: string; ref: string }>
  thresholds: Array<{ name: string; value: string }>
  footer: string
} {
  const clean = stripAnsi(raw)
  const issues: Array<{ label: string; text: string; ref: string }> = []
  const thresholds: Array<{ name: string; value: string }> = []

  // Extract issues từ numbered list hoặc section "Các vấn đề phát hiện"
  const issueMatches = clean.matchAll(
    /(?:\d+\.\s+)?Căn cứ ([^\n:]+)[:\s—–-]+([^\n]+(?:\n(?!\d+\.|Hướng|Căn cứ)[^\n]+)*)/gi
  )
  for (const m of issueMatches) {
    const ref = m[1].trim()
    const text = m[2].trim()
    const label = ref.includes('356') ? 'Bảo vệ dữ liệu cá nhân'
      : ref.includes('200') ? 'Trái phiếu doanh nghiệp'
      : ref.includes('252') ? 'Quản lý thuế'
      : ref.includes('165') ? 'Luật Dữ liệu'
      : ref.includes('90') ? 'Đăng ký thuế'
      : 'Vi phạm pháp luật'
    issues.push({ label, text, ref })
  }

  // Nếu không parse được issues, dùng plain text
  const header = issues.length === 0 ? clean.slice(0, 400) : ''
  const footer = ''

  return { header, issues, thresholds, footer }
}

/** Card một audit record */
function AuditCard({ item, index }: { item: ForensicsAuditRecord; index: number }) {
  const [expanded, setExpanded] = useState(false)
  const isSat = item.z3_status === 'SAT'
  const isUnsat = item.z3_status === 'UNSAT'
  const isUnknown = !isSat && !isUnsat

  const statusColor = isSat
    ? 'text-emerald-400'
    : isUnsat
      ? 'text-red-400'
      : 'text-amber-400'
  const ringColor = isSat
    ? 'ring-1 ring-emerald-400/25'
    : isUnsat
      ? 'ring-1 ring-red-400/25'
      : 'ring-1 ring-amber-400/15'
  const bgGlow = isSat
    ? 'before:absolute before:inset-0 before:rounded-2xl before:bg-emerald-400/[0.03]'
    : isUnsat
      ? 'before:absolute before:inset-0 before:rounded-2xl before:bg-red-400/[0.03]'
      : ''

  const parsed = item.explanation ? parseExplanation(item.explanation) : null

  return (
    <motion.li
      key={item.id}
      initial={{ opacity: 0, y: 14 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: Math.min(index * 0.045, 0.4) }}
      className={`relative surface-glass rounded-2xl ${ringColor} ${bgGlow} overflow-hidden`}
    >
      {/* Header row */}
      <div className="flex flex-wrap items-start gap-3 p-4 pb-3">
        {/* Status icon */}
        <div className="mt-0.5 shrink-0">
          {isSat ? (
            <CheckCircle2 className="h-5 w-5 text-emerald-400" />
          ) : isUnsat ? (
            <XCircle className="h-5 w-5 text-red-400" />
          ) : (
            <AlertTriangle className="h-5 w-5 text-amber-400" />
          )}
        </div>

        {/* Status badge + input */}
        <div className="min-w-0 flex-1">
          <div className="mb-1 flex flex-wrap items-center gap-2">
            <span className={`text-sm font-bold ${statusColor}`}>
              {isSat ? 'SAT — Tuân thủ pháp luật'
                : isUnsat ? 'UNSAT — Vi phạm pháp luật'
                : item.z3_status ?? 'UNKNOWN'}
            </span>
            {item.violations && item.violations.length > 0 && (
              <span className="rounded-full bg-red-500/15 px-2 py-0.5 text-[10px] font-semibold text-red-400">
                {item.violations.length} vi phạm
              </span>
            )}
          </div>
          <p className="text-sm leading-snug text-slate-200">{item.user_input}</p>
        </div>

        {/* Meta */}
        <div className="ml-auto flex shrink-0 flex-col items-end gap-1">
          <div className="flex items-center gap-1 text-[11px] text-slate-500">
            <Clock className="h-3 w-3" />
            {formatVNTime(item.created_at)}
          </div>
          {item.duration_ms && (
            <span className="text-[11px] text-slate-600">{item.duration_ms} ms</span>
          )}
        </div>
      </div>

      {/* Scenario + thresholds bar */}
      {(item.scenario_type || item.legal_thresholds) && (
        <div className="mx-4 mb-3 flex flex-wrap items-center gap-2 rounded-lg border border-white/5 bg-ink-950/50 px-3 py-2">
          {item.scenario_type && (
            <div className="flex items-center gap-1.5">
              <Shield className="h-3 w-3 text-teal-500" />
              <span className="text-[11px] font-medium text-teal-400/80">
                {item.scenario_type.replace(/_/g, ' ').toUpperCase()}
              </span>
            </div>
          )}
          {item.legal_thresholds && Object.entries(item.legal_thresholds).slice(0, 3).map(([k, v]) => (
            <span key={k} className="rounded-md bg-white/[0.04] px-2 py-0.5 text-[10px] text-slate-500">
              {k.split('_').slice(-2).join(' ')}: <span className="text-slate-300">{String(v)}</span>
            </span>
          ))}
          {item.id && (
            <div className="ml-auto flex items-center gap-1 text-[10px] text-slate-600">
              <Hash className="h-2.5 w-2.5" />
              {item.id.slice(0, 8)}
            </div>
          )}
        </div>
      )}

      {/* Violations summary chips */}
      {isUnsat && item.violations && item.violations.length > 0 && (
        <div className="mx-4 mb-3 flex flex-wrap gap-2">
          {item.violations.map((v, i) => (
            <div
              key={i}
              className="flex items-start gap-1.5 rounded-lg border border-red-500/20 bg-red-950/25 px-3 py-2 text-xs"
            >
              <XCircle className="mt-0.5 h-3.5 w-3.5 shrink-0 text-red-400" />
              <div>
                <span className="font-semibold text-red-300">
                  {String(v.rule_name ?? v.rule_description ?? 'Vi phạm')}
                </span>
                {v.legal_reference && (
                  <span className="ml-1 text-red-400/70">
                    · {String(v.legal_reference).replace(/Nghị định|Thông tư/g, 'NĐ/TT')}
                  </span>
                )}
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Expand/collapse explanation */}
      {item.explanation && (
        <>
          <button
            type="button"
            onClick={() => setExpanded((p) => !p)}
            className="flex w-full items-center justify-between border-t border-white/5 px-4 py-2.5 text-left transition hover:bg-white/[0.02]"
          >
            <span className="text-[11px] font-semibold uppercase tracking-[0.14em] text-slate-500">
              Xem báo cáo đầy đủ
            </span>
            {expanded
              ? <ChevronUp className="h-4 w-4 text-slate-500" />
              : <ChevronDown className="h-4 w-4 text-slate-500" />
            }
          </button>

          <AnimatePresence>
            {expanded && (
              <motion.div
                initial={{ height: 0, opacity: 0 }}
                animate={{ height: 'auto', opacity: 1 }}
                exit={{ height: 0, opacity: 0 }}
                transition={{ duration: 0.2 }}
                className="overflow-hidden"
              >
                {/* Parsed issues */}
                {parsed && parsed.issues.length > 0 ? (
                  <div className="space-y-2 px-4 pb-4 pt-1">
                    {parsed.issues.map((issue, i) => (
                      <div
                        key={i}
                        className="rounded-xl border border-orange-500/15 bg-orange-950/20 p-3"
                      >
                        <div className="mb-1 flex flex-wrap items-center gap-2">
                          <AlertTriangle className="h-3.5 w-3.5 text-orange-400" />
                          <span className="text-[11px] font-bold uppercase tracking-wide text-orange-400">
                            Vấn đề {i + 1}: {issue.label}
                          </span>
                          <span className="text-[10px] text-slate-500">{issue.ref}</span>
                        </div>
                        <p className="text-xs leading-relaxed text-slate-300">{issue.text}</p>
                      </div>
                    ))}
                  </div>
                ) : (
                  // Fallback: raw text nhưng styled đẹp hơn
                  <div className="px-4 pb-4 pt-1">
                    <pre className="whitespace-pre-wrap rounded-xl border border-white/5 bg-ink-950/60 p-3 font-sans text-[11px] leading-relaxed text-slate-400">
                      {stripAnsi(item.explanation).slice(0, 2000)}
                    </pre>
                  </div>
                )}
              </motion.div>
            )}
          </AnimatePresence>
        </>
      )}
    </motion.li>
  )
}

export default function AuditTrailPage() {
  const [items, setItems] = useState<ForensicsAuditRecord[]>([])
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [filter, setFilter] = useState<'all' | 'compliant' | 'violation'>('all')

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const params: { limit: number; is_compliant?: boolean } = { limit: 50 }
      if (filter === 'compliant') params.is_compliant = true
      if (filter === 'violation') params.is_compliant = false
      const data = await forensicsListAudits(params)
      setItems(data.items)
      setTotal(data.total)
    } catch (err) {
      setError(extractErrorMessage(err))
    } finally {
      setLoading(false)
    }
  }, [filter])

  useEffect(() => { load() }, [load])

  const satCount = items.filter(i => i.z3_status === 'SAT').length
  const unsatCount = items.filter(i => i.z3_status === 'UNSAT').length

  return (
    <div className="relative mx-auto max-w-5xl px-6 py-10 md:px-10 md:py-14">
      {/* Header */}
      <motion.header
        initial={{ opacity: 0, y: 16 }}
        animate={{ opacity: 1, y: 0 }}
        className="mb-8"
      >
        <div className="mb-3 inline-flex items-center gap-2 text-teal-400/90">
          <ScrollText className="h-5 w-5" />
          <span className="text-[11px] font-semibold uppercase tracking-[0.18em]">
            TrustAgent · Nhật ký kiểm chứng
          </span>
        </div>
        <h1 className="font-display text-3xl font-bold tracking-tight text-white md:text-4xl">
          Audit Trail
        </h1>
        <p className="mt-2 text-sm text-slate-400">
          Lịch sử Forensics bất biến ·{' '}
          <span className="font-mono text-teal-300/80">{total}</span> bản ghi
        </p>

        {/* Stats bar */}
        {total > 0 && (
          <div className="mt-4 flex flex-wrap gap-3">
            <div className="flex items-center gap-2 rounded-xl border border-emerald-500/20 bg-emerald-950/20 px-3 py-2">
              <CheckCircle2 className="h-4 w-4 text-emerald-400" />
              <span className="text-sm font-semibold text-emerald-300">{satCount}</span>
              <span className="text-xs text-emerald-400/70">Tuân thủ</span>
            </div>
            <div className="flex items-center gap-2 rounded-xl border border-red-500/20 bg-red-950/20 px-3 py-2">
              <XCircle className="h-4 w-4 text-red-400" />
              <span className="text-sm font-semibold text-red-300">{unsatCount}</span>
              <span className="text-xs text-red-400/70">Vi phạm</span>
            </div>
            <div className="flex items-center gap-2 rounded-xl border border-white/10 bg-white/[0.03] px-3 py-2">
              <span className="text-xs text-slate-400">
                Tỷ lệ tuân thủ:{' '}
                <span className="font-bold text-white">
                  {total > 0 ? Math.round((satCount / total) * 100) : 0}%
                </span>
              </span>
            </div>
          </div>
        )}
      </motion.header>

      {/* Controls */}
      <div className="mb-6 flex flex-wrap items-center gap-3">
        <div className="relative">
          <Filter className="pointer-events-none absolute left-3 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-slate-500" />
          <select
            value={filter}
            onChange={(e) => setFilter(e.target.value as typeof filter)}
            className="appearance-none rounded-xl border border-white/10 bg-ink-900/80 py-2.5 pl-9 pr-8 text-sm text-slate-200 outline-none focus:border-teal-400/40"
          >
            <option value="all">Tất cả</option>
            <option value="compliant">Tuân thủ (SAT)</option>
            <option value="violation">Vi phạm (UNSAT)</option>
          </select>
        </div>
        <button
          type="button"
          onClick={load}
          className="inline-flex items-center gap-2 rounded-xl border border-white/10 bg-white/[0.04] px-3.5 py-2.5 text-sm text-slate-300 transition hover:border-teal-400/30 hover:text-teal-200"
        >
          <RefreshCw className={`h-4 w-4 ${loading ? 'animate-spin' : ''}`} />
          Làm mới
        </button>
        <span className="ml-auto text-[11px] text-slate-600">
          Múi giờ: Asia/Ho_Chi_Minh (GMT+7)
        </span>
      </div>

      {/* Error */}
      {error && (
        <div className="mb-4 flex items-start gap-2 rounded-xl border border-red-500/25 bg-red-950/35 px-4 py-3 text-sm text-red-300">
          <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
          {error}
        </div>
      )}

      {/* List */}
      {loading && items.length === 0 ? (
        <div className="flex items-center justify-center gap-3 py-24 text-slate-500">
          <Loader2 className="h-5 w-5 animate-spin text-teal-400" />
          Đang tải…
        </div>
      ) : items.length === 0 ? (
        <div className="rounded-2xl border border-dashed border-white/10 bg-white/[0.02] py-20 text-center">
          <ScrollText className="mx-auto mb-3 h-8 w-8 text-slate-600" />
          <p className="text-sm text-slate-500">
            Chưa có bản ghi. Chạy kiểm chứng tại trang Forensics trước.
          </p>
        </div>
      ) : (
        <ul className="space-y-3">
          <AnimatePresence initial={false}>
            {items.map((item, idx) => (
              <AuditCard key={item.id} item={item} index={idx} />
            ))}
          </AnimatePresence>
        </ul>
      )}
    </div>
  )
}
