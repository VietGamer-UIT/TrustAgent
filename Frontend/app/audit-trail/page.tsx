'use client'

import { useCallback, useEffect, useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import {
  RefreshCw, ScrollText, CheckCircle2, XCircle, AlertTriangle, Loader2,
  Filter,
} from 'lucide-react'
import {
  forensicsListAudits,
  ForensicsAuditRecord,
  extractErrorMessage,
} from '@/lib/api'

function stripAnsi(s: string): string {
  return s
    .replace(/\u001b\[[0-9;]*m/g, '')
    .replace(/\x1b\[[0-9;]*m/g, '')
    .replace(/\[(?:\d{1,3}(?:;\d{1,3})*)?m/g, '')
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

  useEffect(() => {
    load()
  }, [load])

  return (
    <div className="relative mx-auto max-w-5xl px-6 py-10 md:px-10 md:py-14">
      <motion.header
        initial={{ opacity: 0, y: 16 }}
        animate={{ opacity: 1, y: 0 }}
        className="mb-8 flex flex-wrap items-end justify-between gap-4"
      >
        <div>
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
        </div>

        <div className="flex items-center gap-2">
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
        </div>
      </motion.header>

      {error && (
        <div className="mb-4 flex items-start gap-2 rounded-xl border border-red-500/25 bg-red-950/35 px-4 py-3 text-sm text-red-300">
          <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
          {error}
        </div>
      )}

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
            {items.map((item, idx) => {
              const isSat = item.z3_status === 'SAT'
              const isUnsat = item.z3_status === 'UNSAT'
              return (
                <motion.li
                  key={item.id}
                  initial={{ opacity: 0, y: 12 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ delay: Math.min(idx * 0.04, 0.35) }}
                  className={`surface-glass rounded-2xl p-4 ${
                    isSat
                      ? 'ring-1 ring-emerald-400/20'
                      : isUnsat
                        ? 'ring-1 ring-red-400/20'
                        : ''
                  }`}
                >
                  <div className="mb-2 flex flex-wrap items-center gap-3">
                    {item.is_compliant ? (
                      <CheckCircle2 className="h-5 w-5 text-emerald-400" />
                    ) : (
                      <XCircle className="h-5 w-5 text-red-400" />
                    )}
                    <span
                      className={`text-sm font-bold ${
                        isSat
                          ? 'text-emerald-400'
                          : isUnsat
                            ? 'text-red-400'
                            : 'text-amber-400'
                      }`}
                    >
                      {isSat
                        ? 'SAT — Tuân thủ'
                        : isUnsat
                          ? 'UNSAT — Vi phạm'
                          : item.z3_status ?? 'UNKNOWN'}
                    </span>
                    <span className="ml-auto text-xs text-slate-500">
                      {item.created_at
                        ? new Date(item.created_at).toLocaleString('vi-VN')
                        : '—'}
                    </span>
                  </div>
                  <p className="text-sm text-slate-200">{item.user_input}</p>
                  {item.explanation && (
                    <pre
                      className={`mt-3 max-h-40 overflow-y-auto whitespace-pre-wrap rounded-lg border border-white/5 bg-ink-950/60 p-3 font-sans text-xs leading-relaxed ${
                        isSat
                          ? 'text-emerald-200/85'
                          : isUnsat
                            ? 'text-red-200/85'
                            : 'text-slate-400'
                      }`}
                    >
                      {stripAnsi(item.explanation)}
                    </pre>
                  )}
                </motion.li>
              )
            })}
          </AnimatePresence>
        </ul>
      )}
    </div>
  )
}
