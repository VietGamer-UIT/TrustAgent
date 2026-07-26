'use client'

import { useState, useEffect } from 'react'
import Link from 'next/link'
import {
  FileSearch, ScrollText, Zap,
  Database, Cpu, ArrowRight, CheckCircle2, XCircle,
  FileText, ShieldAlert, BarChart3, RefreshCw,
} from 'lucide-react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { checkHealth, getTrangThaiPipeline, TrangThaiPipeline, API_BASE } from '@/lib/api'
import { formatDate } from '@/lib/utils'

type SystemStatus = 'checking' | 'online' | 'offline'

// ---------------------------------------------------------------------------
// Stat cards
// ---------------------------------------------------------------------------
const STATS = [
  { icon: FileText,    label: 'Hóa Đơn Đã Soát',      value: '—',   color: 'text-blue-400'   },
  { icon: ShieldAlert, label: 'Cảnh Báo Phát Hiện',    value: '—',   color: 'text-red-400'    },
  { icon: Cpu,         label: 'Agents Đang Hoạt Động', value: '2',   color: 'text-cyan-400'   },
  { icon: Database,    label: 'MST Trong Cache',        value: '—',   color: 'text-green-400'  },
]

// ---------------------------------------------------------------------------
// Feature cards
// ---------------------------------------------------------------------------
const FEATURES = [
  {
    icon: FileSearch,
    title: '🔍 Kiểm Tra Chứng Từ',
    desc: 'Nhập mã phiên và đường dẫn hóa đơn. Hệ thống AI đa tác nhân (Chứng Từ → Tuân Thủ → Giám Sát) tự động phân tích và xuất báo cáo cảnh báo.',
    href: '/investigate',
    cta: 'Bắt đầu kiểm tra',
    color: 'border-blue-700/30 hover:border-blue-500/50 hover:bg-blue-950/20',
  },
  {
    icon: ScrollText,
    title: '📋 Nhật Ký Kiểm Toán',
    desc: 'Mỗi hành động được ghi bất biến vào PostgreSQL với SHA-256 hash. Tra cứu theo mã phiên để xem toàn bộ lịch sử phân tích.',
    href: '/audit',
    cta: 'Xem nhật ký',
    color: 'border-purple-700/30 hover:border-purple-500/50 hover:bg-purple-950/20',
  },
]

// ---------------------------------------------------------------------------
// Architecture cards
// ---------------------------------------------------------------------------
const ARCH_CARDS = [
  {
    icon: '📄',
    name: 'Chứng Từ Agent',
    desc: 'OCR đọc hóa đơn PDF/XML. Kiểm tra lỗi số học VAT, trùng số, lỗi format MST.',
    color: 'border-blue-700/40',
  },
  {
    icon: '🏛️',
    name: 'Tuân Thủ Agent',
    desc: 'Tra cứu MST từ Local Cache (PostgreSQL). Phát hiện công ty ma, lỗi ngày logic, hóa đơn không hợp lệ.',
    color: 'border-emerald-700/40',
  },
  {
    icon: '🎯',
    name: 'Giám Sát Agent',
    desc: 'Điều phối luồng, tổng hợp báo cáo rủi ro, tạo khuyến nghị cho kiểm toán viên.',
    color: 'border-orange-700/40',
  },
  {
    icon: '⚡',
    name: 'Data Pipeline',
    desc: 'Tự động cào MST từ masothue.com, cập nhật định kỳ vào PostgreSQL. Độ trễ tra cứu < 5ms.',
    color: 'border-purple-700/40',
  },
]

