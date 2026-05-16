import { useState, useEffect, useRef } from 'react'
import { useQuery } from '@tanstack/react-query'
import { api } from '@/lib/api'

interface LogEvent { ts: number; msg: string }
interface LogResponse { events: LogEvent[]; next: number }

export default function LogPanel({ endpoint, active }: { endpoint: string; active: boolean }) {
  const [events, setEvents] = useState<LogEvent[]>([])
  const sinceRef = useRef(0)
  const bottomRef = useRef<HTMLDivElement>(null)
  const prevActiveRef = useRef(false)

  // Reset when endpoint changes (new task started)
  useEffect(() => {
    setEvents([])
    sinceRef.current = 0
    prevActiveRef.current = false
  }, [endpoint])

  const { data, refetch } = useQuery<LogResponse>({
    queryKey: ['logs', endpoint],
    queryFn: () => api.get(`${endpoint}?since=${sinceRef.current}`),
    enabled: active,
    refetchInterval: active ? 2000 : false,
    staleTime: 0,
    gcTime: 0,
  })

  // Append new events and advance cursor
  useEffect(() => {
    if (!data) return
    if (data.events.length > 0) {
      setEvents(prev => [...prev, ...data.events])
    }
    sinceRef.current = data.next
  }, [data])

  // Final fetch when task transitions from active → done
  useEffect(() => {
    if (prevActiveRef.current && !active) {
      refetch()
    }
    prevActiveRef.current = active
  }, [active, refetch])

  // Auto-scroll to bottom while active
  useEffect(() => {
    if (active) bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [events, active])

  if (events.length === 0) return null

  return (
    <div className="rounded-lg border bg-muted/30 p-3 font-mono text-xs max-h-52 overflow-y-auto">
      {events.map((e, i) => (
        <div key={i} className="flex gap-2 leading-relaxed">
          <span className="shrink-0 text-muted-foreground/50">
            {new Date(e.ts * 1000).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })}
          </span>
          <span className="text-foreground/80">{e.msg}</span>
        </div>
      ))}
      <div ref={bottomRef} />
    </div>
  )
}
