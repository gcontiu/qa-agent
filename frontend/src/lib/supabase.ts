import { createClient } from '@supabase/supabase-js'

// Module-level promise ensures only one client is ever created,
// even if getSupabaseClient() is called concurrently before the first
// fetch resolves. Multiple GoTrueClient instances cause refresh token
// conflicts (rotation invalidates sibling clients).
let _promise: Promise<ReturnType<typeof createClient>> | null = null

export function getSupabaseClient(): Promise<ReturnType<typeof createClient>> {
  if (_promise) return _promise

  _promise = fetch('/auth/config')
    .then(r => r.json())
    .then(({ supabase_url, anon_key }) => {
      if (!supabase_url || !anon_key) throw new Error('Supabase not configured on server')
      return createClient(supabase_url, anon_key)
    })
    .catch(err => {
      _promise = null  // allow retry on failure
      throw err
    })

  return _promise
}
