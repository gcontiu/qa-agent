import { useParams, Link } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { growthApi } from '../api'
import { Timeline } from '../components/Timeline'
import { Button } from '@/components/ui/button'
import { ArrowLeft, RefreshCw, SkipForward, Send, Sprout } from 'lucide-react'
import { useToast } from '@/hooks/use-toast'

export default function WaitlistDetail() {
  const { id } = useParams<{ id: string }>()
  const qc = useQueryClient()
  const { toast } = useToast()

  const { data, isLoading, error } = useQuery({
    queryKey: ['growth-waitlist-detail', id],
    queryFn: () => growthApi.getWaitlistEntry(id!),
    enabled: !!id,
  })

  const rescan = useMutation({
    mutationFn: () => growthApi.forceRescan(id!),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['growth-waitlist-detail', id] })
      toast({ title: 'Re-scan queued' })
    },
  })

  const skip = useMutation({
    mutationFn: () => growthApi.skipNextDrip(id!),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['growth-waitlist-detail', id] })
      toast({ title: 'Next drip skipped' })
    },
  })

  const invite = useMutation({
    mutationFn: () => growthApi.sendInvite(id!),
    onSuccess: (res) => {
      qc.invalidateQueries({ queryKey: ['growth-waitlist-detail', id] })
      toast({ title: `Invite sent to ${res.email}` })
    },
    onError: (err: Error) => {
      toast({ title: 'Invite failed', description: err.message, variant: 'destructive' })
    },
  })

  const seed = useMutation({
    mutationFn: () => growthApi.seedAccount(id!),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['growth-waitlist-detail', id] })
      toast({ title: 'Account seeded — product created' })
    },
    onError: (err: Error) => {
      toast({ title: 'Seed failed', description: err.message, variant: 'destructive' })
    },
  })

  const inviteStatus = data?.entry.invite_status ?? 'none'
  const canInvite = inviteStatus === 'none' || inviteStatus === 'requested'
  const canSeed = inviteStatus === 'accepted' && !!data?.entry.invite_user_id

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
          <Button
            size="sm"
            onClick={() => invite.mutate()}
            disabled={!canInvite || invite.isPending}
            className={
              inviteStatus === 'requested'
                ? 'bg-amber-500 hover:bg-amber-400 text-black disabled:opacity-40'
                : 'bg-indigo-600 hover:bg-indigo-500 text-white disabled:opacity-40'
            }
          >
            <Send className="w-3 h-3 mr-1.5" />
            {inviteStatus === 'sent' ? 'Invite sent'
              : inviteStatus === 'accepted' ? 'Accepted'
              : inviteStatus === 'requested' ? 'Approve & send invite'
              : 'Send invite'}
          </Button>
          {canSeed && (
            <Button
              size="sm" variant="outline"
              onClick={() => seed.mutate()}
              disabled={seed.isPending}
              className="border-emerald-700 text-emerald-400 bg-transparent hover:bg-emerald-900/30"
            >
              <Sprout className="w-3 h-3 mr-1.5" /> Seed account
            </Button>
          )}
        </div>
      </div>

      {isLoading && <div className="text-slate-500 text-sm">Loading…</div>}
      {error && <div className="text-red-400 text-sm">Failed to load</div>}
      {data && <Timeline data={data} />}
    </div>
  )
}
