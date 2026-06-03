import { NavLink, Outlet, useNavigate } from 'react-router-dom'
import { useAuth } from '@/contexts/auth'
import { useQuota, QuotaProvider } from '@/contexts/quota'
import { Avatar, AvatarFallback } from '@/components/ui/avatar'
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from '@/components/ui/dropdown-menu'
import { cn } from '@/lib/utils'
import { Package, Play, LogOut, TrendingUp } from 'lucide-react'

const NAV = [
  { to: '/products', icon: Package, label: 'Products' },
  { to: '/runs', icon: Play, label: 'Runs' },
]

const ADMIN_NAV = [
  { to: '/admin/growth', icon: TrendingUp, label: 'Growth' },
]

function TierBadge() {
  const { quota, isLoading } = useQuota()
  if (isLoading || !quota) return null
  const tier = quota.tier
  const color =
    tier === 'beta'    ? 'bg-cyan-500/15 text-cyan-400 border-cyan-500/30' :
    tier === 'starter' ? 'bg-blue-500/15 text-blue-400 border-blue-500/30' :
    tier === 'pro'     ? 'bg-purple-500/15 text-purple-400 border-purple-500/30' :
                         'bg-white/10 text-gray-300 border-white/20'
  const { runs_this_month, scans_this_month } = quota.usage
  const { runs_per_month, scans_per_month } = quota.limits
  return (
    <div className="flex items-center gap-3">
      <span className={`inline-flex items-center px-2 py-0.5 rounded-full border text-xs font-medium capitalize ${color}`}>
        {tier}
      </span>
      <span className={`text-xs ${runs_this_month >= runs_per_month ? 'text-red-400' : 'text-gray-500'}`}>
        {runs_this_month}/{runs_per_month} runs
      </span>
      <span className={`text-xs ${scans_this_month >= scans_per_month ? 'text-red-400' : 'text-gray-500'}`}>
        {scans_this_month}/{scans_per_month} scans
      </span>
    </div>
  )
}

function AppLayoutInner() {
  const { session, signOut } = useAuth()
  const { quota } = useQuota()
  const navigate = useNavigate()
  const email = session?.user?.email ?? ''
  const initials = email.slice(0, 2).toUpperCase()
  const isAdmin = (quota?.tier as string) === 'admin'

  async function handleSignOut() {
    await signOut()
    navigate('/login')
  }

  return (
    <div className="min-h-screen bg-[#07091a] text-white font-sans antialiased">
      {/* Topbar */}
      <header className="sticky top-0 z-40 border-b border-white/5 bg-[#07091a]/95 backdrop-blur-sm">
        <div className="mx-auto max-w-4xl w-full px-8 h-14 flex items-center gap-6">
          {/* Logo */}
          <img src="/logo4.png" alt="Steadra" className="h-10 w-auto shrink-0 rounded-md" />

          {/* Nav links */}
          <nav className="flex items-center gap-1">
            {NAV.map(({ to, icon: Icon, label }) => (
              <NavLink key={to} to={to}>
                {({ isActive }) => (
                  <span className={cn(
                    'flex items-center gap-1.5 px-3 py-1.5 rounded-md text-sm transition-colors',
                    isActive
                      ? 'bg-white/10 text-white font-medium'
                      : 'text-gray-400 hover:text-white hover:bg-white/5',
                  )}>
                    <Icon className="h-3.5 w-3.5" />
                    {label}
                  </span>
                )}
              </NavLink>
            ))}
            {isAdmin && ADMIN_NAV.map(({ to, icon: Icon, label }) => (
              <NavLink key={to} to={to}>
                {({ isActive }) => (
                  <span className={cn(
                    'flex items-center gap-1.5 px-3 py-1.5 rounded-md text-sm transition-colors',
                    isActive
                      ? 'bg-white/10 text-white font-medium'
                      : 'text-gray-400 hover:text-white hover:bg-white/5',
                  )}>
                    <Icon className="h-3.5 w-3.5" />
                    {label}
                  </span>
                )}
              </NavLink>
            ))}
          </nav>

          {/* Spacer */}
          <div className="flex-1" />

          {/* Tier + usage */}
          <TierBadge />

          {/* User menu */}
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <button className="flex items-center gap-2 rounded-full focus:outline-none focus:ring-2 focus:ring-cyan-500/50">
                <Avatar className="h-7 w-7">
                  <AvatarFallback className="text-xs bg-white/10 text-gray-300">{initials}</AvatarFallback>
                </Avatar>
              </button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end" className="w-48 bg-[#0d1024] border-white/10 text-white">
              <div className="px-2 py-1.5 text-xs text-gray-500 truncate">{email}</div>
              <DropdownMenuItem
                onClick={handleSignOut}
                className="text-gray-300 focus:text-white focus:bg-white/10 cursor-pointer"
              >
                <LogOut className="mr-2 h-4 w-4" />
                Sign out
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        </div>
      </header>

      {/* Page content */}
      <main className="mx-auto max-w-4xl w-full">
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
