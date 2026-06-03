import { useState } from 'react'
import { Link } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { growthApi } from '../api'
import { ArrowLeft } from 'lucide-react'

const W = 680
const H = 240
const PAD = { top: 12, right: 24, bottom: 32, left: 52 }
const INNER_W = W - PAD.left - PAD.right
const INNER_H = H - PAD.top - PAD.bottom

function fmt(day: string) {
  return new Date(day).toLocaleDateString('en-GB', { day: 'numeric', month: 'short' })
}

interface ChartPoint { label: string; cumulative: number }

function SvgChart({ points }: { points: ChartPoint[] }) {
  const [hover, setHover] = useState<{ x: number; y: number; label: string; value: number } | null>(null)

  if (points.length === 0) return <p className="text-slate-500 text-sm">No scan data yet.</p>

  const maxY = Math.max(...points.map(p => p.cumulative), 200) * 1.1
  const minY = 0

  function px(i: number) {
    return PAD.left + (i / Math.max(points.length - 1, 1)) * INNER_W
  }
  function py(v: number) {
    return PAD.top + INNER_H - ((v - minY) / (maxY - minY)) * INNER_H
  }

  const polyline = points.map((p, i) => `${px(i)},${py(p.cumulative)}`).join(' ')

  // Y axis ticks
  const yTicks: number[] = []
  const step = maxY <= 5 ? 1 : maxY <= 20 ? 5 : maxY <= 50 ? 10 : maxY <= 200 ? 50 : 100
  for (let v = 0; v <= maxY; v += step) yTicks.push(v)

  // X axis ticks — show at most 6
  const xStep = Math.max(1, Math.floor(points.length / 6))
  const xTicks = points
    .map((p, i) => ({ i, label: p.label }))
    .filter((_, i) => i % xStep === 0 || i === points.length - 1)

  return (
    <div className="relative">
      <svg
        viewBox={`0 0 ${W} ${H}`}
        className="w-full"
        style={{ height: H }}
        onMouseLeave={() => setHover(null)}
      >
        {/* grid lines */}
        {yTicks.map(v => (
          <line
            key={v}
            x1={PAD.left} y1={py(v)}
            x2={PAD.left + INNER_W} y2={py(v)}
            stroke="#1e293b" strokeWidth={1}
          />
        ))}

        {/* $50 reference */}
        {50 <= maxY && (
          <>
            <line
              x1={PAD.left} y1={py(50)}
              x2={PAD.left + INNER_W} y2={py(50)}
              stroke="#f59e0b" strokeWidth={1} strokeDasharray="4 4"
            />
            <text x={PAD.left + INNER_W + 3} y={py(50) + 4} fill="#f59e0b" fontSize={10}>$50</text>
          </>
        )}

        {/* $200 reference */}
        {200 <= maxY && (
          <>
            <line
              x1={PAD.left} y1={py(200)}
              x2={PAD.left + INNER_W} y2={py(200)}
              stroke="#ef4444" strokeWidth={1} strokeDasharray="4 4"
            />
            <text x={PAD.left + INNER_W + 3} y={py(200) + 4} fill="#ef4444" fontSize={10}>$200</text>
          </>
        )}

        {/* Y axis ticks */}
        {yTicks.map(v => (
          <text key={v} x={PAD.left - 6} y={py(v) + 4} fill="#64748b" fontSize={10} textAnchor="end">
            ${v}
          </text>
        ))}

        {/* X axis ticks */}
        {xTicks.map(({ i, label }) => (
          <text
            key={i}
            x={px(i)} y={PAD.top + INNER_H + 16}
            fill="#64748b" fontSize={10} textAnchor="middle"
          >
            {label}
          </text>
        ))}

        {/* fill area */}
        <polygon
          points={`${PAD.left},${py(0)} ${polyline} ${PAD.left + INNER_W * (Math.max(points.length - 1, 1)) / Math.max(points.length - 1, 1)},${py(0)}`}
          fill="#6366f1" fillOpacity={0.08}
        />

        {/* line */}
        <polyline points={polyline} fill="none" stroke="#6366f1" strokeWidth={2} strokeLinejoin="round" />

        {/* dots + hover targets */}
        {points.map((p, i) => (
          <circle
            key={i}
            cx={px(i)} cy={py(p.cumulative)}
            r={4} fill="#6366f1" stroke="#0f172a" strokeWidth={1.5}
            style={{ cursor: 'crosshair' }}
            onMouseEnter={() => setHover({ x: px(i), y: py(p.cumulative), label: p.label, value: p.cumulative })}
          />
        ))}

        {/* tooltip */}
        {hover && (() => {
          const tx = hover.x + 12 > W - 100 ? hover.x - 120 : hover.x + 12
          return (
            <g>
              <rect x={tx} y={hover.y - 28} width={108} height={36}
                rx={6} fill="#0f172a" stroke="#1e293b" strokeWidth={1} />
              <text x={tx + 8} y={hover.y - 12} fill="#94a3b8" fontSize={10}>{hover.label}</text>
              <text x={tx + 8} y={hover.y + 2} fill="#ffffff" fontSize={12} fontWeight="bold">
                ${hover.value.toFixed(4)}
              </text>
            </g>
          )
        })()}
      </svg>

      {/* legend */}
      <div className="flex items-center gap-4 mt-2 text-xs text-slate-500">
        <span className="flex items-center gap-1.5">
          <span className="inline-block w-6 h-0.5 bg-indigo-500 rounded" />
          Cumulative cost
        </span>
        <span className="flex items-center gap-1.5">
          <span className="inline-block w-6 border-t border-dashed border-amber-400" />
          $50
        </span>
        <span className="flex items-center gap-1.5">
          <span className="inline-block w-6 border-t border-dashed border-red-500" />
          $200
        </span>
      </div>
    </div>
  )
}

