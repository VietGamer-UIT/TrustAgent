import "./globals.css";
import type { Metadata } from "next";
import { Be_Vietnam_Pro, JetBrains_Mono } from "next/font/google";
import { ReactNode } from "react";
import { AppShell } from "@/components/layout/AppShell";

/** Be Vietnam Pro — hỗ trợ đầy đủ dấu tiếng Việt */
const sans = Be_Vietnam_Pro({
  subsets: ["latin", "vietnamese"],
  variable: "--font-sans",
  weight: ["400", "500", "600", "700"],
  display: "swap",
});

const display = Be_Vietnam_Pro({
  subsets: ["latin", "vietnamese"],
  variable: "--font-display",
  weight: ["600", "700"],
  display: "swap",
});

const mono = JetBrains_Mono({
  subsets: ["latin", "latin-ext"],
  variable: "--font-mono",
  weight: ["400", "500", "600"],
  display: "swap",
});

export const metadata: Metadata = {
  title: "TrustAgent — Neuro-Symbolic Audit Platform",
  description:
    "TrustAgent: kiểm toán chứng từ và kiểm chứng pháp lý bằng LLM + Z3 Theorem Prover",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html
      lang="vi"
      className={`${sans.variable} ${display.variable} ${mono.variable}`}
    >
      <body className="font-sans antialiased">{/* AppShell */}
        <AppShell>{children}</AppShell>
      </body>
    </html>
  );
}
