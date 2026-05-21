import { useState } from 'react'
import { ArrowRight, CheckCircle2, Zap, ListChecks, Moon, Check, ImageIcon } from 'lucide-react'

export default function LandingPage() {
  const [email, setEmail] = useState('')
  const [status, setStatus] = useState<'idle' | 'loading' | 'success' | 'error'>('idle')
  const [errorMsg, setErrorMsg] = useState('')

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (!email) return
    setStatus('loading')
    setErrorMsg('')
    try {
      const res = await fetch('/waitlist', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email }),
      })
      if (res.status === 409) {
        setErrorMsg("You're already on the list.")
        setStatus('error')
        return
      }
      if (!res.ok) throw new Error()
      setStatus('success')
    } catch {
      setErrorMsg('Something went wrong. Try again.')
      setStatus('error')
    }
  }

  return (
    <div className="min-h-screen bg-[#07091a] text-white font-sans antialiased">

      {/* ── Nav ─────────────────────────────────────────────────────────── */}
      <nav className="px-6 py-5 border-b border-white/5">
        <div className="max-w-5xl mx-auto flex items-center justify-between">
          <span className="text-xl font-bold tracking-tight">Steadra</span>
          <a href="/login" className="text-sm text-gray-400 hover:text-white transition-colors">
            Sign in →
          </a>
        </div>
      </nav>

      {/* ── Hero ────────────────────────────────────────────────────────── */}
      <section className="pt-24 pb-12 px-6 text-center">
        <div className="max-w-3xl mx-auto">

          <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full border border-cyan-500/30 bg-cyan-500/10 text-cyan-400 text-xs font-medium mb-8">
            <span className="w-1.5 h-1.5 rounded-full bg-cyan-400 animate-pulse" />
            Closed beta · Limited spots
          </div>

          <h1 className="text-5xl sm:text-6xl font-bold leading-tight tracking-tight mb-4">
            Find what's broken<br />
            <span className="text-cyan-400">on your site in 2 minutes.</span>
          </h1>

          <p className="text-lg font-medium text-gray-300 mb-4">
            Free. No specs, no setup, no test scripts.
          </p>

          <p className="text-base text-gray-500 mb-10 max-w-xl mx-auto leading-relaxed">
            Point Steadra at any URL — it crawls your web app and surfaces console
            errors, broken images, dead links, and accessibility issues instantly.
            Write scenarios when you want deeper QA.
          </p>

          {/* Email capture */}
          <div id="waitlist" className="max-w-md mx-auto">
            {status === 'success' ? (
              <div className="flex items-center justify-center gap-2 text-cyan-400 text-sm py-3">
                <CheckCircle2 className="h-5 w-5" />
                You're on the list. We'll reach out soon.
              </div>
            ) : (
              <form onSubmit={handleSubmit} className="flex flex-col sm:flex-row gap-3">
                <input
                  type="email"
                  required
                  value={email}
                  onChange={e => setEmail(e.target.value)}
                  placeholder="you@company.com"
                  className="flex-1 px-4 py-2.5 rounded-lg bg-white/5 border border-white/10 text-white placeholder:text-gray-600 focus:outline-none focus:border-cyan-500/50 text-sm"
                />
                <button
                  type="submit"
                  disabled={status === 'loading'}
                  className="px-5 py-2.5 rounded-lg bg-cyan-500 hover:bg-cyan-400 text-black font-semibold text-sm transition-colors disabled:opacity-60 flex items-center justify-center gap-2 whitespace-nowrap"
                >
                  {status === 'loading'
                    ? 'Joining…'
                    : <><span>Request beta access</span><ArrowRight className="h-4 w-4" /></>
                  }
                </button>
              </form>
            )}
            {status === 'error' && (
              <p className="text-red-400 text-xs mt-2 text-left">{errorMsg}</p>
            )}
          </div>

        </div>
      </section>

      {/* ── Screenshot placeholder ──────────────────────────────────────── */}
      <section className="pb-20 px-6">
        <div className="max-w-5xl mx-auto">
          <div className="rounded-xl border border-dashed border-white/10 bg-white/[0.02] overflow-hidden"
               style={{ aspectRatio: '16/9' }}>
            <div className="h-full flex flex-col items-center justify-center gap-3 text-center p-8">
              <div className="w-14 h-14 rounded-xl bg-white/5 border border-white/10 flex items-center justify-center">
                <ImageIcon className="h-7 w-7 text-gray-700" />
              </div>
              <div>
                <p className="text-sm font-medium text-gray-600">Issue report</p>
                <p className="text-xs text-gray-700 mt-0.5">Screenshot coming soon</p>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* ── How it works ────────────────────────────────────────────────── */}
      <section className="py-20 px-6 border-t border-white/5">
        <div className="max-w-5xl mx-auto">
          <p className="text-center text-xs text-gray-600 uppercase tracking-widest mb-3">How it works</p>
          <h2 className="text-center text-2xl font-semibold mb-14">
            From zero to bug report in minutes
          </h2>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
            {[
              {
                icon: <Zap className="h-5 w-5 text-cyan-400" />,
                step: '01',
                title: 'Free issue scan',
                body: 'Give Steadra a URL. It crawls your web app and immediately detects console errors, network failures, broken images, dead links, and accessibility issues — no specs needed.',
                tag: 'Free · Always included',
              },
              {
                icon: <ListChecks className="h-5 w-5 text-cyan-400" />,
                step: '02',
                title: 'Define your scenarios',
                body: 'Write Gherkin specs (or let Steadra generate them during analysis) for the user flows you care about. Your on-demand QA junior reads them exactly as written.',
                tag: 'Optional · Tier-based',
              },
              {
                icon: <Moon className="h-5 w-5 text-cyan-400" />,
                step: '03',
                title: 'Ship with confidence',
                body: 'Steadra runs every scenario autonomously — overnight, before releases, on demand. A prioritized pass/fail report with evidence is waiting in the morning.',
                tag: 'Set it and forget it',
              },
            ].map(({ icon, step, title, body, tag }) => (
              <div key={step} className="rounded-xl border border-white/5 bg-white/[0.03] p-6 flex flex-col">
                <div className="flex items-center gap-3 mb-5">
                  <div className="flex items-center justify-center w-8 h-8 rounded-md bg-cyan-500/10 shrink-0">
                    {icon}
                  </div>
                  <span className="text-xs text-gray-700 font-mono">{step}</span>
                </div>
                <h3 className="text-base font-semibold mb-2">{title}</h3>
                <p className="text-sm text-gray-500 leading-relaxed flex-1">{body}</p>
                <p className="text-xs text-cyan-600 mt-4 font-medium">{tag}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ── Pricing ─────────────────────────────────────────────────────── */}
      <section className="py-20 px-6 border-t border-white/5">
        <div className="max-w-5xl mx-auto text-center">
          <p className="text-xs text-gray-600 uppercase tracking-widest mb-3">Pricing</p>
          <h2 className="text-2xl font-semibold mb-2">Simple, transparent tiers</h2>
          <p className="text-gray-600 text-sm mb-12">Available at launch. Join the waitlist for early access.</p>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-5 max-w-3xl mx-auto">
            {[
              {
                name: 'Free',
                price: '$0',
                description: 'Try it out',
                highlight: false,
                features: [
                  { label: 'Every issue, every scan', highlight: true },
                  { label: '1 product', highlight: false },
                  { label: '2 site scans / mo · ≤ 20 pages', highlight: false },
                  { label: '5 test runs / month', highlight: false },
                  { label: '15 scenarios per run', highlight: false },
                  { label: 'Haiku + 1 Sonnet teaser / mo', highlight: false },
                ],
              },
              {
                name: 'Starter',
                price: '$29 / mo',
                description: 'Solo & small teams',
                highlight: true,
                features: [
                  { label: 'Every issue, every scan', highlight: true },
                  { label: '1 product', highlight: false },
                  { label: '5 site scans / mo · ≤ 50 pages', highlight: false },
                  { label: '20 test runs / month', highlight: false },
                  { label: '30 scenarios per run', highlight: false },
                  { label: 'Haiku + Sonnet', highlight: false },
                ],
              },
              {
                name: 'Pro',
                price: '$99 / mo',
                description: 'Growing teams',
                highlight: false,
                features: [
                  { label: 'Every issue, every scan', highlight: true },
                  { label: '3 products', highlight: false },
                  { label: '10 site scans / mo · ≤ 200 pages', highlight: false },
                  { label: '50 test runs / month', highlight: false },
                  { label: '75 scenarios per run', highlight: false },
                  { label: 'Haiku + Sonnet + Opus', highlight: false },
                ],
              },
            ].map(({ name, price, description, features, highlight }) => (
              <div
                key={name}
                className={`rounded-xl border p-6 text-left relative flex flex-col ${
                  highlight
                    ? 'border-cyan-500/40 bg-cyan-500/5'
                    : 'border-white/5 bg-white/[0.02]'
                }`}
              >
                {highlight && (
                  <span className="absolute -top-3 left-1/2 -translate-x-1/2 text-xs bg-cyan-500 text-black px-3 py-0.5 rounded-full font-medium">
                    Recommended
                  </span>
                )}
                <p className="text-xs text-gray-600 mb-2">{description}</p>
                <p className="text-2xl font-bold mb-1">{price}</p>
                <p className="text-sm font-medium mb-5">{name}</p>
                <ul className="space-y-2.5 flex-1">
                  {features.map(f => (
                    <li key={f.label} className="flex items-start gap-2.5 text-xs">
                      <Check className={`h-3.5 w-3.5 mt-0.5 shrink-0 ${f.highlight ? 'text-cyan-400' : 'text-gray-600'}`} />
                      <span className={f.highlight ? 'text-cyan-400 font-medium' : 'text-gray-500'}>{f.label}</span>
                    </li>
                  ))}
                </ul>
              </div>
            ))}
          </div>

          <a
            href="#waitlist"
            className="inline-flex items-center gap-2 mt-10 text-sm text-cyan-400 hover:text-cyan-300 transition-colors"
          >
            Join the waitlist to get notified at launch <ArrowRight className="h-4 w-4" />
          </a>
        </div>
      </section>

      {/* ── Footer ──────────────────────────────────────────────────────── */}
      <footer className="py-10 px-6 border-t border-white/5">
        <div className="max-w-5xl mx-auto flex flex-col sm:flex-row items-center justify-between gap-3 text-xs text-gray-700">
          <span className="font-semibold text-gray-500">Steadra</span>
          <span>QA that works while you sleep.</span>
          <span>© 2026 Steadra · steadra.dev</span>
        </div>
      </footer>

    </div>
  )
}
