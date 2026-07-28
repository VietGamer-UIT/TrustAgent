'use client'

import React, { useState, useRef, DragEvent } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { Upload, FileText, X, Zap, Loader2, AlertTriangle } from 'lucide-react'
import { API_BASE } from '@/lib/api'

interface AuditLog {
  incident_id: string
  status: string
  tong_hoa_don: number
  tong_loi_thue: number
  tong_loi_phap_ly: number
  z3_status: string
  tax_warnings: any[]
  legal_violations: any[]
  messages: any[]
  timestamp?: string
  audit_trail_steps?: {
    step: string
    status: string
    details: string
  }[]
}

export default function Workspace() {
  const [files, setFiles] = useState<File[]>([])
  const [isDragging, setIsDragging] = useState(false)
  const [isLoading, setIsLoading] = useState(false)
  const [auditResult, setAuditResult] = useState<AuditLog | null>(null)
  const [error, setError] = useState<string | null>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)

  const handleDragOver = (e: DragEvent<HTMLDivElement>) => {
    e.preventDefault()
    setIsDragging(true)
  }
  const handleDragLeave = (e: DragEvent<HTMLDivElement>) => {
    e.preventDefault()
    setIsDragging(false)
  }
  const handleDrop = (e: DragEvent<HTMLDivElement>) => {
    e.preventDefault()
    setIsDragging(false)
    if (e.dataTransfer.files?.length) {
      setFiles(Array.from(e.dataTransfer.files))
    }
  }
  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files?.length) setFiles(Array.from(e.target.files))
  }
  const removeFile = (index: number) => {
    setFiles((prev) => prev.filter((_, i) => i !== index))
  }

  const startAudit = async () => {
    if (files.length === 0) {
      setError('Vui lòng tải lên ít nhất một file để bắt đầu.')
      return
    }
    setIsLoading(true)
    setError(null)
    setAuditResult(null)

    const formData = new FormData()
    files.forEach((file) => formData.append('file', file))
    formData.append(
      'contract_data',
      JSON.stringify({
        tong_gia_tri: 150000000,
        phat_vi_pham: 15000000,
        thue_suat: 8,
      })
    )

    try {
      const response = await fetch(`${API_BASE}/api/v1/kiem-tra/upload`, {
        method: 'POST',
        body: formData,
      })
      if (!response.ok) {
        throw new Error(`Lỗi server: ${response.status} ${response.statusText}`)
      }
      const data = await response.json()
      setAuditResult(data.final_audit_log ?? data.bao_cao_kiem_tra ?? data)
    } catch (err: any) {
      setError(err.message || 'Không kết nối được máy chủ TrustAgent.')
    } finally {
      setIsLoading(false)
    }
  }

  return (
    <div className="relative mx-auto max-w-5xl px-6 py-10 md:px-10 md:py-14">
      <motion.header
        initial={{ opacity: 0, y: 16 }}
        animate={{ opacity: 1, y: 0 }}
        className="mb-10"
      >
        <p className="mb-3 text-[11px] font-semibold uppercase tracking-[0.18em] text-teal-400/90">
          TrustAgent · Workspace
        </p>
        <h1 className="font-display text-4xl font-bold tracking-tight text-white md:text-5xl">
          Kiểm toán chứng từ
        </h1>
        <p className="mt-3 max-w-xl text-slate-400">
          Upload hóa đơn / bảng kê / hợp đồng để multi-agent kiểm tra thuế và pháp lý.
          Để kiểm chứng hoạt động bằng mô tả tiếng Việt (không cần upload), dùng mục{' '}
          <a href="/forensics" className="text-teal-300 underline-offset-2 hover:underline">
            Forensics
          </a>
          .
        </p>
      </motion.header>

      <motion.div
        initial={{ opacity: 0, y: 12 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.06 }}
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onDrop={handleDrop}
        onClick={() => fileInputRef.current?.click()}
        className={`surface-glass relative cursor-pointer overflow-hidden rounded-2xl border-2 border-dashed p-12 text-center transition ${
          isDragging
            ? 'border-teal-400/60 bg-teal-400/5 shadow-[0_0_40px_rgba(45,212,191,0.15)]'
            : 'border-white/10 hover:border-teal-400/35'
        }`}
      >
        <input
          type="file"
          multiple
          className="sr-only"
          ref={fileInputRef}
          onChange={handleFileChange}
        />
        <div className="mx-auto mb-4 flex h-14 w-14 items-center justify-center rounded-2xl bg-teal-400/10 text-teal-300 ring-1 ring-teal-400/25">
          <Upload className="h-6 w-6" />
        </div>
        <p className="text-sm font-medium text-slate-200">
          Kéo thả file vào đây, hoặc{' '}
          <span className="text-teal-300 underline-offset-2 hover:underline">chọn file</span>
        </p>
        <p className="mt-2 text-xs text-slate-500">XML, CSV, TSV, XLSX · tối đa 50MB</p>
      </motion.div>

      <AnimatePresence>
        {files.length > 0 && (
          <motion.ul
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: 'auto' }}
            exit={{ opacity: 0 }}
            className="mt-5 space-y-2"
          >
            {files.map((file, index) => (
              <li
                key={`${file.name}-${index}`}
                className="surface-glass flex items-center justify-between rounded-xl px-4 py-3"
              >
                <span className="flex items-center gap-2 truncate text-sm text-slate-300">
                  <FileText className="h-4 w-4 shrink-0 text-teal-400/70" />
                  {file.name}
                </span>
                <button
                  type="button"
                  onClick={(e) => {
                    e.stopPropagation()
                    removeFile(index)
                  }}
                  className="rounded-lg p-1.5 text-slate-500 transition hover:bg-red-500/10 hover:text-red-400"
                >
                  <X className="h-4 w-4" />
                </button>
              </li>
            ))}
          </motion.ul>
        )}
      </AnimatePresence>

      <div className="mt-8 flex flex-wrap items-center justify-between gap-3">
        {error ? (
          <p className="flex items-center gap-2 text-sm text-red-400">
            <AlertTriangle className="h-4 w-4" />
            {error}
          </p>
        ) : (
          <span />
        )}
        <button
          type="button"
          onClick={startAudit}
          disabled={isLoading || files.length === 0}
          className="inline-flex items-center gap-2 rounded-xl bg-gradient-to-r from-teal-500 to-cyan-500 px-6 py-3 text-sm font-semibold text-ink-950 shadow-[0_0_28px_rgba(45,212,191,0.22)] transition hover:brightness-110 disabled:cursor-not-allowed disabled:opacity-45"
        >
          {isLoading ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : (
            <Zap className="h-4 w-4" />
          )}
          {isLoading ? 'Đang phân tích…' : 'Bắt đầu kiểm toán'}
        </button>
      </div>

      <AnimatePresence>
        {auditResult && (
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            className="mt-10 space-y-4"
          >
            <div className="surface-glass rounded-2xl p-5">
              <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
                <h2 className="font-display text-xl font-semibold text-white">
                  Kết quả kiểm toán
                </h2>
                <span
                  className={`rounded-lg px-3 py-1 text-xs font-bold tracking-wide ${
                    auditResult.z3_status === 'UNSAT'
                      ? 'bg-red-500/15 text-red-300 ring-1 ring-red-400/30'
                      : 'bg-emerald-500/15 text-emerald-300 ring-1 ring-emerald-400/30'
                  }`}
                >
                  {auditResult.z3_status === 'UNSAT' ? 'VI PHẠM' : 'HỢP LỆ'}
                </span>
              </div>

              <div className="mb-5 grid grid-cols-1 gap-3 sm:grid-cols-3">
                {[
                  { label: 'Chứng từ', value: auditResult.tong_hoa_don ?? 0 },
                  { label: 'Cảnh báo thuế', value: auditResult.tong_loi_thue ?? 0 },
                  { label: 'Lỗi pháp lý Z3', value: auditResult.tong_loi_phap_ly ?? 0 },
                ].map((s) => (
                  <div
                    key={s.label}
                    className="rounded-xl border border-white/5 bg-ink-950/50 px-4 py-3"
                  >
                    <p className="text-[11px] uppercase tracking-wider text-slate-500">
                      {s.label}
                    </p>
                    <p className="mt-1 font-display text-2xl font-bold text-teal-300">
                      {s.value}
                    </p>
                  </div>
                ))}
              </div>

              <div className="relative overflow-hidden rounded-xl border border-white/5 bg-ink-950 p-5 font-mono text-[13px] leading-relaxed text-slate-300">
                <div className="mb-4 flex items-center gap-2 border-b border-white/5 pb-2 text-[10px] uppercase tracking-[0.2em] text-slate-500">
                  <span className="h-2 w-2 animate-pulse rounded-full bg-red-500" />
                  Live Forensic Stream
                </div>
                <div className="text-teal-400/80">
                  ======================================================================
                </div>
                <div className="my-1 font-bold tracking-wide text-teal-300">
                  🛡️ TRUSTAGENT — AUDIT TRAIL LOG
                </div>
                <div className="mb-4 text-teal-400/80">
                  ======================================================================
                </div>

                <div className="mb-3 text-sky-400 font-semibold">[THÔNG TIN GIAO DỊCH]</div>
                <div>Hoạt động : Phân tích hồ sơ ({auditResult.tong_hoa_don} files)</div>
                <div>ID Phiên : {auditResult.incident_id}</div>
                <div>Thời gian : {auditResult.timestamp || new Date().toISOString()}</div>

                {auditResult.audit_trail_steps?.length ? (
                  <div className="mt-4">
                    <div className="mb-1 font-semibold text-cyan-300">
                      [TIẾN TRÌNH LANGGRAPH]
                    </div>
                    {auditResult.audit_trail_steps.map((step, idx) => (
                      <div key={idx} className="flex flex-wrap gap-2">
                        <span className="text-slate-600">Step {idx + 1}:</span>
                        <span>{step.step}</span>
                        <span
                          className={
                            step.status === 'PASS'
                              ? 'text-emerald-400'
                              : step.status === 'FAIL'
                                ? 'text-red-400'
                                : 'text-amber-400'
                          }
                        >
                          [{step.status}] {step.details}
                        </span>
                      </div>
                    ))}
                  </div>
                ) : null}

                <div className="mt-4 font-semibold text-sky-400">
                  [KẾT QUẢ Z3]
                </div>
                <div>
                  {auditResult.z3_status === 'UNSAT' ? (
                    <span className="font-bold text-red-400">
                      🚫 CHẶN THỰC THI NGAY LẬP TỨC
                    </span>
                  ) : (
                    <span className="font-bold text-emerald-400">
                      ✅ HỢP LỆ, CHO PHÉP THỰC THI
                    </span>
                  )}
                </div>

                {auditResult.legal_violations?.length > 0 && (
                  <div className="mt-4">
                    <div className="mb-2 font-bold text-red-400">
                      [DẪN CHỨNG VI PHẠM]
                    </div>
                    {auditResult.legal_violations.map((violation: any, idx: number) => (
                      <div key={idx} className="mb-3 border-l border-red-800 pl-3">
                        <div className="font-bold text-red-300">
                          VI PHẠM {idx + 1}: {violation.rule || String(violation)}
                        </div>
                        {violation.legal_basis && (
                          <div className="mt-1 whitespace-pre-wrap text-amber-300/90">
                            {violation.legal_basis}
                          </div>
                        )}
                        {violation.description && (
                          <div className="mt-1 text-slate-400">{violation.description}</div>
                        )}
                      </div>
                    ))}
                  </div>
                )}

                <div className="mt-4 text-teal-400/80">
                  ======================================================================
                </div>
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}
