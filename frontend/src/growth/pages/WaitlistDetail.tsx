import { useParams, Link } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { growthApi } from '../api'
import { Timeline } from '../components/Timeline'
import { Button } from '@/components/ui/button'
import { ArrowLeft, RefreshCw, SkipForward } from 'lucide-react'
import { useToast } from '@/components/ui/toaster'

export default function WaitlistDetail() {
  const { id } = useParams<{ id: string }>()
  const qc = useQueryClient()
  const { toast } = useToast?.() ?? { toast: () => {} }

  const { data, isLoading, error } = useQuery({
    queryKey: ['growth-waitlist-detail', id],
    queryFn: () => growthApi.getWaitlistEntry(id!),
    enabled: !!id,
  })

  const rescan = useMutation({
    mutationFn: () => growthApi.forceRescan(id!),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['growth-waitlist-detail', id] })
      toast?.({ title: 'Re-scan queued' })
    },
  })

  const skip = useMutation({
    mutationFn: () => growthApi.skipNextDrip(id!),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['growth-waitlist-detail', id] })
      toast?.({ title: 'Next drip skipped' })
    },
  })

  return (
    <div className="p-8 max-w-2xl mx-auto">
      <div className="flex items-center gap-3 mb-6">
        <Link to="/admin/growth/waitlist" className="text-slate-500 hover:text-slate-300 transition-colors">
          <ArrowLeft className="w-4 h-4" />
        </Link>
        <h1 className="text-lg font-bold text-white">User timeline</h1>
        <div className="ml-auto flex gap-2">
          <Button
            size="sm" variant="outline"
            onClick={() => rescan.mutate()}
            disabled={rescan.isPending}
            className="border-slate-700 text-slate-300 bg-transparent hover:bg-slate-800"
          >
            <RefreshCw className="w-3 h-3 mr-1.5" /> Force re-scan
          </Button>
          <Button
            size="sm" variant="outline"
            onClick={() => skip.mutate()}
            disabled={skip.isPending}
            className="border-slate-700 text-slate-300 bg-transparent hover:bg-slate-800"
          >
            <SkipForward className="w-3 h-3 mr-1.5" /> Skip next drip
          </Button>
        </div>
      </div>

      {isLoading && <div className="text-slate-500 text-sm">Loading…</div>}
      {error && <div className="text-red-400 text-sm">Failed to load</div>}
      {data && <Timeline data={data} />}
    </div>
  )
}
