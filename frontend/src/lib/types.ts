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
