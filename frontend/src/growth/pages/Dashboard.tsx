import { useQuery } from '@tanstack/react-query'
import { growthApi } from '../api'
import { CapMeter } from '../components/CapMeter'
import { SignupFeed } from '../components/SignupFeed'
import { FunnelChart } from '../components/FunnelChart'
import { Link } from 'react-router-dom'

function KPICard({ label, value, sub }: { label: string; value: string | number; sub?: string }) {
  return (
    <div className="p-5 bg-slate-900 rounded-xl border border-slate-800">
      <p className="text-xs font-semibold text-slate-500 uppercase tracking-wider mb-1">{label}</p>
      <p className="text-3xl font-bold text-white">{value}</p>
      {sub && <p className="text-xs text-slate-600 mt-1">{sub}</p>}
    </div>
  )
}

export default function Dashboard() {
  const { data, isLoading } = useQuery({
    queryKey: ['growth-overview'],
    queryFn: growthApi.overview,
    refetchInterval: 30_000,
  })

  if (isLoading) return <div className="p-8 text-slate-500 text-sm">Loading…</div>
  if (!data) return null

  return (
    <div className="p-8 space-y-6 max-w-5xl mx-auto">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-bold text-white">Growth</h1>
        <nav className="flex gap-3 text-sm">
          <Link to="/admin/growth/waitlist" className="text-slate-400 hover:text-white transition-colors">Waitlist</Link>
          <Link to="/admin/growth/beta" className="text-slate-400 hover:text-white transition-colors">Active beta</Link>
          <Link to="/admin/growth/drip" className="text-slate-400 hover:text-white transition-colors">Drip queue</Link>
          <Link to="/admin/growth/cost" className="text-slate-400 hover:text-white transition-colors">Cost</Link>
        </nav>
      </div>

      <div className="grid grid-cols-2 gap-4">
        <KPICard label="Total waitlist" value={data.total_waitlist} />
        <KPICard label="Scans today" value={data.today_scans} sub="20/day cap" />
      </div>

      <CapMeter used={data.today_scans} limit={20} />

      <div className="grid grid-cols-2 gap-4">
        <FunnelChart />
        <SignupFeed />
      </div>
    </div>
  )
}
