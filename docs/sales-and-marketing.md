## Landing page changes

Task list for the landing page rewrite. Items marked `[x]` are implemented in code. Items marked `[ ]` require assets or external setup from the founder.

| # | Task | Status | Notes |
|---|---|---|---|
| 1 | URL field (mandatory) in form + backend `_WaitlistEntry` model updated to store `url` | [x] Done | |
| 2 | H1 rewrite with QA-junior anchor: "Your on-demand QA junior." | [x] Done | |
| 3 | Subhead: "Point it at a URL, get a prioritized bug report in minutes. No hiring, no test scripts." | [x] Done | |
| 4 | Success state: "We're scanning {url} right now — report in ~10 min" | [x] Done | |
| 5 | CTA button: "Get early access →" + scarcity counter "27 of 50 spots claimed this month" | [x] Done | Update `SPOTS_CLAIMED` const in `LandingPage.tsx` manually or wire to API |
| 6 | Remove placeholder screenshot → mock issues preview (styled dark UI with 5 sample issues) | [x] Done | |
| 7 | Segmentation chips (E-commerce / SaaS / Agency) below hero — swap tagline on click | [x] Done | |
| 8 | Privacy microcopy under form: "We only scan public pages. No login required. Report is private to you." | [x] Done | |
| 9 | Founder note section with initials avatar, quote, name, Calendly CTA | [x] Done (partial) | Needs: (a) real founder photo → replace initials `div` with `<img>` in `LandingPage.tsx:FOUNDER_NOTE`; (b) Calendly URL → replace `CALENDLY_URL` const |
| 10 | Pricing subtitle reframed for beta: "Beta cohort gets locked-in pricing — pay nothing during your 30-day trial." | [x] Done | |
| 11 | FAQ section (4 Q&As: vs Lighthouse/Cypress, pages crawled, data storage, invite timing) | [x] Done | |
| 12 | Footer: Privacy + Terms + hello@steadra.dev links | [x] Done | |
| 13 | Fix passive CTA under pricing: "Get my free mini-scan + early access" | [x] Done | |
| 14 | Real screenshot / GIF recording of an actual Steadra run | [ ] Needs founder | Record a run on a real site; replace mock report section or add above it |
| 15 | Social proof strip (testimonial + logo) | [ ] Needs beta users | Add after first 5 beta users complete 3+ runs with NPS ≥4 |

---

## Landing page

# the one sentence
Recommended combination:

  ▎ An on-demand QA junior for your web app — point it at a URL, get a prioritized bug report in minutes. No hiring, no test scripts.

  It pulls both audiences in one sentence:
  - "QA junior" + "no hiring" → anchors price for founders/PMs (€2-4k/mo salary mental model)
  - "point it at a URL" + "no test scripts" → concrete, low-friction promise for devs
  
  Slightly tighter alternate if you want it to fit a hero in one line:

  ▎ Your on-demand QA junior — point it at a URL, get a prioritized bug report in minutes. No hiring, no test scripts.

  The only thing I'd test against this: drop "junior" if your beta users push back on the framing (some teams won't want to think of their AI as
  junior-level — they'll want partner/senior framing). But for cold conversion, "junior" is the right anchor — it sets expectations honestly and
  prices well, since a senior QA mental model implies $99 is too cheap to be real.

---

## Beta user flow

The goal of the beta is not to "collect emails." It is to (1) prove the product solves a real problem on real sites, (2) generate testimonials, case studies and referrals, and (3) convert a meaningful share of beta users into paid Starter customers when the trial expires. Every choice below is in service of one of those three outcomes.

### Guiding principles

- **No dead waitlists.** A user who submits their email gets value within 10 minutes, not a 3-week silence. Silence is churn before the user has even started.
- **Time-to-first-value = 0.** When the user logs in for the first time, the product is already populated with *their* site, *their* specs, *their* first report. Empty states kill activation.
- **Founder talks to users.** During beta, every dissatisfied user gets a Calendly link to talk to the founder personally — not to support. Beta is a learning instrument, not a free tier.
- **Beta has an expiry.** No open-ended free access. 30 days, then the user converts to a paid plan or the account becomes read-only. Forcing the conversation generates the data needed to price, position and improve the product.
- **Capture intent, not just contact.** Every signup field that does not directly improve the user's first experience or our segmentation is dead weight.

### The funnel, end to end

#### 1. Landing page → Capture (T+0)

The CTA is **not** "Join the waitlist." It is **"Get early access — limited to 50 sites this month."** Scarcity is real, not theatrical: cap the cohort. The form asks for two fields only:

