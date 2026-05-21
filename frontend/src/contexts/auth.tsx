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
    let resolved = false

    function resolve(s: typeof session) {
      if (resolved) return
      resolved = true
      setSession(s)
      setToken(s?.access_token ?? null)
      setLoading(false)
    }

    // Safety timeout — if Supabase hasn't resolved auth in 5s, unblock the app.
    const timeout = setTimeout(() => resolve(null), 5000)

    getSupabaseClient().then(sb => {
      setClient(sb)

      const { data: listener } = sb.auth.onAuthStateChange((event, s) => {
        clearTimeout(timeout)

        if (event === 'INITIAL_SESSION' && s) {
          const expiresAt = (s.expires_at ?? 0) * 1000
          if (expiresAt < Date.now() + 10_000) {
            // Token expired or about to — Supabase is refreshing it.
            // Wait for TOKEN_REFRESHED or SIGNED_OUT before unblocking.
            return
          }
        }

        // For all other events (SIGNED_IN, TOKEN_REFRESHED, SIGNED_OUT,
        // or INITIAL_SESSION with a valid token) resolve immediately.
        resolve(s)

        // Keep session in sync for subsequent events after initial resolve.
        if (resolved) {
          setSession(s)
          setToken(s?.access_token ?? null)
        }
      })

      unsubscribe = () => listener.subscription.unsubscribe()
    })

    return () => {
      clearTimeout(timeout)
      unsubscribe?.()
    }
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
