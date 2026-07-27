import "./globals.css";
import type { Metadata } from "next";
import { Inter } from "next/font/google";
import Link from "next/link";
import { ReactNode } from "react";

const inter = Inter({ subsets: ["latin", "vietnamese"] });

export const metadata: Metadata = {
  title: "TrustAgent - AI Audit Platform",
  description: "Nền tảng kiểm toán thông minh bằng AI",
};

export default function RootLayout({
  children,
}: {
  children: ReactNode;
}) {
  return (
    <html lang="vi">
      <body className={`${inter.className} bg-slate-50 text-slate-900 h-screen overflow-hidden flex`}>
        {/* Sidebar Navigation */}
        <aside className="w-64 bg-slate-900 text-white flex flex-col h-full shadow-xl">
          <div className="p-6 border-b border-slate-700">
            <h1 className="text-2xl font-bold tracking-tight text-blue-400">TrustAgent</h1>
            <p className="text-xs text-slate-400 mt-1">AI Audit Platform</p>
          </div>
          
          <nav className="flex-1 py-6 px-3 space-y-2 overflow-y-auto">
            <Link 
              href="/" 
              className="flex items-center gap-3 px-4 py-3 rounded-lg hover:bg-slate-800 transition-colors bg-slate-800 text-white"
            >
              <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><rect x="3" y="3" width="18" height="18" rx="2" ry="2"></rect><line x1="9" y1="3" x2="9" y2="21"></line></svg>
              <span className="font-medium">Workspace</span>
            </Link>
            
            <Link 
              href="/audit-trail" 
              className="flex items-center gap-3 px-4 py-3 rounded-lg hover:bg-slate-800 text-slate-300 transition-colors"
            >
              <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><circle cx="12" cy="12" r="10"></circle><polyline points="12 6 12 12 16 14"></polyline></svg>
              <span className="font-medium">Audit Trail</span>
            </Link>
            
            <Link 
              href="/legal-knowledge" 
              className="flex items-center gap-3 px-4 py-3 rounded-lg hover:bg-slate-800 text-slate-300 transition-colors"
            >
              <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"></path><path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z"></path></svg>
              <span className="font-medium">Legal Knowledge</span>
            </Link>
          </nav>
          
          <div className="p-4 border-t border-slate-700">
            <div className="flex items-center gap-3">
              <div className="w-8 h-8 rounded-full bg-blue-500 flex items-center justify-center text-sm font-bold">
                AD
              </div>
              <div className="text-sm">
                <p className="font-medium">Admin User</p>
                <p className="text-xs text-slate-400">admin@trustagent.vn</p>
              </div>
            </div>
          </div>
        </aside>

        {/* Main Content Area */}
        <main className="flex-1 h-full overflow-y-auto">
          {children}
        </main>
      </body>
    </html>
  );
}
