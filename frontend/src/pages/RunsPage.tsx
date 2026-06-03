import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useForm, Controller } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { z } from 'zod'
import { api, QuotaError } from '@/lib/api'
import { useQuota } from '@/contexts/quota'
import QuotaLimitModal from '@/components/QuotaLimitModal'
import type { Run, Product } from '@/lib/types'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Badge } from '@/components/ui/badge'
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '@/components/ui/dialog'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import type { ComponentProps } from 'react'

// modal prop exists in Radix but is missing from shadcn's re-exported types
const SelectInDialog = Select as React.ComponentType<ComponentProps<typeof Select> & { modal?: boolean }>
import { Play, Loader2, CheckCircle2, XCircle, Clock, Ban } from 'lucide-react'

const runSchema = z.object({
  product_id: z.string().min(1, 'Required'),
  executor_model: z.string().optional(),
  max_scenarios: z.string().optional(),
})
type RunForm = z.infer<typeof runSchema>

// ── status badge ──────────────────────────────────────────────────────────────
export function RunStatusBadge({ status }: { status: Run['status'] }) {
  switch (status) {
    case 'running':
      return <Badge className="gap-1 bg-cyan-500/20 text-cyan-400 border border-cyan-500/30"><Loader2 className="h-3 w-3 animate-spin" />Running</Badge>
    case 'pending':
      return <Badge className="gap-1 bg-white/5 text-gray-400 border border-white/10"><Clock className="h-3 w-3" />Pending</Badge>
    case 'done':
      return <Badge className="gap-1 bg-green-500/20 text-green-400 border border-green-500/30"><CheckCircle2 className="h-3 w-3" />Done</Badge>
    case 'cancelled':
      return <Badge className="gap-1 bg-white/5 text-gray-500 border border-white/10"><Ban className="h-3 w-3" />Cancelled</Badge>
    default:
      return <Badge className="gap-1 bg-red-500/20 text-red-400 border border-red-500/30"><XCircle className="h-3 w-3" />Failed</Badge>
  }
}

function passRate(run: Run): string | null {
  const s = run.summary
  if (!s || s.total === 0) return null
  const pct = Math.round((s.passed / s.total) * 100)
  return `${s.passed}/${s.total} (${pct}%)`
}

