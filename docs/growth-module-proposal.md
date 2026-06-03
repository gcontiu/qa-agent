# Growth module — implementation proposal

> Status: **Phase 1 + 2 implemented** (commit `64b8d1e`)
> Owner: anghel@steadra.dev
> Scope: items #1–#11 of the Build order in `docs/sales-and-marketing.md`

## High-level architecture — as implemented

> This section documents what was actually built in Phase 1 + 2. It supersedes
> the exploratory sketches in the sections below wherever they diverge.

### System context

```
┌─────────────────────────────────────────────────────────────┐
│  Fly.io VM (qa-agent process)                               │
│                                                             │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  FastAPI app  (src/qa_agent/api.py)                  │  │
│  │                                                      │  │
│  │   app.include_router(funnel.router)                  │  │
│  │   ├── POST  /waitlist           ← public             │  │
│  │   └── GET/POST /admin/growth/*  ← admin-gated        │  │
│  │                                                      │  │
│  │   asyncio tasks (started at @app.on_event startup)   │  │
│  │   └── ScanWorker  (10s poll loop)                    │  │
│  └──────────────────────────────────────────────────────┘  │
│                  │ asyncpg pool (shared)                    │
└──────────────────┼──────────────────────────────────────────┘
                   │
         ┌─────────▼─────────┐
         │  Supabase Postgres │
         │  schema: public    │  ← host tables (users, products, jobs)
         │  schema: growth    │  ← module tables (waitlist, drip_jobs, …)
         └───────────────────┘
```

The growth module runs **in-process** with the FastAPI server — no separate worker process, no message broker. In-process `asyncio.create_task` is sufficient until daily scan volume exceeds ~100/day, at which point the scan worker moves to a separate Fly machine.

---

### Infrastructure

| Concern | Choice | Rationale |
|---|---|---|
| Runtime | In-process asyncio worker | Zero infra overhead; extractable later |
| Queue durability | Postgres `growth.drip_jobs` + `FOR UPDATE SKIP LOCKED` | Already have Postgres; no Redis/RabbitMQ until needed |
| Worker poll interval | 10 seconds | Low latency for scan start; cheap on idle |
| DB isolation | Dedicated `growth` schema | No table-name collisions; `DROP SCHEMA growth CASCADE` removes module cleanly |
| Email | Resend (prod) / ConsoleProvider (dev) | Auto-selected by `from_env()` via `RESEND_API_KEY` presence |
| Notifications | Slack webhook (prod) / ConsoleNotifyProvider (dev) | Auto-selected by `SLACK_FOUNDER_WEBHOOK` |
| Anti-abuse | `CompositeGuard(IPRateLimit, DisposableBlocklist, MXCheck)` | Turnstile added when `TURNSTILE_SECRET` is set |
| Templates | Jinja2 HTML | Fits in-repo; no external email builder dependency |
| Dependencies added | `dnspython>=2.6.0`, `jinja2>=3.1.0` | Only new pyproject.toml entries |

---

### API surface

**Public (no auth):**

| Method | Path | Description |
|---|---|---|
| `POST` | `/waitlist` | Submit email + URL; anti-abuse checks, segment detection, daily cap check, returns `{status, id}` |

**Admin (requires `tier == 'admin'`):**

| Method | Path | Description |
|---|---|---|
| `GET` | `/admin/growth/overview` | Dashboard KPIs: total waitlist, today's scan count, last 10 signups |
| `GET` | `/admin/growth/waitlist` | Paginated list; filters: scan_status, invite_status, segment, q |
| `GET` | `/admin/growth/waitlist/:id` | Full per-user timeline payload: entry state + drip jobs + host_summary + cost_summary |
| `POST` | `/admin/growth/waitlist/:id/force-rescan` | Reset scan_status to 'pending' (bypasses daily cap) |
| `POST` | `/admin/growth/waitlist/:id/skip-next-drip` | Mark next pending drip job as 'skipped' |
| `GET` | `/admin/growth/drip` | Drip job queue; filter by status |

Auth gate is a FastAPI `Depends(admin_guard)` injected at `BetaFunnel` construction — growth never imports the host's auth code.

---

### Integration boundary

Only two files cross the module boundary:

```
src/qa_agent/api.py                     ← wires funnel into the app
src/qa_agent/integrations/growth_hooks.py  ← QAAgentHooks (the only host-specific code)
```

**`api.py` wiring (5 lines):**
```python
_funnel = BetaFunnel(config=..., hooks=QAAgentHooks(), email=..., notify=...,
                     antiabuse=..., admin_guard=_require_admin)
app.include_router(_funnel.router)
# startup: _growth_set_pool(db_get_pool()); await _funnel.start_workers()
# shutdown: await _funnel.stop_workers()
```

**`QAAgentHooks` — the 4 mandatory + 2 optional methods:**

