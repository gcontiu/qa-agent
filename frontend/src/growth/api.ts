/**
 * Typed client for growth admin endpoints.
 * Uses the same request() helper as the host's api.ts.
 */
import { api } from '@/lib/api'

export interface WaitlistEntry {
  id: string
  email: string
  url: string | null
  segment: string | null
  submitted_at: string
  scan_status: 'pending' | 'running' | 'done' | 'failed' | 'capped'
  scan_started_at: string | null
  scan_done_at: string | null
  scan_result: ScanResult | null
  scan_cost_usd: number | null
  scan_email_sent_at: string | null
  invite_status: 'none' | 'sent' | 'accepted'
  invite_sent_at: string | null
  invite_user_id: string | null
}

export interface ScanResult {
  issues: ScanIssue[]
  page_count: number
  duration_ms: number
  cost_usd: number
}

export interface ScanIssue {
  severity: 'critical' | 'warning' | 'info'
  type: string
  message: string
  location: string | null
}

export interface DripJob {
  id: string
  template: string
  scheduled_for: string
  status: 'pending' | 'sent' | 'failed' | 'skipped'
  sent_at: string | null
  error: string | null
  email: string
}

export interface WaitlistListResponse {
  total: number
  page: number
  items: WaitlistEntry[]
}

export interface WaitlistDetailResponse {
  entry: WaitlistEntry
  drip_jobs: DripJob[]
  host_summary: Record<string, unknown> | null
  cost_summary: {
    total_usd: number
    breakdown: Record<string, number>
    run_count: number
    last_event_at: string | null
  } | null
}

export interface OverviewResponse {
  total_waitlist: number
  today_scans: number
  recent: WaitlistEntry[]
}

export const growthApi = {
  overview: () => api.get<OverviewResponse>('/admin/growth/overview'),

  listWaitlist: (params: {
    scan_status?: string
    invite_status?: string
    segment?: string
    q?: string
    page?: number
  }) => {
    const qs = new URLSearchParams()
    if (params.scan_status) qs.set('scan_status', params.scan_status)
    if (params.invite_status) qs.set('invite_status', params.invite_status)
    if (params.segment) qs.set('segment', params.segment)
    if (params.q) qs.set('q', params.q)
    if (params.page) qs.set('page', String(params.page))
    return api.get<WaitlistListResponse>(`/admin/growth/waitlist?${qs}`)
  },

  getWaitlistEntry: (id: string) =>
    api.get<WaitlistDetailResponse>(`/admin/growth/waitlist/${id}`),

  forceRescan: (id: string) =>
    api.post(`/admin/growth/waitlist/${id}/force-rescan`),

  skipNextDrip: (id: string) =>
    api.post(`/admin/growth/waitlist/${id}/skip-next-drip`),

  getDripQueue: (status?: string) => {
    const qs = status ? `?status=${status}` : ''
    return api.get<{ items: DripJob[] }>(`/admin/growth/drip${qs}`)
  },
}
