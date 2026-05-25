import type { WaitlistDetailResponse, WaitlistEntry } from '../api'
import { TimelineEvent } from './TimelineEvent'

interface Props {
  data: WaitlistDetailResponse
}

function severityColor(s: string) {
  if (s === 'critical') return 'text-red-400 border-red-500/40 bg-red-500/5'
  if (s === 'warning') return 'text-amber-400 border-amber-500/40 bg-amber-500/5'
  return 'text-blue-400 border-blue-500/40 bg-blue-500/5'
}

export function Timeline({ data }: Props) {
  const e = data.entry

  return (
    <div className="space-y-1">
      {/* Header */}
      <div className="mb-6 p-4 bg-slate-900 rounded-xl border border-slate-800">
        <div className="flex items-center justify-between mb-1">
          <span className="font-mono text-sm text-slate-200">{e.email}</span>
          <StatusBadge entry={e} />
        </div>
        {e.url && (
          <a href={e.url} target="_blank" rel="noopener noreferrer"
            className="text-xs text-indigo-400 hover:underline">
            {e.url}
          </a>
        )}
        <div className="flex gap-4 mt-2 text-xs text-slate-600">
          {e.segment && <span>segment: {e.segment}</span>}
          {e.id && <span className="font-mono">ID: {e.id.slice(0, 8)}…</span>}
        </div>
      </div>

      {/* Events */}
      <TimelineEvent
        status="done"
        timestamp={e.submitted_at}
        title="Waitlist submitted"
        details={{ ip: e.ip ?? undefined }}
      />

      {e.scan_status !== 'pending' && (
        <TimelineEvent
          status={e.scan_status === 'running' ? 'running' : e.scan_status === 'failed' ? 'failed' : 'done'}
          timestamp={e.scan_started_at}
          title={e.scan_status === 'capped' ? 'Mini-scan capped (daily limit)' : 'Mini-scan started'}
        />
      )}

      {e.scan_status === 'done' && e.scan_result && (
        <TimelineEvent
          status="done"
          timestamp={e.scan_done_at}
          title="Mini-scan completed"
          details={{
            issues: e.scan_result.issues.length,
            pages: e.scan_result.page_count,
            duration: `${Math.round(e.scan_result.duration_ms / 1000)}s`,
            cost: e.scan_cost_usd != null ? `$${e.scan_cost_usd.toFixed(4)}` : undefined,
          }}
        />
      )}

      {e.scan_email_sent_at && (
        <TimelineEvent
          status="done"
          timestamp={e.scan_email_sent_at}
          title="Scan results email sent"
        />
      )}

      {/* Drip jobs */}
      {data.drip_jobs.map(job => (
        <TimelineEvent
          key={job.id}
          status={job.status === 'sent' ? 'done' : job.status === 'failed' ? 'failed' : job.status === 'skipped' ? 'failed' : 'pending'}
          timestamp={job.sent_at ?? job.scheduled_for}
          title={`Drip: ${job.template}`}
          details={{ scheduled: job.scheduled_for }}
        />
      ))}

      {e.invite_status !== 'none' && (
        <TimelineEvent
          status={e.invite_status === 'accepted' ? 'done' : 'done'}
          timestamp={e.invite_sent_at}
          title="Invite sent"
          details={{ status: e.invite_status }}
        />
      )}

      {e.invite_user_id && (
        <TimelineEvent
          status="done"
          timestamp={null}
          title="Invite accepted"
          details={{ user_id: e.invite_user_id.slice(0, 8) + '…' }}
        />
      )}

      {/* Issues preview */}
      {e.scan_result && e.scan_result.issues.length > 0 && (
        <div className="mt-4 p-4 bg-slate-900 rounded-xl border border-slate-800">
          <p className="text-xs font-semibold text-slate-500 uppercase tracking-wider mb-3">
            Scan issues ({e.scan_result.issues.length})
          </p>
          <div className="space-y-2">
            {e.scan_result.issues.slice(0, 5).map((issue, i) => (
              <div key={i} className={`text-xs p-2 rounded border ${severityColor(issue.severity)}`}>
                <span className="font-semibold uppercase mr-2">{issue.severity}</span>
                {issue.message}
                {issue.location && (
                  <div className="mt-0.5 text-slate-600 font-mono truncate">{issue.location}</div>
                )}
              </div>
            ))}
            {e.scan_result.issues.length > 5 && (
              <p className="text-xs text-slate-600">+ {e.scan_result.issues.length - 5} more</p>
            )}
          </div>
        </div>
      )}

      {/* Cost card */}
      {(e.scan_cost_usd != null || data.cost_summary) && (
        <div className="mt-4 p-4 bg-slate-900 rounded-xl border border-slate-800">
          <p className="text-xs font-semibold text-slate-500 uppercase tracking-wider mb-3">Cost</p>
          <div className="space-y-1 text-sm">
            {e.scan_cost_usd != null && (
              <div className="flex justify-between">
                <span className="text-slate-400">Mini-scan</span>
                <span className="font-mono text-slate-200">${e.scan_cost_usd.toFixed(4)}</span>
              </div>
            )}
            {data.cost_summary && (
              <div className="flex justify-between">
                <span className="text-slate-400">Beta runs ({data.cost_summary.run_count})</span>
                <span className="font-mono text-slate-200">${data.cost_summary.total_usd.toFixed(4)}</span>
              </div>
            )}
            {(e.scan_cost_usd != null || data.cost_summary) && (
              <div className="flex justify-between border-t border-slate-800 pt-1 mt-1">
                <span className="text-slate-300 font-medium">Total</span>
                <span className="font-mono text-white font-semibold">
                  ${((e.scan_cost_usd ?? 0) + (data.cost_summary?.total_usd ?? 0)).toFixed(4)}
                </span>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Host summary */}
      {data.host_summary && (
        <div className="mt-4 p-4 bg-slate-900 rounded-xl border border-slate-800">
          <p className="text-xs font-semibold text-slate-500 uppercase tracking-wider mb-3">App activity</p>
          <div className="grid grid-cols-3 gap-3">
            {Object.entries(data.host_summary).map(([k, v]) => (
              <div key={k} className="text-center">
                <div className="text-xl font-bold text-white">{String(v)}</div>
                <div className="text-xs text-slate-600">{k.replace(/_/g, ' ')}</div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

function StatusBadge({ entry }: { entry: WaitlistEntry }) {
  if (entry.invite_status === 'accepted') {
    return <span className="text-xs px-2 py-0.5 rounded-full bg-emerald-500/15 text-emerald-400 border border-emerald-500/30">beta active</span>
  }
  if (entry.invite_status === 'sent') {
    return <span className="text-xs px-2 py-0.5 rounded-full bg-indigo-500/15 text-indigo-400 border border-indigo-500/30">invite sent</span>
  }
  if (entry.scan_status === 'done') {
    return <span className="text-xs px-2 py-0.5 rounded-full bg-amber-500/15 text-amber-400 border border-amber-500/30">scan done</span>
  }
  if (entry.scan_status === 'running') {
    return <span className="text-xs px-2 py-0.5 rounded-full bg-yellow-500/15 text-yellow-400 border border-yellow-500/30 animate-pulse">scanning…</span>
  }
  return <span className="text-xs px-2 py-0.5 rounded-full bg-slate-500/15 text-slate-400 border border-slate-500/30">waitlist</span>
}
