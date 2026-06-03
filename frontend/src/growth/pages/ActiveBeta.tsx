import { Link } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { growthApi, type BetaEnrollment } from '../api'
import { ArrowLeft } from 'lucide-react'

function statusColor(status: string, daysLeft: number | null) {
  if (status === 'expired') return 'text-slate-500'
  if (status === 'converted') return 'text-emerald-400'
  if (daysLeft !== null && daysLeft <= 5) return 'text-red-400'
  if (daysLeft !== null && daysLeft <= 10) return 'text-amber-400'
  return 'text-emerald-400'
}

function DaysBar({ daysLeft, total = 30 }: { daysLeft: number | null; total?: number }) {
  if (daysLeft === null) return null
  const pct = Math.max(0, Math.min(100, (daysLeft / total) * 100))
  const color = daysLeft <= 5 ? 'bg-red-500' : daysLeft <= 10 ? 'bg-amber-500' : 'bg-emerald-500'
  return (
    <div className="w-24 h-1.5 bg-slate-800 rounded-full overflow-hidden">
      <div className={`h-full ${color} rounded-full`} style={{ width: `${pct}%` }} />
    </div>
  )
}

function fmt(ts: string) {
  return new Date(ts).toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' })
}

export default function ActiveBeta() {
  const { data, isLoading } = useQuery({
    queryKey: ['growth-beta'],
    queryFn: () => growthApi.getBetaEnrollments(),
    refetchInterval: 60_000,
  })

  const items = data?.items ?? []
  const active = items.filter(e => e.status === 'active').length
  const expired = items.filter(e => e.status === 'expired').length

  return (
    <div className="p-8">
      <div className="flex items-center gap-3 mb-6">
        <Link to="/admin/growth" className="text-slate-500 hover:text-slate-300 transition-colors">
          <ArrowLeft className="w-4 h-4" />
        </Link>
        <h1 className="text-lg font-bold text-white">Active Beta</h1>
        <div className="ml-auto flex gap-3 text-xs text-slate-500">
          <span><span className="text-emerald-400 font-semibold">{active}</span> active</span>
          <span><span className="text-slate-400 font-semibold">{expired}</span> expired</span>
        </div>
      </div>

      {isLoading && <p className="text-slate-500 text-sm">Loading…</p>}

      {!isLoading && items.length === 0 && (
        <p className="text-slate-500 text-sm">No beta enrollments yet. Send an invite from the waitlist.</p>
      )}

      {items.length > 0 && (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-xs text-slate-500 uppercase tracking-wider border-b border-slate-800">
                <th className="pb-3 text-left font-medium">User</th>
                <th className="pb-3 text-left font-medium">Site</th>
                <th className="pb-3 text-left font-medium">Enrolled</th>
                <th className="pb-3 text-left font-medium">Expires</th>
                <th className="pb-3 text-left font-medium">Days left</th>
                <th className="pb-3 text-left font-medium">Status</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800/50">
              {items.map((e: BetaEnrollment) => (
                <tr key={e.user_id} className="hover:bg-slate-900/50 transition-colors">
                  <td className="py-3 pr-4">
                    <div className="text-slate-200">{e.email}</div>
                    <div className="text-xs text-slate-600 font-mono">{e.user_id.slice(0, 8)}…</div>
                  </td>
                  <td className="py-3 pr-4">
                    {e.url ? (
                      <a href={e.url} target="_blank" rel="noopener noreferrer"
                        className="text-indigo-400 hover:underline text-xs font-mono">
                        {e.url.replace(/^https?:\/\//, '')}
                      </a>
                    ) : <span className="text-slate-600">—</span>}
                  </td>
                  <td className="py-3 pr-4 text-slate-400 text-xs">{fmt(e.enrolled_at)}</td>
                  <td className="py-3 pr-4 text-slate-400 text-xs">{fmt(e.expires_at)}</td>
                  <td className="py-3 pr-6">
                    <div className="flex items-center gap-2">
                      <span className={`font-semibold ${statusColor(e.status, e.days_left)}`}>
                        {e.days_left !== null ? `${e.days_left}d` : '—'}
                      </span>
                      <DaysBar daysLeft={e.days_left} />
                    </div>
                  </td>
                  <td className="py-3">
                    {e.status === 'active' && (
                      <span className="text-xs px-2 py-0.5 rounded-full bg-emerald-500/15 text-emerald-400 border border-emerald-500/30">active</span>
                    )}
                    {e.status === 'expired' && (
                      <span className="text-xs px-2 py-0.5 rounded-full bg-slate-500/15 text-slate-400 border border-slate-500/30">expired</span>
                    )}
                    {e.status === 'converted' && (
                      <span className="text-xs px-2 py-0.5 rounded-full bg-purple-500/15 text-purple-400 border border-purple-500/30">{e.converted_to_tier}</span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
