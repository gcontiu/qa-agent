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
  ip: string | null
  submitted_at: string
  scan_status: 'pending' | 'running' | 'done' | 'failed' | 'capped'
  scan_started_at: string | null
  scan_done_at: string | null
  scan_result: ScanResult | null
  scan_cost_usd: number | null
  scan_email_sent_at: string | null
  invite_status: 'none' | 'requested' | 'sent' | 'accepted'
  invite_sent_at: string | null
  invite_user_id: string | null
}

export interface ScanResult {
  issues: ScanIssue[]
  page_count: number
  duration_ms: number
  cost_usd: number
  feature_files: Record<string, string>
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

export interface BetaEnrollment {
  user_id: string
  waitlist_id: string
  email: string
  url: string | null
  segment: string | null
  enrolled_at: string
  expires_at: string
  days_left: number | null
  status: 'active' | 'expired' | 'converted'
  converted_to_tier: string | null
}

export interface OverviewResponse {
  total_waitlist: number
  today_scans: number
  recent: WaitlistEntry[]
}

export interface FunnelStage { label: string; value: number }
export interface CostPoint { day: string; cost_usd: number; scans: number }
export interface CostProjection {
  month_spend: number; daily_avg: number; eom_forecast: number
  days_elapsed: number; days_remaining: number
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

  sendInvite: (id: string) =>
    api.post<{ status: string; email: string }>(`/admin/growth/waitlist/${id}/send-invite`),

  seedAccount: (id: string) =>
    api.post<{ status: string; user_id: string }>(`/admin/growth/waitlist/${id}/seed-account`),

  getDripQueue: (status?: string) => {
    const qs = status ? `?status=${status}` : ''
    return api.get<{ items: DripJob[] }>(`/admin/growth/drip${qs}`)
  },

  getBetaEnrollments: () =>
    api.get<{ items: BetaEnrollment[] }>('/admin/growth/beta'),

  getFunnelStats: () =>
    api.get<{ stages: FunnelStage[] }>('/admin/growth/funnel'),

  getCostSeries: () =>
    api.get<{ series: CostPoint[]; projection: CostProjection | null }>('/admin/growth/cost-series'),

  submitNps: (score: number, contextId?: string, comment?: string) =>
    api.post<{ status: string; id: string }>('/nps', { score, context_id: contextId, comment }),
}
