import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { growthApi } from '../api'
import { WaitlistTable } from '../components/WaitlistTable'
import { Input } from '@/components/ui/input'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'

export default function WaitlistList() {
  const [q, setQ] = useState('')
  const [scanStatus, setScanStatus] = useState('')
  const [inviteStatus, setInviteStatus] = useState('')
  const [page, setPage] = useState(1)

  const { data, isLoading } = useQuery({
    queryKey: ['growth-waitlist', q, scanStatus, inviteStatus, page],
    queryFn: () => growthApi.listWaitlist({
      q: q || undefined,
      scan_status: scanStatus || undefined,
      invite_status: inviteStatus || undefined,
      page,
    }),
    placeholderData: prev => prev,
  })

  return (
    <div className="p-8 space-y-5 max-w-6xl mx-auto">
      <h1 className="text-xl font-bold text-white">Waitlist</h1>

      <div className="flex gap-3 flex-wrap">
        <Input
          placeholder="Search email or URL…"
          value={q}
          onChange={e => { setQ(e.target.value); setPage(1) }}
          className="max-w-xs bg-slate-900 border-slate-700 text-slate-200 placeholder:text-slate-600"
        />
        <Select value={scanStatus} onValueChange={v => { setScanStatus(v === 'all' ? '' : v); setPage(1) }}>
          <SelectTrigger className="w-36 bg-slate-900 border-slate-700 text-slate-300">
            <SelectValue placeholder="Scan status" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All scans</SelectItem>
            <SelectItem value="pending">Pending</SelectItem>
            <SelectItem value="running">Running</SelectItem>
            <SelectItem value="done">Done</SelectItem>
            <SelectItem value="failed">Failed</SelectItem>
            <SelectItem value="capped">Capped</SelectItem>
          </SelectContent>
        </Select>
        <Select value={inviteStatus} onValueChange={v => { setInviteStatus(v === 'all' ? '' : v); setPage(1) }}>
          <SelectTrigger className="w-36 bg-slate-900 border-slate-700 text-slate-300">
            <SelectValue placeholder="Invite status" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All invites</SelectItem>
            <SelectItem value="none">No invite</SelectItem>
            <SelectItem value="sent">Sent</SelectItem>
            <SelectItem value="accepted">Accepted</SelectItem>
          </SelectContent>
        </Select>
      </div>

      {isLoading ? (
        <div className="text-slate-500 text-sm">Loading…</div>
      ) : (
        <>
          <WaitlistTable items={data?.items ?? []} />
          <div className="flex items-center justify-between text-sm text-slate-500">
            <span>{data?.total ?? 0} entries</span>
            <div className="flex gap-2">
              <button
                onClick={() => setPage(p => Math.max(1, p - 1))}
                disabled={page <= 1}
                className="px-3 py-1 rounded bg-slate-800 hover:bg-slate-700 disabled:opacity-40 text-slate-300 text-xs"
              >← prev</button>
              <span className="px-3 py-1 text-xs">page {page}</span>
              <button
                onClick={() => setPage(p => p + 1)}
                disabled={!data || data.items.length < 50}
                className="px-3 py-1 rounded bg-slate-800 hover:bg-slate-700 disabled:opacity-40 text-slate-300 text-xs"
              >next →</button>
            </div>
          </div>
        </>
      )}
    </div>
  )
}