```
run_mini_scan()          → wraps run_analysis(model='claude-opus-4-7', 60s cap)
seed_user_account()      → creates product + seeds specs from scan_result (idempotent)
grant_tier()             → UPDATE users SET tier = $2
revoke_tier()            → grant_tier(user_id, 'free')
get_host_summary()       → queries jobs table: total_runs, completed_runs, last_run_at
get_user_cost_summary()  → queries jobs table: SUM(cost_usd), run_count
```

The last two are optional — growth degrades gracefully if they return `None`.

---

### DB pool sharing

The host's asyncpg pool (created by `qa_agent.db.init()` at startup) is passed into the growth module at startup via:

```python
from qa_agent.growth.db import set_pool as _growth_set_pool
_growth_set_pool(db_get_pool())
```

Growth uses this pool through its own `growth.db.get_pool()` accessor. The two schemas share one connection pool — no second connection overhead.

---

### Anti-abuse pipeline

Every `POST /waitlist` request passes through this pipeline in order:

```
1. Turnstile token verify   (if TURNSTILE_SECRET set; otherwise skipped)
2. Email format check       (regex — always)
3. Disposable domain check  (in-memory blocklist — always)
4. MX record check          (DNS lookup — always)
5. IP rate-limit            (3/hour sliding window, in-memory — always)
6. DB duplicate check       (email UNIQUE — always)
7. Daily cap check          (growth.daily_counters — marks 'capped', doesn't block)
```

Steps 1–6 return HTTP 422/429 and block the submission. Step 7 stores the row with `scan_status='capped'` — the user gets on the waitlist but the scan is queued for the next day.

---

### Scan worker flow

```
every 10s:
  if daily_counters['mini_scans'] >= 20 → skip
  row = claim_next_pending_scan()   ← FOR UPDATE SKIP LOCKED (one worker safe)
  if none → skip

  send "mini_scan_running" email (T+0)
  notify founder via Slack
  run hooks.run_mini_scan(url) with asyncio.wait_for(60s)
    → on timeout  → mark_scan_failed('timeout')
    → on error    → mark_scan_failed(str(exc))
    → on success  → mark_scan_done(result)
                    increment daily_counters['mini_scans']
                    send "mini_scan_results" email with issues list
                    mark_scan_email_sent
                    schedule drip job 'invite' at T+24h
```

`scan_cost_usd` is written by `MiniScanResult.cost_usd` which `QAAgentHooks.run_mini_scan` populates from the Anthropic API usage response (`result.cost_usd`).

---

### Key architectural decisions

| Decision | Choice | Alternative rejected | Why |
|---|---|---|---|
| Schema isolation | `growth.*` schema | Prefixed tables (`growth_waitlist`) | `DROP SCHEMA CASCADE` removes module; no name collisions |
| Worker model | In-process `asyncio.create_task` | Separate Fly process group | Zero infra overhead for Phase 1-2 volume |
| Queue backend | Postgres `FOR UPDATE SKIP LOCKED` | Redis/RabbitMQ | Avoids new infra; durability is sufficient |
| Duplicate submit | `{status: 'already_queued'}` 200 | 409 error | Friendlier UX; cheaper (no re-scan) |
| Admin auth gate | Injected `FastAPI.Depends` callable | Hard-coded tier check inside growth | Growth stays auth-agnostic; host decides who's admin |
| Cost boundary | Growth owns `scan_cost_usd`; host owns `jobs.cost_usd` | Single cost table | Each schema owns what it caused; clean on extraction |
| Provider selection | `from_env()` factory per provider | Config file | Twelve-factor; no config format to maintain |
| No double opt-in | Confirmed email via MX check only | Confirmation email | MX + disposable blocklist catches ~95% junk; 20-30% drop from double opt-in unacceptable |

---

## Why a separate module

The 11-item Build order in `sales-and-marketing.md` covers what is, in effect, a generic SaaS beta funnel: capture → activation → onboarding → conversion. Most of it is project-agnostic: waitlist storage, drip scheduling, invite issuance, expiry tracking, NPS capture, founder notifications, anti-abuse.

Only three pieces are project-specific:

1. The **mini-scan** that converts a URL into immediate value (qa-agent runs an Opus analyst pass; another product might do a Lighthouse audit, a screenshot diff, a price scrape, etc.)
2. The **preconfigured account seeding** invoked on first sign-in (qa-agent creates a product + spec drafts; another product seeds whatever its empty-state would otherwise be)
3. The **tier mechanism** that gates access (qa-agent uses `public.users.tier`; another project might use `subscriptions`, custom claims, etc.)

If those three pieces sit behind explicit interfaces, the remaining 90% of the beta funnel becomes a drop-in module reusable across products.

## Non-goals

