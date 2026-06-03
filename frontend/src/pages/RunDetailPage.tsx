import { useParams, useNavigate } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from '@/lib/api'
import type { Run } from '@/lib/types'
import { RunStatusBadge } from './RunsPage'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Separator } from '@/components/ui/separator'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { ArrowLeft, Ban, CheckCircle2, XCircle, AlertTriangle, Loader2, Download, Copy, Check } from 'lucide-react'
import { useToast } from '@/hooks/use-toast'
import LogPanel from '@/components/LogPanel'
import { useState } from 'react'

interface ScenarioResult {
  requirement_id: string
  title: string
  status: 'pass' | 'fail' | 'error'
  priority?: string
  duration_ms?: number
  reasoning?: string
  actual?: string
}

interface Report {
  run_id: string
  url?: string
  started_at?: string
  summary?: { total: number; passed: number; failed: number; errored: number }
  results: ScenarioResult[]
  report_markdown?: string
}

function ScenarioBadge({ status }: { status: ScenarioResult['status'] }) {
  if (status === 'pass') return <Badge className="gap-1 bg-green-500/20 text-green-400 border border-green-500/30 text-xs"><CheckCircle2 className="h-3 w-3" />pass</Badge>
  if (status === 'fail') return <Badge className="gap-1 bg-red-500/20 text-red-400 border border-red-500/30 text-xs"><XCircle className="h-3 w-3" />fail</Badge>
  return <Badge className="gap-1 bg-amber-500/20 text-amber-400 border border-amber-500/30 text-xs"><AlertTriangle className="h-3 w-3" />error</Badge>
}

function StatCard({ label, value, color }: { label: string; value: number; color?: string }) {
  return (
    <div className="border border-white/10 rounded-lg p-4 text-center bg-white/5">
      <div className={`text-3xl font-semibold ${color ?? 'text-white'}`}>{value}</div>
      <div className="text-xs text-gray-400 mt-1">{label}</div>
    </div>
  )
}

