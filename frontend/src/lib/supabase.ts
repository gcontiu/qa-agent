import { createClient, type SupabaseClient } from '@supabase/supabase-js'

// Module-level promise ensures only one client is ever created,
// even if getSupabaseClient() is called concurrently before the first
// fetch resolves. Multiple GoTrueClient instances cause refresh token
// conflicts (rotation invalidates sibling clients).
// eslint-disable-next-line @typescript-eslint/no-explicit-any
let _promise: Promise<SupabaseClient<any>> | null = null

// eslint-disable-next-line @typescript-eslint/no-explicit-any
export function getSupabaseClient(): Promise<SupabaseClient<any>> {
  if (_promise) return _promise

  const p: Promise<SupabaseClient<any>> = fetch('/auth/config')
    .then(r => r.json())
    .then(({ supabase_url, anon_key }: { supabase_url: string; anon_key: string }) => {
      if (!supabase_url || !anon_key) throw new Error('Supabase not configured on server')
      return createClient(supabase_url, anon_key)
    })
    .catch(err => {
      _promise = null
      throw err
    })

  _promise = p
  return p
}
