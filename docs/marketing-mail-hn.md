# Beta promotion — launch playbook & assets

> Context: beta is live, full admin suite built (Dashboard, WaitlistList, WaitlistDetail
> timeline, ActiveBeta, CostProjection, DripQueue, SignupFeed, CapMeter, FunnelChart).
> Budget: €300. Constraint: **low founder time** — favour one-shot, high-leverage moves
> over daily manual grind. This reframes `docs/sales-and-marketing.md`, whose plan is
> outreach-led (founder-labour-dominated). With the funnel below the top already
> automated (mini-scan → drip → invite → seed), the only missing piece is **traffic**,
> and the cheapest low-time way to get a spike is **launch-led**, not outreach-led.

## Pre-launch checklist — don't waste the one shot

A Show HN / Product Hunt spike is a single opportunity. Sending traffic into a broken
funnel burns it. Verify before driving any traffic:

1. **Full flow end-to-end** with a real email: submit → mini-scan email → click CTA →
   invite → set-password → product seeded. (The `/set-password` redirect fix and the
   `redirect_to` top-level fix must be confirmed in prod.)
2. **Founder notifications live** — `EmailNotifyProvider` now sends signup/claim alerts
   to `FOUNDER_NOTIFY_EMAIL` (set to anghel.contiu@simplepath.tech) via Resend, since
   there's no Slack. Without this you're blind during the spike.
3. **Turnstile armed** — set `VITE_TURNSTILE_SITE_KEY` (fly.toml build arg) +
   `TURNSTILE_SECRET` (fly secret). A public launch will draw bots to the form.

## Channel plan — ordered by (impact / time)

1. **Launch spikes (free, one-shot):** Show HN (best ROI/time — dev audience, the
   "drop a URL" hook gives live demos in-thread), Product Hunt (scheduled, 10–15
   first-hour upvoters lined up), 2–3 subreddits (r/webdev, r/SaaS, r/agency) as
   value posts, not spam. Stagger over 2–3 weeks; each = 100–500 visitors.
2. **"Scan-and-tell" content (compounds, low effort/unit):** 1 post/week on X/LinkedIn
   with a real bug found on a public site. Natively shareable for a QA tool.
3. **Scan-first outreach — only if automated:** instead of 60 manual emails/day, write
   a weekend script that scrapes ~100 agency client URLs, runs the mini-scan, and emails
   a teaser ("found 3 things on [client-site]"). Converts dev time (available) into
   marketing time (scarce). If you won't build it, skip cold email entirely — it's a
   time sink (domain warmup, deliverability, follow-ups) and a poor fit for low-time.

## €300 allocation (low-time variant)

| Line | Cost | Why |
|---|---|---|
| Show HN + Product Hunt + Reddit | €0 | Traffic from launches, not ads |
| 1 niche newsletter sponsorship (dev/agency) | ~€120 | One-shot, zero management; extends the launch tail |
| Loom Pro + Calendly Pro | ~€40 | Personalised 90s Loom lifts warm-lead reply rate sharply |
| Apollo / lead list (only if doing the outreach script) | ~€50 | 100–300 agencies with one client URL each |
| Reserve / 2nd newsletter | ~€90 | Repeat what worked |

Removed vs. the original plan: the full cold-email machine (~€130 — domains, inboxes,
Smartlead). Justified only if outreach is the main bet and you have time to run it. You
don't — that money is better spent on one-shot newsletter placements.

Ignore: Google Ads (€4–12 CPC = wasted), any daily-touch channel, running all three ICP
segments at n=50. Focus on **small agencies (3–15 people)** — public client portfolios =
ready-made scan-first ammunition.

Realistic expectation: at €300 + low time you won't fill 50 spots fast. Launches yield
~20–35 signups in a good month; the rest comes from compounding content. That's fine —
the `tier='beta'` cohort is capped at 50/month anyway.

---

## Show HN — post

Post format on HN: **title + URL**, then immediately a **maker's first comment** telling
the story. HN rewards technical honesty and the ability to try it live; it penalises hype.

**Title** (no superlatives — HN down-ranks "revolutionary" etc.):

```
Show HN: Steadra – point it at a URL, get a prioritized bug report
```

**URL:** https://steadra.dev

**Maker's first comment:**

```
Hi HN, I built Steadra because I was tired of two bad options for QA on small
web apps: write and maintain brittle Selenium/Cypress suites that break on every
restyle, or skip testing and ship bugs.

Steadra is an agent that reads a web app the way a person does — through the
accessibility tree, not CSS selectors — so the same test keeps working when the
UI is restructured. You give it a URL and it does two things:

1. A free "mini-scan": crawls the site and reports the deterministic stuff —
   console errors, 4xx/5xx, broken assets, dead links, basic a11y issues. No
   config, no signup needed to understand the value.

2. If you want behavioral tests, you write scenarios in plain Gherkin (or let it
   draft them from the scan). It interprets each step as free text with an LLM —
   there are no step-definition bindings to write. It executes in a real browser
   and reports pass/fail with the reasoning behind every verdict, plus evidence
   (DOM snapshot, actions log).

Tech: it's built on the Claude Agent SDK with Playwright MCP for the browser
layer. The interesting/hard part was cost. Naively, an agent that snapshots the
page after every action burns tokens insanely fast — my first runs were ~$10
each. Using the accessibility tree instead of screenshots, snapshotting only
after state changes, and routing cheap steps to Haiku got a full run down to
~$1.50. It also runs against local models (Ollama, qwen2.5/llama3.1) if you
don't want to send anything to a provider.

It's product-agnostic by design — same binary tests a web app, a REST API, or a
CLI; you just swap the spec directory.

Honest limitations: it's strongest on flows you can describe in a few sentences;
very stateful multi-tab flows still need babysitting. Local models work but the
reasoning on large/dense pages is noticeably weaker than Sonnet. And it's early —
I'm opening a closed beta now (30 days free, no card).

I'd love feedback on two things specifically:
- Drop a URL in the comments and I'll run a scan and post what it finds — genuinely
  curious where it breaks on sites I haven't seen.
- For those of you doing QA at small teams: is "LLM-interprets-Gherkin, no step
  defs" actually useful to you, or do you want the determinism of bindings?

Beta signup is on the site (it kicks off a scan of your URL immediately). Happy
to answer anything.
```

### Why it's built this way
- **"Drop a URL and I'll scan it"** = product-led growth in-thread. Every URL you answer
  with real bugs is a public demo and proof. This is the engine.
- **Cost story ($10 → $1.50)** = the kind of technical detail that earns HN upvotes.
- **Stated limitations** = credibility; disarms critics.
- **Two concrete questions** = prompt comments (engagement drives ranking).

### Execution
1. Post Tue–Thu, ~15:00–16:00 UTC (8–9 AM US Eastern).
2. Stay on the thread the **first hour** — answer every URL with a real scan. This is
   where it's won.
3. Confirm the pre-launch checklist first, or the spike is wasted.
