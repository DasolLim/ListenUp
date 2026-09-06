# SUBSCRIPTION — tier design, Stripe setup, build order

Free + Paid at **$5.99/month**. This records what to build, what to change about the original plan, and why.

---

## 1. How comparable products do it

| Product | Model | Takeaway for us |
|---|---|---|
| **Ava** (live captions for deaf/HoH) | Free tier with limited hours/month; paid for more | Closest competitor. **Meters hours, doesn't wall features.** |
| **Otter.ai** | Free 300 min/mo; paid raises the cap | Same shape: transcription is metered because it *costs* per minute |
| **Duolingo / Spotify** | Free tier is genuinely useful, not crippled | A usable free tier drives the word-of-mouth that sells the paid one |
| **Superhuman, Notion** | **Reverse trial** — full features for N days automatically, then drop to free | No card up front. Shows value before asking for money |

**The pattern that matters:** every product whose costs scale with usage *meters usage*. Nobody in this category sells unlimited real-time transcription at a flat consumer price.

---

## 2. The number that should shape the plan

```
$5.99/mo  →  Stripe fee $0.47  →  net $5.52
Break-even on captions alone (AssemblyAI $0.15/hr): 37 hours/subscriber/month
```

Add Google translation, the LLM cultural pass, and ElevenLabs read-aloud (~870 chars/min), and the real ceiling is well under 37 hours.

**So a flat "unlimited $5.99" is a margin risk, not a plan.** One heavy user costs more than they pay, and there is no upper bound. Every comparable product solved this with caps — we should too, from day one, because retrofitting a limit onto existing subscribers is far worse than launching with one.

The cost tracking already exists (`LiveCaptions` computes `est_cost_usd` per session). It just isn't enforced anywhere.

---

## 3. Recommended tiers

| | **Free** | **Paid — $5.99/mo** |
|---|---|---|
| Captions | ✅ Unlimited-feeling cap (e.g. 5 hrs/mo) | ✅ Higher cap (e.g. 40 hrs/mo) |
| Speaker names (voice profiles) | ❌ "Speaker 1" | ✅ Enrolled people appear by name |
| Translate | ❌ | ✅ |
| Explain a term | ❌ | ✅ |
| Recorded voices (cloning) | ❌ | ✅ (needs paid ElevenLabs) |
| Read-aloud + voice shaping | ✅ Browser voices | ✅ Cloud voices |

### Four changes from the original plan

**1. Keep captions free — this instinct is right.** It's the accessibility core. Gating it would be both bad for adoption and hard to defend for a product built for deaf and HoH users. It's also the best possible funnel: free captions that say "Speaker 1" sell paid captions that say "Mom."

**2. One trial, not per-feature trials.** Two independent 3-day clocks for Translate and Explain is confusing to explain and awkward to build. Use **one trial of the whole paid plan**.

**3. Make it 7 days, not 3.** This is an occasional-use tool — someone might install it Monday and not have a conversation that needs translation until the weekend. A 3-day trial can easily contain **zero** real use, which converts nobody and teaches you nothing.

**4. Add usage caps.** See §2. Cap both tiers, show remaining usage in Settings, and write honest copy when it's reached.

### On "how it sounds is free"

Correct as stated, and worth keeping: **voice *shaping* is free** (pitch, rate, volume, pauses cost nothing — they run in the browser). What's paid is *whose* voice: enrolled speaker profiles and recorded/cloned voices.

---

## 4. Trial design

**Reverse trial, no card required.** On signup, grant 7 days of Paid automatically. When it lapses, drop to Free — nothing is deleted, features just lock.

- Higher signup rate than a card-gated trial, and for an accessibility product asking for a card before any value is shown is poor form
- Stripe supports card-required trials via `trial_period_days`; a no-card reverse trial is simply an entitlement in our own DB with an expiry
- **Cancel anytime** must be one click, and should route to Stripe's hosted Customer Portal rather than a page we build

---

## 5. Stripe test credentials

