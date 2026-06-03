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

// ── source mode toggle ────────────────────────────────────────────────────────
type SourceMode = 'product' | 'spec_dir'

const productSchema = z.object({
  mode: z.literal('product'),
  product_id: z.string().min(1, 'Required'),
  executor_model: z.string().optional(),
  max_scenarios: z.string().optional(),
})
const specDirSchema = z.object({
  mode: z.literal('spec_dir'),
  spec_dir: z.string().min(1, 'Required'),
  executor_model: z.string().optional(),
  max_scenarios: z.string().optional(),
})
const runSchema = z.discriminatedUnion('mode', [productSchema, specDirSchema])
type RunForm = z.infer<typeof runSchema>

// ── status badge ──────────────────────────────────────────────────────────────
export function RunStatusBadge({ status }: { status: Run['status'] }) {
  switch (status) {
    case 'running':
      return <Badge variant="secondary" className="gap-1"><Loader2 className="h-3 w-3 animate-spin" />Running</Badge>
    case 'pending':
      return <Badge variant="outline" className="gap-1"><Clock className="h-3 w-3" />Pending</Badge>
    case 'done':
      return <Badge className="gap-1 bg-green-600"><CheckCircle2 className="h-3 w-3" />Done</Badge>
    case 'cancelled':
      return <Badge variant="outline" className="gap-1 text-muted-foreground"><Ban className="h-3 w-3" />Cancelled</Badge>
    default:
      return <Badge variant="destructive" className="gap-1"><XCircle className="h-3 w-3" />Failed</Badge>
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
  const [sourceMode, setSourceMode] = useState<SourceMode>('product')
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

  const { data: specDirs = [] } = useQuery<string[]>({
    queryKey: ['spec-dirs'],
    queryFn: () => api.get('/spec-dirs'),
    enabled: newRunOpen,
  })

  const { data: products = [] } = useQuery<Product[]>({
    queryKey: ['products'],
    queryFn: () => api.get('/products'),
    enabled: newRunOpen && sourceMode === 'product',
  })

  const { register, handleSubmit, reset, control, formState: { errors } } = useForm<RunForm>({
    resolver: zodResolver(runSchema),
    defaultValues: { mode: 'product', product_id: '', executor_model: '', max_scenarios: '' },
  })

  function openDialog() {
    setSourceMode('product')
    reset({ mode: 'product', product_id: '', executor_model: '', max_scenarios: '' })
    setNewRunOpen(true)
  }

  function switchMode(mode: SourceMode) {
    setSourceMode(mode)
    if (mode === 'product') {
      reset({ mode: 'product', product_id: '', executor_model: '', max_scenarios: '' })
    } else {
      reset({ mode: 'spec_dir', spec_dir: '', executor_model: '', max_scenarios: '' })
    }
  }

  const create = useMutation({
    mutationFn: (data: RunForm) => {
      const maxS = data.max_scenarios ? parseInt(data.max_scenarios, 10) : undefined
      const body =
        data.mode === 'product'
          ? { product_id: data.product_id }
          : { spec_dir: `specs/${data.spec_dir}` }
      return api.post<Run>('/runs', {
        ...body,
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
        <Button onClick={openDialog}>
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
        <p>Start a run by selecting a <span className="font-medium text-white">Product</span> (uses its approved specs) or a <span className="font-medium text-white">Spec directory</span> (uses files from the <code>specs/</code> folder on the server).</p>
        <p>Only specs with status <span className="font-medium text-white">approved</span> are included. Approve specs from the product's detail page before running.</p>
      </div>

      {isLoading ? (
        <p className="text-sm text-muted-foreground">Loading…</p>
      ) : runs.length === 0 ? (
        <p className="text-sm text-muted-foreground">
          No runs yet. Start one from a product's detail page or use the New run button.
        </p>
      ) : (
        <div className="border rounded-lg overflow-hidden">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Run ID</TableHead>
                <TableHead>Status</TableHead>
                <TableHead>Pass rate</TableHead>
                <TableHead>Started</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {runs.map(run => (
                <TableRow
                  key={run.run_id}
                  className="cursor-pointer hover:bg-muted/50"
                  onClick={() => navigate(`/runs/${encodeURIComponent(run.run_id)}`)}
                >
                  <TableCell className="font-mono text-sm">{run.run_id}</TableCell>
                  <TableCell><RunStatusBadge status={run.status} /></TableCell>
                  <TableCell className="text-sm text-muted-foreground">
                    {passRate(run) ?? '—'}
                  </TableCell>
                  <TableCell className="text-sm text-muted-foreground">
                    {run.started_at ? new Date(run.started_at).toLocaleString() : '—'}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      )}

      <Dialog open={newRunOpen} onOpenChange={setNewRunOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>New run</DialogTitle>
          </DialogHeader>
          <form onSubmit={handleSubmit(d => create.mutate(d))}>
            <div className="space-y-4 py-2">

              {/* source toggle */}
              <div className="flex gap-1 p-1 bg-muted rounded-md w-fit">
                <button
                  type="button"
                  onClick={() => switchMode('product')}
                  className={`px-3 py-1 text-sm rounded transition-colors ${
                    sourceMode === 'product'
                      ? 'bg-background shadow text-foreground'
                      : 'text-muted-foreground hover:text-foreground'
                  }`}
                >
                  Product
                </button>
                <button
                  type="button"
                  onClick={() => switchMode('spec_dir')}
                  className={`px-3 py-1 text-sm rounded transition-colors ${
                    sourceMode === 'spec_dir'
                      ? 'bg-background shadow text-foreground'
                      : 'text-muted-foreground hover:text-foreground'
                  }`}
                >
                  Spec dir
                </button>
              </div>

              {/* source-specific field */}
              {sourceMode === 'product' ? (
                <div className="space-y-1">
                  <Label>Product</Label>
                  <Controller
                    name={'product_id' as never}
                    control={control}
                    render={({ field }) => (
                      <SelectInDialog modal={false} onValueChange={field.onChange} value={field.value as string}>
                        <SelectTrigger>
                          <SelectValue placeholder={products.length === 0 ? 'No products found' : 'Select a product…'} />
                        </SelectTrigger>
                        <SelectContent>
                          {products.map(p => (
                            <SelectItem key={p.id} value={p.id}>
                              <span>{p.name}</span>
                              <span className="ml-2 text-muted-foreground text-xs">{p.url}</span>
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </SelectInDialog>
                    )}
                  />
                  {'product_id' in errors && errors.product_id && (
                    <p className="text-xs text-destructive">{errors.product_id.message as string}</p>
                  )}
                </div>
              ) : (
                <div className="space-y-1">
                  <Label>Spec directory</Label>
                  <Controller
                    name={'spec_dir' as never}
                    control={control}
                    render={({ field }) => (
                      <SelectInDialog modal={false} onValueChange={field.onChange} value={field.value as string}>
                        <SelectTrigger>
                          <SelectValue placeholder={specDirs.length === 0 ? 'No spec dirs found' : 'Select a spec directory…'} />
                        </SelectTrigger>
                        <SelectContent>
                          {specDirs.map(d => (
                            <SelectItem key={d} value={d}>{d}</SelectItem>
                          ))}
                        </SelectContent>
                      </SelectInDialog>
                    )}
                  />
                  {'spec_dir' in errors && errors.spec_dir && (
                    <p className="text-xs text-destructive">{errors.spec_dir.message as string}</p>
                  )}
                </div>
              )}

              <div className="space-y-1">
                <Label>Executor model <span className="text-muted-foreground">(optional)</span></Label>
                <Controller
                  name={'executor_model' as never}
                  control={control}
                  render={({ field }) => (
                    <SelectInDialog modal={false} onValueChange={field.onChange} value={field.value as string}>
                      <SelectTrigger>
                        <SelectValue placeholder="Default (Haiku — fastest, cheapest)" />
                      </SelectTrigger>
                      <SelectContent>
                        {MODEL_OPTIONS.map(({ value, label }) => {
                          const allowed = modelsAllowed.includes(value)
                          return (
                            <SelectItem key={value} value={value} disabled={!allowed}>
                              <span className={allowed ? '' : 'text-muted-foreground'}>{label}</span>
                              {!allowed && (
                                <span className="ml-2 text-xs rounded px-1.5 py-0.5 bg-muted text-muted-foreground">
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
              <div className="space-y-1">
                <Label>Max scenarios <span className="text-muted-foreground">(optional)</span></Label>
                <Input {...register('max_scenarios')} type="number" min={1} className="w-28" />
              </div>
            </div>
            <DialogFooter className="mt-4">
              <Button type="button" variant="outline" onClick={() => setNewRunOpen(false)}>Cancel</Button>
              <Button type="submit" disabled={create.isPending}>
                {create.isPending ? 'Starting…' : 'Start run'}
              </Button>
            </DialogFooter>
            {create.isError && (
              <p className="text-xs text-destructive mt-2">
                {create.error instanceof Error ? create.error.message : 'Error'}
              </p>
            )}
          </form>
        </DialogContent>
      </Dialog>
    </div>
  )
}
