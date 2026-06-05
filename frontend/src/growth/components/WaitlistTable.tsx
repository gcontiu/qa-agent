import { useNavigate } from 'react-router-dom'
import type { WaitlistEntry } from '../api'

interface Props {
  items: WaitlistEntry[]
}

function ScanBadge({ status }: { status: string }) {
  const map: Record<string, string> = {
    pending: 'text-slate-400 bg-slate-500/10 border-slate-500/20',
    running: 'text-amber-400 bg-amber-500/10 border-amber-500/20 animate-pulse',
    done:    'text-emerald-400 bg-emerald-500/10 border-emerald-500/20',
    failed:  'text-red-400 bg-red-500/10 border-red-500/20',
    capped:  'text-orange-400 bg-orange-500/10 border-orange-500/20',
  }
  return (
    <span className={`text-xs px-2 py-0.5 rounded-full border font-medium ${map[status] ?? map.pending}`}>
      {status}
    </span>
  )
}

function InviteBadge({ status }: { status: string }) {
  const map: Record<string, string> = {
    none:      'text-slate-600 bg-slate-500/5 border-slate-700',
    requested: 'text-amber-400 bg-amber-500/10 border-amber-500/20',
    sent:      'text-indigo-400 bg-indigo-500/10 border-indigo-500/20',
    accepted:  'text-emerald-400 bg-emerald-500/10 border-emerald-500/20',
  }
  return (
    <span className={`text-xs px-2 py-0.5 rounded-full border ${map[status] ?? map.none}`}>
      {status}
    </span>
  )
}

function fmt(ts: string | null) {
  if (!ts) return '—'
  return new Date(ts).toLocaleDateString('en-GB', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' })
}

export function WaitlistTable({ items }: Props) {
  const navigate = useNavigate()
  return (
    <div className="overflow-x-auto rounded-xl border border-slate-800">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-slate-800 bg-slate-900/50">
            <th className="text-left px-4 py-3 text-xs font-semibold text-slate-500 uppercase tracking-wider">Email</th>
            <th className="text-left px-4 py-3 text-xs font-semibold text-slate-500 uppercase tracking-wider">URL</th>
            <th className="text-left px-4 py-3 text-xs font-semibold text-slate-500 uppercase tracking-wider">Segment</th>
            <th className="text-left px-4 py-3 text-xs font-semibold text-slate-500 uppercase tracking-wider">Scan</th>
            <th className="text-right px-4 py-3 text-xs font-semibold text-slate-500 uppercase tracking-wider">Cost</th>
            <th className="text-left px-4 py-3 text-xs font-semibold text-slate-500 uppercase tracking-wider">Invite</th>
            <th className="text-right px-4 py-3 text-xs font-semibold text-slate-500 uppercase tracking-wider">Submitted</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-800/50">
          {items.map(item => (
            <tr
              key={item.id}
              onClick={() => navigate(`/admin/growth/waitlist/${item.id}`)}
              className="hover:bg-slate-800/30 cursor-pointer transition-colors"
            >
              <td className="px-4 py-3 font-mono text-xs text-slate-200">{item.email}</td>
              <td className="px-4 py-3 text-xs text-slate-400 max-w-[200px] truncate">
                {item.url ?? <span className="text-slate-700">—</span>}
              </td>
              <td className="px-4 py-3 text-xs text-slate-500">{item.segment ?? '—'}</td>
              <td className="px-4 py-3"><ScanBadge status={item.scan_status} /></td>
              <td className="px-4 py-3 text-right font-mono text-xs text-slate-400">
                {item.scan_cost_usd != null ? `$${item.scan_cost_usd.toFixed(4)}` : '—'}
              </td>
              <td className="px-4 py-3"><InviteBadge status={item.invite_status} /></td>
              <td className="px-4 py-3 text-right text-xs text-slate-600">{fmt(item.submitted_at)}</td>
            </tr>
          ))}
          {items.length === 0 && (
            <tr>
              <td colSpan={7} className="px-4 py-10 text-center text-slate-600 text-sm">No entries</td>
            </tr>
          )}
        </tbody>
      </table>
    </div>
  )
}
