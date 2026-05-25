import { useState } from 'react'
import { ArrowRight, CheckCircle2, Zap, ListChecks, Moon, Check, ChevronDown, ChevronUp, User } from 'lucide-react'

const SPOTS_TOTAL = 50
const SPOTS_CLAIMED = 27

const SEGMENTS = [
  {
    label: 'E-commerce',
    tagline: 'Catch broken checkout flows before your next campaign launch.',
  },
  {
    label: 'SaaS',
    tagline: 'Catch regressions before they reach paying customers.',
  },
  {
    label: 'Agency',
    tagline: 'Test 10 client sites with one config.',
  },
]

const MOCK_ISSUES = [
  { sev: 'error', type: 'Console error', msg: "TypeError: Cannot read properties of undefined (reading 'cart')", loc: 'checkout.js:1:4521' },
  { sev: 'error', type: 'Network 500',   msg: 'POST /api/orders → 500 Internal Server Error', loc: '/checkout' },
  { sev: 'warn',  type: 'Broken image',  msg: '/assets/hero-banner.webp → 404 Not Found', loc: '/' },
  { sev: 'warn',  type: 'Dead link',     msg: '/faq/returns → 404 Not Found', loc: '/footer' },
  { sev: 'warn',  type: 'Accessibility', msg: '4 images missing alt attribute (WCAG 1.1.1)', loc: '/products' },
]

const FAQS = [
  {
    q: 'How is this different from Lighthouse or Cypress?',
    a: 'Lighthouse grades performance and accessibility on a single page. Cypress requires you to write test scripts. Steadra crawls your entire app autonomously, finds issues without any setup, and lets you describe scenarios in plain English — no scripts, no infrastructure.',
  },
  {
    q: 'Which pages do you scan?',
    a: 'We crawl the public URL you provide and follow internal links up to the page limit for your tier. No login, no forms submitted — only pages reachable by an anonymous visitor.',
  },
  {
    q: 'Do you store data from my site?',
    a: 'We store the issue report (console errors, network responses, page URLs found). We do not store page content, user data, or screenshots beyond what is needed to generate your report. Reports are private to your account.',
  },
  {
    q: 'How long until I get my invite?',
    a: 'You receive a mini-scan report by email within 10 minutes of joining the waitlist. The full invite follows within 24 hours — we review each site before granting access during the closed beta.',
  },
]

// TODO: replace with real Calendly link
const CALENDLY_URL = '#waitlist'