- Email
- URL of the site they want tested

The URL is mandatory. It gives us intent, segmentation data, and the fuel for step 2.

#### 2. Instant mini-scan (T+0 to T+10 minutes)

On submit, the backend automatically queues a *capped* scan against the submitted URL:

- Limit: 3 scenarios, hard cap at 5 minutes of wall time
- Output: a short, opinionated report sent by email — top 3 issues found, framed as "Here is what we found on your site, right now."

This is the single highest-leverage change in the entire funnel. It transforms a passive waitlist into an activation loop. The user does not wait for permission — they have already received value.

If the mini-scan finds nothing meaningful, the email still ships with framing such as: "Your site passed our quick checks. Want the full scan? Your invite is below." Either outcome is a win.

#### 3. Confirmation drip (T+0 minutes to T+14 days)

The user enters a 5-email sequence (Resend, Postmark or equivalent). The sequence is short, opinionated and ends in a conversion ask.

| When | Subject | Goal |
|---|---|---|
| T+0 min | Your mini-scan is running | Confirm receipt, set expectation |
| T+10 min | We found N issues on yoursite.com | Deliver the mini-report. This is the activation email |
| T+24 h | Your full Steadra account is ready | Invite link to log in; account is preconfigured with their product, specs, and the mini-report visible |
| T+3 days | Top issue we found across your scans | Reinforce value. Offer a 15-min guided tour with the founder |
| T+14 days | Two weeks of beta left — what's missing? | Solicit feature requests and intent-to-pay signals |

#### 4. Activation (T+24 hours)

When the user clicks the invite link in email #3, the experience is **not** an empty product:

- Their product is already created (from the URL they submitted)
- The specs from the mini-scan are present, viewable and editable
- The mini-report is visible on the runs page
- A subtle tour highlights the "Run full scan" button

First action they can take is the highest-value one. No empty states, no "Create your first product" wizard, no friction.

#### 5. Segmentation by intent

The URL the user submitted gives us enough to classify them coarsely:

- **E-commerce** → messaging: *"Catch broken checkout flows before your next campaign launch."*
- **SaaS** → messaging: *"Catch regressions before they reach paying customers."*
- **Agency / consultancy** → messaging: *"Test 10 client sites with one config."*

Segmentation drives the copy in emails #3, #4 and #5, and the in-app tour. Same product, three value props, materially higher activation.

#### 6. Feedback capture (continuous)

After every completed run, an in-app NPS-style prompt: *"Was this report useful? 1–5."*

- 4–5 → trigger the social-proof loop (step 8)
- 1–3 → auto-ship a Calendly link for a 15-minute call **with the founder**. Not with support. Founder.

In beta, every detractor is a free product research session.

#### 7. Beta cohort report (T+30 days)

At the end of the 30-day window, send each user a personal report:

> *"In your 30 days on Steadra you ran X scans, we surfaced Y issues, and you saved approximately Z hours of manual QA. Here is what we'd recommend doing next."*

Then, and only then, present the upgrade choice. The framing is **not** "upgrade or get cut off." The framing is "look at what we did together — let's keep going."

This is the moment of truth. Track conversion rate religiously.

#### 8. Social proof loop

After the 5th successful run with a 4–5 NPS, surface a one-shot in-app prompt:

> *"Mind sharing two sentences about why you'd recommend Steadra?"*

Reward: one free month on the Starter plan, post-beta. Bonus opt-in: permission to use their logo on the landing page.

The output of this loop directly feeds:

- Testimonial carousel on the landing page
- Logo bar on the landing page
- Quote-style social posts
- Case study material for sales

#### 9. Founder-led closure for power users

Manually flag users who hit ≥10 scans, ≥3 products, or have explicitly asked for features. Personally email them: 15 minutes, founder direct, no agenda. This cohort produces case studies, paid pilots, and the first design partners.

### What we measure

| Metric | Target (beta) | Why |
|---|---|---|
| Email → mini-scan delivered | 95%+ | Pipeline health |
| Mini-scan email open rate | 40%+ | Subject line + delivery quality |
| Mini-scan → invite accepted | 30%+ | Mini-report value |
| Invite → first full run | 50%+ | Onboarding quality |
| First run → 5th run | 25%+ | Stickiness |
| NPS ≥4 share | 50%+ | Product quality signal |
| Beta → paid conversion | 15%+ at day 30 | The number that matters |

If beta → paid lands above 15%, the funnel is healthy enough to scale paid acquisition. If it lands below 8%, the problem is not the funnel — it is the product or the price, and we go back to discovery.