- **Not a microservice.** The growth module lives inside the qa-agent Python process. Extraction is a folder copy, not an API split.
- **Not a PyPI package** (yet). When two projects share it, packaging becomes worth doing — not before.
- **Not multi-tenant.** One growth module instance = one product. Multi-tenancy can be retrofitted via `tenant_id` columns later; YAGNI for now.

## Constraints (carried forward from BD-005 + sales-and-marketing.md)

- Mini-scan: Opus, `pages=[root_url]`, 60s wall-time cap, default bootstrap depth
- Hard daily cap of 20 mini-scans; submissions beyond cap are queued
- Anti-abuse stack: MX check + disposable-domain blocklist + Cloudflare Turnstile + IP rate-limit 3/hour. No double opt-in.
- Cohort soft cap: 50 users/month (used for landing scarcity counter)
- Beta enrolment: 30 days, then read-only state
- Drip cadence: T+0 / T+10min / T+24h / T+3d / T+14d, plus cohort report at T+30d
- Founder notification on every signup (Slack webhook or email)

## Architecture

### Module layout

```
src/qa_agent/growth/         # easy to mv to src/growth/ on extraction
├── __init__.py              # public re-exports
├── README.md                # how to integrate
├── config.py                # FunnelConfig
├── hooks.py                 # FunnelHooks (project extension points)
├── models.py                # Pydantic models
├── funnel.py                # BetaFunnel orchestrator (public entry point)
├── db/
│   ├── schema.sql           # CREATE SCHEMA growth + tables
│   ├── migrations/          # numbered upgrades (00001_init.sql, …)
│   ├── waitlist.py
│   ├── invites.py
│   ├── drip.py
│   ├── nps.py
│   └── counters.py
├── providers/
│   ├── email/               # EmailProvider Protocol + Resend / Postmark / Console
│   ├── notify/              # NotificationProvider + Slack / Email / Webhook
│   └── antiabuse/           # AntiAbuseGuard + Turnstile, MX, Disposable, RateLimit, Composite
├── workers/
│   ├── scan_worker.py       # picks pending scans, calls hooks.run_mini_scan
│   ├── drip_worker.py       # processes drip_jobs table
│   └── expiry_worker.py     # sweeps beta_enrollments where expires_at < now()
├── api/
│   ├── waitlist.py          # POST /waitlist
│   ├── nps.py               # POST /nps
│   ├── invite.py            # admin: POST /admin/growth/invite
│   └── admin.py             # admin: GET dashboard data
├── emails/
│   ├── templates/           # Jinja2 templates (HTML + plaintext) per drip stage
│   └── render.py            # segment-aware rendering
└── tests/
```

A frontend twin lives at `frontend/src/growth/` and mirrors the backend module — same decoupling rules, travels with extraction. Full layout in the **UI** section below.

### Module boundaries (the contract)

**Growth imports from:** stdlib, FastAPI, Pydantic, HTTPX, Jinja2.

**Growth never imports from:** `qa_agent.*`, Anthropic SDK, Playwright, MCP, any host-app domain code.

**Host project provides:** a `FunnelHooks` implementation + `FunnelConfig` + provider instances (email, notify, anti-abuse) + a DB pool. That's the integration surface — nothing else.

### The hook contract

```python
# growth/hooks.py
from typing import Protocol
from .models import MiniScanResult, WaitlistEntry

class FunnelHooks(Protocol):
    """Project-specific extension points. Growth calls these but never
    imports host-app code directly."""

    async def run_mini_scan(self, email: str, url: str) -> MiniScanResult:
        """Produce the value the user receives in the activation email."""

    async def seed_user_account(self, user_id: str, waitlist_row: WaitlistEntry) -> None:
        """Called once when a beta user signs in for the first time.
        Implementations should be idempotent."""

    async def grant_tier(self, user_id: str, tier: str = "beta") -> None:
        """Mark the user as beta-enrolled in the host app's auth/tier system."""

    async def revoke_tier(self, user_id: str) -> None:
        """Called when beta expires. Host decides what 'expired' means
        (read-only, downgrade, freeze, etc.)."""
```

`MiniScanResult` is a project-agnostic envelope:

```python
class ScanIssue(BaseModel):
    severity: Literal['critical', 'warning', 'info']
    type: str            # 'Console error', 'Network 500', 'Accessibility', …
    message: str
    location: str | None = None

class MiniScanResult(BaseModel):
    issues: list[ScanIssue]
    page_count: int
    duration_ms: int
    full_report_url: str | None = None  # optional deep link
```

### Data model

Postgres schema `growth`, fully isolated from host tables. Cross-schema reference only via loose `user_id TEXT` — growth never FK's into the host's user table.

Tables (5):

