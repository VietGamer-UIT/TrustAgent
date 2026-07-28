'use client'

import { useState } from 'react'
import { motion } from 'framer-motion'
import {
  BookOpen, Search, Loader2,
} from 'lucide-react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { traCuuLuat, extractErrorMessage } from '@/lib/api'

const SUGGESTIONS = [
  'Xử lý dữ liệu vân tay nhân viên cần biện pháp gì theo Nghị định 356?',
  'Thời hạn thông báo sự cố lộ dữ liệu cá nhân là bao lâu?',
  'Điều kiện phát hành trái phiếu doanh nghiệp theo Nghị định 200?',
  'Mức phạt vi phạm hợp đồng thương mại tối đa bao nhiêu phần trăm?',
]

export default function LegalKnowledgePage() {
  const [query, setQuery] = useState('')
  const [answer, setAnswer] = useState('')
  const [context, setContext] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  const runSearch = async (q: string) => {
    const text = q.trim()
    if (!text) return
    setLoading(true)
    setAnswer('')
    setContext('')
    setError('')
    try {
      const data = await traCuuLuat(text)
      setAnswer(data.answer || 'Không có câu trả lời.')
      setContext(data.context || '')
    } catch (err: unknown) {
      setError(
        'Không gọi được Backend TrustAgent. Kiểm tra container backend (:8000). Chi tiết: ' +
          extractErrorMessage(err)
      )
    } finally {
      setLoading(false)
    }
  }

  const handleSearch = async (e: React.FormEvent) => {
    e.preventDefault()
    await runSearch(query)
  }

  return (
    <div className="relative mx-auto flex h-full max-w-4xl flex-col overflow-hidden px-6 py-10 md:px-10">
      <motion.header
        initial={{ opacity: 0, y: 14 }}
        animate={{ opacity: 1, y: 0 }}
        className="mb-8 shrink-0"
      >
        <div className="mb-3 flex items-center gap-2 text-teal-400">
          <BookOpen className="h-5 w-5" />
          <span className="text-[11px] font-semibold uppercase tracking-[0.18em]">
            TrustAgent · Tra cứu luật
          </span>
        </div>
        <h1 className="font-display text-3xl font-bold tracking-tight text-white md:text-4xl">
          Hỏi đáp pháp lý
        </h1>
        <p className="mt-2 text-sm text-slate-400">
          Đặt câu hỏi bằng tiếng Việt — TrustAgent tìm trong kho Nghị định / Thông tư và trả lời.
        </p>
      </motion.header>

      <form onSubmit={handleSearch} className="mb-4 flex shrink-0 gap-3">
        <div className="relative flex-1">
          <Search className="pointer-events-none absolute left-3.5 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-500" />
          <input
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Ví dụ: Thời hạn thông báo lộ dữ liệu cá nhân là bao lâu?"
            className="w-full rounded-xl border border-white/10 bg-ink-900/70 py-3 pl-10 pr-4 text-sm text-slate-100 outline-none transition focus:border-teal-400/40 focus:ring-2 focus:ring-teal-400/15"
          />
        </div>
        <button
          type="submit"
          disabled={loading}
          className="inline-flex items-center gap-2 rounded-xl bg-gradient-to-r from-teal-500 to-cyan-500 px-5 py-3 text-sm font-semibold text-ink-950 disabled:opacity-50"
        >
          {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Search className="h-4 w-4" />}
          Hỏi
        </button>
      </form>

      <div className="mb-6 flex shrink-0 flex-wrap gap-2">
        {SUGGESTIONS.map((s) => (
          <button
            key={s}
            type="button"
            onClick={() => {
              setQuery(s)
              void runSearch(s)
            }}
            className="rounded-lg border border-white/8 bg-white/[0.03] px-3 py-1.5 text-left text-xs text-slate-400 transition hover:border-teal-400/30 hover:text-teal-200"
          >
            {s.length > 56 ? `${s.slice(0, 56)}…` : s}
          </button>
        ))}
      </div>

      <div className="min-h-0 flex-1 space-y-4 overflow-y-auto pb-8">
        {error && (
          <div className="rounded-xl border border-red-500/25 bg-red-950/30 px-4 py-3 text-sm text-red-300">
            {error}
          </div>
        )}
        {answer && (
          <motion.div
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            className="surface-glass rounded-2xl p-5"
          >
            <p className="mb-3 text-[10px] font-semibold uppercase tracking-[0.16em] text-slate-500">
              Trả lời
            </p>
            <div className="prose prose-invert prose-sm max-w-none prose-headings:text-teal-200 prose-a:text-cyan-300">
              <ReactMarkdown remarkPlugins={[remarkGfm]}>{answer}</ReactMarkdown>
            </div>
          </motion.div>
        )}
        {context && (
          <details className="rounded-2xl border border-white/5 bg-ink-950/60 p-4">
            <summary className="cursor-pointer text-[10px] font-semibold uppercase tracking-[0.16em] text-slate-500">
              Nguồn tài liệu (RAG)
            </summary>
            <pre className="mt-3 whitespace-pre-wrap font-mono text-xs leading-relaxed text-slate-500">
              {context}
            </pre>
          </details>
        )}
      </div>
    </div>
  )
}