// ---------------------------------------------------------------------------
// Page Component
// ---------------------------------------------------------------------------
export default function DashboardPage() {
  const [status, setStatus] = useState<SystemStatus>('checking')
  const [serviceName, setServiceName] = useState('')
  const [pipeline, setPipeline] = useState<TrangThaiPipeline | null>(null)

  useEffect(() => {
    checkHealth()
      .then((res) => {
        setStatus('online')
        setServiceName(res.service)
      })
      .catch(() => setStatus('offline'))

    getTrangThaiPipeline()
      .then(setPipeline)
      .catch(() => {/* pipeline optional */})
  }, [])

  return (
    <div className="mx-auto max-w-5xl space-y-8">

      {/* ── Hero ─────────────────────────────────────────────────────────── */}
      <div className="relative overflow-hidden rounded-xl border border-primary/20 bg-gradient-to-br from-primary/10 via-background to-background p-8">
        {/* Background glow */}
        <div className="pointer-events-none absolute -right-20 -top-20 h-64 w-64 rounded-full bg-primary/5 blur-3xl" />
        <div className="pointer-events-none absolute -left-10 -bottom-10 h-48 w-48 rounded-full bg-cyan-500/5 blur-2xl" />

        <div className="relative flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <div className="mb-2 flex flex-wrap items-center gap-2">
              <Badge variant="outline" className="border-primary/40 text-primary text-[11px]">
                🇻🇳 Kiểm Toán Tài Chính Việt Nam
              </Badge>
              <Badge variant="outline" className="border-cyan-700/40 text-cyan-400 text-[11px]">
                LangGraph · MCP · PostgreSQL
              </Badge>
            </div>
            <h1 className="text-2xl font-bold text-foreground">
              TaxLens
              <span className="text-primary">-AI</span>
            </h1>
            <p className="mt-1 max-w-lg text-sm text-muted-foreground leading-relaxed">
              Trợ lý ảo phát hiện lỗi chứng từ, hóa đơn và gian lận tài chính.
              Hệ thống đa tác nhân AI với Local Data Caching — tốc độ mili-giây.
            </p>
          </div>

          {/* Backend status */}
          <div className="flex-shrink-0">
            {status === 'checking' && (
              <div className="flex items-center gap-2 rounded-lg border border-border bg-secondary/30 px-4 py-2.5 text-xs text-muted-foreground">
                <RefreshCw className="h-3.5 w-3.5 animate-spin" />
                Đang kiểm tra...
              </div>
            )}
            {status === 'online' && (
              <div className="flex flex-col gap-1.5">
                <div className="flex items-center gap-2 rounded-lg border border-green-700/40 bg-green-950/30 px-4 py-2.5 text-xs text-green-400">
                  <CheckCircle2 className="h-3.5 w-3.5" />
                  {serviceName || 'Backend'} — Hoạt động
                </div>
                {pipeline && (
                  <div className="flex items-center gap-2 rounded-lg border border-blue-700/40 bg-blue-950/30 px-3 py-2 text-[11px] text-blue-400">
                    <Database className="h-3 w-3" />
                    {pipeline.so_ban_ghi.toLocaleString('vi-VN')} MST trong cache
                  </div>
                )}
              </div>
            )}
            {status === 'offline' && (
              <div className="flex items-center gap-2 rounded-lg border border-red-700/40 bg-red-950/30 px-4 py-2.5 text-xs text-red-400">
                <XCircle className="h-3.5 w-3.5" />
                Backend không phản hồi
              </div>
            )}
          </div>
        </div>
      </div>

      {/* ── Stat Cards ───────────────────────────────────────────────────── */}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        {STATS.map(({ icon: Icon, label, value, color }, i) => {
          // Inject pipeline data
          let displayValue = value
          if (i === 3 && pipeline) {
            displayValue = pipeline.so_ban_ghi.toLocaleString('vi-VN')
          }
          return (
            <Card key={label} className="border-border">
              <CardContent className="pt-4">
                <div className="flex items-center gap-2 mb-2">
                  <Icon className={`h-4 w-4 ${color}`} />
                  <span className="text-[10px] text-muted-foreground uppercase tracking-wide">{label}</span>
                </div>
                <p className={`text-2xl font-bold ${color}`}>{displayValue}</p>
              </CardContent>
            </Card>
          )
        })}
      </div>

      {/* ── Feature Cards ────────────────────────────────────────────────── */}
      <div className="grid gap-4 sm:grid-cols-2">
        {FEATURES.map(({ icon: Icon, title, desc, href, cta, color }) => (
          <Card key={href} className={`border transition-all duration-200 ${color}`}>
            <CardHeader>
              <CardTitle className="flex items-center gap-2 text-base">
                <Icon className="h-5 w-5 text-primary" />
                {title}
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <p className="text-sm text-muted-foreground leading-relaxed">{desc}</p>
              <Link href={href}>
                <Button className="gap-2 w-full sm:w-auto">
                  {cta}
                  <ArrowRight className="h-4 w-4" />
                </Button>
              </Link>
            </CardContent>
          </Card>
        ))}
      </div>

      {/* ── Architecture Cards ────────────────────────────────────────────── */}
      <div>
        <h2 className="mb-3 text-xs font-semibold uppercase tracking-widest text-muted-foreground">
          Kiến Trúc Hệ Thống
        </h2>
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          {ARCH_CARDS.map(({ icon, name, desc, color }) => (
            <Card key={name} className={`border ${color} bg-card/50`}>
              <CardContent className="pt-4">
                <p className="mb-2 text-2xl">{icon}</p>
                <p className="text-sm font-semibold text-foreground">{name}</p>
                <p className="mt-1 text-[11px] text-muted-foreground leading-relaxed">{desc}</p>
              </CardContent>
            </Card>
          ))}
        </div>
      </div>

      {/* ── Pipeline Status ───────────────────────────────────────────────── */}
      {pipeline && (
        <Card className="border-purple-700/30 bg-purple-950/10">
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-sm">
              <Zap className="h-4 w-4 text-purple-400" />
              Trạng Thái Data Pipeline — Local MST Cache
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-2 gap-4 sm:grid-cols-4 text-xs">
              <div>
                <p className="text-muted-foreground">Tổng bản ghi</p>
                <p className="font-bold text-purple-400 text-lg">
                  {pipeline.so_ban_ghi.toLocaleString('vi-VN')}
                </p>
              </div>
              <div>
                <p className="text-muted-foreground">Đang hoạt động</p>
                <p className="font-bold text-green-400 text-lg">
                  {(pipeline.so_ban_ghi - pipeline.so_ngung_hoat_dong).toLocaleString('vi-VN')}
                </p>
              </div>
              <div>
                <p className="text-muted-foreground">Ngừng hoạt động</p>
                <p className="font-bold text-red-400 text-lg">
                  {pipeline.so_ngung_hoat_dong.toLocaleString('vi-VN')}
                </p>
              </div>
              <div>
                <p className="text-muted-foreground">Cập nhật lần cuối</p>
                <p className="font-mono text-muted-foreground text-[11px]">
                  {pipeline.lan_chay_cuoi ? formatDate(pipeline.lan_chay_cuoi) : '—'}
                </p>
              </div>
            </div>
          </CardContent>
        </Card>
      )}

      {/* ── API Info ─────────────────────────────────────────────────────── */}
      <div className="rounded-md border border-border bg-secondary/20 p-4">
        <p className="text-[11px] text-muted-foreground">
          <span className="font-medium text-foreground">Backend API:</span>{' '}
          <code className="font-mono text-primary">{API_BASE}</code>
          {' · '}
          <a
            href={`${API_BASE}/docs`}
            target="_blank"
            rel="noopener noreferrer"
            className="text-primary hover:underline"
          >
            Swagger Docs ↗
          </a>
        </p>
      </div>
    </div>
  )
}