```sql
CREATE SCHEMA IF NOT EXISTS growth;

CREATE TABLE growth.waitlist (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email           TEXT NOT NULL UNIQUE,
    url             TEXT,
    segment         TEXT,              -- 'ecommerce' | 'saas' | 'agency' | NULL
    ip              TEXT,
    user_agent      TEXT,
    submitted_at    TIMESTAMPTZ NOT NULL DEFAULT now(),

    scan_status     TEXT NOT NULL DEFAULT 'pending', -- pending|running|done|failed|capped
    scan_started_at TIMESTAMPTZ,
    scan_done_at    TIMESTAMPTZ,
    scan_result     JSONB,
    scan_cost_usd   NUMERIC(8,4),       -- mini-scan cost; NULL until scan completes
    scan_email_sent_at TIMESTAMPTZ,

    invite_status   TEXT NOT NULL DEFAULT 'none',    -- none|sent|accepted
    invite_sent_at  TIMESTAMPTZ,
    invite_user_id  TEXT
);

CREATE TABLE growth.beta_enrollments (
    user_id           TEXT PRIMARY KEY,
    waitlist_id       UUID REFERENCES growth.waitlist(id),
    enrolled_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at        TIMESTAMPTZ NOT NULL,
    status            TEXT NOT NULL DEFAULT 'active', -- active|expired|converted
    converted_to_tier TEXT,
    converted_at      TIMESTAMPTZ
);

CREATE TABLE growth.drip_jobs (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    waitlist_id   UUID REFERENCES growth.waitlist(id),
    template      TEXT NOT NULL,
    scheduled_for TIMESTAMPTZ NOT NULL,
    sent_at       TIMESTAMPTZ,
    status        TEXT NOT NULL DEFAULT 'pending', -- pending|sent|failed|skipped
    error         TEXT
);

CREATE TABLE growth.nps_responses (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id      TEXT NOT NULL,
    score        INT  NOT NULL CHECK (score BETWEEN 1 AND 5),
    context_id   TEXT,                  -- e.g. run_id; opaque to growth
    comment      TEXT,
    submitted_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE growth.daily_counters (
    counter_date  DATE NOT NULL,
    counter_name  TEXT NOT NULL,
    counter_value INT  NOT NULL DEFAULT 0,
    PRIMARY KEY (counter_date, counter_name)
);
```

Migrations ship as part of the module (`growth/db/migrations/`). Host project runs them through whatever migration pipeline it already uses (Supabase CLI in our case).

### Provider adapters

Each external dependency sits behind a Protocol. Default implementations ship with the module; new ones are ~50 LOC each.

```python
class EmailProvider(Protocol):
    async def send(self, to: str, subject: str, html: str, text: str | None = None) -> None: ...

class NotificationProvider(Protocol):
    async def notify(self, channel: str, message: str, data: dict | None = None) -> None: ...

class AntiAbuseGuard(Protocol):
    async def verify_token(self, token: str, remote_ip: str) -> bool: ...
    async def check_email(self, email: str) -> EmailCheckResult: ...
    async def check_ip_rate(self, ip: str) -> RateCheckResult: ...
```

Shipped implementations:

- **Email:** `ResendProvider`, `PostmarkProvider`, `ConsoleProvider` (dev/test — prints to stdout)
- **Notify:** `SlackProvider`, `EmailNotifyProvider`, `WebhookProvider`
- **AntiAbuse:** `TurnstileGuard`, `MXCheck`, `DisposableBlocklist`, `IPRateLimit`, plus a `CompositeGuard` that chains them and returns the strictest verdict

### Configuration

Single dataclass, all dials in one place:

```python
@dataclass
class FunnelConfig:
    cohort_monthly_cap: int = 50
    daily_scan_cap: int = 20
    ip_rate_limit_per_hour: int = 3
    beta_duration_days: int = 30
    mini_scan_wall_time_seconds: int = 60

    drip_schedule: dict[str, timedelta] = field(default_factory=lambda: {
        'mini_scan_running': timedelta(),
        'mini_scan_results': timedelta(minutes=10),
        'invite':            timedelta(hours=24),
        'reinforce':         timedelta(days=3),
        'beta_check_in':     timedelta(days=14),
        'cohort_report':     timedelta(days=30),
    })

    segment_rules: list[SegmentRule] = ...  # URL → segment classification
    segment_copy:  dict[str, SegmentCopy] = ...  # per-segment email subject/body

    founder_notify_channel: str = "#signups"
```

## UI

The UI is part of the module's deliverables. Like the backend, it lives behind clean boundaries so it travels with the module on extraction.

### Goals

