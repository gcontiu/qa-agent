import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAuth } from '@/contexts/auth'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'

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
    <div className="min-h-screen flex items-center justify-center bg-background p-4">
      <Card className="w-full max-w-md">
        <CardHeader className="text-center">
          <CardTitle className="text-2xl">Steadra</CardTitle>
          <CardDescription>Automated QA for your products</CardDescription>
        </CardHeader>
        <CardContent>
          {linkSent ? (
            <p className="text-sm text-center text-muted-foreground">
              Check your email — we sent you a login link.
            </p>
          ) : forgotMode ? (
            <div className="space-y-4">
              <p className="text-sm text-muted-foreground">
                Enter your email and we'll send you a login link.
              </p>
              <div className="space-y-1">
                <Label htmlFor="forgot-email">Email</Label>
                <Input
                  id="forgot-email"
                  type="email"
                  value={email}
                  onChange={(e: React.ChangeEvent<HTMLInputElement>) => setEmail(e.target.value)}
                  placeholder="you@example.com"
                  onKeyDown={(e: React.KeyboardEvent) => e.key === 'Enter' && handleMagicLink()}
                />
              </div>
              {error && <p className="text-sm text-destructive">{error}</p>}
              <Button className="w-full" onClick={handleMagicLink} disabled={loading}>
                {loading ? 'Sending…' : 'Send login link'}
              </Button>
              <button
                className="text-xs text-muted-foreground hover:underline w-full text-center"
                onClick={() => { setForgotMode(false); setError('') }}
              >
                Back to sign in
              </button>
            </div>
          ) : (
            <>
              <Button
                variant="outline"
                className="w-full mb-4 gap-2"
                onClick={() => signInWithGitHub().catch((e: Error) => setError(e.message))}
                disabled={loading}
              >
                <svg viewBox="0 0 24 24" className="w-4 h-4 fill-current"><path d="M12 0C5.37 0 0 5.37 0 12c0 5.31 3.435 9.795 8.205 11.385.6.105.825-.255.825-.57 0-.285-.015-1.23-.015-2.235-3.015.555-3.795-.735-4.035-1.41-.135-.345-.72-1.41-1.23-1.695-.42-.225-1.02-.78-.015-.795.945-.015 1.62.87 1.845 1.23 1.08 1.815 2.805 1.305 3.495.99.105-.78.42-1.305.765-1.605-2.67-.3-5.46-1.335-5.46-5.925 0-1.305.465-2.385 1.23-3.225-.12-.3-.54-1.53.12-3.18 0 0 1.005-.315 3.3 1.23.96-.27 1.98-.405 3-.405s2.04.135 3 .405c2.295-1.56 3.3-1.23 3.3-1.23.66 1.65.24 2.88.12 3.18.765.84 1.23 1.905 1.23 3.225 0 4.605-2.805 5.625-5.475 5.925.435.375.81 1.095.81 2.22 0 1.605-.015 2.895-.015 3.3 0 .315.225.69.825.57A12.02 12.02 0 0 0 24 12c0-6.63-5.37-12-12-12z"/></svg>
                Continue with GitHub
              </Button>
              <div className="relative mb-4">
                <div className="absolute inset-0 flex items-center"><span className="w-full border-t" /></div>
                <div className="relative flex justify-center text-xs uppercase">
                  <span className="bg-card px-2 text-muted-foreground">or</span>
                </div>
              </div>
              <div className="space-y-4">
                <div className="space-y-1">
                  <Label htmlFor="email">Email</Label>
                  <Input
                    id="email"
                    type="email"
                    value={email}
                    onChange={(e: React.ChangeEvent<HTMLInputElement>) => setEmail(e.target.value)}
                    placeholder="you@example.com"
                    onKeyDown={(e: React.KeyboardEvent) => e.key === 'Enter' && handleSignIn()}
                  />
                </div>
                <div className="space-y-1">
                  <Label htmlFor="password">Password</Label>
                  <Input
                    id="password"
                    type="password"
                    value={password}
                    onChange={(e: React.ChangeEvent<HTMLInputElement>) => setPassword(e.target.value)}
                    onKeyDown={(e: React.KeyboardEvent) => e.key === 'Enter' && handleSignIn()}
                  />
                </div>
                {error && <p className="text-sm text-destructive">{error}</p>}
                <Button className="w-full" onClick={handleSignIn} disabled={loading}>
                  {loading ? 'Please wait…' : 'Sign in'}
                </Button>
                <button
                  className="text-xs text-muted-foreground hover:underline w-full text-center"
                  onClick={() => { setForgotMode(true); setError('') }}
                >
                  Forgot password? Get a login link
                </button>
              </div>
            </>
          )}
        </CardContent>
      </Card>
    </div>
  )
}
