import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAuth } from '@/contexts/auth'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'

export default function LoginPage() {
  const { signIn, signUp } = useAuth()
  const navigate = useNavigate()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const [signedUp, setSignedUp] = useState(false)

  async function handle(action: 'login' | 'signup') {
    setError('')
    setLoading(true)
    try {
      if (action === 'login') {
        await signIn(email, password)
        navigate('/products')
      } else {
        await signUp(email, password)
        setSignedUp(true)
      }
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
          <CardTitle className="text-2xl">qa-agent</CardTitle>
          <CardDescription>Automated QA for your products</CardDescription>
        </CardHeader>
        <CardContent>
          {signedUp ? (
            <p className="text-sm text-center text-muted-foreground">
              Account created. Check your email to confirm, then sign in.
            </p>
          ) : (
            <Tabs defaultValue="login">
              <TabsList className="w-full mb-4">
                <TabsTrigger value="login" className="flex-1">Sign in</TabsTrigger>
                <TabsTrigger value="signup" className="flex-1">Sign up</TabsTrigger>
              </TabsList>

              {(['login', 'signup'] as const).map(tab => (
                <TabsContent key={tab} value={tab}>
                  <div className="space-y-4">
                    <div className="space-y-1">
                      <Label htmlFor={`${tab}-email`}>Email</Label>
                      <Input
                        id={`${tab}-email`}
                        type="email"
                        value={email}
                        onChange={(e: React.ChangeEvent<HTMLInputElement>) => setEmail(e.target.value)}
                        placeholder="you@example.com"
                        onKeyDown={(e: React.KeyboardEvent) => e.key === 'Enter' && handle(tab)}
                      />
                    </div>
                    <div className="space-y-1">
                      <Label htmlFor={`${tab}-password`}>Password</Label>
                      <Input
                        id={`${tab}-password`}
                        type="password"
                        value={password}
                        onChange={(e: React.ChangeEvent<HTMLInputElement>) => setPassword(e.target.value)}
                        onKeyDown={(e: React.KeyboardEvent) => e.key === 'Enter' && handle(tab)}
                      />
                    </div>
                    {error && <p className="text-sm text-destructive">{error}</p>}
                    <Button className="w-full" onClick={() => handle(tab)} disabled={loading}>
                      {loading ? 'Please wait…' : tab === 'login' ? 'Sign in' : 'Create account'}
                    </Button>
                  </div>
                </TabsContent>
              ))}
            </Tabs>
          )}
        </CardContent>
      </Card>
    </div>
  )
}