1. **Per-user observability.** For any waitlist entry, an operator can see the full funnel state on one page: capture → anti-abuse verdict → mini-scan → drip emails → invite → onboarding → beta lifecycle → NPS. This is the canonical debugging tool when something goes wrong.
2. **Live signup feed.** Founder-on-screen replacement for "Slack ping on every submit" — the dashboard shows the last 20 signups in real time.
3. **Operational levers.** A small set of actions (resend invite, force re-scan, skip drip, extend beta, mark converted) without dropping into psql.
4. **Cost visibility.** Daily mini-scan cap usage + cumulative monthly cost, so the migration trigger from BD-005 ("Opus > $50/mo for 2 months") is visible at a glance.

### Pages

| Route | Purpose |
|---|---|
| `/admin/growth` | Dashboard: 7 KPIs from the funnel doc + live signup feed + daily cap meter + monthly cost line |
| `/admin/growth/waitlist` | Paginated list of all waitlist rows; filters by `scan_status`, `invite_status`, segment, date range; search by email/URL |
| `/admin/growth/waitlist/:id` | **Per-user timeline** — the canonical view (see below) |
| `/admin/growth/active-beta` | Users currently in their beta window, sorted by `expires_at ASC`. Days-remaining badge (red <7, yellow <14, green ≥14), last sign-in, run count (host hook), last NPS, quick "Extend +30d" action. Top filter: "Expiring in <7 days" / "Active >14 days" / "All" |
| `/admin/growth/cost` | Cost projection: daily mini-scan spend (last 30 days) + EOM forecast, with reference lines for the **$50/mo Opus → Haiku migration trigger** and the **$200/mo BD-005 budget cap**. Top 10 spenders table + pre-invite vs in-beta breakdown |
| `/admin/growth/drip` | Drip queue: pending jobs (sortable by `scheduled_for`), failed jobs (with error), recently sent |
| `/admin/growth/nps` | NPS responses with score distribution + detractor list |

### Per-user timeline — the canonical view

A vertical timeline. Each row = one event, with timestamp, status icon, headline, and an expandable "raw data" block (JSON).

Sample render for one waitlist entry:

```
─────────────────────────────────────────────────────────────────────
 user@example-shop.com  ·  https://example-shop.com  ·  segment: ecommerce
 ID: 8f3a…  ·  Status: beta_active  ·  Day 12 / 30
─────────────────────────────────────────────────────────────────────

 ✓  2026-05-25 14:02:11   Waitlist submitted
       IP 203.0.113.42  ·  user-agent Chrome/130  ·  Turnstile ✓
       MX check ✓  ·  Disposable ✗  ·  IP rate 1/3 this hour

 ✓  2026-05-25 14:02:13   Mini-scan queued
       Position 4 of 12  ·  Daily cap usage 4/20

 ⏳ 2026-05-25 14:02:45   Mini-scan running
       Model: claude-opus-4-7  ·  Wall-time cap 60s

 ✓  2026-05-25 14:04:27   Mini-scan completed
       8 issues found  ·  12 pages crawled  ·  duration 1m 42s
       [View raw scan_result JSON ▾]

 ✓  2026-05-25 14:14:30   "Mini-scan results" email sent
       Resend ID: re_8a4f…  ·  Subject: "We found 8 issues on example-shop.com"

 ✓  2026-05-26 14:02:11   "Invite" email sent (T+24h)
       Magic-link URL  ·  expires 2026-06-02

 ✓  2026-05-26 18:43:02   Invite accepted
       Supabase user_id: 91b3e…  ·  tier set to 'beta'

 ✓  2026-05-26 18:43:08   Account seeded
       Product created  ·  3 spec drafts populated from scan_result

 ✓  2026-05-26 19:01:55   First full run completed
       (data from host hook — optional)

 ✓  2026-05-26 19:02:30   NPS captured
       Score 5/5  ·  "saved me half a day already"

 ⏳ 2026-05-29 14:02:11   Scheduled: "Reinforce" email (T+3d)

 ⏳ 2026-06-25 14:02:11   Scheduled: beta expiry sweep

 ─── Cost ──────────────────────────────────────────────────────
 Mini-scan:    $0.184   (one-time · Opus · 1m 42s)
 Beta runs:    $1.420   (from host hook · 4 runs · 2 analyst, 2 executor)
 ───────────────────────
 Total:        $1.604

 ─── Operational actions ───────────────────────────────────────
 [Resend invite]  [Force re-scan]  [Skip next drip email]
 [Extend beta by 30 days]  [Mark as converted to Starter]
```

The timeline reads chronologically. Future events (drip jobs scheduled but not sent, expiry date) appear greyed-out at the bottom. The operator can see exactly where in the funnel the user is and what's coming next.

### Frontend module layout

