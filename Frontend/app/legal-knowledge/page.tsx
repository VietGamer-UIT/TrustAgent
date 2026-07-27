"use client";
import { useState } from "react";

export default function LegalKnowledgePage() {
  const [query, setQuery] = useState("");
  const [answer, setAnswer] = useState("");
  const [context, setContext] = useState("");
  const [loading, setLoading] = useState(false);

  const handleSearch = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!query.trim()) return;
    setLoading(true);
    setAnswer("");
    setContext("");

    try {
      const res = await fetch("/api/v1/tra-cuu-luat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ query }),
      });
      if (!res.ok) throw new Error("Lỗi kết nối Backend API");
      const data = await res.json();
      setAnswer(data.answer);
      setContext(data.context);
    } catch (err: any) {
      setAnswer("Đã xảy ra lỗi khi truy vấn: " + err.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="p-8 max-w-4xl mx-auto flex flex-col h-full overflow-hidden">
      <h1 className="text-3xl font-bold mb-2">Tra Cứu Luật Pháp Việt Nam</h1>
      <p className="text-slate-500 mb-8">Trợ lý AI chuyên môn pháp lý, trả lời dựa trên kho dữ liệu Luật/Nghị định/Thông tư đã cấu hình.</p>
      
      <form onSubmit={handleSearch} className="mb-8 flex gap-4">
        <input 
          type="text" 
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Ví dụ: Quy định về bảo vệ dữ liệu cá nhân nhạy cảm?"
          className="flex-1 px-4 py-3 border border-slate-300 rounded-lg shadow-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
        />
        <button 
          type="submit" 
          disabled={loading}
          className="px-6 py-3 bg-blue-600 hover:bg-blue-700 text-white font-medium rounded-lg shadow transition-colors disabled:opacity-50"
        >
          {loading ? "Đang truy vấn..." : "Hỏi AI"}
        </button>
      </form>

      <div className="flex-1 overflow-y-auto space-y-6 pb-8">
        {loading && (
          <div className="animate-pulse space-y-4">
            <div className="h-4 bg-slate-200 rounded w-1/4"></div>
            <div className="h-32 bg-slate-200 rounded w-full"></div>
          </div>
        )}
        
        {!loading && answer && (
          <div className="bg-white p-6 rounded-xl shadow-sm border border-slate-200">
            <h2 className="text-lg font-semibold text-blue-800 mb-4 flex items-center gap-2">
              <span className="text-2xl">🤖</span> AI Answer
            </h2>
            <div className="text-slate-700 leading-relaxed whitespace-pre-wrap">
              {answer}
            </div>
          </div>
        )}

        {!loading && context && (
          <div className="bg-slate-50 p-6 rounded-xl border border-slate-200">
            <h2 className="text-lg font-semibold text-slate-700 mb-4 flex items-center gap-2">
              <span className="text-2xl">📚</span> Legal Sources (Trích dẫn gốc)
            </h2>
            <div className="text-slate-600 text-sm whitespace-pre-wrap font-mono bg-slate-100 p-4 rounded-lg overflow-x-auto">
              {context}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
