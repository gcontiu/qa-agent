import { useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { z } from 'zod'
import { api, QuotaError } from '@/lib/api'
import { useQuota } from '@/contexts/quota'
import QuotaLimitModal from '@/components/QuotaLimitModal'
import type { Product, Spec, AnalyzeTask } from '@/lib/types'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { Badge } from '@/components/ui/badge'
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '@/components/ui/dialog'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Separator } from '@/components/ui/separator'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { ArrowLeft, Play, Loader2, CheckCircle2, XCircle, FileText, ExternalLink, Download } from 'lucide-react'
import LogPanel from '@/components/LogPanel'
import IssuesPanel from '@/components/IssuesPanel'

const analyzeSchema = z.object({
  url: z.string().url('Must be a valid URL'),
  description: z.string().min(1, 'Required'),
  spec_prefix: z.string().min(1, 'Required').max(6),
  pages: z.string().optional(),
  max_scenarios: z.string().optional(),
})
type AnalyzeForm = z.infer<typeof analyzeSchema>

function StatusBadge({ status }: { status: AnalyzeTask['status'] }) {
  if (status === 'running') return (
    <Badge className="gap-1 bg-cyan-500/20 text-cyan-400 border border-cyan-500/30">
      <Loader2 className="h-3 w-3 animate-spin" /> Running
    </Badge>
  )
  if (status === 'done') return (
    <Badge className="gap-1 bg-green-500/20 text-green-400 border border-green-500/30">
      <CheckCircle2 className="h-3 w-3" /> Done
    </Badge>
  )
  return (
    <Badge className="gap-1 bg-red-500/20 text-red-400 border border-red-500/30">
      <XCircle className="h-3 w-3" /> Failed
    </Badge>
  )
}

