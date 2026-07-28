'use client'

import Link from 'next/link'
import { usePathname } from 'next/navigation'
import { ReactNode } from 'react'
import { motion } from 'framer-motion'
import {
  Shield,
  ScrollText,
  FileSearch,
  BookOpen,
} from 'lucide-react'
import { cn } from '@/lib/utils'

const NAV = [
  { href: '/', label: 'Chứng từ', desc: 'Upload & kiểm toán hóa đơn', icon: FileSearch },
  { href: '/forensics', label: 'Forensics', desc: 'Kiểm chứng pháp lý Z3', icon: Shield },
  { href: '/audit-trail', label: 'Audit Trail', desc: 'Lịch sử kiểm chứng', icon: ScrollText },
  { href: '/legal-knowledge', label: 'Tra cứu luật', desc: 'Hỏi đáp pháp lý (RAG)', icon: BookOpen },
] as const

export function AppShell({ children }: { children: ReactNode }) {
  const pathname = usePathname()

  return (
    <div className="flex h-screen overflow-hidden bg-ink-950 text-slate-100">
      <aside className="relative z-20 flex w-[272px] shrink-0 flex-col border-r border-white/5 bg-ink-900/90 backdrop-blur-xl">
        <div className="absolute inset-0 bg-mesh-ink opacity-70 pointer-events-none" />

        <div className="relative border-b border-white/5 px-6 py-7">
          <Link href="/" className="group block">
            <p className="font-display text-[1.65rem] font-bold tracking-tight text-white">
              Trust
              <span className="bg-gradient-to-r from-teal-300 to-sky-400 bg-clip-text text-transparent">
                Agent
              </span>
            </p>
            <p className="mt-1 flex items-center gap-2 text-[11px] font-medium uppercase tracking-[0.22em] text-slate-500">
              <span className="relative flex h-1.5 w-1.5">
                <span className="absolute inline-flex h-full w-full animate-pulse-ring rounded-full bg-teal-400" />
                <span className="relative inline-flex h-1.5 w-1.5 rounded-full bg-teal-400" />
              </span>
              Neuro-Symbolic Audit
            </p>
          </Link>
        </div>

        <nav className="relative flex-1 space-y-1 overflow-y-auto px-3 py-5">
          <p className="mb-3 px-3 text-[10px] font-semibold uppercase tracking-[0.2em] text-slate-600">
            Modules
          </p>
          {NAV.map(({ href, label, desc, icon: Icon }) => {
            const active =
              href === '/' ? pathname === '/' : pathname.startsWith(href)
            return (
              <Link key={href} href={href} className="relative block">
                {active && (
                  <motion.div
                    layoutId="nav-pill"
                    className="absolute inset-0 rounded-xl bg-gradient-to-r from-teal-500/15 to-sky-500/10 ring-1 ring-teal-400/25"
                    transition={{ type: 'spring', stiffness: 380, damping: 32 }}
                  />
                )}
                <div
                  className={cn(
                    'relative flex items-center gap-3 rounded-xl px-3 py-3 transition-colors',
                    active
                      ? 'text-teal-200'
                      : 'text-slate-400 hover:bg-white/[0.03] hover:text-slate-200'
                  )}
                >
                  <Icon className={cn('h-[18px] w-[18px]', active && 'text-teal-300')} />
                  <div className="min-w-0">
                    <p className="text-sm font-medium leading-none">{label}</p>
                    <p className="mt-1 truncate text-[11px] text-slate-500">{desc}</p>
                  </div>
                </div>
              </Link>
            )
          })}
        </nav>

        <div className="relative border-t border-white/5 p-4">
          <div className="surface-glass flex items-center gap-3 rounded-xl px-3 py-3">
            <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-gradient-to-br from-teal-400/30 to-sky-500/20 text-xs font-bold text-teal-200 ring-1 ring-teal-400/30">
              TA
            </div>
            <div className="min-w-0">
              <p className="truncate text-sm font-medium text-slate-200">TrustAgent</p>
              <p className="truncate text-[11px] text-slate-500">
                Đoàn Hoàng Việt (Việt Gamer)
              </p>
            </div>
          </div>
        </div>
      </aside>

      <main className="relative flex-1 overflow-y-auto">
        <div className="pointer-events-none absolute inset-0 bg-mesh-ink" />
        <div className="pointer-events-none absolute inset-0 grid-atmosphere animate-grid-drift opacity-40" />
        <div className="relative min-h-full">{children}</div>
      </main>
    </div>
  )
}