export default function CostProjection() {
  const { data, isLoading } = useQuery({
    queryKey: ['growth-cost-series'],
    queryFn: growthApi.getCostSeries,
    refetchInterval: 120_000,
  })

  const proj = data?.projection

  let cumulative = 0
  const chartPoints: ChartPoint[] = (data?.series ?? []).map(p => {
    cumulative += p.cost_usd
    return { label: fmt(p.day), cumulative: Math.round(cumulative * 10000) / 10000 }
  })

  return (
    <div className="p-8 max-w-4xl mx-auto">
      <div className="flex items-center gap-3 mb-6">
        <Link to="/admin/growth" className="text-slate-500 hover:text-slate-300 transition-colors">
          <ArrowLeft className="w-4 h-4" />
        </Link>
        <h1 className="text-lg font-bold text-white">Cost projection</h1>
      </div>

      {proj && (
        <div className="grid grid-cols-3 gap-4 mb-6">
          <div className="p-4 bg-slate-900 rounded-xl border border-slate-800">
            <p className="text-xs text-slate-500 uppercase tracking-wider mb-1">Month to date</p>
            <p className="text-2xl font-bold text-white">${proj.month_spend.toFixed(4)}</p>
            <p className="text-xs text-slate-600 mt-1">{proj.days_elapsed} days elapsed</p>
          </div>
          <div className="p-4 bg-slate-900 rounded-xl border border-slate-800">
            <p className="text-xs text-slate-500 uppercase tracking-wider mb-1">Daily avg</p>
            <p className="text-2xl font-bold text-white">${proj.daily_avg.toFixed(4)}</p>
            <p className="text-xs text-slate-600 mt-1">{proj.days_remaining} days remaining</p>
          </div>
          <div className={`p-4 rounded-xl border ${proj.eom_forecast >= 50 ? 'bg-red-500/10 border-red-500/30' : 'bg-slate-900 border-slate-800'}`}>
            <p className="text-xs text-slate-500 uppercase tracking-wider mb-1">EOM forecast</p>
            <p className={`text-2xl font-bold ${proj.eom_forecast >= 50 ? 'text-red-400' : proj.eom_forecast >= 20 ? 'text-amber-400' : 'text-white'}`}>
              ${proj.eom_forecast.toFixed(2)}
            </p>
            <p className="text-xs text-slate-600 mt-1">end of month</p>
          </div>
        </div>
      )}

      <div className="p-5 bg-slate-900 rounded-xl border border-slate-800">
        <p className="text-xs font-semibold text-slate-500 uppercase tracking-wider mb-4">
          Cumulative scan cost ($)
        </p>
        {isLoading && <p className="text-slate-500 text-sm">Loading…</p>}
        <SvgChart points={chartPoints} />
      </div>

      {(data?.series ?? []).length > 0 && (
        <div className="mt-4 p-5 bg-slate-900 rounded-xl border border-slate-800">
          <p className="text-xs font-semibold text-slate-500 uppercase tracking-wider mb-3">Daily breakdown</p>
          <table className="w-full text-sm">
            <thead>
              <tr className="text-xs text-slate-500 border-b border-slate-800">
                <th className="pb-2 text-left font-medium">Date</th>
                <th className="pb-2 text-right font-medium">Scans</th>
                <th className="pb-2 text-right font-medium">Cost</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800/50">
              {(data?.series ?? []).slice().reverse().map(row => (
                <tr key={row.day}>
                  <td className="py-2 text-slate-400">{fmt(row.day)}</td>
                  <td className="py-2 text-right text-slate-300">{row.scans}</td>
                  <td className="py-2 text-right font-mono text-slate-200">${row.cost_usd.toFixed(4)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
