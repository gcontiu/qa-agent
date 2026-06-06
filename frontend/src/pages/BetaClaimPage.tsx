import { useEffect, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { CheckCircle2, Loader2, XCircle, Mail } from 'lucide-react'

type State = 'loading' | 'ok' | 'error'

export default function BetaClaimPage() {
  const [params] = useSearchParams()
  const token = params.get('token')
  const [state, setState] = useState<State>('loading')
  const [errorDetail, setErrorDetail] = useState<string>('')

  useEffect(() => {
    if (!token) { setErrorDetail('no token in URL'); setState('error'); return }
    fetch(`/growth/claim-beta?token=${encodeURIComponent(token)}`, { method: 'POST' })
      .then(async r => {
        if (r.ok) { setState('ok'); return }
        const body = await r.text().catch(() => '')
        setErrorDetail(`HTTP ${r.status}: ${body.slice(0, 200)}`)
        setState('error')
      })
      .catch(err => { setErrorDetail(String(err)); setState('error') })
  }, [token])

  return (
    <div className="min-h-screen bg-[#07090f] flex items-center justify-center px-4">
      <div className="max-w-md w-full text-center space-y-6">
        <div className="flex justify-center">
          {state === 'loading' && <Loader2 className="h-12 w-12 text-cyan-400 animate-spin" />}
          {state === 'ok'      && <CheckCircle2 className="h-12 w-12 text-emerald-400" />}
          {state === 'error'   && <XCircle className="h-12 w-12 text-red-400" />}
        </div>

        {state === 'loading' && (
          <>
            <h1 className="text-xl font-semibold text-white">Registering your request…</h1>
            <p className="text-sm text-gray-500">Just a moment.</p>
          </>
        )}

        {state === 'ok' && (
          <>
            <h1 className="text-xl font-semibold text-white">You're on the list</h1>
            <p className="text-sm text-gray-400 leading-relaxed">
              We've noted your interest in the Steadra beta. Once we review your site,
              you'll receive an invite link by email — usually within 24 hours.
            </p>
            <div className="flex items-start gap-3 bg-white/5 border border-white/10 rounded-lg px-4 py-3 text-left">
              <Mail className="h-4 w-4 text-cyan-400 mt-0.5 shrink-0" />
              <p className="text-xs text-gray-400 leading-relaxed">
                <span className="text-white font-medium">Check your spam folder</span> — invite emails
                from Steadra occasionally land there. Add{' '}
                <span className="text-white">hello@steadra.dev</span> to your contacts to be safe.
              </p>
            </div>
          </>
        )}

        {state === 'error' && (
          <>
            <h1 className="text-xl font-semibold text-white">Link expired or invalid</h1>
            <p className="text-sm text-gray-400 leading-relaxed">
              This link may have expired (valid for 7 days) or already been used.
              If you think this is a mistake, reply to the email you received and we'll sort it out.
            </p>
            {errorDetail && (
              <p className="text-xs text-gray-600 font-mono break-all">{errorDetail}</p>
            )}
          </>
        )}

        <a
          href="https://steadra.dev"
          className="inline-block text-xs text-gray-600 hover:text-gray-400 transition-colors"
        >
          ← Back to steadra.dev
        </a>
      </div>
    </div>
  )
}
