/**
 * AdminGrowthRoutes — mount under /admin/growth/*
 *
 * In host App.tsx:
 *   import { AdminGrowthRoutes } from '@/growth/routes'
 *   <Route path="/admin/growth/*" element={<RequireAdmin><AdminGrowthRoutes /></RequireAdmin>} />
 */
import { Routes, Route, Navigate } from 'react-router-dom'
import Dashboard from './pages/Dashboard'
import WaitlistList from './pages/WaitlistList'
import WaitlistDetail from './pages/WaitlistDetail'
import DripQueue from './pages/DripQueue'

export function AdminGrowthRoutes() {
  return (
    <Routes>
      <Route index element={<Dashboard />} />
      <Route path="waitlist" element={<WaitlistList />} />
      <Route path="waitlist/:id" element={<WaitlistDetail />} />
      <Route path="drip" element={<DripQueue />} />
      <Route path="*" element={<Navigate to="" replace />} />
    </Routes>
  )
}