export default function LandingPage() {
  const [email, setEmail] = useState('')
  const [url, setUrl] = useState('')
  const [status, setStatus] = useState<'idle' | 'loading' | 'success' | 'error'>('idle')
  const [errorMsg, setErrorMsg] = useState('')
  const [segment, setSegment] = useState(0)
  const [openFaq, setOpenFaq] = useState<number | null>(null)
  const [submittedUrl, setSubmittedUrl] = useState('')

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (!email || !url) return
    setStatus('loading')
    setErrorMsg('')
    try {
      const res = await fetch('/waitlist', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email, url }),
      })
      if (res.status === 409) {
        setErrorMsg("You're already on the list.")
        setStatus('error')
        return
      }
      if (!res.ok) throw new Error()
      setSubmittedUrl(url)
      setStatus('success')
    } catch {
      setErrorMsg('Something went wrong. Try again.')
      setStatus('error')
    }
  }

  return (
    <div className="min-h-screen bg-[#07091a] text-white font-sans antialiased">

      {/* ── Nav ──────────────────────────────────────────────────────────── */}
      <nav className="px-6 py-5 border-b border-white/5">
        <div className="max-w-5xl mx-auto flex items-center justify-between">
          <span className="text-xl font-bold tracking-tight">Steadra</span>
          <a href="/login" className="text-sm text-gray-400 hover:text-white transition-colors">
            Sign in →
          </a>
        </div>
      </nav>

      {/* ── Hero ─────────────────────────────────────────────────────────── */}
      <section className="pt-24 pb-12 px-6 text-center">
        <div className="max-w-3xl mx-auto">

          <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full border border-cyan-500/30 bg-cyan-500/10 text-cyan-400 text-xs font-medium mb-8">
            <span className="w-1.5 h-1.5 rounded-full bg-cyan-400 animate-pulse" />
            Closed beta · {SPOTS_CLAIMED} of {SPOTS_TOTAL} spots claimed this month
          </div>

          <h1 className="text-5xl sm:text-6xl font-bold leading-tight tracking-tight mb-4">
            Your on-demand<br />
            <span className="text-cyan-400">QA junior.</span>
          </h1>

          <p className="text-lg font-medium text-gray-300 mb-4 max-w-2xl mx-auto">
            Scans your site for bugs in minutes.<br />
            Then drafts the test scenarios you should be running and reruns the full suite every time you ship — no scripts, no setup.
          </p>

          {/* Segmentation chips */}
          <div className="flex items-center justify-center gap-2 mb-3">
            {SEGMENTS.map((s, i) => (
              <button
                key={s.label}
                onClick={() => setSegment(i)}
                className={`px-3 py-1 rounded-full text-xs font-medium transition-colors border ${
                  segment === i
                    ? 'bg-cyan-500/20 border-cyan-500/40 text-cyan-400'
                    : 'bg-white/[0.03] border-white/10 text-gray-500 hover:text-gray-300'
                }`}
              >
                {s.label}
              </button>
            ))}
          </div>
          <p className="text-sm text-gray-500 mb-10 max-w-xl mx-auto min-h-[1.25rem]">
            {SEGMENTS[segment].tagline}
          </p>

          {/* Capture form */}
          <div id="waitlist" className="max-w-md mx-auto">
            {status === 'success' ? (
              <div className="rounded-lg bg-cyan-500/10 border border-cyan-500/20 px-5 py-4 text-left">
                <div className="flex items-center gap-2 text-cyan-400 text-sm font-medium mb-1">
                  <CheckCircle2 className="h-4 w-4 shrink-0" />
                  We're scanning {submittedUrl} right now.
                </div>
                <p className="text-xs text-gray-500">Your report lands in your inbox in ~10 minutes. Check spam if it doesn't arrive.</p>
              </div>
            ) : (
              <form onSubmit={handleSubmit} className="flex flex-col gap-3">
                <input
                  type="email"
                  required
                  value={email}
                  onChange={e => setEmail(e.target.value)}
                  placeholder="you@company.com"
                  className="w-full px-4 py-2.5 rounded-lg bg-white/5 border border-white/10 text-white placeholder:text-gray-600 focus:outline-none focus:border-cyan-500/50 text-sm"
                />
                <div className="flex flex-col sm:flex-row gap-3">
                  <input
                    type="url"
                    required
                    value={url}
                    onChange={e => setUrl(e.target.value)}
                    placeholder="https://yoursite.com"
                    className="flex-1 px-4 py-2.5 rounded-lg bg-white/5 border border-white/10 text-white placeholder:text-gray-600 focus:outline-none focus:border-cyan-500/50 text-sm"
                  />
                  <button
                    type="submit"
                    disabled={status === 'loading'}
                    className="px-5 py-2.5 rounded-lg bg-cyan-500 hover:bg-cyan-400 text-black font-semibold text-sm transition-colors disabled:opacity-60 flex items-center justify-center gap-2 whitespace-nowrap"
                  >
                    {status === 'loading'
                      ? 'Scanning…'
                      : <><span>Get early access</span><ArrowRight className="h-4 w-4" /></>
                    }
                  </button>
                </div>
              </form>
            )}
            {status === 'error' && (
              <p className="text-red-400 text-xs mt-2 text-left">{errorMsg}</p>
            )}
            {status !== 'success' && (
              <p className="text-xs text-gray-700 mt-3">
                We only scan public pages. No login required. Report is private to you.
              </p>
            )}
          </div>

        </div>
      </section>

      {/* ── Mock report preview ──────────────────────────────────────────── */}
      <section className="pb-20 px-6">
        <div className="max-w-5xl mx-auto">
          <div className="rounded-xl border border-white/10 bg-[#0d1024] overflow-hidden shadow-2xl">
            <div className="border-b border-white/5 px-5 py-3 flex items-center gap-3">
              <div className="flex gap-1.5">
                <span className="w-3 h-3 rounded-full bg-white/10" />
                <span className="w-3 h-3 rounded-full bg-white/10" />
                <span className="w-3 h-3 rounded-full bg-white/10" />
              </div>
              <span className="text-xs text-gray-600 font-mono">Steadra · Run #demo · example-shop.com</span>
              <span className="ml-auto text-xs text-red-400 font-medium">8 issues found</span>
            </div>
            <div className="divide-y divide-white/[0.03]">
              {MOCK_ISSUES.map((issue, i) => (
                <div key={i} className="px-5 py-3.5 flex items-start gap-3">
                  <span className={`mt-1.5 w-2 h-2 rounded-full shrink-0 ${issue.sev === 'error' ? 'bg-red-500' : 'bg-yellow-500/80'}`} />
                  <div className="min-w-0">
                    <span className={`text-xs font-medium mr-2 ${issue.sev === 'error' ? 'text-red-400' : 'text-yellow-400'}`}>{issue.type}</span>
                    <span className="text-xs text-gray-400 break-all">{issue.msg}</span>
                    <p className="text-xs text-gray-700 mt-0.5 font-mono">{issue.loc}</p>
                  </div>
                </div>
              ))}
            </div>
            <div className="border-t border-white/5 px-5 py-3 flex items-center justify-between">
              <span className="text-xs text-gray-700">Scan completed in 1m 42s · 12 pages crawled</span>
              <span className="text-xs text-cyan-700 font-medium">Generated by Steadra</span>
            </div>
          </div>
          <p className="text-center text-xs text-gray-700 mt-4">Sample report — your site, your actual issues.</p>
        </div>
      </section>

      {/* ── How it works ─────────────────────────────────────────────────── */}
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

      {/* ── Founder note ─────────────────────────────────────────────────── */}
      <section className="py-20 px-6 border-t border-white/5">
        <div className="max-w-2xl mx-auto text-center">
          {/* TODO: replace icon with <img src="/founder.jpg" ... /> when ready */}
          <div className="w-16 h-16 rounded-full bg-cyan-500/20 border border-cyan-500/30 flex items-center justify-center mx-auto mb-6">
            <User className="h-7 w-7 text-cyan-400" />
          </div>
          <p className="text-base text-gray-300 leading-relaxed mb-8 max-w-xl mx-auto">
            "During beta, every report and every feature request reaches me directly. You get my calendar — not a support queue. Beta users shape what ships first."
          </p>
          <a
            href={CALENDLY_URL}
            className="inline-flex items-center gap-2 text-sm text-cyan-400 hover:text-cyan-300 transition-colors"
          >
            Skip support — book 15 minutes with the founder <ArrowRight className="h-4 w-4" />
          </a>
        </div>
      </section>

      {/* ── Pricing ──────────────────────────────────────────────────────── */}
      <section className="py-20 px-6 border-t border-white/5">
        <div className="max-w-5xl mx-auto text-center">
          <p className="text-xs text-gray-600 uppercase tracking-widest mb-3">Pricing</p>
          <h2 className="text-2xl font-semibold mb-2">Simple, transparent tiers</h2>
          <p className="text-gray-600 text-sm mb-12">Available at launch. Beta cohort gets locked-in pricing — pay nothing during your 30-day trial.</p>

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
            Get my free mini-scan + early access <ArrowRight className="h-4 w-4" />
          </a>
        </div>
      </section>

      {/* ── FAQ ──────────────────────────────────────────────────────────── */}
      <section className="py-20 px-6 border-t border-white/5">
        <div className="max-w-2xl mx-auto">
          <p className="text-center text-xs text-gray-600 uppercase tracking-widest mb-3">FAQ</p>
          <h2 className="text-center text-2xl font-semibold mb-10">Common questions</h2>
          <div className="space-y-2">
            {FAQS.map((faq, i) => (
              <div key={i} className="rounded-xl border border-white/5 bg-white/[0.02] overflow-hidden">
                <button
                  onClick={() => setOpenFaq(openFaq === i ? null : i)}
                  className="w-full px-5 py-4 text-left flex items-center justify-between gap-4"
                >
                  <span className="text-sm font-medium text-gray-200">{faq.q}</span>
                  {openFaq === i
                    ? <ChevronUp className="h-4 w-4 text-gray-600 shrink-0" />
                    : <ChevronDown className="h-4 w-4 text-gray-600 shrink-0" />
                  }
                </button>
                {openFaq === i && (
                  <div className="px-5 pb-4">
                    <p className="text-sm text-gray-500 leading-relaxed">{faq.a}</p>
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ── Footer ───────────────────────────────────────────────────────── */}
      <footer className="py-10 px-6 border-t border-white/5">
        <div className="max-w-5xl mx-auto flex flex-col sm:flex-row items-center justify-between gap-4 text-xs text-gray-700">
          <span className="font-semibold text-gray-500">Steadra</span>
          <div className="flex items-center gap-5">
            <a href="/privacy" className="hover:text-gray-400 transition-colors">Privacy</a>
            <a href="/terms" className="hover:text-gray-400 transition-colors">Terms</a>
            <a href="mailto:hello@steadra.dev" className="hover:text-gray-400 transition-colors">hello@steadra.dev</a>
          </div>
          <span>© 2026 Steadra · steadra.dev</span>
        </div>
      </footer>

    </div>
  )
}