### Build order (priority-ranked)

Reflects the constraints agreed in `docs/business-decisions.md` BD-005 § "Pre-invite acquisition cost (mini-scan)": Opus analyst with single-page scope, 60s wall-time cap, hard daily limit of 20 mini-scans, IP rate-limit, no double opt-in.

| # | Build | What it includes | Impact | Effort |
|---|---|---|---|---|
| 1 | Waitlist refactor + anti-abuse | Add mandatory URL field on landing form. Move waitlist from `reports/.state/waitlist.json` to Postgres table `waitlist`. Server-side syntax + MX record check on submitted email. Disposable-domain blocklist. Cloudflare Turnstile on the form. IP rate-limit at 3 submits/hour. | High | Low |
| 2 | Auto mini-scan on submit | Background worker triggers the analyst with `pages=[root_url]`, Opus model, 60s wall-time cap, default bootstrap depth. Enforce global hard cap of 20 mini-scans/day — submissions beyond the cap are saved to the waitlist and queued for the next day. | **Massive** | Medium |
| 3 | Mini-scan → email report | HTML email rendered from a template ("We found N issues on yoursite.com") containing deterministic scanner output (console errors, 4xx/5xx, broken assets) and an invite-to-beta CTA. Send via Resend or Postmark. | High | Low |
| 4 | Founder notification on submit | Webhook (Slack or email) to `anghel@steadra.dev` on every waitlist submit: URL, email, time, today's mini-scan count vs daily cap. Surfaces signups in real time and flags when the cap is near. | Medium | Low |
| 5 | Invite → `tier='beta'` flow | Convert a waitlist row into an invited beta user: Supabase Auth invite email + the existing `handle_new_auth_user` trigger sets `users.tier='beta'` automatically for invited users. CLI script (or admin endpoint) to issue invites. | High | Low |
| 6 | Onboarding: preconfigured product | On first sign-in from an invited beta user, auto-create their product from the URL captured at waitlist submission and populate spec drafts from the mini-scan output. No empty-state wizard, no "create your first product" screen. | High | Medium |
| 7 | 30-day beta expiry + upgrade CTA | Background job (or on-request check) flips `tier='beta'` to a read-only state when `created_at + 30 days` passes. UI surfaces an upgrade modal on the next action. | High | Low |
| 8 | 5-email drip sequence | Transactional emails scheduled at T+0, T+10 min, T+24 h, T+3 days, T+14 days. Copy varies by URL-based segment (e-commerce / SaaS / agency). | High | Low |
| 9 | In-app NPS after every run | Inline post-run prompt: "Was this report useful? 1–5". On 1–3, surface a Calendly link to the founder directly (not support). | Medium | Low |
| 10 | Cohort report email at T+30 | Personalised summary email: scans run, issues found, estimated hours saved, plain upgrade choice. | High | Low |
| 11 | Admin dashboard for waitlist | Lists pending waitlist entries, today's daily-cap usage, cumulative mini-scan cost. Allows manual invite trigger and waitlist row inspection. | Medium | Medium |

#2 remains the highest-leverage build in the roadmap. Items #1–#3 are the minimum cut to ship the activation loop; #5–#7 close the loop from waitlist to first run; #8–#10 are the conversion tail.

#### Deferred — not on the critical path for the first beta cohort

- **Manual report review before send.** Activates only when the Haiku migration trigger fires (BD-005 § Pre-invite acquisition cost — Opus mini-scan cost > $50/mo sustained for 2+ months). Adds a `pending_review` status to mini-scans, an approve/edit/reject UI, and founder notification on each draft. Builds on top of item #11.
- **Social proof capture loop.** In-app "share two sentences" prompt after the 5th successful run, with a Starter-month reward for opt-in. Build after the first 5 beta users have completed at least 3 runs each — earlier is wasted effort.
- **Power-user founder outreach automation.** Manual flag-then-email loop for users with ≥10 scans or ≥3 products. Operational rather than software for the first cohort.

### What we are explicitly not doing

- **No "Join the waitlist" copy.** Communicates passivity. Replaced by "Get early access — limited to N sites."
- **No open-ended free tier disguised as beta.** Beta has a hard 30-day clock. Otherwise users never convert.
- **No empty-state onboarding.** A new user never sees a blank product screen — their site, their specs, their report are already there.
- **No "we'll be in touch" emails.** Every email in the sequence either delivers value or asks for a specific action.
- **No support-team-only feedback channel during beta.** Detractors get the founder's calendar.