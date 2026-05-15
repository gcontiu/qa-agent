import { createClient } from '@supabase/supabase-js'

// Fetched at runtime from GET /auth/config so we don't need build-time env vars.
let _client: ReturnType<typeof createClient> | null = null

export async function getSupabaseClient() {
  if (_client) return _client

  const res = await fetch('/auth/config')
  const { supabase_url, anon_key } = await res.json()

  if (!supabase_url || !anon_key) {
    throw new Error('Supabase not configured on server')
  }

  _client = createClient(supabase_url, anon_key)
  return _client
}
