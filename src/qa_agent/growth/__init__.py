"""Growth module — drop-in SaaS beta funnel."""
from .config import FunnelConfig
from .funnel import BetaFunnel
from .hooks import FunnelHooks
from .models import CostSummary, MiniScanResult, ScanIssue, WaitlistEntry

__all__ = [
    "BetaFunnel",
    "FunnelConfig",
    "FunnelHooks",
    "MiniScanResult",
    "ScanIssue",
    "WaitlistEntry",
    "CostSummary",
]
