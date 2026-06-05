import { createContext, useContext, useEffect, useState, type ReactNode } from 'react'
import type { Session, SupabaseClient } from '@supabase/supabase-js'
import { getSupabaseClient } from '@/lib/supabase'
import { setToken } from '@/lib/api'

interface AuthContextValue {
  session: Session | null
  loading: boolean
  signIn: (email: string, password: string) => Promise<void>
  sendMagicLink: (email: string) => Promise<void>
  updatePassword: (password: string) => Promise<void>
  signInWithGitHub: () => Promise<void>
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
            return
          }
        }

        resolve(s)

        if (resolved) {
          setSession(s)
          setToken(s?.access_token ?? null)
        }

        // On sign-in, seed the beta user's product (idempotent, best-effort).
        if (event === 'SIGNED_IN' && s?.access_token) {
          fetch('/me/activate', {
            method: 'POST',
            headers: { 'Authorization': `Bearer ${s.access_token}` },
          }).catch(() => { /* non-blocking */ })
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

  async function sendMagicLink(email: string) {
    if (!client) throw new Error('Not initialised')
    // Land on /set-password so "Forgot password? Get a login link" actually lets the
    // user set a password (not just log in). Requires /set-password in Supabase's
    // Redirect URLs allow-list (explicit entry — the /** wildcard does not match it).
    const { error } = await client.auth.signInWithOtp({
      email,
      options: { emailRedirectTo: `${window.location.origin}/set-password` },
    })
    if (error) throw error
  }

  async function updatePassword(password: string) {
    if (!client) throw new Error('Not initialised')
    const { error } = await client.auth.updateUser({ password })
    if (error) throw error
  }

  async function signInWithGitHub() {
    if (!client) throw new Error('Not initialised')
    const { error } = await client.auth.signInWithOAuth({
      provider: 'github',
      options: { redirectTo: `${window.location.origin}/products` },
    })
    if (error) throw error
  }

  async function signOut() {
    if (!client) return
    await client.auth.signOut()
  }

  return (
    <AuthContext.Provider value={{ session, loading, signIn, sendMagicLink, updatePassword, signInWithGitHub, signOut }}>
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth() {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used inside AuthProvider')
  return ctx
}