```
frontend/src/growth/                    # mirrors backend module; travels on extraction
├── routes.tsx                          # AdminGrowthRoutes (host mounts under /admin/growth)
├── api.ts                              # typed client for growth admin endpoints
├── components/
│   ├── Timeline.tsx                    # the per-user timeline
│   ├── TimelineEvent.tsx
│   ├── CostCard.tsx                    # per-user cost sub-card on timeline
│   ├── WaitlistTable.tsx
│   ├── ActiveBetaTable.tsx             # sorted by expires_at; days-remaining badges
│   ├── SignupFeed.tsx                  # live last-20 feed (polls every 30s)
│   ├── FunnelChart.tsx                 # waitlist → scan → invite → run → paid
│   ├── CostChart.tsx                   # time-series with EOM projection + reference lines
│   ├── TopSpenders.tsx                 # top 10 users by total cost-to-date
│   ├── CapMeter.tsx                    # 14/20 mini-scans today
│   └── ActionBar.tsx                   # operational levers
├── pages/
│   ├── Dashboard.tsx
│   ├── WaitlistList.tsx
│   ├── WaitlistDetail.tsx
│   ├── ActiveBeta.tsx
│   ├── CostProjection.tsx
│   ├── DripQueue.tsx
│   └── NPSResponses.tsx
└── README.md                           # how to mount in host app
```

Host wiring (one block in `App.tsx`):

```tsx
import { AdminGrowthRoutes } from '@/growth/routes'

<Route path="/admin/growth/*" element={
  <RequireTier tier="admin"><AdminGrowthRoutes /></RequireTier>
} />
```

### Backend endpoints (the read/action surface for the UI)

Mounted under `/admin/growth/*`, all gated by `tier == 'admin'`:

| Method + Path | Purpose |
|---|---|
| `GET /admin/growth/overview` | Dashboard KPIs + live feed |
| `GET /admin/growth/waitlist?status=&segment=&q=&page=` | List with filters/search |
| `GET /admin/growth/waitlist/:id` | Per-user timeline payload (events + current state + scheduled jobs + cost block) |
| `GET /admin/growth/active-beta?expiring_in=` | Active beta users; optional `expiring_in=<days>` filter |
| `GET /admin/growth/cost?range=30d` | Cost projection: daily series, EOM forecast, reference lines, top spenders, phase breakdown |
| `POST /admin/growth/waitlist/:id/resend-invite` | Action |
| `POST /admin/growth/waitlist/:id/force-rescan` | Action — bypasses daily cap |
| `POST /admin/growth/waitlist/:id/skip-next-drip` | Action |
| `POST /admin/growth/waitlist/:id/extend-beta` | Action — body `{days: int}` |
| `POST /admin/growth/waitlist/:id/mark-converted` | Action — body `{tier: str}` |
| `GET /admin/growth/drip?status=` | Drip queue inspector |
| `GET /admin/growth/nps?score_lte=&since=` | NPS list |

### Optional host hooks (for richer UI without coupling)

Two optional hooks let the host surface its own data inside growth's UI without growth ever importing host code. Both degrade gracefully — if not implemented or returning `None`, the relevant UI blocks are simply omitted.

```python
class FunnelHooks(Protocol):
    ...

    async def get_host_summary(self, user_id: str) -> dict | None:
        """Optional. Arbitrary key/value pairs about the user from the host's domain
        (e.g. last sign-in, total runs, latest run status). Rendered as a sub-card
        on the per-user timeline and as columns in the active-beta list."""

    async def get_user_cost_summary(self, user_id: str) -> CostSummary | None:
        """Optional. Host-side accumulated cost for a beta user. Combined with
        growth's own `scan_cost_usd` to render the timeline cost card, the
        cost-projection top-spenders table, and the pre-invite vs in-beta
        breakdown chart."""


class CostSummary(BaseModel):
    total_usd:     float
    breakdown:     dict[str, float]   # e.g. {"analyst_haiku": 0.12, "executor_sonnet": 1.30}
    run_count:     int = 0
    last_event_at: datetime | None = None
```

The UI degrades gracefully — if either hook returns `None` or isn't implemented, those blocks are simply omitted. This keeps growth's UI decoupled from qa-agent's domain while still letting us surface useful per-user context and cost data.

For qa-agent, `get_user_cost_summary` reads from the existing `jobs` table where per-run cost is already tracked (analyst + executor token usage × model price). Pre-invite cost (`scan_cost_usd`) stays in `growth.waitlist`; post-invite cost stays in `public.jobs`. The boundary is clean: growth owns what growth caused, host owns what host caused.

### Auth and access

Gated by `tier == 'admin'` from the host's auth system. The growth module doesn't decide who's an admin — it just receives the tier value via existing auth middleware. For qa-agent: reuse the current `RequireTier` wrapper.

---

### Beta user login flow

**Invite-only beta — no public sign-up.** Account creation happens server-side when the admin sends an invite (`POST /admin/growth/waitlist/:id/send-invite`). Self-service sign-up is intentionally absent from the login page; new users enter through the waitlist on the landing page only.

