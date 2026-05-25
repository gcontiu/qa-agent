import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { growthApi } from '../api'

function fmt(ts: string) {
  return new Date(ts).toLocaleString('en-GB', {
    day: 'numeric', month: 'short',
    hour: '2-digit', minute: '2-digit',
  })
}

export default function DripQueue() {
  const [status, setStatus] = useState('')
  const { data, isLoading } = useQuery({
    queryKey: ['growth-drip', status],
    queryFn: () => growthApi.getDripQueue(status || undefined),
    refetchInterval: 30_000,
  })

  const items = data?.items ?? []
  const statusColor: Record<string, string> = {
    pending: 'text-amber-400',
    sent: 'text-emerald-400',
    failed: 'text-red-400',
    skipped: 'text-slate-500',
  }

  return (
    <div className="p-8 max-w-4xl mx-auto space-y-5">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-bold text-white">Drip queue</h1>
        <div className="flex gap-2">
          {['', 'pending', 'sent', 'failed'].map(s => (
            <button
              key={s}
              onClick={() => setStatus(s)}
              className={`text-xs px-3 py-1.5 rounded-lg border transition-colors ${
                status === s
                  ? 'border-indigo-500/50 bg-indigo-500/10 text-indigo-400'
                  : 'border-slate-700 text-slate-500 hover:border-slate-600'
              }`}
            >
              {s || 'All'}
            </button>
          ))}
        </div>
      </div>

      {isLoading ? (
        <div className="text-slate-500 text-sm">Loading…</div>
      ) : (
        <div className="rounded-xl border border-slate-800 overflow-hidden">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-slate-800 bg-slate-900/50">
                <th className="text-left px-4 py-3 text-xs font-semibold text-slate-500 uppercase tracking-wider">Email</th>
                <th className="text-left px-4 py-3 text-xs font-semibold text-slate-500 uppercase tracking-wider">Template</th>
                <th className="text-left px-4 py-3 text-xs font-semibold text-slate-500 uppercase tracking-wider">Scheduled</th>
                <th className="text-left px-4 py-3 text-xs font-semibold text-slate-500 uppercase tracking-wider">Status</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800/50">
              {items.map(job => (
                <tr key={job.id} className="hover:bg-slate-800/20 transition-colors">
                  <td className="px-4 py-3 font-mono text-xs text-slate-300">{job.email}</td>
                  <td className="px-4 py-3 text-xs text-slate-400">{job.template}</td>
                  <td className="px-4 py-3 text-xs text-slate-500">{fmt(job.scheduled_for)}</td>
                  <td className={`px-4 py-3 text-xs font-medium ${statusColor[job.status] ?? 'text-slate-400'}`}>
                    {job.status}
                    {job.error && <span className="ml-2 text-red-400 font-normal truncate max-w-[200px] inline-block">{job.error}</span>}
                  </td>
                </tr>
              ))}
              {items.length === 0 && (
                <tr><td colSpan={4} className="px-4 py-10 text-center text-slate-600 text-sm">No jobs</td></tr>
              )}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
