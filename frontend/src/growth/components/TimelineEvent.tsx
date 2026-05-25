import { CheckCircle2, Clock, XCircle } from 'lucide-react'

export type EventStatus = 'done' | 'pending' | 'failed' | 'running'

interface TimelineEventProps {
  status: EventStatus
  timestamp: string | null
  title: string
  details?: Record<string, string | number | null | undefined>
}

const STATUS_ICON = {
  done:    <CheckCircle2 className="w-4 h-4 text-emerald-400 shrink-0 mt-0.5" />,
  pending: <Clock className="w-4 h-4 text-slate-500 shrink-0 mt-0.5" />,
  running: <Clock className="w-4 h-4 text-amber-400 shrink-0 mt-0.5 animate-pulse" />,
  failed:  <XCircle className="w-4 h-4 text-red-400 shrink-0 mt-0.5" />,
}

function fmt(ts: string | null) {
  if (!ts) return '—'
  return new Date(ts).toLocaleString('en-GB', {
    year: 'numeric', month: 'short', day: 'numeric',
    hour: '2-digit', minute: '2-digit',
  })
}

export function TimelineEvent({ status, timestamp, title, details }: TimelineEventProps) {
  const isPast = status === 'done' || status === 'failed'
  return (
    <div className={`flex gap-3 ${!isPast ? 'opacity-50' : ''}`}>
      <div className="flex flex-col items-center gap-1">
        {STATUS_ICON[status]}
        <div className="w-px flex-1 bg-slate-800" />
      </div>
      <div className="pb-5 min-w-0">
        <div className="flex items-baseline gap-2 mb-1">
          <span className={`text-sm font-medium ${isPast ? 'text-slate-200' : 'text-slate-500'}`}>
            {title}
          </span>
          <span className="text-xs text-slate-600">{fmt(timestamp)}</span>
        </div>
        {details && (
          <div className="text-xs text-slate-500 flex flex-wrap gap-x-4 gap-y-0.5">
            {Object.entries(details).map(([k, v]) =>
              v != null ? (
                <span key={k}>
                  <span className="text-slate-600">{k}:</span> {String(v)}
                </span>
              ) : null
            )}
          </div>
        )}
      </div>
    </div>
  )
}
