import { createContext, useContext, useEffect, useState, type ReactNode } from 'react'
import type { Session, SupabaseClient } from '@supabase/supabase-js'
import { getSupabaseClient } from '@/lib/supabase'
import { setToken } from '@/lib/api'

interface AuthContextValue {
  session: Session | null
  loading: boolean
  signIn: (email: string, password: string) => Promise<void>
  signUp: (email: string, password: string) => Promise<void>
  signOut: () => Promise<void>
}

const AuthContext = createContext<AuthContextValue | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [session, setSession] = useState<Session | null>(null)
  const [loading, setLoading] = useState(true)
  const [client, setClient] = useState<SupabaseClient | null>(null)

  useEffect(() => {
    let unsubscribe: (() => void) | null = null

    getSupabaseClient().then(sb => {
      setClient(sb)
      // onAuthStateChange fires immediately with INITIAL_SESSION event,
      // giving us the current session (auto-refreshed if expired).
      // We no longer call getSession() separately — that caused loading=false
      // to fire before Supabase had a chance to refresh an expired token.
      const { data: listener } = sb.auth.onAuthStateChange((_event, s) => {
        setSession(s)
        setToken(s?.access_token ?? null)
        setLoading(false)
      })
      unsubscribe = () => listener.subscription.unsubscribe()
    })

    return () => { unsubscribe?.() }
  }, [])

  async function signIn(email: string, password: string) {
    if (!client) throw new Error('Not initialised')
    const { error } = await client.auth.signInWithPassword({ email, password })
    if (error) throw error
  }

  async function signUp(email: string, password: string) {
    if (!client) throw new Error('Not initialised')
    const { error } = await client.auth.signUp({ email, password })
    if (error) throw error
  }

  async function signOut() {
    if (!client) return
    await client.auth.signOut()
  }

  return (
    <AuthContext.Provider value={{ session, loading, signIn, signUp, signOut }}>
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth() {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used inside AuthProvider')
  return ctx
}