**Use a Sandbox** (Stripe's newer isolated test environment; each has its own `acct_...` id) or the classic **Test mode** toggle. Both give fake money and identical APIs.

1. **Secret key** — Dashboard → *Developers → API keys* → `sk_test_...`
2. **Webhook secret** — two ways:
   ```bash
   # local development (prints whsec_... and forwards events)
   stripe listen --forward-to localhost:8000/stripe/webhook
   ```
   Deployed: *Developers → Webhooks* → add endpoint → reveal signing secret.
3. **Price** — create a $5.99/month recurring Price; store the `price_...` id in env, never in code.

```bash
# .env
STRIPE_SECRET_KEY=sk_test_...
STRIPE_WEBHOOK_SECRET=whsec_...
STRIPE_PRICE_BASIC=price_...            # $7.99/month recurring
STRIPE_PRICE_PRO=price_...              # $14.99/month recurring
STRIPE_COUPON_PRO_FIRST_MONTH=promo_... # optional: 20% off, duration=once
NEXT_PUBLIC_STRIPE_PUBLISHABLE_KEY=pk_test_...
```

### Test cards

Any future expiry, any CVC, any postcode.

| Card | Result |
|---|---|
| `4242 4242 4242 4242` | Succeeds |
| `4000 0025 0000 3155` | Requires 3D Secure — **test this one**, it's common in the EU/UK |
| `4000 0000 0000 9995` | Declined, insufficient funds |
| `4000 0000 0000 0341` | Attaches but fails on later charges — tests failed renewals |

⚠️ Never let a `sk_test_` key reach production, or a `sk_live_` key reach a dev machine. Different Stripe accounts entirely.

---

## 6. Architecture

**Entitlements live in our database, never in the client.**

```
Checkout → Stripe → webhook → subscriptions table → backend reads entitlement
```

- New table `subscriptions`: `user_id`, `stripe_customer_id`, `stripe_subscription_id`, `status`, `current_period_end`, `trial_ends_at`. Owner-only RLS, same as every other table.
- **The webhook is the source of truth**, not the checkout redirect. A user can close the tab before redirecting; the webhook still fires.
- **Verify the webhook signature** with `STRIPE_WEBHOOK_SECRET` on every request. Unsigned webhooks are an open door to free subscriptions.
- **Make handlers idempotent** — Stripe retries, and events can arrive out of order.
- Gate on the **backend** (`/translate`, `/genz`, `/profiles`, `/tts/custom-voices`). A frontend-only gate is a suggestion, not a limit.
- **Use Stripe's Customer Portal** for payment method, invoices, and cancellation. Don't build billing UI — it's weeks of work and PCI surface for no differentiation.

---

## 7. Settings / profile page

`/settings` already holds voice profiles and read-aloud. Add:

- **Account** — name, email, password. If the Clerk migration completes, use Clerk's prebuilt `<UserProfile />` rather than writing these; they are its job, not ours.
- **Subscription** — current plan, trial days remaining, usage this month against the cap, and a **Manage billing** button linking to the Stripe Customer Portal.

---

## 8. Build order

1. `subscriptions` table + RLS migration
2. Stripe Checkout session endpoint + webhook handler (signature-verified, idempotent)
3. Entitlement check in the backend; gate Translate, Explain, voice profiles, cloning
4. Usage metering + caps (the numbers already exist in `LiveCaptions`)
5. Settings → Subscription section + Customer Portal link
6. Reverse trial: grant 7 days on signup
7. Paywall UI on locked features — explain what it unlocks, never a dead end

**Do 1–3 first and test with `4242 4242 4242 4242`.** Everything after that is refinement.

---

## 9. Two things to decide before building

- **iOS changes the economics.** Apple takes 15–30% on in-app digital subscriptions. Since the 2025 *Epic* ruling US apps can link out to web checkout, but this is jurisdiction-dependent. If iOS is coming, plan to use **RevenueCat** for cross-platform entitlements rather than wiring Stripe twice.
- **Sales tax / VAT.** Stripe is not a merchant of record — you are liable for registration where you sell. **Paddle** (or Stripe Tax) handles this. For a solo founder selling internationally, an MoR is worth the higher fee.

---

## 10. Usage caps — what to meter, and at what level

### The finding that decides the design

Cost per hour of conversation, by what is switched on:

| mode | $/hour | hours on $5.52 net |
|---|---|---|
| captions only | **0.15** | 36.8 |
| captions + translation | **1.40** | 3.9 |
| captions + translation + cloud read-aloud | **7.15** | 0.8 |

**The three modes differ by 48×.** So a single "hours per month" cap is the wrong
instrument: sized for plain captions it lets read-aloud run at a $137/month loss,
and sized for read-aloud it makes captions useless. Meter the *expensive modes*,
not "usage".

Modelled against real personas:

| persona | cost | margin |
|---|---|---|
| 8h captions, 1h translated | $2.60 | +$2.92 |
| 20h captions, 3h translated | $7.21 | −$1.69 |
| 20h all spoken | $142.92 | **−$137.40** |

### Recommendation

**1. Keep cloud TTS off the live-caption path.** This is the highest-leverage
decision available and it costs nothing to make: browser voices are free,
offline, and already implemented. Reserve ElevenLabs for on-demand playback of a
*single* translation the user explicitly asked to hear. That removes the 48×
tail almost entirely.

**2. Meter two things, show one.** Caption minutes is the headline number people
understand; translated minutes is the real constraint. Display "4.2 / 20 hours"
prominently and translated minutes underneath.

**3. Caps that keep the tail profitable at $5.99:**

| | Free | Paid — $5.99 |
|---|---|---|
| Captions | 2 hrs/mo | 20 hrs/mo |
| Translated captions | — | 2 hrs/mo |
| Explain a term | — | 100 lookups/mo |
| Read-aloud | Browser voices, unlimited | Browser unlimited; cloud on-demand only |

**4. $5.99 may be underpriced if translation is the core value.** At that price
the translated allowance has to stay near 2 hours to hold a margin. At $9.99 it
comfortably reaches 4–5 hours. Decide which product you are selling before
setting the cap — the price follows the feature, not the other way round.

**5. Before raising the price, look at the biggest cost lever.** Of the $1.40 per
translated hour, **$1.04 is Google Translate at $20/M characters** — three
quarters of it, and far more than the LLM pass ($0.21). Continuous speech
translation is simply expensive at that rate. Harder caching, or a cheaper
provider for the fast lane, moves the economics more than any pricing change.

### How to implement it

- **One `usage` table**, aggregated per user per billing period: caption seconds,
  translated characters, explain lookups. Aggregate rather than event-log — this
  is read on every gated request and must be a single indexed lookup.
- **Record where the spend happens**: caption seconds when the websocket closes,
  translated characters per `/translate` call, lookups per `/genz/explain`. The
  numbers already exist — `LiveCaptions` computes `est_cost_usd` today and throws
  it away.
- **Reset on the Stripe billing period**, not the calendar month. `current_period_end`
  is already stored; aligning to it means the allowance renews when the payment
  does, which is what users expect and what avoids a mid-month argument.
- **Enforce in the same dependency as the paywall.** Entitlement and allowance are
  the same question — "may this request proceed?" — and splitting them creates
  two places to forget.

### The rule that matters most for this product

**Never cut off captions mid-conversation.** A hard stop is normal for a music
app; here the user may be in a medical appointment, and captions are how they are
participating in it. So:

- Warn at 80%, in Settings and once in-session
- When the limit is reached, **let the current session finish** — block the next
  *start*, not the sentence in progress
- Say plainly what ran out, when it resets, and what upgrading changes
- Keep a small emergency reserve past the cap rather than a cliff

A cap that fires mid-appointment converts nobody and does real harm. One that
warns early and lands softly is just a plan.



---

## 11. What shipped — three tiers (2026-08-08)

The two-tier plan above was superseded before launch. Shipped shape:

| | **Free** | **Basic — $7.99** | **Pro — $14.99** |
|---|---|---|---|
| Captions | 3 hrs/mo | 12 hrs/mo | 36 hrs/mo |
| Translated captions | — | 3 hrs/mo | 6 hrs/mo |
| Speaker names | 1 person | Up to 4 | Up to 4 |
| Explain a term | 5 lookups | 100/mo | Unlimited |
| Read-aloud | Browser voices | Browser voices | Cloud voices, 30 min/mo |
| Voice cloning | — | — | ✅ |

Pro carries **20% off its first month** as a launch incentive — a Stripe coupon
(`duration=once`) rather than a second Price, so the renewal figure stays honest
in the checkout summary and on the invoice. It is applied only to Pro, and only
advertised when `STRIPE_COUPON_PRO_FIRST_MONTH` is actually set.

**The trial picks its plan up front.** Stripe needs to know what to charge when a
trial converts, so checkout takes `{plan: "basic"|"pro"}` and the seven free days
run on that plan. Nothing is lost by that ordering: the card isn't charged for a
week, the plan can be switched in the Customer Portal, and cancelling during the
trial costs nothing.

### Where the numbers live

`backend/app/plans.py` is the **only** place a limit is written down. The API
sends limits and usage together on `/billing/subscription`, so Settings renders
bars from the same figures the backend enforces — a hard-coded "3 hrs" in the UI
is a support ticket waiting for the day a cap changes.

### Units, and why they differ from what's displayed

| metric | stored as | displayed as |
|---|---|---|
| captions | seconds | hours |
| translated | characters | hours (`CHARS_PER_HOUR` = 52,200) |
| explain | lookups | lookups |
| cloud read-aloud | seconds | minutes |

Translation is metered in characters because that is what providers bill, so the
cap tracks cost rather than wall-clock. Two consequences, both deliberate:

- **A cached phrase costs nothing.** `characters` is 0 on a cache hit, so a
  conversation that repeats itself doesn't draw down the allowance.
- **The cultural pass is weighted at `ENHANCED_COST_RATIO` (0.2).** Live captions
  send every finalised line through both lanes; metering each at full character
  weight would charge twice for one sentence and quietly halve the advertised
  allowance.

### Enforcement

One dependency answers both halves of "may this request proceed?" —
`requires(metric)` in `app/routes/billing.py`. There is deliberately no bare
"is this user paid?" helper: a generic one would look like it checked allowances
while checking only entitlement.

Refusals are `402` with a **structured** body, never a bare string, so the client
can tell the two no's apart without parsing English:

```json
{"reason": "limit_reached", "metric": "translated", "resetsAt": "…",
 "upgradeTo": "pro", "limit": 156600, "message": "…"}
```

### The soft landing, in code

- The caption allowance is read **once, at websocket connect**, and never again.
  There is no mid-session re-check that could cut someone off mid-sentence.
- Past 80% the socket sends a `usage` frame *and starts the session anyway*.
- At the limit it refuses the **next start** with what ran out, when it returns,
  and what upgrading changes — and the UI renders that as a plan notice with one
  upgrade button, not a red error.
- Every metering failure **fails open**. If Supabase is unreachable the session
  proceeds unmetered and logs loudly, because a monitoring blip must never be the
  reason someone can't follow a medical appointment.

### Storage

Migration `0006_usage_and_tiers.sql`: a `tier` column on `subscriptions`, and one
aggregated `usage` row per user per billing period (aggregated, not an event log
— it is read on every gated request).

Writes go through a **security-definer, increment-only RPC** called with the
user's own token, not the service role. A user can add to their own meter and
read their own row and nothing else; there is no `update` or `delete` policy on
`usage` at all, so zeroing your own meter is not expressible. This keeps the
service-role allowlist at exactly one table (`subscriptions`).

The period is the **Stripe billing anniversary**, never the 1st. Free users have
no Stripe period, so they anchor on their signup day — still an anniversary, and
it means someone who signs up on the 28th doesn't get a three-day month.