#### First login (invite acceptance)

```
Admin sends invite
  └─ Supabase generate_link(type=magiclink, redirect_to=/set-password)
       └─ Email with magic link → user clicks
            └─ /set-password  (Supabase processes hash, signs user in)
                 └─ User sets password
                      └─ navigate(/products)
                           └─ /me/activate fires (seeds product from scan_result, idempotent)
```

The magic link is single-use and expires in ~1 hour. Each new `send-invite` call invalidates the previous token.

#### Returning login (after logout)

```
/login page:
  ├─ Email + password  →  signIn()  →  /products
  ├─ GitHub OAuth      →  signInWithGitHub()  →  /products
  └─ "Forgot password? Get a login link"
       └─ sendMagicLink(email, redirectTo=/products)
            └─ OTP email → user clicks → /products
```

The "Get a login link" path (OTP via `signInWithOtp`) acts as forgot-password. It redirects to `/products` directly (no password re-set prompt), since the user already has an account.

#### Non-invited users

Users who never received an invite cannot create accounts. If an uninvited email is used on the login page:
- Password sign-in: Supabase returns "Invalid credentials"
- "Get a login link": Supabase sends an OTP — **but** the user has no account, so the link creates a new unverified Supabase user with no products and no `tier`. This is an accepted edge case; the `/products` page shows an empty state. A future gate (check `tier != 'free'` or `beta_enrollments` presence) can redirect to a waiting page.

#### Frontend files

| File | Role |
|---|---|
| `frontend/src/pages/LoginPage.tsx` | Sign-in form + GitHub OAuth + forgot-password magic link mode |
| `frontend/src/pages/SetPasswordPage.tsx` | Password setup after first invite login; protected route at `/set-password` |
| `frontend/src/contexts/auth.tsx` | Exposes `signIn`, `sendMagicLink`, `updatePassword`, `signInWithGitHub`, `signOut` |

### Reusability for extraction

When extracting to project #2, copy two folders:

1. `src/qa_agent/growth/` → `src/growth/`
2. `frontend/src/growth/` → `frontend/src/growth/` (path stays the same)

Then the standard 6-step extraction checklist applies. The UI travels with the module.

## Integration with qa-agent (concrete example)

Top-level wiring lives in `src/qa_agent/main.py`:

```python
from qa_agent.growth import BetaFunnel, FunnelConfig
from qa_agent.growth.providers.email import ResendProvider
from qa_agent.growth.providers.notify import SlackProvider
from qa_agent.growth.providers.antiabuse import CompositeGuard, TurnstileGuard
from qa_agent.integrations.growth_hooks import QAAgentHooks

funnel = BetaFunnel(
    config=FunnelConfig(),  # defaults match BD-005
    hooks=QAAgentHooks(),
    email=ResendProvider(api_key=env["RESEND_API_KEY"]),
    notify=SlackProvider(webhook=env["SLACK_FOUNDER_WEBHOOK"]),
    antiabuse=CompositeGuard(turnstile=TurnstileGuard(secret=env["TURNSTILE_SECRET"])),
    db=db,
)

app.include_router(funnel.router)           # mounts /waitlist, /nps, /admin/growth/*
app.on_event("startup")(funnel.start_workers)
app.on_event("shutdown")(funnel.stop_workers)
```

The only qa-agent-specific file is the hook implementation:

```python
# src/qa_agent/integrations/growth_hooks.py
from qa_agent.growth.hooks import FunnelHooks
from qa_agent.growth.models import MiniScanResult, ScanIssue, WaitlistEntry
from qa_agent.analyst import run_analysis
from qa_agent.db import products, users

class QAAgentHooks:
    async def run_mini_scan(self, email, url) -> MiniScanResult:
        result = await run_analysis(pages=[url], model='claude-opus-4-7', wall_time_seconds=60)
        return MiniScanResult(
            issues=[ScanIssue(...) for r in result.findings],
            page_count=result.pages_crawled,
            duration_ms=result.duration_ms,
        )

    async def seed_user_account(self, user_id, waitlist_row: WaitlistEntry):
        product_id = await products.create(user_id=user_id, name=waitlist_row.url, url=waitlist_row.url)
        if waitlist_row.scan_result:
            await products.seed_specs_from_scan(product_id, waitlist_row.scan_result)

    async def grant_tier(self, user_id, tier="beta"):
        await users.update_tier(user_id, tier)

    async def revoke_tier(self, user_id):
        await users.update_tier(user_id, "free")  # or "read_only"
```

Total qa-agent-specific surface: one file, ~50 lines. Everything else lives in `growth/`.

## Build phases — mapping to Build order

