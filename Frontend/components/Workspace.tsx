"use client";

import React, { useState, useRef, DragEvent } from 'react';

interface AuditLog {
  incident_id: string;
  status: string;
  tong_hoa_don: number;
  tong_loi_thue: number;
  tong_loi_phap_ly: number;
  z3_status: string;
  tax_warnings: any[];
  legal_violations: any[];
  messages: any[];
  timestamp?: string;
  audit_trail_steps?: {
    step: string;
    status: string;
    details: string;
  }[];
}

export default function Workspace() {
  const [files, setFiles] = useState<File[]>([]);
  const [isDragging, setIsDragging] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [auditResult, setAuditResult] = useState<AuditLog | null>(null);
  const [error, setError] = useState<string | null>(null);
  
  const fileInputRef = useRef<HTMLInputElement>(null);

  const handleDragOver = (e: DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    setIsDragging(true);
  };

  const handleDragLeave = (e: DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    setIsDragging(false);
  };

  const handleDrop = (e: DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    setIsDragging(false);
    if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
      setFiles(Array.from(e.dataTransfer.files));
    }
  };

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files.length > 0) {
      setFiles(Array.from(e.target.files));
    }
  };

  const removeFile = (index: number) => {
    const newFiles = [...files];
    newFiles.splice(index, 1);
    setFiles(newFiles);
  };

  const startAudit = async () => {
    if (files.length === 0) {
      setError("Vui lòng tải lên ít nhất một file (XML, CSV, TSV, XLSX) để bắt đầu.");
      return;
    }

    setIsLoading(true);
    setError(null);
    setAuditResult(null);

    const formData = new FormData();
    files.forEach((file) => {
      formData.append("file", file);
    });
    
    // Giả lập gửi thêm contract data cho legal agent
    const mockContractData = JSON.stringify({
      tong_gia_tri: 150000000,
      phat_vi_pham: 15000000, // 10% - Cố ý vi phạm luật thương mại (vượt 8%) để Z3 báo lỗi
      thue_suat: 8
    });
    formData.append("contract_data", mockContractData);

    try {
      const response = await fetch("/api/v1/kiem-tra/upload", {
        method: "POST",
        body: formData,
      });

      if (!response.ok) {
        throw new Error(`Lỗi server: ${response.status} ${response.statusText}`);
      }

      const data = await response.json();
      setAuditResult(data.final_audit_log);
    } catch (err: any) {
      setError(err.message || "Đã xảy ra lỗi khi kết nối tới máy chủ kiểm toán.");
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="p-8 max-w-6xl mx-auto">
      <header className="mb-8">
        <h1 className="text-3xl font-bold text-slate-800">Workspace Kiểm Toán</h1>
        <p className="text-slate-500 mt-2">Tải lên chứng từ, bảng kê và hợp đồng để AI phân tích.</p>
      </header>

      {/* Upload Area */}
      <div 
        className={`border-2 border-dashed rounded-xl p-10 text-center transition-all ${
          isDragging ? 'border-blue-500 bg-blue-50' : 'border-slate-300 bg-white hover:border-blue-400'
        }`}
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onDrop={handleDrop}
      >
        <svg className="mx-auto h-12 w-12 text-slate-400" stroke="currentColor" fill="none" viewBox="0 0 48 48" aria-hidden="true">
          <path d="M28 8H12a4 4 0 00-4 4v20m32-12v8m0 0v8a4 4 0 01-4 4H12a4 4 0 01-4-4v-4m32-4l-3.172-3.172a4 4 0 00-5.656 0L28 28M8 32l9.172-9.172a4 4 0 015.656 0L28 28m0 0l4 4m4-24h8m-4-4v8m-12 4h.02" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
        <div className="mt-4 flex justify-center text-sm text-slate-600">
          <label className="relative cursor-pointer rounded-md bg-white font-medium text-blue-600 focus-within:outline-none focus-within:ring-2 focus-within:ring-blue-500 focus-within:ring-offset-2 hover:text-blue-500">
            <span>Tải lên file</span>
            <input type="file" multiple className="sr-only" ref={fileInputRef} onChange={handleFileChange} />
          </label>
          <p className="pl-1">hoặc kéo thả vào đây</p>
        </div>
        <p className="text-xs text-slate-500 mt-2">Hỗ trợ XML, CSV, TSV, XLSX lên đến 50MB</p>
      </div>

      {/* File List */}
      {files.length > 0 && (
        <div className="mt-6">
          <h3 className="text-lg font-medium text-slate-800 mb-3">File đã chọn ({files.length})</h3>
          <ul className="space-y-2">
            {files.map((file, index) => (
              <li key={index} className="flex items-center justify-between py-2 px-4 bg-white rounded-lg border border-slate-200 shadow-sm">
                <span className="text-sm font-medium text-slate-700 truncate">{file.name}</span>
                <button onClick={() => removeFile(index)} className="text-red-500 hover:text-red-700 p-1">
                  <svg xmlns="http://www.w3.org/2000/svg" className="h-5 w-5" viewBox="0 0 20 20" fill="currentColor">
                    <path fillRule="evenodd" d="M4.293 4.293a1 1 0 011.414 0L10 8.586l4.293-4.293a1 1 0 111.414 1.414L11.414 10l4.293 4.293a1 1 0 01-1.414 1.414L10 11.414l-4.293 4.293a1 1 0 01-1.414-1.414L8.586 10 4.293 5.707a1 1 0 010-1.414z" clipRule="evenodd" />
                  </svg>
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* Action Area */}
      <div className="mt-8 flex items-center justify-between">
        <div className="text-red-500 text-sm font-medium">{error}</div>
        <button
          onClick={startAudit}
          disabled={isLoading || files.length === 0}
          className={`flex items-center gap-2 px-6 py-3 rounded-lg text-white font-semibold shadow-md transition-all ${
            isLoading || files.length === 0 ? 'bg-blue-300 cursor-not-allowed' : 'bg-blue-600 hover:bg-blue-700 hover:shadow-lg'
          }`}
        >
          {isLoading ? (
            <>
              <svg className="animate-spin -ml-1 mr-2 h-5 w-5 text-white" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
              </svg>
              Đang phân tích...
            </>
          ) : (
            <>
              <svg xmlns="http://www.w3.org/2000/svg" className="h-5 w-5" viewBox="0 0 20 20" fill="currentColor">
                <path fillRule="evenodd" d="M11.3 1.046A1 1 0 0112 2v5h4a1 1 0 01.82 1.573l-7 10A1 1 0 018 18v-5H4a1 1 0 01-.82-1.573l7-10a1 1 0 011.12-.381z" clipRule="evenodd" />
              </svg>
              Bắt đầu Kiểm toán
            </>
          )}
        </button>
      </div>

      {/* Result Area */}
      {auditResult && (
        <div className="mt-12 bg-white rounded-xl shadow-lg border border-slate-200 overflow-hidden animate-fade-in-up">
          <div className="bg-slate-50 px-6 py-4 border-b border-slate-200 flex justify-between items-center">
            <h2 className="text-xl font-bold text-slate-800">Kết quả Kiểm toán (Audit Trail Log)</h2>
            <span className={`px-3 py-1 rounded-full text-xs font-bold uppercase ${auditResult.z3_status === 'UNSAT' ? 'bg-red-100 text-red-800' : 'bg-green-100 text-green-800'}`}>
              {auditResult.z3_status === 'UNSAT' ? 'Phát hiện vi phạm' : 'Hoàn tất'}
            </span>
          </div>
          
          <div className="p-6">
            {/* Cảnh báo Z3 */}
            {auditResult.z3_status === 'UNSAT' ? (
              <div className="mb-6 p-5 bg-red-50 border-l-4 border-red-600 rounded-r-lg">
                <div className="flex items-center gap-3 mb-2">
                  <span className="text-3xl">❌</span>
                  <h3 className="text-red-800 font-bold text-lg">PHÁN QUYẾT TOÁN HỌC: VI PHẠM PHÁP LUẬT (UNSATISFIABLE)</h3>
                </div>
                <p className="text-red-700 font-medium ml-11">
                  Hệ thống đã tự động NGẮT KẾT NỐI API. Nghiêm cấm AI thực thi hành động này để bảo vệ doanh nghiệp khỏi rủi ro pháp lý và phạt tiền.
                </p>
              </div>
            ) : (
              <div className="mb-6 p-5 bg-green-50 border-l-4 border-green-600 rounded-r-lg">
                <div className="flex items-center gap-3 mb-2">
                  <span className="text-3xl">✅</span>
                  <h3 className="text-green-800 font-bold text-lg">PHÁN QUYẾT TOÁN HỌC: HỢP LỆ (SATISFIABLE)</h3>
                </div>
                <p className="text-green-700 font-medium ml-11">
                  Mọi điều khoản đều tuân thủ quy định pháp luật. Hệ thống cho phép thực thi tiếp tục.
                </p>
              </div>
            )}

            <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-8">
              <div className="bg-blue-50 rounded-lg p-4 border border-blue-100">
                <p className="text-sm text-blue-600 font-medium">Tổng số chứng từ (OCR)</p>
                <p className="text-3xl font-bold text-blue-900 mt-1">{auditResult.tong_hoa_don}</p>
              </div>
              <div className={`rounded-lg p-4 border ${auditResult.tong_loi_thue > 0 ? 'bg-yellow-50 border-yellow-100' : 'bg-green-50 border-green-100'}`}>
                <p className={`text-sm font-medium ${auditResult.tong_loi_thue > 0 ? 'text-yellow-600' : 'text-green-600'}`}>Cảnh báo Thuế</p>
                <p className={`text-3xl font-bold mt-1 ${auditResult.tong_loi_thue > 0 ? 'text-yellow-900' : 'text-green-900'}`}>{auditResult.tong_loi_thue}</p>
              </div>
              <div className={`rounded-lg p-4 border ${auditResult.tong_loi_phap_ly > 0 ? 'bg-red-50 border-red-100' : 'bg-green-50 border-green-100'}`}>
                <p className={`text-sm font-medium ${auditResult.tong_loi_phap_ly > 0 ? 'text-red-600' : 'text-green-600'}`}>Lỗi Pháp lý Z3</p>
                <p className={`text-3xl font-bold mt-1 ${auditResult.tong_loi_phap_ly > 0 ? 'text-red-900' : 'text-green-900'}`}>{auditResult.tong_loi_phap_ly}</p>
              </div>
            </div>

            {/* Forensic Terminal Log */}
            <div className="bg-slate-900 rounded-lg p-5 overflow-x-auto border border-slate-700 shadow-inner">
              <div className="flex justify-between items-center mb-4 border-b border-slate-800 pb-2">
                <span className="text-slate-400 text-xs font-mono uppercase tracking-widest flex items-center gap-2">
                  <span className="w-2 h-2 rounded-full bg-red-500 animate-pulse"></span>
                  Live Forensic Stream
                </span>
              </div>
              
              <div className="font-mono text-[13px] leading-relaxed text-slate-300">
                <div className="text-cyan-500 mb-1">======================================================================</div>
                <div className="text-cyan-400 font-bold mb-1 tracking-wide">🛡️ TRUSTAGENT.FORENSICS — AUDIT TRAIL LOG</div>
                <div className="text-cyan-500 mb-4">======================================================================</div>
                
                <div className="mb-4">
                  <div className="text-blue-400 font-bold mb-1">[THÔNG TIN GIAO DỊCH]</div>
                  <div className="text-slate-300">Hoạt động : Phân tích hồ sơ hợp đồng & chứng từ ({auditResult.tong_hoa_don} files)</div>
                  <div className="text-slate-300">ID Phiên : {auditResult.incident_id}</div>
                  <div className="text-slate-300">Thời gian : {auditResult.timestamp || new Date().toISOString()}</div>
                </div>

                {auditResult.audit_trail_steps && auditResult.audit_trail_steps.length > 0 && (
                  <div className="mb-4">
                    <div className="text-purple-400 font-bold mb-1">[TIẾN TRÌNH THỰC THI LANGGRAPH]</div>
                    {auditResult.audit_trail_steps.map((step: any, idx: number) => (
                      <div key={idx} className="flex gap-2">
                        <span className="text-slate-500">Step {idx + 1}:</span>
                        <span className="text-slate-300">{step.step}</span>
                        <span className="text-slate-500">-&gt;</span>
                        <span className={step.status === 'PASS' ? 'text-green-400' : (step.status === 'FAIL' ? 'text-red-400' : 'text-yellow-400')}>
                          [{step.status}] {step.details}
                        </span>
                      </div>
                    ))}
                  </div>
                )}

                <div className="mb-4">
                  <div className="text-blue-400 font-bold mb-1">[KẾT QUẢ KIỂM CHỨNG LOGIC PHÁP LÝ]</div>
                  <div className="text-slate-300">
                    Phán quyết: {auditResult.z3_status === 'UNSAT' 
                      ? <span className="text-red-400 font-bold">🚫 CHẶN THỰC THI NGAY LẬP TỨC</span> 
                      : <span className="text-green-400 font-bold">✅ HỢP LỆ, CHO PHÉP THỰC THI</span>}
                  </div>
                </div>

                {auditResult.legal_violations && auditResult.legal_violations.length > 0 && (
                  <div className="mb-4">
                    <div className="text-red-400 font-bold mb-2">[DẪN CHỨNG PHÁP LÝ & BẰNG CHỨNG VI PHẠM]</div>
                    
                    {auditResult.legal_violations.map((violation: any, idx: number) => (
                      <div key={idx} className="mb-4 pl-2 border-l border-red-800">
                        <div className="text-red-300 font-bold">📍 VI PHẠM {idx + 1}: {violation.rule}</div>
                        {violation.legal_basis && (
                          <div className="text-yellow-400 mt-1 whitespace-pre-wrap">⚠️ {violation.legal_basis}</div>
                        )}
                        <div className="text-slate-300 mt-1">Bằng chứng: {violation.description}</div>
                        {violation.remediation && (
                          <div className="text-green-400 mt-1">Hướng khắc phục: {violation.remediation}</div>
                        )}
                      </div>
                    ))}
                  </div>
                )}

                <div className="mt-6 mb-2">
                  <div className="text-blue-400 font-bold mb-1">[HÀNH ĐỘNG CỦA HỆ THỐNG]</div>
                  {auditResult.z3_status === 'UNSAT' ? (
                    <>
                      <div className="text-red-400">Trạng thái: Đã ngắt kết nối — luồng dữ liệu bị chặn để tránh rủi ro pháp lý.</div>
                      <div className="text-slate-400">Mục tiêu  : Chặn đứng luồng dữ liệu để bảo vệ doanh nghiệp trước rủi ro pháp lý và hành chính.</div>
                    </>
                  ) : (
                    <>
                      <div className="text-green-400">Trạng thái: Đã xác thực thành công. Dữ liệu sạch sẽ và tuân thủ.</div>
                      <div className="text-slate-400">Mục tiêu  : Đảm bảo luồng tài chính liên tục và hợp pháp.</div>
                    </>
                  )}
                </div>

                <div className="text-cyan-500 mt-4">======================================================================</div>
                <div className="text-slate-500 text-[10px] mt-1 flex justify-end">EOF - {auditResult.incident_id}</div>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
