import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from '@/lib/api'
import type { Issue, IssuesSummary } from '@/lib/types'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { AlertTriangle, AlertCircle, Info, ExternalLink, CheckCircle2, ShieldCheck } from 'lucide-react'

const SEVERITY_CONFIG = {
  high:   { icon: AlertCircle,  color: 'text-destructive',    border: 'border-destructive/40',  bg: 'bg-destructive/5'  },
  medium: { icon: AlertTriangle, color: 'text-amber-600',      border: 'border-amber-400/40',    bg: 'bg-amber-50/50'    },
  low:    { icon: Info,         color: 'text-muted-foreground', border: 'border-border',          bg: ''                  },
} as const

const TYPE_LABEL: Record<Issue['type'], string> = {
  console_error:   'JS Error',
  console_warning: 'JS Warning',
  network_5xx:     'Server Error',
  network_4xx:     'Not Found',
  broken_link:     'Broken Link',
  flow_stuck:      'Flow Blocked',
  semantic:        'UX Issue',
}

const STATUS_OPTIONS: Array<{ value: Issue['status']; label: string }> = [
  { value: 'acknowledged', label: 'Acknowledge' },
  { value: 'wont_fix',     label: "Won't fix"   },
  { value: 'resolved',     label: 'Mark resolved' },
  { value: 'open',         label: 'Reopen'       },
]

function SeverityBadge({ severity }: { severity: Issue['severity'] }) {
  const cfg = SEVERITY_CONFIG[severity]
  const Icon = cfg.icon
  return (
    <span className={`inline-flex items-center gap-1 text-xs font-medium ${cfg.color}`}>
      <Icon className="h-3.5 w-3.5" />
      {severity}
    </span>
  )
}

function IssueRow({ issue, productId }: { issue: Issue; productId: string }) {
  const qc = useQueryClient()
  const cfg = SEVERITY_CONFIG[issue.severity]

  const updateStatus = useMutation({
    mutationFn: (status: Issue['status']) =>
      api.patch(`/products/${productId}/issues/${issue.id}`, { status }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['issues', productId] })
      qc.invalidateQueries({ queryKey: ['issues-summary', productId] })
    },
  })

  const actions = STATUS_OPTIONS.filter(o => o.value !== issue.status)

  return (
    <details className={`border rounded-lg group ${cfg.border}`}>
      <summary className={`flex items-start gap-3 px-4 py-3 cursor-pointer list-none hover:${cfg.bg || 'bg-muted/30'} rounded-lg`}>
        <div className="mt-0.5 shrink-0">
          <SeverityBadge severity={issue.severity} />
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <Badge variant="outline" className="text-xs shrink-0">
              {TYPE_LABEL[issue.type]}
            </Badge>
            <span className="text-sm truncate">{issue.message}</span>
          </div>
          <div className="flex items-center gap-3 mt-1 text-xs text-muted-foreground">
            <span className="truncate max-w-xs">{issue.url}</span>
            {issue.occurrences > 1 && (
              <span className="shrink-0">× {issue.occurrences}</span>
            )}
          </div>
        </div>
        {issue.status !== 'open' && (
          <Badge variant="secondary" className="text-xs shrink-0">{issue.status}</Badge>
        )}
      </summary>

      <div className="px-4 pb-4 pt-2 border-t space-y-3">
        {/* Details */}
        {issue.details && Object.keys(issue.details).length > 0 && (() => {
          const d = issue.details as Record<string, string>
          return (
            <div className="space-y-1">
              {d['expected'] && (
                <div>
                  <p className="text-xs font-medium text-muted-foreground">Expected</p>
                  <p className="text-sm">{d['expected']}</p>
                </div>
              )}
              {d['actual'] && (
                <div>
                  <p className="text-xs font-medium text-muted-foreground">Actual</p>
                  <p className="text-sm">{d['actual']}</p>
                </div>
              )}
              {d['raw'] && (
                <div>
                  <p className="text-xs font-medium text-muted-foreground">Raw</p>
                  <pre className="text-xs text-muted-foreground bg-muted rounded p-2 overflow-x-auto whitespace-pre-wrap break-words">
                    {d['raw']}
                  </pre>
                </div>
              )}
            </div>
          )
        })()}

        {/* URL link */}
        <div className="flex items-center gap-2">
          <a
            href={issue.url}
            target="_blank"
            rel="noreferrer"
            className="text-xs text-muted-foreground hover:text-foreground flex items-center gap-1"
          >
            {issue.url} <ExternalLink className="h-3 w-3" />
          </a>
        </div>

        {/* Meta */}
        <div className="text-xs text-muted-foreground">
          First seen: {new Date(issue.first_seen_at).toLocaleString()}
          {issue.occurrences > 1 && ` · Last seen: ${new Date(issue.last_seen_at).toLocaleString()}`}
        </div>

        {/* Status actions */}
        <div className="flex flex-wrap gap-2">
          {actions.map(action => (
            <Button
              key={action.value}
              variant="outline"
              size="sm"
              className="h-7 text-xs"
              disabled={updateStatus.isPending}
              onClick={() => updateStatus.mutate(action.value)}
            >
              {action.label}
            </Button>
          ))}
        </div>
      </div>
    </details>
  )
}

