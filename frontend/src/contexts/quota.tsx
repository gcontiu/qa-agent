import { createContext, useContext } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '@/lib/api'
import type { Quota } from '@/lib/types'

interface QuotaCtx {
  quota: Quota | null
  isLoading: boolean
  refresh: () => void
}

const QuotaContext = createContext<QuotaCtx>({ quota: null, isLoading: false, refresh: () => {} })

export function QuotaProvider({ children }: { children: React.ReactNode }) {
  const qc = useQueryClient()
  const { data: quota = null, isLoading } = useQuery<Quota>({
    queryKey: ['quota'],
    queryFn: () => api.get('/me/quota'),
    staleTime: 30_000,
  })

  function refresh() {
    qc.invalidateQueries({ queryKey: ['quota'] })
  }

  return (
    <QuotaContext.Provider value={{ quota, isLoading, refresh }}>
      {children}
    </QuotaContext.Provider>
  )
}

export function useQuota() {
  return useContext(QuotaContext)
}