| Phase | Build order items | Backend deliverables | UI deliverables |
|---|---|---|---|
| **Phase 1 — Foundations** | #1 (waitlist + anti-abuse), #4 (founder notify) | `growth.config`, `hooks`, `models`, `db.schema`, `providers.{email,notify,antiabuse}`, `api.waitlist`, host-side `growth_hooks.py` stubs | `frontend/src/growth/` scaffold, `WaitlistList`, basic per-user timeline (capture + anti-abuse events only) |
| **Phase 2 — Activation loop** | #2 (auto mini-scan), #3 (mini-scan email) | `workers.scan_worker` (captures `scan_cost_usd` from Anthropic usage response), `emails.templates.mini_scan_*`, real `run_mini_scan` hook | Timeline extended with scan events + scan_result viewer + initial `CostCard` (mini-scan only); `CapMeter` + live signup feed on dashboard |
| **Phase 3 — Invite & onboarding** | #5 (invite → tier=beta), #6 (preconfigured product) | `api.invite`, real `seed_user_account` + `grant_tier` hooks | Timeline extended with invite + onboarding events; "Resend invite" action |
| **Phase 4 — Lifecycle** | #7 (30-day expiry), #8 (drip), #10 (cohort report) | `workers.expiry_worker`, `workers.drip_worker`, remaining templates | `DripQueue` page; **`ActiveBeta` page** with days-remaining badges; timeline shows scheduled drip events; "Skip next drip" + "Extend beta" actions |
| **Phase 5 — Feedback** | #9 (NPS), #11 (admin dashboard) | `api.nps`, `api.admin`, optional `get_user_cost_summary` host hook wired up | `NPSResponses` page; **`CostProjection` page** with EOM forecast + $50/$200 reference lines + top spenders; full `Dashboard` with funnel chart; `CostCard` extended with host-side runs cost; "Force re-scan" + "Mark converted" actions |

Recommendation: ship Phases 1 + 2 in one iteration. They unlock the highest-leverage funnel transformation (passive waitlist → active activation loop). The minimum-viable UI in that iteration is just `WaitlistList` + per-user `Timeline` with capture/scan events — enough to debug the activation loop while it's still fresh.

## Reusability checklist — extracting to project #2

1. Copy `src/qa_agent/growth/` → new project's `src/growth/`
2. Copy `frontend/src/growth/` → new project's `frontend/src/growth/` (path unchanged)
3. Update backend imports in the copy (`qa_agent.growth.X` → `growth.X`) — one `find / sed`
4. Implement the new project's `FunnelHooks` (the only mandatory rewrite)
5. Set env vars: `RESEND_API_KEY`, `SLACK_FOUNDER_WEBHOOK`, `TURNSTILE_SECRET`
6. Run `growth/db/migrations/*` against the new DB
7. Mount the backend router in FastAPI setup; mount `AdminGrowthRoutes` in React router

No other code changes. Target: a junior engineer should be able to do this in an afternoon.

## Open questions to resolve before implementation starts

1. **Postgres schema vs prefixed tables?** Schema is cleaner but requires the host DB to allow schema creation. On Supabase this is fine. **Default: schema.**

2. **Workers: in-process or separate process?** Phase 1–2 can run in-process via `asyncio.create_task` + background loops. When daily volume exceeds ~100 scans, extract to a separate Fly machine (`growth-workers` process group). **Default: in-process for now.**

3. **Drip queue durability.** Postgres `drip_jobs` table is durable; polling every 30s is acceptable until volume forces Redis/RabbitMQ. **Default: Postgres polling.**

4. **Turnstile on the frontend.** Requires `VITE_TURNSTILE_SITE_KEY` env var + a small widget component in `LandingPage.tsx`. The growth module's `verify_token` handles the server side.

5. **Idempotency on duplicate submit.** Current behaviour: 409. Proposed change: 200 with `{status: 'already_queued'}` and re-send the existing report instead of re-scanning. Cheaper and friendlier.

6. **Where do segment classification rules live?** In `FunnelConfig.segment_rules` as a list of `(regex, segment)` tuples. Defaults match common platforms (`*.shopify.com` → ecommerce, etc.). Host project can override.

7. **What does "read-only" mean on expiry for qa-agent specifically?** Block new runs and product creation, keep historical data viewable. The growth module just calls `revoke_tier`; semantics belong to `QAAgentHooks.revoke_tier` implementation.

8. **Frontend admin dashboard scope.** Phase 5 admin view: waitlist list, daily-cap usage, cumulative mini-scan cost, manual invite button. Read-only otherwise. Lives in `frontend/src/pages/AdminWaitlistPage.tsx`, gated by `tier == 'admin'`.

## What this proposal explicitly does **not** decide

- Final email copy (per stage, per segment) — drafted during Phase 4
- Exact regex set for segment classification — drafted during Phase 1
- Resend vs Postmark — defer to a separate decision based on EU vs US delivery rates; the adapter pattern makes the choice reversible