export default function RunDetailPage() {
  const { runId } = useParams<{ runId: string }>()
  const navigate = useNavigate()
  const qc = useQueryClient()
  const { toast } = useToast()
  const [copied, setCopied] = useState(false)

  async function copyMarkdown() {
    try {
      const text = await fetch(`/runs/${runId}/report/markdown`).then(r => r.text())
      await navigator.clipboard.writeText(text)
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    } catch {
      toast({ title: 'Copy failed', variant: 'destructive' })
    }
  }

  const { data: run, isLoading: runLoading } = useQuery<Run>({
    queryKey: ['run', runId],
    queryFn: () => api.get(`/runs/${runId}`),
    enabled: !!runId,
    refetchInterval: (query) => {
      const status = query.state.data?.status
      return status === 'running' || status === 'pending' ? 3000 : false
    },
  })

  const { data: report } = useQuery<Report>({
    queryKey: ['report', runId],
    queryFn: () => api.get(`/runs/${runId}/report`),
    enabled: run?.status === 'done',
  })

  const cancel = useMutation({
    mutationFn: () => api.post(`/runs/${runId}/cancel`, {}),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['run', runId] })
      qc.invalidateQueries({ queryKey: ['runs'] })
      toast({ title: 'Run cancelled' })
    },
    onError: (e) => toast({ title: 'Cancel failed', description: e instanceof Error ? e.message : 'Error', variant: 'destructive' }),
  })

  if (runLoading) return <div className="p-8 text-sm text-gray-400">Loading…</div>
  if (!run) return <div className="p-8 text-sm text-gray-400">Run not found.</div>

  const summary = run.summary ?? report?.summary
  const isActive = run.status === 'running' || run.status === 'pending'

  return (
    <div className="p-8 max-w-4xl">
      <button
        onClick={() => navigate('/runs')}
        className="flex items-center gap-1 text-sm text-gray-400 hover:text-white mb-6"
      >
        <ArrowLeft className="h-4 w-4" /> Runs
      </button>

      {/* Header */}
      <div className="flex items-start justify-between mb-4">
        <div>
          <h1 className="text-xl font-semibold font-mono">{run.run_id}</h1>
          {run.spec_dir && (
            <p className="text-sm text-gray-400 mt-1">{run.spec_dir}</p>
          )}
        </div>
        <div className="flex items-center gap-2">
          <RunStatusBadge status={run.status} />
          {run.status === 'done' && (
            <>
              <Button
                variant="outline"
                size="sm"
                className="border-white/20 text-gray-300 hover:bg-white/10 hover:text-white gap-1.5"
                onClick={copyMarkdown}
              >
                {copied ? <Check className="h-3.5 w-3.5 text-green-400" /> : <Copy className="h-3.5 w-3.5" />}
                {copied ? 'Copied!' : 'Copy as markdown'}
              </Button>
              <a href={`/runs/${runId}/export`} download>
                <Button variant="outline" size="sm" className="border-white/20 text-gray-300 hover:bg-white/10 hover:text-white gap-1.5">
                  <Download className="h-3.5 w-3.5" /> Download
                </Button>
              </a>
            </>
          )}
          {isActive && (
            <Button
              variant="outline"
              size="sm"
              className="border-white/20 text-gray-300 hover:bg-white/10 hover:text-white"
              onClick={() => cancel.mutate()}
              disabled={cancel.isPending}
            >
              {cancel.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Ban className="h-4 w-4" />}
              Cancel
            </Button>
          )}
        </div>
      </div>

      {/* Timestamps + cost */}
      <div className="flex flex-wrap gap-4 text-xs text-gray-400 mb-6">
        {run.started_at && <span>Started: {new Date(run.started_at).toLocaleString()}</span>}
        {run.completed_at && <span>Completed: {new Date(run.completed_at).toLocaleString()}</span>}
      </div>

      {/* Error banner */}
      {run.status === 'failed' && run.error && (
        <Alert variant="destructive" className="mb-6">
          <AlertDescription>{run.error}</AlertDescription>
        </Alert>
      )}

      {/* Live log panel — shows while running, retained until page navigates away */}
      {runId && (
        <div className="mb-6">
          {isActive && (
            <div className="flex items-center gap-2 text-sm text-gray-400 mb-2">
              <Loader2 className="h-4 w-4 animate-spin" />
              Running scenarios…
            </div>
          )}
          <LogPanel endpoint={`/runs/${runId}/logs`} active={isActive} />
        </div>
      )}

      {/* Summary stats */}
      {summary && (
        <>
          <div className="grid grid-cols-4 gap-3 mb-6">
            <StatCard label="Total" value={summary.total} />
            <StatCard label="Passed" value={summary.passed} color="text-green-400" />
            <StatCard label="Failed" value={summary.failed} color="text-red-400" />
            <StatCard label="Errored" value={summary.errored} color="text-amber-400" />
          </div>
          <Separator className="mb-6" />
        </>
      )}

      {/* Scenario results */}
      {report && report.results.length > 0 && (
        <div>
          <h2 className="text-base font-medium mb-3">
            Scenarios
            <span className="ml-2 text-sm font-normal text-gray-400">({report.results.length})</span>
          </h2>
          <div className="space-y-2">
            {report.results.map((r) => (
              <details key={r.requirement_id} className="border border-white/10 rounded-lg group bg-white/[0.03]">
                <summary className="flex items-center gap-3 px-4 py-3 cursor-pointer list-none hover:bg-white/5">
                  <ScenarioBadge status={r.status} />
                  <span className="font-mono text-xs text-gray-400 w-20 shrink-0">{r.requirement_id}</span>
                  <span className="text-sm flex-1">{r.title}</span>
                  {r.duration_ms !== undefined && (
                    <span className="text-xs text-gray-400 shrink-0">{(r.duration_ms / 1000).toFixed(1)}s</span>
                  )}
                  {r.priority && (
                    <Badge className="text-xs shrink-0 bg-white/5 text-gray-400 border border-white/10">{r.priority}</Badge>
                  )}
                </summary>
                {(r.reasoning || r.actual) && (
                  <div className="px-4 pb-4 pt-1 space-y-2 border-t border-white/10">
                    {r.actual && (
                      <div>
                        <p className="text-xs font-medium text-gray-400 mb-1">Actual</p>
                        <p className="text-sm">{r.actual}</p>
                      </div>
                    )}
                    {r.reasoning && (
                      <div>
                        <p className="text-xs font-medium text-gray-400 mb-1">Reasoning</p>
                        <p className="text-sm text-gray-400">{r.reasoning}</p>
                      </div>
                    )}
                  </div>
                )}
              </details>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