export default function ProductDetailPage() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const qc = useQueryClient()
  const [analyzeOpen, setAnalyzeOpen] = useState(false)
  const [taskId, setTaskId] = useState<string | null>(null)
  const [quotaModal, setQuotaModal] = useState<{ type: 'run_blocked' | 'scan_blocked'; used: number; limit: number; tier: string } | null>(null)
  const { quota, refresh: refreshQuota } = useQuota()

  const { data: product, isLoading: productLoading } = useQuery<Product>({
    queryKey: ['product', id],
    queryFn: () => api.get(`/products/${id}`),
  })

  const { data: specs = [], isLoading: specsLoading } = useQuery<Spec[]>({
    queryKey: ['specs', id],
    queryFn: () => api.get(`/products/${id}/specs`),
    enabled: !!id,
  })

  const { data: task } = useQuery<AnalyzeTask>({
    queryKey: ['analyze', id, taskId],
    queryFn: () => api.get(`/products/${id}/analyze/${taskId}`),
    enabled: !!taskId,
    refetchInterval: (query) => {
      const status = query.state.data?.status
      return status === 'running' ? 3000 : false
    },
    gcTime: 0,
  })

  // Invalidate specs + issues once analysis completes
  if (task?.status === 'done' && taskId) {
    qc.invalidateQueries({ queryKey: ['specs', id] })
    qc.invalidateQueries({ queryKey: ['issues', id] })
    qc.invalidateQueries({ queryKey: ['issues-summary', id] })
  }

  const { register, handleSubmit, reset, setValue, formState: { errors } } = useForm<AnalyzeForm>({
    resolver: zodResolver(analyzeSchema),
    defaultValues: { spec_prefix: 'SC' },
  })

  const analyze = useMutation({
    mutationFn: (data: AnalyzeForm) => {
      const maxS = data.max_scenarios ? parseInt(data.max_scenarios, 10) : undefined
      const body = {
        url: data.url,
        description: data.description,
        spec_prefix: data.spec_prefix,
        pages: data.pages ? data.pages.split(',').map(p => p.trim()).filter(Boolean) : undefined,
        max_scenarios: maxS && !isNaN(maxS) ? maxS : undefined,
      }
      return api.post<AnalyzeTask>(`/products/${id}/analyze`, body)
    },
    onSuccess: (t) => {
      setTaskId(t.task_id)
      setAnalyzeOpen(false)
      refreshQuota()
      reset()
    },
    onError: (err) => {
      if (err instanceof QuotaError) {
        setAnalyzeOpen(false)
        setQuotaModal({ type: err.quotaType, used: err.used, limit: err.limit, tier: err.tier })
      }
    },
  })

  function openAnalyzeDialog() {
    if (product) {
      setValue('url', product.url)
      setValue('description', product.description ?? '')
    }
    setAnalyzeOpen(true)
  }

  if (productLoading) return <div className="p-8 text-gray-400 text-sm">Loading…</div>
  if (!product) return <div className="p-8 text-gray-400 text-sm">Product not found.</div>

  return (
    <div className="p-8 max-w-4xl">
      <button
        onClick={() => navigate('/products')}
        className="flex items-center gap-1 text-sm text-gray-400 hover:text-white mb-6"
      >
        <ArrowLeft className="h-4 w-4" /> Products
      </button>

      {/* Header */}
      <div className="flex items-start justify-between mb-1">
        <div>
          <h1 className="text-2xl font-semibold">{product.name}</h1>
          <a
            href={product.url}
            target="_blank"
            rel="noreferrer"
            className="text-sm text-gray-400 hover:text-white flex items-center gap-1 mt-1"
          >
            {product.url} <ExternalLink className="h-3 w-3" />
          </a>
        </div>
        <div className="flex flex-col items-end gap-2">
          <div className="flex items-center gap-2">
            {specs.length > 0 && (
              <a href={`/products/${id}/specs/export`} download>
                <Button variant="outline" size="sm" className="border-white/20 text-gray-300 hover:bg-white/10 hover:text-white gap-1.5">
                  <Download className="h-3.5 w-3.5" /> Download specs
                </Button>
              </a>
            )}
            <Button onClick={openAnalyzeDialog} disabled={task?.status === 'running'} className="bg-cyan-500 hover:bg-cyan-400 text-black disabled:opacity-60">
              {task?.status === 'running'
                ? <><Loader2 className="h-4 w-4 mr-2 animate-spin" /> Scanning…</>
                : <><Play className="h-4 w-4 mr-2" /> Scan</>
              }
            </Button>
          </div>
          {quota && (
            <span className={`text-xs ${quota.usage.scans_this_month >= quota.limits.scans_per_month ? 'text-red-400' : 'text-gray-400'}`}>
              {quota.usage.scans_this_month}/{quota.limits.scans_per_month} scans this month
            </span>
          )}
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
      </div>

      {product.description && (
        <p className="text-sm text-gray-400 mt-2">{product.description}</p>
      )}

      {/* Analysis status */}
      {task && (
        <div className="mt-6">
          <div className="flex items-center gap-3 mb-2">
            <span className="text-sm font-medium">Last scan</span>
            <StatusBadge status={task.status} />
            {task.cost_usd && (
              <span className="text-xs text-gray-400">${task.cost_usd.toFixed(3)}</span>
            )}
          </div>
          {task.status === 'running' && (
            <p className="text-sm text-gray-400">Scanning and generating specs…</p>
          )}
          {task.status === 'done' && (
            <div className="mt-4 space-y-3">
              {task.issues_count !== undefined && (
                <span className={`inline-flex items-center text-xs font-medium px-3 py-1 rounded-full ${
                  task.issues_count > 0
                    ? 'bg-amber-500/10 text-amber-600'
                    : 'bg-green-500/10 text-green-600'
                }`}>
                  {task.issues_count > 0
                    ? `${task.issues_count} issue${task.issues_count !== 1 ? 's' : ''} found`
                    : 'No issues found'}
                </span>
              )}
              {task.summary && (
                <details className="group" open>
                  <summary className="text-xs text-gray-400 cursor-pointer hover:text-foreground list-none flex items-center gap-1">
                    <span className="group-open:hidden">▶ Show summary</span>
                    <span className="hidden group-open:inline">▼ Hide summary</span>
                  </summary>
                  <p className="mt-2 text-sm text-gray-400 leading-relaxed border-l-2 border-white/20 pl-3">
                    {task.summary}
                  </p>
                </details>
              )}
            </div>
          )}
          {task.status === 'failed' && task.error && (
            <Alert variant="destructive" className="mt-2">
              <AlertDescription>{task.error}</AlertDescription>
            </Alert>
          )}
          {taskId && (
            <div className="mt-3">
              <LogPanel
                endpoint={`/products/${id}/analyze/${taskId}/logs`}
                active={task.status === 'running'}
              />
            </div>
          )}
        </div>
      )}

      <Separator className="my-6" />

      {/* Specs list */}
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-base font-medium">
          Specs
          {specs.length > 0 && (
            <span className="ml-2 text-gray-400 font-normal text-sm">({specs.length})</span>
          )}
        </h2>
      </div>

      {specs.length > 0 && (
        <div className="mb-4 rounded-lg border border-white/10 bg-white/5 px-4 py-3 text-xs text-gray-400 space-y-1">
          <p><span className="font-medium text-white">draft</span> — generated by the analyst, not yet reviewed. Open the file to edit or approve it.</p>
          <p><span className="font-medium text-white">approved</span> — reviewed and ready to execute. Only approved specs are included in a run.</p>
          <p><span className="font-medium text-white">config.yaml</span> — product metadata (base URL, environment, context for the executor). Not a test file and not subject to approval.</p>
        </div>
      )}

      {specsLoading ? (
        <p className="text-sm text-gray-400">Loading specs…</p>
      ) : specs.length === 0 ? (
        <p className="text-sm text-gray-400">
          No specs yet. Run the analyst to generate Gherkin specifications.
        </p>
      ) : (
        <div className="border border-white/10 rounded-lg overflow-hidden">
          <Table>
            <TableHeader>
              <TableRow className="border-b border-white/10 hover:bg-transparent">
                <TableHead className="text-gray-400">File</TableHead>
                <TableHead className="text-gray-400">Status</TableHead>
                <TableHead className="text-gray-400">Updated</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {specs.map(spec => (
                <TableRow key={spec.id} className="cursor-pointer border-b border-white/10 hover:bg-white/5"
                  onClick={() => navigate(`/products/${id}/specs/${encodeURIComponent(spec.filename)}`)}>
                  <TableCell>
                    <span className="flex items-center gap-2 font-medium text-sm">
                      <FileText className="h-4 w-4 text-gray-400" />
                      {spec.filename}
                    </span>
                  </TableCell>
                  <TableCell>
                    {spec.filename === 'config.yaml'
                      ? <Badge className="bg-white/5 text-gray-400 border border-white/10">config</Badge>
                      : <Badge className={spec.approved
                            ? 'bg-cyan-500/20 text-cyan-400 border border-cyan-500/30'
                            : 'bg-white/5 text-gray-400 border border-white/10'}>
                          {spec.approved ? 'approved' : 'draft'}
                        </Badge>
                    }
                  </TableCell>
                  <TableCell className="text-sm text-gray-400">
                    {new Date(spec.updated_at).toLocaleDateString()}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      )}

      {id && (
        <>
          <Separator className="my-6" />
          <IssuesPanel productId={id} hasScanned={!!task || specs.length > 0} />
        </>
      )}

      {/* Analyze dialog */}
      <Dialog open={analyzeOpen} onOpenChange={setAnalyzeOpen}>
        <DialogContent onOpenAutoFocus={(e) => e.preventDefault()} className="bg-[#0d1024] border border-white/10 text-white">
          <DialogHeader>
            <DialogTitle className="text-white">Scan product</DialogTitle>
          </DialogHeader>
          <form onSubmit={handleSubmit(d => analyze.mutate(d))}>
            <div className="space-y-4 py-2">
              <div className="space-y-1.5">
                <Label className="text-gray-300">URL to crawl</Label>
                <Input
                  {...register('url')}
                  className="bg-white/5 border-white/10 text-white placeholder:text-gray-600 focus:border-cyan-500/50"
                />
                {errors.url && <p className="text-xs text-red-400">{errors.url.message}</p>}
              </div>
              <div className="space-y-1.5">
                <Label className="text-gray-300">Description</Label>
                <Textarea
                  {...register('description')}
                  rows={3}
                  placeholder="Short description of the product for the analyst"
                  className="bg-white/5 border-white/10 text-white placeholder:text-gray-600 focus:border-cyan-500/50 resize-none"
                />
                {errors.description && <p className="text-xs text-red-400">{errors.description.message}</p>}
              </div>
              <div className="space-y-1.5">
                <Label className="text-gray-300">Spec prefix</Label>
                <Input
                  {...register('spec_prefix')}
                  className="w-24 bg-white/5 border-white/10 text-white placeholder:text-gray-600 focus:border-cyan-500/50"
                />
                <p className="text-xs text-gray-500">Short uppercase prefix for requirement IDs (e.g. SC, GP)</p>
                {errors.spec_prefix && <p className="text-xs text-red-400">{errors.spec_prefix.message}</p>}
              </div>
              <div className="space-y-1.5">
                <Label className="text-gray-300">
                  Pages <span className="text-gray-500 font-normal">(optional)</span>
                </Label>
                <Input
                  {...register('pages')}
                  placeholder="/,/about,/contact"
                  className="bg-white/5 border-white/10 text-white placeholder:text-gray-600 focus:border-cyan-500/50"
                />
                <p className="text-xs text-gray-500">Comma-separated paths. Leave blank to crawl the whole site.</p>
              </div>
              <div className="space-y-1.5">
                <Label className="text-gray-300">
                  Max scenarios per page <span className="text-gray-500 font-normal">(optional)</span>
                </Label>
                <Input
                  {...register('max_scenarios')}
                  type="number"
                  min={1}
                  className="w-28 bg-white/5 border-white/10 text-white placeholder:text-gray-600 focus:border-cyan-500/50"
                  placeholder="e.g. 3"
                />
                <p className="text-xs text-gray-500">Hard cap on scenarios generated per feature file.</p>
              </div>
            </div>
            <DialogFooter className="mt-6">
              <Button
                type="button"
                variant="ghost"
                onClick={() => setAnalyzeOpen(false)}
                className="text-gray-400 hover:bg-white/10 hover:text-white"
              >
                Cancel
              </Button>
              <Button type="submit" disabled={analyze.isPending} className="bg-cyan-500 hover:bg-cyan-400 text-black">
                {analyze.isPending ? 'Starting…' : 'Start scan'}
              </Button>
            </DialogFooter>
            {analyze.isError && (
              <p className="text-xs text-red-400 mt-2">
                {analyze.error instanceof Error ? analyze.error.message : 'Error'}
              </p>
            )}
          </form>
        </DialogContent>
      </Dialog>
    </div>
  )
}