// ── page ──────────────────────────────────────────────────────────────────────
export default function RunsPage() {
  const navigate = useNavigate()
  const qc = useQueryClient()
  const { quota, refresh: refreshQuota } = useQuota()
  const [newRunOpen, setNewRunOpen] = useState(false)
  const [quotaModal, setQuotaModal] = useState<{ type: 'run_blocked' | 'scan_blocked'; used: number; limit: number; tier: string } | null>(null)

  const { data: runs = [], isLoading } = useQuery<Run[]>({
    queryKey: ['runs'],
    queryFn: () => api.get('/runs'),
    refetchInterval: (query) => {
      const active = (query.state.data ?? []).some(
        r => r.status === 'running' || r.status === 'pending',
      )
      return active ? 3000 : false
    },
  })

  const { data: products = [] } = useQuery<Product[]>({
    queryKey: ['products'],
    queryFn: () => api.get('/products'),
    enabled: newRunOpen,
  })

  const { register, handleSubmit, reset, control, formState: { errors } } = useForm<RunForm>({
    resolver: zodResolver(runSchema),
    defaultValues: { product_id: '', executor_model: '', max_scenarios: '' },
  })

  function openDialog() {
    reset({ product_id: '', executor_model: '', max_scenarios: '' })
    setNewRunOpen(true)
  }

  const create = useMutation({
    mutationFn: (data: RunForm) => {
      const maxS = data.max_scenarios ? parseInt(data.max_scenarios, 10) : undefined
      return api.post<Run>('/runs', {
        product_id: data.product_id,
        executor_model: data.executor_model || undefined,
        max_scenarios: maxS && !isNaN(maxS) ? maxS : undefined,
      })
    },
    onSuccess: (run) => {
      qc.invalidateQueries({ queryKey: ['runs'] })
      refreshQuota()
      setNewRunOpen(false)
      reset()
      navigate(`/runs/${encodeURIComponent(run.run_id)}`)
    },
    onError: (err) => {
      if (err instanceof QuotaError) {
        setNewRunOpen(false)
        setQuotaModal({ type: err.quotaType, used: err.used, limit: err.limit, tier: err.tier })
      }
    },
  })

  const runsUsed = quota?.usage.runs_this_month ?? 0
  const runsLimit = quota?.limits.runs_per_month ?? 0
  const modelsAllowed = quota?.models_allowed ?? ['claude-haiku-4-5-20251001']

  const MODEL_OPTIONS = [
    { value: 'claude-haiku-4-5-20251001', label: 'Haiku', requiredTier: 'free' },
    { value: 'claude-sonnet-4-6',         label: 'Sonnet', requiredTier: 'starter' },
    { value: 'claude-opus-4-7',           label: 'Opus',   requiredTier: 'pro' },
  ]

  return (
    <div className="p-8 max-w-4xl">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-semibold">Runs</h1>
          {quota && (
            <p className={`text-xs mt-0.5 ${runsUsed >= runsLimit ? 'text-red-400' : 'text-muted-foreground'}`}>
              {runsUsed}/{runsLimit} runs used this month
            </p>
          )}
        </div>
        <Button onClick={openDialog} className="bg-cyan-500 hover:bg-cyan-400 text-black">
          <Play className="h-4 w-4 mr-2" />New run
        </Button>
      </div>

      {quotaModal && (
        <QuotaLimitModal
          open
          onClose={() => setQuotaModal(null)}
          type={quotaModal.type}
          used={quotaModal.used}
          limit={quotaModal.limit}
          tier={quotaModal.tier}
        />
      )}

      <div className="mb-6 rounded-lg border border-white/10 bg-white/5 px-4 py-3 text-xs text-gray-400 space-y-1">
        <p>A <span className="font-medium text-white">Run</span> executes your approved specs against the live product and reports a pass/fail verdict for each scenario.</p>
        <p>Only specs with status <span className="font-medium text-white">approved</span> are included. Approve specs from the product's detail page before running.</p>
      </div>

      {isLoading ? (
        <p className="text-sm text-muted-foreground">Loading…</p>
      ) : runs.length === 0 ? (
        <p className="text-sm text-muted-foreground">
          No runs yet. Start one from a product's detail page or use the New run button.
        </p>
      ) : (
        <div className="border border-white/10 rounded-lg overflow-hidden">
          <Table>
            <TableHeader>
              <TableRow className="border-b border-white/10 hover:bg-transparent">
                <TableHead className="text-gray-400">Run ID</TableHead>
                <TableHead className="text-gray-400">Status</TableHead>
                <TableHead className="text-gray-400">Pass rate</TableHead>
                <TableHead className="text-gray-400">Started</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {runs.map(run => (
                <TableRow
                  key={run.run_id}
                  className="cursor-pointer border-b border-white/10 hover:bg-white/5"
                  onClick={() => navigate(`/runs/${encodeURIComponent(run.run_id)}`)}
                >
                  <TableCell className="font-mono text-sm text-white">{run.run_id}</TableCell>
                  <TableCell><RunStatusBadge status={run.status} /></TableCell>
                  <TableCell className="text-sm text-gray-400">
                    {passRate(run) ?? '—'}
                  </TableCell>
                  <TableCell className="text-sm text-gray-400">
                    {run.started_at ? new Date(run.started_at).toLocaleString() : '—'}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      )}

      <Dialog open={newRunOpen} onOpenChange={setNewRunOpen}>
        <DialogContent className="bg-[#0d1024] border border-white/10 text-white">
          <DialogHeader>
            <DialogTitle className="text-white">New run</DialogTitle>
          </DialogHeader>
          <form onSubmit={handleSubmit(d => create.mutate(d))}>
            <div className="space-y-4 py-2">

              <div className="space-y-1.5">
                <Label className="text-gray-300">Product</Label>
                <Controller
                  name="product_id"
                  control={control}
                  render={({ field }) => (
                    <SelectInDialog modal={false} onValueChange={field.onChange} value={field.value}>
                      <SelectTrigger className="bg-white/5 border-white/10 text-white focus:border-cyan-500/50">
                        <SelectValue placeholder={products.length === 0 ? 'No products found' : 'Select a product…'} />
                      </SelectTrigger>
                      <SelectContent className="bg-[#0d1024] border-white/10">
                        {products.map(p => (
                          <SelectItem key={p.id} value={p.id} className="text-white focus:bg-white/10 focus:text-white">
                            <span>{p.name}</span>
                            <span className="ml-2 text-gray-500 text-xs">{p.url}</span>
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </SelectInDialog>
                  )}
                />
                {errors.product_id && (
                  <p className="text-xs text-red-400">{errors.product_id.message}</p>
                )}
              </div>

              <div className="space-y-1.5">
                <Label className="text-gray-300">
                  Executor model <span className="text-gray-500 font-normal">(optional)</span>
                </Label>
                <Controller
                  name="executor_model"
                  control={control}
                  render={({ field }) => (
                    <SelectInDialog modal={false} onValueChange={field.onChange} value={field.value}>
                      <SelectTrigger className="bg-white/5 border-white/10 text-white focus:border-cyan-500/50">
                        <SelectValue placeholder="Default (Haiku — fastest, cheapest)" />
                      </SelectTrigger>
                      <SelectContent className="bg-[#0d1024] border-white/10">
                        {MODEL_OPTIONS.map(({ value, label }) => {
                          const allowed = modelsAllowed.includes(value)
                          return (
                            <SelectItem key={value} value={value} disabled={!allowed} className="text-white focus:bg-white/10 focus:text-white">
                              <span className={allowed ? '' : 'text-gray-500'}>{label}</span>
                              {!allowed && (
                                <span className="ml-2 text-xs rounded px-1.5 py-0.5 bg-white/5 text-gray-500">
                                  Not on your plan
                                </span>
                              )}
                            </SelectItem>
                          )
                        })}
                      </SelectContent>
                    </SelectInDialog>
                  )}
                />
              </div>

              <div className="space-y-1.5">
                <Label className="text-gray-300">
                  Max scenarios <span className="text-gray-500 font-normal">(optional)</span>
                </Label>
                <Input
                  {...register('max_scenarios')}
                  type="number"
                  min={1}
                  className="w-28 bg-white/5 border-white/10 text-white placeholder:text-gray-600 focus:border-cyan-500/50"
                />
              </div>
            </div>
            <DialogFooter className="mt-6">
              <Button
                type="button"
                variant="outline"
                onClick={() => setNewRunOpen(false)}
                className="border-white/20 text-gray-300 hover:bg-white/10 hover:text-white"
              >
                Cancel
              </Button>
              <Button type="submit" disabled={create.isPending} className="bg-cyan-500 hover:bg-cyan-400 text-black">
                {create.isPending ? 'Starting…' : 'Start run'}
              </Button>
            </DialogFooter>
            {create.isError && (
              <p className="text-xs text-red-400 mt-2">
                {create.error instanceof Error ? create.error.message : 'Error'}
              </p>
            )}
          </form>
        </DialogContent>
      </Dialog>
    </div>
  )
}
