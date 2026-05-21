import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'

interface Props {
  open: boolean
  onClose: () => void
  type: 'run_blocked' | 'scan_blocked'
  used: number
  limit: number
  tier: string
}

export default function QuotaLimitModal({ open, onClose, type, used, limit, tier }: Props) {
  const label = type === 'run_blocked' ? 'test runs' : 'site scans'
  const limitLabel = type === 'run_blocked' ? 'runs' : 'scans'

  return (
    <Dialog open={open} onOpenChange={onClose}>
      <DialogContent className="max-w-sm">
        <DialogHeader>
          <DialogTitle>Monthly limit reached</DialogTitle>
        </DialogHeader>
        <div className="space-y-4 py-2 text-sm">
          <p className="text-muted-foreground">
            You've used <span className="font-semibold text-foreground">{used}/{limit} {label}</span> this month
            {tier !== 'free' ? ` on your ${tier} plan` : ''}.
          </p>
          <p className="text-muted-foreground">
            You're clearly getting value from Steadra. Paid plans with higher {limitLabel} limits are coming soon — join the list and you'll be first to know.
          </p>
          <div className="flex flex-col gap-2 pt-1">
            <a
              href="mailto:anghel@steadra.dev?subject=I need more beta access"
              className="inline-flex items-center justify-center rounded-md bg-cyan-500 px-4 py-2 text-sm font-semibold text-black hover:bg-cyan-400 transition-colors"
              onClick={onClose}
            >
              Talk to founder for more access
            </a>
            <Button variant="ghost" size="sm" onClick={onClose}>
              Close
            </Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  )
}
