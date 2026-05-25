import { useNavigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { growthApi } from '../api'

function fmt(ts: string) {
  const d = new Date(ts)
  const diff = Date.now() - d.getTime()
  if (diff < 60_000) return 'just now'
  if (diff < 3_600_000) return `${Math.round(diff / 60_000)}m ago`
  if (diff < 86_400_000) return `${Math.round(diff / 3_600_000)}h ago`
  return d.toLocaleDateString('en-GB', { day: 'numeric', month: 'short' })
}

export function SignupFeed() {
  const navigate = useNavigate()
  const { data } = useQuery({
    queryKey: ['growth-overview'],
    queryFn: growthApi.overview,
    refetchInterval: 30_000,
  })

  const items = data?.recent ?? []

  return (
    <div className="p-4 bg-slate-900 rounded-xl border border-slate-800">
      <p className="text-xs font-semibold text-slate-500 uppercase tracking-wider mb-3">Recent signups</p>
      {items.length === 0 ? (
        <p className="text-sm text-slate-600">No signups yet</p>
      ) : (
        <ul className="space-y-2">
          {items.map(item => (
            <li
              key={item.id}
              onClick={() => navigate(`/admin/growth/waitlist/${item.id}`)}
              className="flex items-center justify-between cursor-pointer hover:bg-slate-800/50 px-2 py-1.5 rounded-lg transition-colors"
            >
              <div className="min-w-0">
                <p className="text-xs font-mono text-slate-300 truncate">{item.email}</p>
                {item.url && (
                  <p className="text-xs text-slate-600 truncate">{item.url}</p>
                )}
              </div>
              <span className="text-xs text-slate-600 ml-4 shrink-0">{fmt(item.submitted_at)}</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
