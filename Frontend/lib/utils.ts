import { type ClassValue, clsx } from 'clsx'
import { twMerge } from 'tailwind-merge'

/** Merge Tailwind classes safely */
export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}

/** Format ISO date string → Vietnamese locale */
export function formatDate(dateStr: string | null | undefined): string {
  if (!dateStr) return '—'
  try {
    return new Intl.DateTimeFormat('vi-VN', {
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
      hour12: false,
    }).format(new Date(dateStr))
  } catch {
    return dateStr
  }
}

/** Truncate long string */
export function truncate(str: string, maxLen = 48): string {
  if (!str || str.length <= maxLen) return str
  return str.slice(0, maxLen) + '…'
}

/** Format số tiền VNĐ */
export function formatTien(so: number | null | undefined): string {
  if (so == null) return '—'
  return new Intl.NumberFormat('vi-VN', {
    style: 'currency',
    currency: 'VND',
    maximumFractionDigits: 0,
  }).format(so)
}

/** Severity color mapping */
export function severityColor(severity: string): {
  text: string
  bg: string
  border: string
  badge: string
} {
  switch (severity?.toLowerCase().trim()) {
    case 'nghiêm trọng':
    case 'critical':
      return {
        text: 'text-red-400',
        bg: 'bg-red-950/50',
        border: 'border-red-700',
        badge: 'bg-red-900 text-red-300 border-red-700',
      }
    case 'cao':
    case 'high':
      return {
        text: 'text-orange-400',
        bg: 'bg-orange-950/50',
        border: 'border-orange-700',
        badge: 'bg-orange-900 text-orange-300 border-orange-700',
      }
    case 'trung bình':
    case 'medium':
      return {
        text: 'text-yellow-400',
        bg: 'bg-yellow-950/50',
        border: 'border-yellow-700',
        badge: 'bg-yellow-900 text-yellow-300 border-yellow-700',
      }
    case 'thấp':
    case 'low':
      return {
        text: 'text-green-400',
        bg: 'bg-green-950/50',
        border: 'border-green-700',
        badge: 'bg-green-900 text-green-300 border-green-700',
      }
    default:
      return {
        text: 'text-slate-400',
        bg: 'bg-slate-900/50',
        border: 'border-slate-700',
        badge: 'bg-slate-800 text-slate-300 border-slate-600',
      }
  }
}

/** Nhãn mức độ rủi ro tiếng Việt */
export function severityLabel(severity: string): string {
  const map: Record<string, string> = {
    'nghiêm trọng': 'NGHIÊM TRỌNG',
    critical: 'NGHIÊM TRỌNG',
    cao: 'CAO',
    high: 'CAO',
    'trung bình': 'TRUNG BÌNH',
    medium: 'TRUNG BÌNH',
    thấp: 'THẤP',
    low: 'THẤP',
    unknown: 'CHƯA XÁC ĐỊNH',
  }
  return map[severity?.toLowerCase()] ?? severity?.toUpperCase() ?? '—'
}

/** Nhãn trạng thái tiếng Việt */
export function statusLabel(status: string): string {
  const map: Record<string, string> = {
    'hoàn tất': 'Hoàn tất',
    complete: 'Hoàn tất',
    'một phần': 'Một phần',
    partial: 'Một phần',
    'thất bại': 'Thất bại',
    failed: 'Thất bại',
    ok: 'Thành công',
    error: 'Lỗi',
    blocked: 'Bị chặn',
    unknown: 'Chưa rõ',
    'chưa rõ': 'Chưa rõ',
  }
  return map[status?.toLowerCase()] ?? status ?? '—'
}

/** Nhãn loại sự kiện tiếng Việt */
export function eventTypeLabel(t: string): string {
  const map: Record<string, string> = {
    GRAPH_STARTED:        'Bắt đầu đồ thị',
    GRAPH_COMPLETED:      'Hoàn tất đồ thị',
    AGENT_STARTED:        'Agent khởi động',
    AGENT_COMPLETED:      'Agent hoàn tất',
    SUPERVISOR_ROUTED:    'Giám sát điều phối',
    SUPERVISOR_COMPLETED: 'Giám sát hoàn tất',
    TOOL_CALLED:          'Gọi công cụ',
    TOOL_SUCCEEDED:       'Công cụ thành công',
    TOOL_FAILED:          'Công cụ thất bại',
    HTTP_REQUEST:         'Yêu cầu HTTP',
  }
  return map[t] ?? t ?? '—'
}

/** Nhãn tên agent tiếng Việt */
export function agentLabel(name: string): string {
  const map: Record<string, string> = {
    supervisor:       'Giám Sát',
    chung_tu_agent:   'Chứng Từ',
    tuan_thu_agent:   'Tuân Thủ',
    // backward compat
    forensics_agent:  'Pháp Y (cũ)',
    network_agent:    'Mạng (cũ)',
    database_agent:   'Threat Intel (cũ)',
    system:           'Hệ thống',
  }
  return map[name?.toLowerCase()] ?? name ?? '—'
}

/** Màu badge theo loại cảnh báo */
export function loaiCanhBaoColor(loai: string): string {
  const map: Record<string, string> = {
    'lỗi số học':           'text-orange-400 border-orange-700 bg-orange-950/30',
    'trùng số hóa đơn':     'text-red-400 border-red-700 bg-red-950/30',
    'lỗi format mst':       'text-yellow-400 border-yellow-700 bg-yellow-950/30',
    'mst danh sách đen':    'text-red-500 border-red-600 bg-red-900/40',
    'lỗi ngày logic':       'text-purple-400 border-purple-700 bg-purple-950/30',
    'hóa đơn không hợp lệ tct': 'text-red-500 border-red-600 bg-red-900/40',
  }
  return map[loai?.toLowerCase()] ?? 'text-slate-400 border-slate-700 bg-slate-900/30'
}
