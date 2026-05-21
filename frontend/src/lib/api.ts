let _token: string | null = null

export function setToken(t: string | null) {
  _token = t
}

export class QuotaError extends Error {
  quotaType: 'run_blocked' | 'scan_blocked'
  used: number
  limit: number
  tier: string

  constructor(quotaType: 'run_blocked' | 'scan_blocked', used: number, limit: number, tier: string) {
    super('quota_exceeded')
    this.name = 'QuotaError'
    this.quotaType = quotaType
    this.used = used
    this.limit = limit
    this.tier = tier
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...(init?.headers as Record<string, string>),
  }
  if (_token) headers['Authorization'] = `Bearer ${_token}`

  const res = await fetch(path, { ...init, headers })
  if (res.status === 401) {
    setToken(null)
    window.location.replace('/login')
    throw new Error('Session expired')
  }
  if (res.status === 429) {
    const body = await res.json().catch(() => ({}))
    const detail = body?.detail
    if (detail?.code === 'quota_exceeded') {
      throw new QuotaError(detail.type, detail.used, detail.limit, detail.tier)
    }
  }
  if (!res.ok) {
    const text = await res.text().catch(() => res.statusText)
    throw new Error(`${res.status} ${text}`)
  }
  return res.json() as Promise<T>
}

export const api = {
  get: <T>(path: string) => request<T>(path),
  post: <T>(path: string, body?: unknown) =>
    request<T>(path, { method: 'POST', body: body ? JSON.stringify(body) : undefined }),
  put: <T>(path: string, body?: unknown) =>
    request<T>(path, { method: 'PUT', body: body ? JSON.stringify(body) : undefined }),
  patch: <T>(path: string, body?: unknown) =>
    request<T>(path, { method: 'PATCH', body: body ? JSON.stringify(body) : undefined }),
  delete: <T>(path: string) => request<T>(path, { method: 'DELETE' }),
}
