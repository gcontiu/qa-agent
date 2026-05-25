interface Props {
  used: number
  limit: number
}

export function CapMeter({ used, limit }: Props) {
  const pct = Math.min(100, (used / limit) * 100)
  const color = pct >= 90 ? 'bg-red-500' : pct >= 70 ? 'bg-amber-500' : 'bg-emerald-500'
  return (
    <div className="p-4 bg-slate-900 rounded-xl border border-slate-800">
      <div className="flex items-center justify-between mb-2">
        <span className="text-xs font-semibold text-slate-500 uppercase tracking-wider">Mini-scans today</span>
        <span className="text-sm font-mono font-bold text-slate-200">{used}/{limit}</span>
      </div>
      <div className="h-2 rounded-full bg-slate-800 overflow-hidden">
        <div className={`h-full rounded-full transition-all ${color}`} style={{ width: `${pct}%` }} />
      </div>
      {used >= limit && (
        <p className="text-xs text-red-400 mt-2">Daily cap reached — new submissions queued</p>
      )}
    </div>
  )
}
