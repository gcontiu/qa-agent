import { useState } from 'react'
import { useNavigate, Link } from 'react-router-dom'
import { useAuth } from '@/contexts/auth'
import logo4 from '@/assets/logo4.png'

export default function LoginPage() {
  const { signIn, signInWithGitHub, sendMagicLink } = useAuth()
  const navigate = useNavigate()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const [forgotMode, setForgotMode] = useState(false)
  const [linkSent, setLinkSent] = useState(false)

  async function handleSignIn() {
    setError('')
    setLoading(true)
    try {
      await signIn(email, password)
      navigate('/products')
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Unknown error')
    } finally {
      setLoading(false)
    }
  }

  async function handleMagicLink() {
    setError('')
    setLoading(true)
    try {
      await sendMagicLink(email)
      setLinkSent(true)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Unknown error')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen bg-[#07091a] text-white font-sans antialiased flex items-center justify-center p-4">
      <div className="w-full max-w-sm">
        {/* Logo */}
        <div className="flex justify-center mb-8">
          <Link to="/"><img src={logo4} alt="Steadra" className="h-10 w-auto rounded-md" /></Link>
        </div>

        {/* Card */}
        <div className="rounded-xl border border-white/10 bg-[#0d1024] p-8">
          {linkSent ? (
            <div className="text-center space-y-2">
              <p className="text-sm text-gray-300">Check your email — we sent you a login link.</p>
              <button
                className="text-xs text-gray-500 hover:text-gray-300 transition-colors"
                onClick={() => { setLinkSent(false); setForgotMode(false) }}
              >
                Back to sign in
              </button>
            </div>
          ) : forgotMode ? (
            <div className="space-y-4">
              <p className="text-sm text-gray-400">Enter your email and we'll send you a login link.</p>
              <div className="space-y-1.5">
                <label className="text-xs text-gray-400" htmlFor="forgot-email">Email</label>
                <input
                  id="forgot-email"
                  type="email"
                  value={email}
                  onChange={e => setEmail(e.target.value)}
                  placeholder="you@example.com"
                  onKeyDown={e => e.key === 'Enter' && handleMagicLink()}
                  className="w-full px-3 py-2.5 rounded-lg bg-white/5 border border-white/10 text-white placeholder:text-gray-600 focus:outline-none focus:border-cyan-500/50 text-sm"
                />
              </div>
              {error && <p className="text-xs text-red-400">{error}</p>}
              <button
                onClick={handleMagicLink}
                disabled={loading}
                className="w-full px-4 py-2.5 rounded-lg bg-cyan-500 hover:bg-cyan-400 text-black font-semibold text-sm transition-colors disabled:opacity-60"
              >
                {loading ? 'Sending…' : 'Send login link'}
              </button>
              <button
                className="text-xs text-gray-500 hover:text-gray-300 transition-colors w-full text-center"
                onClick={() => { setForgotMode(false); setError('') }}
              >
                Back to sign in
              </button>
            </div>
          ) : (
            <div className="space-y-4">
              {/* GitHub */}
              <button
                onClick={() => signInWithGitHub().catch((e: Error) => setError(e.message))}
                disabled={loading}
                className="w-full flex items-center justify-center gap-2 px-4 py-2.5 rounded-lg bg-white/5 border border-white/10 text-sm text-gray-300 hover:bg-white/10 hover:text-white transition-colors disabled:opacity-60"
              >
                <svg viewBox="0 0 24 24" className="w-4 h-4 fill-current"><path d="M12 0C5.37 0 0 5.37 0 12c0 5.31 3.435 9.795 8.205 11.385.6.105.825-.255.825-.57 0-.285-.015-1.23-.015-2.235-3.015.555-3.795-.735-4.035-1.41-.135-.345-.72-1.41-1.23-1.695-.42-.225-1.02-.78-.015-.795.945-.015 1.62.87 1.845 1.23 1.08 1.815 2.805 1.305 3.495.99.105-.78.42-1.305.765-1.605-2.67-.3-5.46-1.335-5.46-5.925 0-1.305.465-2.385 1.23-3.225-.12-.3-.54-1.53.12-3.18 0 0 1.005-.315 3.3 1.23.96-.27 1.98-.405 3-.405s2.04.135 3 .405c2.295-1.56 3.3-1.23 3.3-1.23.66 1.65.24 2.88.12 3.18.765.84 1.23 1.905 1.23 3.225 0 4.605-2.805 5.625-5.475 5.925.435.375.81 1.095.81 2.22 0 1.605-.015 2.895-.015 3.3 0 .315.225.69.825.57A12.02 12.02 0 0 0 24 12c0-6.63-5.37-12-12-12z"/></svg>
                Continue with GitHub
              </button>

              {/* Divider */}
              <div className="relative">
                <div className="absolute inset-0 flex items-center">
                  <span className="w-full border-t border-white/10" />
                </div>
                <div className="relative flex justify-center text-xs">
                  <span className="bg-[#0d1024] px-2 text-gray-600 uppercase tracking-widest">or</span>
                </div>
              </div>

              {/* Email + password */}
              <div className="space-y-1.5">
                <label className="text-xs text-gray-400" htmlFor="email">Email</label>
                <input
                  id="email"
                  type="email"
                  value={email}
                  onChange={e => setEmail(e.target.value)}
                  placeholder="you@example.com"
                  onKeyDown={e => e.key === 'Enter' && handleSignIn()}
                  className="w-full px-3 py-2.5 rounded-lg bg-white/5 border border-white/10 text-white placeholder:text-gray-600 focus:outline-none focus:border-cyan-500/50 text-sm"
                />
              </div>
              <div className="space-y-1.5">
                <label className="text-xs text-gray-400" htmlFor="password">Password</label>
                <input
                  id="password"
                  type="password"
                  value={password}
                  onChange={e => setPassword(e.target.value)}
                  onKeyDown={e => e.key === 'Enter' && handleSignIn()}
                  className="w-full px-3 py-2.5 rounded-lg bg-white/5 border border-white/10 text-white placeholder:text-gray-600 focus:outline-none focus:border-cyan-500/50 text-sm"
                />
              </div>
              {error && <p className="text-xs text-red-400">{error}</p>}
              <button
                onClick={handleSignIn}
                disabled={loading}
                className="w-full px-4 py-2.5 rounded-lg bg-cyan-500 hover:bg-cyan-400 text-black font-semibold text-sm transition-colors disabled:opacity-60"
              >
                {loading ? 'Please wait…' : 'Sign in'}
              </button>
              <button
                className="text-xs text-gray-500 hover:text-gray-300 transition-colors w-full text-center"
                onClick={() => { setForgotMode(true); setError('') }}
              >
                Forgot password? Get a login link
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
