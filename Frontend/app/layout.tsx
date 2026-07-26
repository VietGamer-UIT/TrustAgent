import type { Metadata } from 'next'
import { Inter } from 'next/font/google'
import './globals.css'
import { Sidebar } from '@/components/layout/Sidebar'
import { TopBar } from '@/components/layout/TopBar'

// ---------------------------------------------------------------------------
// Font — Inter cho body text (hỗ trợ tiếng Việt)
// ---------------------------------------------------------------------------
const inter = Inter({
  subsets: ['latin', 'vietnamese'],
  variable: '--font-inter',
  display: 'swap',
})

// ---------------------------------------------------------------------------
// SEO Metadata
// ---------------------------------------------------------------------------
export const metadata: Metadata = {
  title: {
    default: 'TrustAgent | Trợ Lý Ảo Phát Hiện Lỗi Chứng Từ',
    template: '%s | TrustAgent',
  },
  description:
    'TrustAgent bởi Đoàn Hoàng Việt (Việt Gamer) — Nền tảng AI đa tác nhân phát hiện lỗi chứng từ, hóa đơn và gian lận tài chính cho ngành kiểm toán Việt Nam.',
  authors: [{ name: 'Đoàn Hoàng Việt (Việt Gamer)' }],
  keywords: ['Kiểm toán', 'Hóa đơn', 'Chứng từ', 'Gian lận', 'OCR', 'LangGraph', 'MCP', 'AI'],
}

// ---------------------------------------------------------------------------
// Root Layout
// ---------------------------------------------------------------------------
export default function RootLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <html lang="vi" className="dark">
      <body className={`${inter.variable} font-sans`}>
        {/* Fixed sidebar — 256 px wide */}
        <Sidebar />

        {/* Fixed top bar — positioned after sidebar */}
        <TopBar />

        {/* Main content area — offset by sidebar + topbar */}
        <main className="ml-64 mt-16 min-h-[calc(100vh-4rem)] bg-background">
          <div className="p-6">{children}</div>
        </main>
      </body>
    </html>
  )
}
