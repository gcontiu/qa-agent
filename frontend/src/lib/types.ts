export interface Product {
  id: string
  name: string
  url: string
  description: string | null
  created_at: string
  updated_at: string
  active: boolean
}

export interface Spec {
  id: string
  product_id: string
  filename: string
  content: string
  approved: boolean
  created_at: string
  updated_at: string
}

export interface AnalyzeTask {
  task_id: string
  product_id: string
  status: 'running' | 'done' | 'failed'
  started_at: string
  completed_at?: string
  files_written?: string[]
  file_count?: number
  summary?: string
  cost_usd?: number
  error?: string
}

export interface RunSummary {
  total: number
  passed: number
  failed: number
  errored: number
}

export interface Issue {
  id: string
  product_id: string
  fingerprint: string
  type: 'console_error' | 'console_warning' | 'network_5xx' | 'network_4xx' | 'broken_link' | 'flow_stuck' | 'semantic'
  severity: 'high' | 'medium' | 'low'
  url: string
  message: string
  details: Record<string, unknown>
  status: 'open' | 'acknowledged' | 'wont_fix' | 'resolved'
  first_seen_at: string
  last_seen_at: string
  occurrences: number
}

export interface IssuesSummary {
  total: number
  high: number
  medium: number
  low: number
}

export interface QuotaLimits {
  runs_per_month: number
  scans_per_month: number
  scenarios_per_run: number
}

export interface QuotaUsage {
  runs_this_month: number
  scans_this_month: number
}

export interface Quota {
  tier: 'free' | 'beta' | 'starter' | 'pro'
  limits: QuotaLimits
  usage: QuotaUsage
  models_allowed: string[]
}

export interface Run {
  run_id: string
  status: 'pending' | 'running' | 'done' | 'failed' | 'cancelled'
  spec_dir: string | null
  started_at: string | null
  completed_at: string | null
  summary: RunSummary | null
  report_path: string | null
  error: string | null
}
