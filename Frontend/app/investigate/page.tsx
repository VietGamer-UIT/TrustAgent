'use client'

import { useState, useRef, useCallback, DragEvent, ChangeEvent } from 'react'
import {
  FileSearch, Play, Loader2, AlertTriangle, CheckCircle2, XCircle,
  ChevronDown, ChevronRight, FileText, Building2, CalendarX, Hash,
  ShieldAlert, ClipboardList, UploadCloud, ImageOff, FileX,
} from 'lucide-react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import {
  kiemTraChungTu, uploadHoaDon,
  KetQuaKiemTra, BaoCaoKiemTra, CanhBao, KetQuaMST,
  extractErrorMessage,
} from '@/lib/api'
import {
  formatDate, severityColor, severityLabel, statusLabel,
  agentLabel, loaiCanhBaoColor, formatTien,
} from '@/lib/utils'

// ---------------------------------------------------------------------------
// Định dạng được phép upload
// ---------------------------------------------------------------------------
const DINH_DANG_DUOC_PHEP = ['.jpg', '.jpeg', '.png', '.webp', '.pdf', '.tiff', '.tif', '.bmp']
const KICH_THUOC_TOI_DA_MB = 20

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

function MucDoRuiRoBadge({ muc_do }: { muc_do: string }) {
  const c = severityColor(muc_do)
  return (
    <span className={`inline-flex items-center gap-1 rounded-full border px-2.5 py-0.5 text-xs font-semibold ${c.badge}`}>
      {severityLabel(muc_do)}
    </span>
  )
}

function CanhBaoRow({ c, idx }: { c: CanhBao; idx: number }) {
  const [open, setOpen] = useState(false)
  const colorClass = loaiCanhBaoColor(c.loai)
  return (
    <div className={`rounded-md border bg-card/50 ${severityColor(c.muc_do).border}`}>
      <button
        onClick={() => setOpen(!open)}
        className="flex w-full items-center gap-3 px-4 py-3 text-left"
        aria-expanded={open}
      >
        <span className="w-5 text-center text-xs text-muted-foreground">{idx + 1}</span>
        <span className={`rounded border px-2 py-0.5 text-[10px] font-semibold ${colorClass}`}>
          {c.loai.toUpperCase()}
        </span>
        <span className="flex-1 text-sm font-medium text-foreground truncate">
          HD: {c.so_hoa_don}
        </span>
        <MucDoRuiRoBadge muc_do={c.muc_do} />
        <span className="text-[10px] text-muted-foreground">{c.nguon}</span>
        {open ? <ChevronDown className="h-3.5 w-3.5 text-muted-foreground" />
               : <ChevronRight className="h-3.5 w-3.5 text-muted-foreground" />}
      </button>
      {open && (
        <div className="border-t border-border px-4 py-3 text-sm text-muted-foreground leading-relaxed">
          {c.mo_ta}
        </div>
      )}
    </div>
  )
}

function MSTCard({ m }: { m: KetQuaMST }) {
  const isOk = m.tinh_trang?.toLowerCase().includes('đang hoạt động')
  const hasWarning = !!m.canh_bao
  return (
    <div className={`rounded-md border p-3 text-xs ${
      hasWarning
        ? 'border-red-700/60 bg-red-950/20'
        : isOk
          ? 'border-green-700/40 bg-green-950/10'
          : 'border-yellow-700/40 bg-yellow-950/10'
    }`}>
      <div className="flex items-center justify-between mb-1.5">
        <span className="font-mono font-bold text-sm text-foreground">{m.mst}</span>
        <span className={`rounded-full px-2 py-0.5 text-[10px] font-semibold border ${
          hasWarning
            ? 'bg-red-900 text-red-300 border-red-700'
            : isOk
              ? 'bg-green-900 text-green-300 border-green-700'
              : 'bg-yellow-900 text-yellow-300 border-yellow-700'
        }`}>
          {hasWarning ? '⚠ Vi phạm' : isOk ? '✓ Hợp lệ' : '⚡ Chú ý'}
        </span>
      </div>
      <p className="font-medium text-foreground/80 mb-1">{m.ten_doanh_nghiep}</p>
      <p className="text-muted-foreground">{m.dia_chi}</p>
      <p className="text-muted-foreground">
        {m.co_quan_thue} · {m.ngay_cap ? `Cấp: ${m.ngay_cap}` : ''}
      </p>
      {m.canh_bao && (
        <p className="mt-2 text-red-400 font-medium">{m.canh_bao}</p>
      )}
    </div>
  )
}

