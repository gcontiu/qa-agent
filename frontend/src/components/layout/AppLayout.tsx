import { NavLink, Outlet, useNavigate } from 'react-router-dom'
import { useAuth } from '@/contexts/auth'
import { Button } from '@/components/ui/button'
import { Avatar, AvatarFallback } from '@/components/ui/avatar'
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from '@/components/ui/dropdown-menu'
import { Separator } from '@/components/ui/separator'
import { cn } from '@/lib/utils'
import { LayoutDashboard, Package, Play, LogOut } from 'lucide-react'

const NAV = [
  { to: '/products', icon: Package, label: 'Products' },
  { to: '/runs', icon: Play, label: 'Runs' },
]

export default function AppLayout() {
  const { session, signOut } = useAuth()
  const navigate = useNavigate()
  const email = session?.user?.email ?? ''
  const initials = email.slice(0, 2).toUpperCase()

  async function handleSignOut() {
    await signOut()
    navigate('/login')
  }

  return (
    <div className="flex h-screen bg-background">
      {/* Sidebar */}
      <aside className="w-56 flex flex-col border-r bg-sidebar">
        <div className="px-4 py-5 flex items-center gap-2">
          <LayoutDashboard className="h-5 w-5 text-sidebar-primary" />
          <span className="font-semibold text-sidebar-foreground">qa-agent</span>
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
