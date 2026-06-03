import { NavLink, Outlet, useNavigate } from 'react-router-dom'
import { useAuth } from '@/contexts/auth'
import { useQuota, QuotaProvider } from '@/contexts/quota'
import { Button } from '@/components/ui/button'
import { Avatar, AvatarFallback } from '@/components/ui/avatar'
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from '@/components/ui/dropdown-menu'
import { Separator } from '@/components/ui/separator'
import { cn } from '@/lib/utils'
import { Package, Play, LogOut, TrendingUp } from 'lucide-react'

const NAV = [
  { to: '/products', icon: Package, label: 'Products' },
  { to: '/runs', icon: Play, label: 'Runs' },
]

const ADMIN_NAV = [
  { to: '/admin/growth', icon: TrendingUp, label: 'Growth' },
]

function AdminNav() {
  const { quota } = useQuota()
  if ((quota?.tier as string) !== 'admin') return null
  return (
    <>
      <Separator className="bg-sidebar-border" />
      <div className="px-2 py-2">
        <p className="px-3 pb-1 text-xs font-semibold text-sidebar-foreground/50 uppercase tracking-wider">Admin</p>
        {ADMIN_NAV.map(({ to, icon: Icon, label }) => (
          <NavLink key={to} to={to}>
            {({ isActive }) => (
              <span className={cn(
                'flex items-center gap-3 rounded-md px-3 py-2 text-sm transition-colors',
                isActive
                  ? 'bg-sidebar-accent text-sidebar-accent-foreground font-medium'
                  : 'text-sidebar-foreground hover:bg-sidebar-accent/50',
              )}>
                <Icon className="h-4 w-4" />
                {label}
              </span>
            )}
          </NavLink>
        ))}
      </div>
    </>
  )
}

function TierBadge() {
  const { quota, isLoading } = useQuota()
  if (isLoading) return <div className="px-3 py-2 text-xs text-muted-foreground">Loading…</div>
  if (!quota) return null
  const tier = quota.tier
  const color =
    tier === 'beta'    ? 'bg-cyan-500/15 text-cyan-400 border-cyan-500/30' :
    tier === 'starter' ? 'bg-blue-500/15 text-blue-400 border-blue-500/30' :
    tier === 'pro'     ? 'bg-purple-500/15 text-purple-400 border-purple-500/30' :
                         'bg-white/10 text-gray-300 border-white/20'
  const { runs_this_month, scans_this_month } = quota.usage
  const { runs_per_month, scans_per_month } = quota.limits
  return (
    <div className="px-3 py-2 space-y-1.5">
      <span className={`inline-flex items-center px-2 py-0.5 rounded-full border text-xs font-medium capitalize ${color}`}>
        {tier}
      </span>
      <div className="text-xs text-muted-foreground space-y-0.5">
        <div className={runs_this_month >= runs_per_month ? 'text-red-400' : ''}>
          {runs_this_month}/{runs_per_month} runs
        </div>
        <div className={scans_this_month >= scans_per_month ? 'text-red-400' : ''}>
          {scans_this_month}/{scans_per_month} scans
        </div>
      </div>
    </div>
  )
}

function AppLayoutInner() {
  const { session, signOut } = useAuth()
  const navigate = useNavigate()
  const email = session?.user?.email ?? ''
  const initials = email.slice(0, 2).toUpperCase()

  async function handleSignOut() {
    await signOut()
    navigate('/login')
  }

  return (
    <div className="dark flex h-screen bg-background text-foreground">
      {/* Sidebar */}
      <aside className="w-56 flex flex-col border-r bg-sidebar">
        <div className="px-4 py-4 flex items-center">
          <img src="/logo4.png" alt="Steadra" className="h-10 w-auto rounded-md" />
        </div>
        <Separator className="bg-sidebar-border" />
        <nav className="flex-1 px-2 py-3 space-y-1">
          {NAV.map(({ to, icon: Icon, label }) => (
            <NavLink key={to} to={to}>
              {({ isActive }) => (
                <span className={cn(
                  'flex items-center gap-3 rounded-md px-3 py-2 text-sm transition-colors',
                  isActive
                    ? 'bg-sidebar-accent text-sidebar-accent-foreground font-medium'
                    : 'text-sidebar-foreground hover:bg-sidebar-accent/50',
                )}>
                  <Icon className="h-4 w-4" />
                  {label}
                </span>
              )}
            </NavLink>
          ))}
        </nav>
        <AdminNav />
        <Separator className="bg-sidebar-border" />
        <TierBadge />
        <Separator className="bg-sidebar-border" />
        <div className="px-3 py-3">
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button variant="ghost" className="w-full justify-start gap-2 px-2">
                <Avatar className="h-6 w-6">
                  <AvatarFallback className="text-xs">{initials}</AvatarFallback>
                </Avatar>
                <span className="text-sm truncate text-sidebar-foreground">{email}</span>
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent side="top" align="start" className="w-48">
              <DropdownMenuItem onClick={handleSignOut}>
                <LogOut className="mr-2 h-4 w-4" />
                Sign out
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        </div>
      </aside>

      {/* Main content */}
      <main className="flex-1 overflow-auto">
        <Outlet />
      </main>
    </div>
  )
}

export default function AppLayout() {
  return (
    <QuotaProvider>
      <AppLayoutInner />
    </QuotaProvider>
  )
}