function BaoCaoPanels({ bao_cao }: { bao_cao: BaoCaoKiemTra }) {
  const [tab, setTab] = useState<'canh_bao' | 'mst' | 'khuyen_nghi'>('canh_bao')

  const tabs = [
    { key: 'canh_bao',    label: `Cảnh Báo (${bao_cao.danh_sach_canh_bao.length})`,  icon: AlertTriangle },
    { key: 'mst',         label: `Tra Cứu MST (${bao_cao.ket_qua_mst.length})`,        icon: Building2 },
    { key: 'khuyen_nghi', label: `Khuyến Nghị (${bao_cao.khuyen_nghi.length})`,       icon: ClipboardList },
  ] as const

  return (
    <div className="space-y-4">
      <div className="flex gap-1 rounded-lg bg-secondary/30 p-1">
        {tabs.map(({ key, label, icon: Icon }) => (
          <button
            key={key}
            onClick={() => setTab(key)}
            className={`flex flex-1 items-center justify-center gap-1.5 rounded-md px-3 py-2 text-xs font-medium transition-all ${
              tab === key
                ? 'bg-background text-foreground shadow-sm'
                : 'text-muted-foreground hover:text-foreground'
            }`}
          >
            <Icon className="h-3.5 w-3.5" />
            {label}
          </button>
        ))}
      </div>

      {tab === 'canh_bao' && (
        <div className="space-y-2">
          {bao_cao.danh_sach_canh_bao.length === 0 ? (
            <div className="flex items-center gap-2 rounded-md border border-green-700/40 bg-green-950/20 px-4 py-3 text-sm text-green-400">
              <CheckCircle2 className="h-4 w-4" />
              Không phát hiện cảnh báo nào trong bộ chứng từ này.
            </div>
          ) : (
            bao_cao.danh_sach_canh_bao.map((c, i) => (
              <CanhBaoRow key={i} c={c} idx={i} />
            ))
          )}
        </div>
      )}

      {tab === 'mst' && (
        <div className="grid gap-3 sm:grid-cols-2">
          {bao_cao.ket_qua_mst.length === 0 ? (
            <p className="text-sm text-muted-foreground col-span-2">Không có dữ liệu MST.</p>
          ) : (
            bao_cao.ket_qua_mst.map((m) => <MSTCard key={m.mst} m={m} />)
          )}
        </div>
      )}

      {tab === 'khuyen_nghi' && (
        <div className="space-y-2">
          {bao_cao.khuyen_nghi.map((kn, i) => (
            <div
              key={i}
              className="flex items-start gap-3 rounded-md border border-border bg-secondary/20 px-4 py-3 text-sm text-foreground"
            >
              <span className="flex h-5 w-5 flex-shrink-0 items-center justify-center rounded-full bg-primary/15 text-[10px] font-bold text-primary">
                {i + 1}
              </span>
              <p className="leading-relaxed">{kn}</p>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// FileDropZone Component
// ---------------------------------------------------------------------------
interface FileDropZoneProps {
  file: File | null
  onFileSelect: (file: File) => void
  onFileRemove: () => void
  disabled: boolean
}

function FileDropZone({ file, onFileSelect, onFileRemove, disabled }: FileDropZoneProps) {
  const [isDragging, setIsDragging] = useState(false)
  const [dragError, setDragError] = useState<string | null>(null)
  const inputRef = useRef<HTMLInputElement>(null)

  const validateAndSet = useCallback((f: File) => {
    setDragError(null)
    const ext = '.' + f.name.split('.').pop()?.toLowerCase()
    if (!DINH_DANG_DUOC_PHEP.includes(ext)) {
      setDragError(`Định dạng "${ext}" không được hỗ trợ. Chỉ chấp nhận: JPG, PNG, PDF, WebP, BMP, TIFF.`)
      return
    }
    const sizeMb = f.size / (1024 * 1024)
    if (sizeMb > KICH_THUOC_TOI_DA_MB) {
      setDragError(`File quá lớn (${sizeMb.toFixed(1)}MB). Tối đa ${KICH_THUOC_TOI_DA_MB}MB.`)
      return
    }
    onFileSelect(f)
  }, [onFileSelect])

  const handleDrop = useCallback((e: DragEvent<HTMLDivElement>) => {
    e.preventDefault()
    setIsDragging(false)
    if (disabled) return
    const droppedFile = e.dataTransfer.files[0]
    if (droppedFile) validateAndSet(droppedFile)
  }, [disabled, validateAndSet])

  const handleDragOver = (e: DragEvent<HTMLDivElement>) => {
    e.preventDefault()
    if (!disabled) setIsDragging(true)
  }

  const handleDragLeave = () => setIsDragging(false)

  const handleInputChange = (e: ChangeEvent<HTMLInputElement>) => {
    const f = e.target.files?.[0]
    if (f) validateAndSet(f)
    // Reset input để có thể chọn lại cùng file
    e.target.value = ''
  }

  if (file) {
    // Hiển thị file đã chọn
    const sizeMb = (file.size / (1024 * 1024)).toFixed(2)
    const isImage = file.type.startsWith('image/')
    return (
      <div className="rounded-lg border border-primary/40 bg-primary/5 p-4">
        <div className="flex items-center gap-3">
          <div className="flex h-10 w-10 flex-shrink-0 items-center justify-center rounded-md border border-border bg-background">
            {isImage ? (
              <FileText className="h-5 w-5 text-primary" />
            ) : (
              <FileText className="h-5 w-5 text-primary" />
            )}
          </div>
          <div className="flex-1 min-w-0">
            <p className="text-sm font-medium text-foreground truncate">{file.name}</p>
            <p className="text-xs text-muted-foreground">{sizeMb} MB · {file.type || 'không rõ định dạng'}</p>
          </div>
          <button
            onClick={onFileRemove}
            disabled={disabled}
            className="flex-shrink-0 rounded-md p-1.5 text-muted-foreground hover:bg-destructive/10 hover:text-destructive disabled:opacity-40 transition-colors"
            aria-label="Xóa file"
          >
            <XCircle className="h-4 w-4" />
          </button>
        </div>
        {isImage && (
          <p className="mt-2 text-[11px] text-primary/70">
            ✅ File ảnh hóa đơn sẵn sàng — Gemini Vision sẽ đọc và bóc tách dữ liệu.
          </p>
        )}
      </div>
    )
  }

  return (
    <div>
      <div
        onClick={() => !disabled && inputRef.current?.click()}
        onDrop={handleDrop}
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        className={`relative flex cursor-pointer flex-col items-center justify-center gap-3 rounded-lg border-2 border-dashed px-6 py-10 text-center transition-all select-none ${
          disabled
            ? 'cursor-not-allowed opacity-50 border-border'
            : isDragging
              ? 'border-primary bg-primary/10 scale-[1.01]'
              : 'border-border hover:border-primary/60 hover:bg-secondary/30'
        }`}
      >
        <UploadCloud
          className={`h-10 w-10 transition-colors ${
            isDragging ? 'text-primary' : 'text-muted-foreground'
          }`}
        />
        <div>
          <p className="text-sm font-medium text-foreground">
            {isDragging ? 'Thả file vào đây…' : 'Kéo & thả file hóa đơn vào đây'}
          </p>
          <p className="text-xs text-muted-foreground mt-1">
            hoặc <span className="text-primary font-medium underline underline-offset-2">bấm để chọn file</span>
          </p>
          <p className="text-[11px] text-muted-foreground/70 mt-2">
            JPG · PNG · PDF · WebP · BMP · TIFF · Tối đa {KICH_THUOC_TOI_DA_MB}MB
          </p>
        </div>
      </div>
      <input
        ref={inputRef}
        type="file"
        accept={DINH_DANG_DUOC_PHEP.join(',')}
        onChange={handleInputChange}
        disabled={disabled}
        className="hidden"
        id="file-upload-input"
        aria-label="Upload file hóa đơn"
      />
      {dragError && (
        <div className="mt-2 flex items-start gap-2 rounded-md border border-red-700/50 bg-red-950/30 px-3 py-2 text-xs text-red-400">
          <FileX className="h-3.5 w-3.5 mt-0.5 flex-shrink-0" />
          {dragError}
        </div>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Main Page
// ---------------------------------------------------------------------------
type CheDoKiemTra = 'upload' | 'demo'

export default function InvestigatePage() {
  const [cheDoKiemTra, setCheDoKiemTra] = useState<CheDoKiemTra>('upload')
  const [maPhien, setMaPhien]   = useState('')
  const [selectedFile, setSelectedFile] = useState<File | null>(null)
  const [loading, setLoading]   = useState(false)
  const [error, setError]       = useState<string | null>(null)
  const [result, setResult]     = useState<KetQuaKiemTra | null>(null)
  const resultRef               = useRef<HTMLDivElement>(null)

  const handleFileSelect = (f: File) => {
    setSelectedFile(f)
    setError(null)
    setResult(null)
    // Tự động sinh mã phiên từ tên file nếu chưa có
    if (!maPhien.trim()) {
      const baseName = f.name.replace(/\.[^.]+$/, '').replace(/[^a-zA-Z0-9]/g, '-').toUpperCase()
      setMaPhien(`KT-${baseName.slice(0, 20)}-${Date.now().toString().slice(-4)}`)
    }
  }

  const submitUpload = async () => {
    if (!selectedFile) {
      setError('Vui lòng chọn file hóa đơn để upload.')
      return
    }
    setLoading(true)
    setError(null)
    setResult(null)

    try {
      const res = await uploadHoaDon(selectedFile, maPhien.trim() || undefined)
      setResult(res)
      setTimeout(() => resultRef.current?.scrollIntoView({ behavior: 'smooth' }), 100)
    } catch (err) {
      setError(extractErrorMessage(err))
    } finally {
      setLoading(false)
    }
  }

  const submitDemo = async () => {
    if (!maPhien.trim()) {
      setMaPhien('KT-2024-DEMO-001')
    }
    setLoading(true)
    setError(null)
    setResult(null)

    try {
      const res = await kiemTraChungTu({
        ma_phien: maPhien.trim() || 'KT-2024-DEMO-001',
        duong_dan_chung_tu: ['/hoa_don/tat_ca.pdf'],
      })
      setResult(res)
      setTimeout(() => resultRef.current?.scrollIntoView({ behavior: 'smooth' }), 100)
    } catch (err) {
      setError(extractErrorMessage(err))
    } finally {
      setLoading(false)
    }
  }

  const bao_cao = result?.bao_cao_kiem_tra
  const sc = bao_cao ? severityColor(bao_cao.muc_do_rui_ro) : null

  return (
    <div className="mx-auto max-w-3xl space-y-6">

      {/* ── Header ─────────────────────────────────────────────────────── */}
      <div>
        <div className="flex items-center gap-2 mb-1">
          <FileSearch className="h-5 w-5 text-primary" />
          <h1 className="text-lg font-bold text-foreground">Kiểm Tra Chứng Từ</h1>
        </div>
        <p className="text-sm text-muted-foreground">
          Upload file hóa đơn thật — Gemini Vision AI sẽ tự động đọc và phát hiện
          lỗi số học, công ty ma, gian lận ngày tháng.
        </p>
      </div>

      {/* ── Chế độ kiểm tra ─────────────────────────────────────────────── */}
      <div className="flex gap-1 rounded-lg bg-secondary/30 p-1">
        {([
          { key: 'upload', label: '📄 Upload File Thật', desc: 'Gemini Vision OCR' },
          { key: 'demo',   label: '🎯 Demo 13 Hóa Đơn',  desc: 'Mock Data Mẫu'  },
        ] as const).map(({ key, label, desc }) => (
          <button
            key={key}
            id={`tab-${key}`}
            onClick={() => {
              setCheDoKiemTra(key)
              setError(null)
              setResult(null)
            }}
            disabled={loading}
            className={`flex flex-1 flex-col items-center rounded-md px-3 py-2.5 transition-all disabled:opacity-50 ${
              cheDoKiemTra === key
                ? 'bg-background text-foreground shadow-sm'
                : 'text-muted-foreground hover:text-foreground'
            }`}
          >
            <span className="text-xs font-semibold">{label}</span>
            <span className="text-[10px] text-muted-foreground">{desc}</span>
          </button>
        ))}
      </div>

      {/* ── Input Card ──────────────────────────────────────────────────── */}
      <Card className="border-border">
        <CardHeader>
          <CardTitle className="text-sm font-semibold">
            {cheDoKiemTra === 'upload' ? 'Upload Hóa Đơn Thật' : 'Demo Mode — Dữ Liệu Mẫu'}
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-5">

          {/* Mã phiên */}
          <div className="space-y-1.5">
            <label htmlFor="ma-phien" className="text-xs font-medium text-muted-foreground uppercase tracking-wide">
              Mã Phiên Kiểm Tra
              <span className="ml-1 font-normal normal-case">(tự sinh nếu để trống)</span>
            </label>
            <input
              id="ma-phien"
              type="text"
              value={maPhien}
              onChange={(e) => setMaPhien(e.target.value)}
              disabled={loading}
              placeholder="KT-2024-001"
              className="w-full rounded-md border border-border bg-background px-3 py-2 text-sm font-mono text-foreground placeholder:text-muted-foreground/50 focus:outline-none focus:ring-2 focus:ring-primary/40 disabled:opacity-50"
            />
          </div>

          {/* Upload zone hoặc Demo note */}
          {cheDoKiemTra === 'upload' ? (
            <div className="space-y-2">
              <label className="text-xs font-medium text-muted-foreground uppercase tracking-wide">
                File Hóa Đơn / Chứng Từ
              </label>
              <FileDropZone
                file={selectedFile}
                onFileSelect={handleFileSelect}
                onFileRemove={() => { setSelectedFile(null); setError(null) }}
                disabled={loading}
              />
              <div className="rounded-md border border-blue-700/30 bg-blue-950/20 px-3 py-2 text-[11px] text-blue-400">
                🤖 <strong>Gemini Vision:</strong> AI sẽ đọc hình ảnh hóa đơn và bóc tách dữ liệu.
                Nếu file không phải hóa đơn (ảnh chó mèo, v.v.) — AI sẽ cảnh báo thay vì bị crash.
              </div>
            </div>
          ) : (
            <div className="rounded-md border border-blue-700/30 bg-blue-950/20 px-3 py-2 text-[11px] text-blue-400">
              💡 <strong>Demo mode:</strong> Tải 13 hóa đơn mẫu (gồm lỗi số học, công ty ma, ngày logic sai).
              Không cần upload file, không cần GOOGLE_API_KEY.
            </div>
          )}

          {/* Error */}
          {error && (
            <div className="flex items-start gap-2 rounded-md border border-red-700/50 bg-red-950/30 px-3 py-2.5 text-sm text-red-400">
              <XCircle className="h-4 w-4 mt-0.5 flex-shrink-0" />
              {error}
            </div>
          )}

          {/* Submit */}
          <Button
            id="btn-kiem-tra"
            onClick={cheDoKiemTra === 'upload' ? submitUpload : submitDemo}
            disabled={loading || (cheDoKiemTra === 'upload' && !selectedFile)}
            className="w-full gap-2"
          >
            {loading ? (
              <>
                <Loader2 className="h-4 w-4 animate-spin" />
                {cheDoKiemTra === 'upload' ? 'Đang OCR và phân tích…' : 'Đang phân tích chứng từ…'}
              </>
            ) : (
              <>
                <Play className="h-4 w-4" />
                {cheDoKiemTra === 'upload' ? 'Upload & Kiểm Tra Ngay' : 'Chạy Demo Kiểm Tra'}
              </>
            )}
          </Button>
        </CardContent>
      </Card>

      {/* ── Loading state ──────────────────────────────────────────────── */}
      {loading && (
        <Card className="border-primary/20 bg-primary/5">
          <CardContent className="pt-6">
            <div className="flex flex-col items-center gap-4 py-4">
              <Loader2 className="h-10 w-10 animate-spin text-primary" />
              <div className="text-center">
                <p className="text-sm font-semibold text-foreground">
                  {cheDoKiemTra === 'upload'
                    ? 'Gemini Vision đang đọc hóa đơn…'
                    : 'Đang phân tích bộ chứng từ mẫu…'}
                </p>
                <p className="text-xs text-muted-foreground mt-1">
                  {cheDoKiemTra === 'upload'
                    ? 'OCR → Bóc tách JSON → Kiểm tra số học → Tra cứu MST → Báo cáo'
                    : 'OCR đọc hóa đơn → Kiểm tra số học → Tra cứu MST → Tổng hợp báo cáo'}
                </p>
              </div>
              {/* Agent progress */}
              <div className="flex gap-3 text-[11px]">
                {['📄 Chứng Từ Agent', '🏛️ Tuân Thủ Agent', '🎯 Giám Sát'].map((a) => (
                  <div key={a} className="flex items-center gap-1 text-muted-foreground">
                    <Loader2 className="h-2.5 w-2.5 animate-spin" />
                    {a}
                  </div>
                ))}
              </div>
            </div>
          </CardContent>
        </Card>
      )}

      {/* ── Result ─────────────────────────────────────────────────────── */}
      {result && bao_cao && sc && (
        <div ref={resultRef} className="space-y-4">

          {/* Summary card */}
          <Card className={`border ${sc.border} ${sc.bg}`}>
            <CardHeader>
              <CardTitle className="flex flex-wrap items-center gap-2 text-sm">
                <ShieldAlert className={`h-4 w-4 ${sc.text}`} />
                Kết Quả Kiểm Tra — {bao_cao.ma_phien}
                <Badge variant="outline" className={sc.badge}>
                  {severityLabel(bao_cao.muc_do_rui_ro)}
                </Badge>
                <Badge variant="outline" className="ml-auto text-[10px]">
                  {statusLabel(bao_cao.trang_thai)}
                </Badge>
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <p className="text-sm text-muted-foreground leading-relaxed">{bao_cao.tom_tat}</p>

              {/* Quick stats */}
              <div className="grid grid-cols-3 gap-3 text-xs">
                <div className="rounded-md border border-border bg-background/50 p-3 text-center">
                  <p className={`text-xl font-bold ${sc.text}`}>
                    {bao_cao.danh_sach_canh_bao.filter(c => c.muc_do === 'nghiêm trọng').length}
                  </p>
                  <p className="text-muted-foreground">Nghiêm trọng</p>
                </div>
                <div className="rounded-md border border-border bg-background/50 p-3 text-center">
                  <p className="text-xl font-bold text-orange-400">
                    {bao_cao.danh_sach_canh_bao.filter(c => c.muc_do === 'cao').length}
                  </p>
                  <p className="text-muted-foreground">Cao</p>
                </div>
                <div className="rounded-md border border-border bg-background/50 p-3 text-center">
                  <p className="text-xl font-bold text-yellow-400">
                    {bao_cao.danh_sach_canh_bao.filter(c => c.muc_do === 'trung bình').length}
                  </p>
                  <p className="text-muted-foreground">Trung bình</p>
                </div>
              </div>

              {/* Meta */}
              <div className="flex flex-wrap gap-3 text-[11px] text-muted-foreground">
                <span>🔄 {bao_cao.so_vong_lap} vòng lặp</span>
                <span>🤖 {bao_cao.agents_da_chay.map(agentLabel).join(' → ')}</span>
                <span>⏱ {formatDate(bao_cao.hoan_tat_luc)}</span>
                {bao_cao.so_loi > 0 && (
                  <span className="text-yellow-400">⚠ {bao_cao.so_loi} lỗi công cụ</span>
                )}
              </div>
            </CardContent>
          </Card>

          {/* Detail tabs */}
          <BaoCaoPanels bao_cao={bao_cao} />
        </div>
      )}
    </div>
  )
}