type StatusFilter = 'open' | 'all'

export default function IssuesPanel({ productId, hasScanned }: { productId: string; hasScanned: boolean }) {
  const [statusFilter, setStatusFilter] = useState<StatusFilter>('open')

  const { data: summary, isLoading } = useQuery<IssuesSummary>({
    queryKey: ['issues-summary', productId],
    queryFn: () => api.get(`/products/${productId}/issues/summary`),
  })

  const { data: issues = [] } = useQuery<Issue[]>({
    queryKey: ['issues', productId, statusFilter],
    queryFn: () =>
      api.get(`/products/${productId}/issues${statusFilter === 'open' ? '?status=open' : ''}`),
    enabled: !!summary && summary.total > 0,
  })

  if (isLoading) return null

  // No analysis run yet
  if (!hasScanned) {
    return (
      <div>
        <h2 className="text-base font-medium mb-3">Issues</h2>
        <div className="flex items-center gap-2 text-sm text-muted-foreground py-4">
          <ShieldCheck className="h-4 w-4 shrink-0" />
          Run an analysis to automatically detect JS errors, broken links, and server errors.
        </div>
      </div>
    )
  }

  // Analysis ran but no issues found
  if (!summary || summary.total === 0) {
    return (
      <div>
        <h2 className="text-base font-medium mb-3">Issues</h2>
        <div className="flex items-center gap-2 text-sm text-green-600 py-4">
          <CheckCircle2 className="h-4 w-4 shrink-0" />
          No issues detected on last scan.
        </div>
      </div>
    )
  }

  return (
    <div>
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-base font-medium">
          Issues
          <span className="ml-2 text-sm font-normal text-muted-foreground">
            ({summary.total} found)
          </span>
        </h2>
        <div className="flex items-center gap-3 text-sm">
          {summary.high > 0 && (
            <span className="flex items-center gap-1 text-destructive font-medium">
              <AlertCircle className="h-4 w-4" /> {summary.high} high
            </span>
          )}
          {summary.medium > 0 && (
            <span className="flex items-center gap-1 text-amber-600 font-medium">
              <AlertTriangle className="h-4 w-4" /> {summary.medium} medium
            </span>
          )}
          {summary.low > 0 && (
            <span className="flex items-center gap-1 text-muted-foreground">
              <Info className="h-4 w-4" /> {summary.low} low
            </span>
          )}
        </div>
      </div>

      {/* Filter toggle */}
      <div className="flex gap-2 mb-3">
        {(['open', 'all'] as StatusFilter[]).map(f => (
          <button
            key={f}
            onClick={() => setStatusFilter(f)}
            className={`text-xs px-3 py-1 rounded-full border transition-colors ${
              statusFilter === f
                ? 'bg-foreground text-background border-foreground'
                : 'border-border text-muted-foreground hover:text-foreground'
            }`}
          >
            {f === 'open' ? 'Open' : 'All'}
          </button>
        ))}
      </div>

      <div className="space-y-2">
        {issues.length === 0 ? (
          <p className="text-sm text-muted-foreground">No open issues.</p>
        ) : (
          issues.map(issue => (
            <IssueRow key={issue.id} issue={issue} productId={productId} />
          ))
        )}
      </div>
    </div>
  )
}
