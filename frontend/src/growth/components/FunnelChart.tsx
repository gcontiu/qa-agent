import { useQuery } from '@tanstack/react-query'
import { growthApi, type FunnelStage } from '../api'

export function FunnelChart() {
  const { data } = useQuery({
    queryKey: ['growth-funnel'],
    queryFn: growthApi.getFunnelStats,
    refetchInterval: 60_000,
  })

  const stages: FunnelStage[] = data?.stages ?? []
  const max = stages[0]?.value || 1

  const colors = [
    'bg-indigo-500',
    'bg-indigo-400',
    'bg-indigo-300',
    'bg-emerald-400',
  ]

  return (
    <div className="p-5 bg-slate-900 rounded-xl border border-slate-800">
      <p className="text-xs font-semibold text-slate-500 uppercase tracking-wider mb-4">Conversion funnel</p>
      <div className="space-y-2">
        {stages.map((stage, i) => {
          const pct = max > 0 ? (stage.value / max) * 100 : 0
          const convRate = i > 0 && stages[i - 1].value > 0
            ? Math.round((stage.value / stages[i - 1].value) * 100)
            : null
          return (
            <div key={stage.label}>
              <div className="flex items-center justify-between mb-1">
                <span className="text-xs text-slate-400">{stage.label}</span>
                <div className="flex items-center gap-2">
                  {convRate !== null && (
                    <span className="text-xs text-slate-600">{convRate}%</span>
                  )}
                  <span className="text-sm font-semibold text-white tabular-nums">{stage.value}</span>
                </div>
              </div>
              <div className="h-2 bg-slate-800 rounded-full overflow-hidden">
                <div
                  className={`h-full ${colors[i] ?? 'bg-slate-500'} rounded-full transition-all duration-500`}
                  style={{ width: `${pct}%` }}
                />
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}
