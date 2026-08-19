# PLAN — ListenUp as a mobile app (Capacitor → App Store / Play Store)

Current state: a Next.js web app, built and tested for desktop browsers.
Goal: an installable app, submitted to both stores, with the product intact.

Decisions already made: **Capacitor** (one codebase, native shell) and **fix
the phone experience before packaging it**. A polished install of a broken
phone experience is worse than no install.

---

## Read this first: what "100% identical" can and cannot mean

The request was "every feature and functionality, 100% the same — the same
speed, accuracy, efficiency, consistency." Most of that is achievable and some
of it will get *better*. But three things cannot be identical, and a plan that
pretends otherwise fails at submission instead of failing here.

| | web today | app | why |
|---|---|---|---|
| STT accuracy | AssemblyAI | **identical** | same backend, same provider, same audio |
| Speaker ID | ECAPA on the server | **identical** | runs server-side; the phone only sends PCM |
| Translation / slang | Google + OpenRouter | **identical** | same endpoints |
| Caption latency | mic → socket → caption | **±50–150 ms**, network-dependent | cellular adds a little; a native socket removes some browser overhead |
| Background operation | dies when tab is hidden | **better** | native background-audio entitlement |
| Read-aloud voices | desktop OS voices | **different set** | iOS ships different `speechSynthesis` voices than macOS/Chrome |
| Buying a subscription | Stripe Checkout | **must change on iOS** | App Store Guideline 3.1.1 |

Two of those are hard constraints from Apple and one is physics. Everything
else is engineering, and this plan covers it.

**The honest summary: feature parity is achievable; byte-identical behaviour is
not, and in two places the app should deliberately differ because it can do
better.**

---

## "Swift, or can I do it in VS Code?"

**~95% of this is TypeScript in VS Code.** You will likely write **zero lines
of Swift** for v1.

| tool | what it is for | can you avoid it |
|---|---|---|
| **VS Code** | all app code, Capacitor config, plugins wiring | — this is where you live |
| **Xcode** | building, signing, capabilities, simulator, submission | **No.** Required on macOS for any iOS build. You mostly click through it. |
| **Android Studio** | Android SDK, emulator, signing | **No**, but you can build from CLI once installed |
| **Swift / Kotlin** | only if you need a *custom native plugin* | **Yes, avoid** — see Task 3.4 |

You are on macOS, which is the requirement for iOS builds. The realistic split
is: ~2 days total inside Xcode/Android Studio across the whole project, and
everything else in VS Code.

**You would only reach for Swift if** the WebView audio path (Task 1.2) cannot
be made to work — in which case a native microphone plugin becomes necessary.
Task 1.2 exists to find that out in week one rather than week six.

---

## Where this starts from — measured, not assumed

Verified against the codebase on 2026-08-18:

| fact | value | why it matters |
|---|---|---|
| Route handlers (`app/**/route.ts`) | **0** | nothing server-side to port |
| Server actions (`"use server"`) | **0** | " |
| `cookies()` / `headers()` calls | **0** | no page depends on a request |
| `page.tsx` files | 10, all thin wrappers | each renders a client component |
| `"use client"` components | 30 | the product is already client-side |
| Supabase clients | `client.ts`, `proxy.ts` | **no** `server.ts` — auth is browser-side already |
| Server-only dependencies | `proxy.ts` + `next.config.ts` `redirects()` | **the entire porting surface** |
| Backend | separate FastAPI service | unaffected; the app is another client |

**This is the best possible starting position for a Capacitor migration.** The
app is a client-side SPA that happens to be served by Next. Almost nothing has
to be rewritten — it has to be re-*configured*.

---

## The three hard problems

These change the plan, so they come before the tasks.

### 1. Apple will not let you charge through Stripe (business-critical)

`app/routes/billing.py` creates Stripe Checkout sessions with web
`success_url`s. Digital subscriptions consumed inside an iOS app must use
**In-App Purchase** (Guideline 3.1.1). Apple takes 30%, or 15% under the Small
Business Program (<$1M/yr, which is you).

Against the cost model in `SUBSCRIPTION.md`:

```
Basic $7.99, at full utilisation
  COGS (12h captions @ $0.15 + 3h translated @ $1.25)      $5.55

  web (Stripe 2.9% + $0.30)     net $7.46  →  margin  $1.91   26%
  iOS IAP at 15%                net $6.79  →  margin  $1.24   18%
  iOS IAP at 30%                net $5.59  →  margin  $0.04    0.7%
```

**Pro is already negative at full utilisation before Apple takes anything.**

Options, in the order I would consider them:

1. **Cut COGS first.** `SUBSCRIPTION.md` §5 already identifies the lever:
   $1.04 of the $1.25 translated hour is Google Translate, and the LLM pass
   *overwrites* that text seconds later. Running Google only when the LLM is
   slow or fails takes Basic's COGS to ~$3.20 and margin to ~57% (web) /
   ~47% (IAP 15%). **Do this regardless of the app.**
2. **Price differently on iOS.** Common and permitted: a higher in-app price
   that absorbs the commission.
3. **Web-only purchase.** Legal, but you may not link to it from inside the
   app in most jurisdictions, and the funnel is dreadful.
4. **Launch the app free-tier-only** and defer paid tiers to a second release.
   Given you have zero validated users, this is the fastest path to the store
   and removes the whole problem from v1.

**Recommendation: (1) + (4).** Fix the margin leak, ship v1 with the free tier
and no purchase surface, and add IAP once you know people use it.

### 2. iOS may refuse your audio pipeline

`lib/usePcmRecorder.ts:38` does `new AudioContext({ sampleRate: 16000 })`.
iOS Safari and WKWebView have a long history of ignoring this and giving you
the hardware rate (44,100 or 48,000 Hz). The whole pipeline — the worklet, the
socket frames, AssemblyAI's declared rate, `embedder.embed(pcm, 16000)` —
assumes 16 kHz. If the context comes back at 48 kHz, **captions will be
garbage and speaker ID will be meaningless**, and it will look like a model
problem rather than a sample-rate problem.

This is the single highest-risk unknown and Task 1.2 resolves it first.

### 3. Static export removes your auth guard

`proxy.ts` guards `/dashboard`, `/captions`, `/translate`, `/explain`,
`/settings` server-side. Under `output: "export"` there is no server, so the
guard does not run. Route protection has to move client-side.

This is not a security regression — the **backend** already enforces auth on
every gated endpoint via `requires(metric)`, and RLS enforces data access. The
middleware was always a UX redirect, not a security boundary. But it has to be
replaced or the app will render tool pages to signed-out users.

---

## Invariants — true at every step

1. **The backend does not change.** FastAPI stays as-is; the app is one more
   client. Any change needed for the app is a bug in the app.
2. **The web build keeps working.** Both targets ship from one codebase; the
   web build keeps middleware and redirects, the app build does not.
3. **No feature is dropped to make packaging easier.** If something cannot
   work in the WebView, it gets a native plugin or an explicit, stated
   degradation — never a silent one.
4. **Every gate is verified on a real device.** Simulators do not have real
   microphones, real Bluetooth audio, or real network conditions. iOS Simulator
   in particular fakes audio in ways that hide exactly the bugs in Task 1.2.
5. **`make check` and `make e2e` stay green throughout.**

---

## Phase 0 — Production infrastructure (this does not exist yet)

**Verified on 2026-08-18: the backend has never been deployed.** There is no
`infra/` directory (CLAUDE.md's repo layout claims one), no `Dockerfile`, no
`Procfile`, no Railway/Render/Fly config. There is no privacy policy page and
no terms page. The product runs on `localhost` only.

This is a larger gap than the app packaging, and every phase below depends on
it. An app whose backend is your laptop cannot be reviewed, let alone shipped.

### Task 0.1 — Deploy the backend — ❌ BLOCKED 2026-08-18

**Container files written and committed; nothing about them is verified, because
Docker is not installed on this machine and the deploy needs your accounts.**

Delivered: `backend/Dockerfile` (CPU-only torch wheels — the default PyPI torch
pulls the whole CUDA runtime, over a gigabyte this app can never use — with
dependency layers before `app/` so a code push reuses them, and the ECAPA
weights baked in at build), `backend/.dockerignore`, `backend/railway.json`,
and `infra/README.md` as the deploy checklist.

One thing was buildable here and was built test-first: **`app/preflight.py`
refuses to start a production deploy that is missing configuration.** Every
provider in this app falls back to a mock by constraint (§6), so a deploy
without `ASSEMBLYAI_API_KEY` previously started cleanly, reported healthy, and
served the first real user a fixture conversation — the one misconfiguration
that looks perfectly well. 8 tests, three mutations confirmed to fail (mocks not
reported, credentials not required, warnings promoted to errors). 520 backend
tests.

**Blocked on you, and none of it is code:**
1. Railway project, root directory set to `backend/`, **≥2 GB memory** (torch +
   model is 1–1.5 GB resident; 512 MB OOMs as a restart loop).
2. Upstash Redis → `REDIS_URL`.
3. The env vars in `infra/README.md` §3.
4. **Google Translation auth.** Local dev uses `gcloud` ADC because the org
   policy blocks service-account key files (decisions log 2026-07-17). ADC does
   not exist in a container. This is the one credential that cannot be pasted
   into Railway, and it should be resolved before the first deploy.

**Update 2026-08-18 — the image now builds and runs, and getting there cost
four real defects.** Docker was installed (Colima; the OrbStack cask is broken
on this Homebrew) and the container was built for `linux/amd64`, the platform
Railway uses. Verified:

| check | result |
|---|---|
| builds | ✅ `linux/amd64`, **478 MB** — small because the CPU-only wheels worked |
| starts and serves `/health` | ✅ **6 s** |
| ECAPA loads **offline, as the runtime user** | ✅ `--network none` |
| preflight refuses a broken production config | ✅ exits 3, names all 8 problems |
| a code change reuses the torch layer | ✅ all layers `CACHED` |

**The four defects, none of which any other loop could see:**
1. `torchaudio>=2.13` — **a version that does not exist**; the ceiling is 2.11.
   Unsatisfiable on every platform.
2. `stripe` imported at module scope and **declared in no requirements file**.
   The container started and died. CI would fail collection the same way and
   has evidently never run on this code.
3. Shell-form `CMD` left the shell as PID 1, so **`SIGTERM` never reached
   uvicorn** — a redeploy would hard-kill live caption sessions rather than
   drain them, in an app whose central promise is never to cut one.
4. **The model bake looked like it worked and did not.** SpeechBrain writes
   *symlinks* into the HuggingFace cache rather than copying weights, so
   `savedir` held 24 KB of links into `/root` that the non-root runtime user
   could not read. With `SPEAKER_ID_SERVICE=real` — which preflight requires in
   production — `lifespan` calls `load()` at startup, so **Railway would have
   crash-looped**. Only loading the model as that user with the network cut
   exposed it; every cheap check said yes.

Two guards were added and mutation-checked: `tests/test_requirements.py` (a pin
must name a version that exists) and `tests/test_dependencies.py` (every import
must be declared, AST-walked, with a guard on the walk itself).

**Gate remaining — all of it yours:** `wss://` session from a phone on cellular
produces captions; `/health` green on Railway.

### Original specification

**Do:**
- **Dockerfile.** `requirements-ml.txt` (torch, torchaudio, speechbrain) is
  already split from the base requirements — keep that split and install ML
  deps in their own layer so a code change does not re-download torch.
- **Bake the ECAPA weights into the image.** If the model downloads from
  HuggingFace on first use, your first user after every deploy waits for it,
  and an upstream outage becomes your outage.
- **Size the instance for torch.** Expect roughly 1–1.5 GB RSS with the model
  loaded. This does not fit a hobby tier. Budget accordingly — this is a real
  monthly cost that belongs in the unit economics.
- **Host must support long-lived WebSockets** (Railway, Render, Fly all do).
  Serverless platforms do not; do not put this on Vercel functions.
- **Redis** for the translation and TTS caches — the cache is what makes
  repeated phrases free, so without it your COGS goes *up*.
- Health check already exists at `/health`.

**Gate:** `wss://` transcription session from a phone on cellular produces
captions; `/health` green; a redeploy does not re-download the model.

### Task 0.2 — CORS will break the app on day one — ✅ DONE 2026-08-18

`app/cors.py` adds both Capacitor WebView origins to the allow-list; 13 tests,
five mutations confirmed to fail. **533 backend tests.**

The two origins are written as constants, not expected in an environment
variable: nobody chooses `capacitor://localhost` and no deploy changes it, so
requiring an operator to know it would just be a way to get it wrong.
`EXTRA_CORS_ORIGINS` covers what *is* a deployment choice — preview hostnames.
A `*` anywhere raises at startup rather than being passed through: it is the
obvious way to make a stubborn CORS error go away, this API carries bearer
tokens and biometric data, and Starlette silently drops credentials for a
wildcard, so the "fix" would appear to work while breaking authentication in a
way nobody would connect back to CORS.

**Two findings.** The WebSocket needed no change and could not have: CORS
middleware does not apply to WebSockets — browsers send no preflight for them —
so `/ws/transcribe` already accepted any origin. That is not an exposure here,
because the socket authenticates on a token in its **first message** rather than
on a cookie, so a hostile page cannot open a session it has no token for. It is
pinned by a test that says so.

*And a defect in my own tests, found by mutation:* the integration checks
parametrised over `CAPACITOR_ORIGINS`, so emptying that constant produced zero
cases and they **skipped instead of failing** ("1 failed, 7 passed, 2 skipped").
The origins are now written out literally, with one test asserting the literals
still match the constant — the same mutation now fails six tests and skips none.

**Deferred, not blocked:** the gate's "from a real device build" clause needs a
build, which Phase 3 creates. Carried into Task 3.1's gate rather than left
here.

### Original specification

`app/main.py:57` sets `allow_origins=[FRONTEND_ORIGIN]` — one web origin.

**A Capacitor WebView does not use your web origin.** It is
`capacitor://localhost` on iOS and `https://localhost` on Android. Every single
API call from the app will fail CORS preflight until those are allowed.

**Do:** allow the two Capacitor origins alongside the web origin, from config
rather than hard-coded. Do **not** reach for `allow_origins=["*"]` — this API
carries bearer tokens and biometric data.

**Gate:** an authenticated request and a WebSocket upgrade both succeed from a
real device build, not just from the simulator.

### Task 0.3 — Legal pages — ❌ BLOCKED 2026-08-18

**Both pages written, linked and browser-verified. Blocked on legal review,
which is the part that actually matters here.**

`/privacy` and `/terms`, linked from the site footer (a new Legal column) and
from **Settings** — someone looking for how to withdraw a consent they gave is
already signed in, and sending them to the marketing site to find it would be
the wrong way round.

**The content is derived from the schema, not from a template.** Every claim was
checked against `db/migrations/` and the code: audio is streamed and never
written to disk; **transcripts are not stored at all** (six migrations, none of
them a conversation, so "opt-in transcripts" would have been a lie); a voice
profile is 192 numbers and cannot be played back; consent is recorded with the
consenting person's name, the exact wording and a timestamp; slang lookups are
logged with **no link to an account** (`slang_gap_log` has no user column).

Two clauses carry real weight and should not be softened without advice: the
requirement to have permission before enrolling somebody else's voice, and an
**emergency clause** — this is an accessibility tool, and a deaf user relying on
it in a safety-critical moment is a foreseeable use, so the terms say plainly
not to.

**Verified:** 56 browser checks green (up from 40) — both pages axe-clean in
both contrast modes, AA against the gradient measured from pixels, no overflow
at 390/834/1440, touch targets reachable.

**Blocked on you:**
1. **A lawyer must read the biometric section.** Voiceprints collected from
   third parties is the fact pattern BIPA suits are built on, and statutory
   damages are per violation. A source comment on each page says so.
2. `privacy@listenup.app` and `hello@listenup.app` must become deliverable
   addresses, or be replaced.
3. App Store Connect: the privacy policy URL, and Privacy Nutrition Labels that
   **declare biometric collection**.

### Original specification

Apple requires a privacy policy URL. Neither a privacy policy nor terms exists.

For most apps this is boilerplate. **It is not boilerplate for you.** You
process voiceprints, which are biometric identifiers under Illinois BIPA, GDPR
Article 9, and Quebec Law 25, and you collect them from **third parties** — the
user's mother, not the account holder. The policy has to state what is
collected, the legal basis, retention, deletion, and that consent comes from
the enrolled person.

The good news is the product already behaves correctly: consent is gated on the
enrolled person, `consent_text_version` is recorded, and export and delete
exist. The document has to describe what the code already does.

**Do:** privacy policy and terms as real pages on the web build, linked from
Settings and the store listing. **Have a lawyer read the biometric section.**
BIPA statutory damages are per-violation and this is exactly the fact pattern
plaintiffs' firms look for.

**Gate:** both pages live at stable URLs, linked in-app and in App Store
Connect; Apple's Privacy Nutrition Labels declare biometric collection.

### Task 0.4 — Monitoring and a spend circuit-breaker — ✅ DONE 2026-08-18

`app/spend.py` — a daily ceiling in dollars, in the units the app already
meters. 15 tests, **six mutations confirmed to fail**. 548 backend tests.

Unset means off: a default ceiling would be a number nobody chose silently
deciding when captions stop working, and for an accessibility tool that is not
a decision to make on someone's behalf. Preflight now warns when production
runs without one.

**It refuses the next start, never a live session** — the same trade
`CaptionSession` already makes for the per-user allowance, because a cap that
fires mid-sentence can fire in a medical appointment. The refusal is
`reason: "service_capacity"` with copy that says nothing is wrong with your
account, because the user may have hours of allowance left and be refused
anyway; wording borrowed from the per-user cap would be a lie they cannot act
on.

**It fails open.** Every failure inside the ledger is swallowed and an
unanswerable ledger reports "not over". An hour of unnoticed overspend is
recoverable; a deaf user unable to follow a conversation because a counter
broke is not.

**Found while building it: an anonymous caption session is completely
unmetered.** `open()` treats the token as optional, so a client that sends none
gets a real provider connection with no allowance check — per-user metering only
runs when `_who` exists. The ledger deliberately records **outside** that guard
so the global ceiling at least sees the spend, and a test pins it. *The
underlying hole is not closed and is not this task's scope* — see the log.

**Deliberately not done:** translation spend is *recorded* but never *refused*.
Live captions push every finished line through `/translate`, so refusing there
would strip translations out of a conversation in progress — the mid-session cut
this feature exists to avoid. The ceiling closes the loop by refusing the next
session instead.

**Sentry DSNs remain yours to set** (`SENTRY_DSN`, `NEXT_PUBLIC_SENTRY_DSN`);
the code is wired and alerts once per day rather than once per refusal.

### Original specification

Sentry is wired as an env-guarded no-op in both stacks — it needs real DSNs.

More importantly: **per-user metering exists, global spend control does not.**
Every user is capped by `requires(metric)`, but nothing stops 500 signups on a
good day from running an AssemblyAI bill you did not agree to. You cannot cap
this at the provider for streaming sessions.

**Do:** Sentry DSNs in both stacks. A daily global spend ceiling that degrades
to refusing *new* sessions (never cutting an active one — the soft-landing rule
already in `CaptionSession`) and alerts you. Watch the `perf span=` lines you
already emit.

**Gate:** a forced error appears in Sentry from both stacks; the global ceiling
is provably reachable in a test and refuses new sessions without killing live
ones.

### Task 0.5 — Accounts — ❌ BLOCKED 2026-08-18 (by choice)

**Deferred by you: the Apple Developer Program is your last step before
production.** Nothing here is code and nothing else in the plan depends on it
until Phase 5 — Phases 1–4 all run without a developer account. The one caution
worth repeating: enrolment takes 24–48 hours of pure waiting, so start it while
Phase 3 is in progress rather than after.

Bundle id `com.<you>.listenup` is still a placeholder in Task 3.1 and needs a
real value before `npx cap init`.

### Original specification

Apple Developer Program ($99/yr, ~24–48h). Google Play Console ($25 once).
Bundle id reserved. **Back up the Android keystore somewhere you will still
have it in five years** — losing it means never updating that listing again.

---

## Phase 1 — Make the phone experience correct (before any packaging)

### Task 1.1 — Fix the phone layout — ✅ DONE 2026-08-18

The transcript now fits the screen on every phone viewport in both
orientations. **62 browser checks** (up from 56), four mutations confirmed to
fail.

**What changed.** `SessionHeader` is extracted and shared by both transcripts,
with a `compact` mode that collapses while a session runs or is paused: the orb
drops from 64px to 32px, the heading goes `sr-only` (still in the
accessibility tree — a screen-reader user needs to know which tool this is; a
person reading their own conversation does not need 30px spent saying so), and
the setup controls move behind one `Session settings` disclosure. **Nothing is
removed**: the spoken-language picker is already `disabled` while listening, so
displaying it was spending height on something inert, and the rest stays one tap
away because a translation target is still worth changing mid-conversation.

That took the header from **189px to 96px**, and the chrome around the pane to a
measured **274px** on every phone viewport. `lib/paneHeight.ts` holds the two
heights both transcripts use, so the live pane is sized from what is left:
`clamp(6rem, calc(100dvh - 18rem), 34rem)`. `dvh` rather than `vh` because
mobile browser chrome grows and shrinks as you scroll and `vh` freezes at the
largest size. Safe-area insets added to the app shell.

**The 18rem was measured, not guessed** — a first guess of 20rem was wrong and
the fold check caught it: 47px past the fold in portrait, 81px in landscape.
The 6rem floor is what a 375px-tall landscape phone allows after the chrome;
the transcript is genuinely small there, which is the honest consequence of
captioning on a phone held sideways.

**How it is measured, given `/captions` is auth-gated.**
`components/design/LiveSessionSample.tsx` renders the **same** `SessionHeader`
and `ConversationPane`, at the same shared height constant, inside the same
shell spacing, and is placed first on `/design` so it sits under the same
`<Navbar />`. Composing the real components rather than describing them is what
keeps the measurement about the product.

**A real defect found on the way, and a bigger one in the check itself.**
Tightening the touch-target probe exposed `/login`'s inline `Register` button at
**54x20** — half the required height. Fixed with the pseudo-element pattern
`SpeakerName` already uses, so it stays inline in its sentence and still offers
a thumb 44px.

Worse: **the touch-target check had only ever inspected controls above the
fold.** `elementFromPoint` works on the visible viewport only, so everything
further down was silently skipped — on `/design` at 844px that was most of the
page, including the icon buttons the rule exists for. It read as a page-wide
check and was a first-screen one. Controls are now scrolled into view before
measuring, and the mutation that shrinks `IconButton` to 40x40 — which had
passed three times — now fails.

**Mutations:** live height reverted to the fixed clamp (3 fail) · `compact`
ignored (5 fail) · `IconButton` at 40x40 (1 fail) · the inline hit area removed
(1 fail).

### Original specification

**Known defect** (`CLAUDE.md`, 2026-08-14): on a 390×844 phone the caption
pane's bottom edge sits at 1010px — **166px below the fold** — so a phone user
must scroll before the "newest line never moves" guarantee takes over. Tablet
and desktop are clear. The recorded fix is "collapsing chrome while a session
is live, which is a design change."

**Do:**
- While a session is live, collapse the header, tagline, and setup controls to
  a single compact bar. The transcript is the product during a session;
  everything else is setup.
- Size the pane from the *visual viewport*, not `vh` — mobile browser chrome
  changes height as you scroll, and `dvh` alone still fights the keyboard.
- Respect safe-area insets (notch, home indicator) with `env(safe-area-inset-*)`.

**Gate:** the pane's bottom edge is above the fold at 390×844, 375×667
(iPhone SE), and 412×915 (Pixel), in both orientations, with a live session.
Extend `e2e/layout.spec.ts` with those viewports; it already measures exactly
this and will fail loudly if it regresses.

### Task 1.2 — Prove the audio path on real iOS and Android (HIGHEST RISK)

**Do:**
- Add a diagnostic that reports `AudioContext.sampleRate` actually granted,
  frames sent, and bytes/sec, visible in a debug panel.
- Open the deployed web app in **Safari on a real iPhone** and read it.
- If the rate is not 16,000: resample **inside `public/pcm-worklet.js`** rather
  than changing the wire format. 16 kHz is assumed end-to-end — by the STT
  request, by `audio_seconds()`, and by `embedder.embed(pcm, 16000)` — and
  changing that contract ripples into speaker ID. Linear interpolation is
  adequate for 48k→16k speech; do not add a DSP library for this.

**Gate:** on a real iPhone and a real Android phone, a 30-second recording
produces a transcript whose word error rate is within 2 points of the same
speech recorded on desktop. **If this cannot be achieved in the WebView, stop
and reconsider** — that is the one scenario where a native audio plugin (and
therefore Swift/Kotlin) becomes necessary, and it changes the estimate.

### Task 1.3 — Revisit the microphone constraints (may improve the product)

`usePcmRecorder.ts:27` requests `echoCancellation: true, noiseSuppression: true`.
Both are tuned for **one near-field speaker on a phone call**. They attenuate
far-field voices and distort exactly the spectral detail ECAPA uses to tell
people apart — and your use case is a table of people at different distances.

This may be contributing to the noise-robustness failure already measured
(`--noise 0.5`: two speakers merge, enrolled naming → 0.00).

**Do:** run `scripts/eval_speaker_id.py` against recordings captured with each
combination — both on, both off, AEC only — from a phone on a table with 3
people. Pick by measurement.

**Gate:** a recorded number for each combination, and the constraint set chosen
on evidence. If "both off" wins, that is a product improvement the web app
gets too.

### Task 1.4 — Touch and gesture pass

**Do:** run the touch-target and overflow checks (already built) across every
tool page at phone widths. They currently only cover public pages because the
tool pages are auth-gated — add a signed-in Playwright fixture (a throwaway
Supabase test user in `E2E_EMAIL`/`E2E_PASSWORD`) so the pages that matter get
covered. Add `touch-action: manipulation` to controls to kill the 300ms delay,
and verify no gesture conflicts with the transcript's scroll container.

**Gate:** `make e2e` green with the signed-in fixture, at 390/412/375 widths.

---

## Phase 2 — Static export

### Task 2.1 — Two build modes from one codebase

**Do:** make the export target conditional so the web deployment is unchanged.

```ts
// next.config.ts
const isApp = process.env.BUILD_TARGET === "app";

const nextConfig: NextConfig = {
  ...(isApp && { output: "export", images: { unoptimized: true } }),
  // `redirects()` is not supported under `output: "export"`, and is not needed
  // there: the redirects exist so old *web* bookmarks keep working, and an app
  // bundle has no legacy URLs. The web build keeps them.
  ...(!isApp && { async redirects() { /* unchanged */ } }),
};
```

**Gate:** `BUILD_TARGET=app npm run build` produces `out/` with no server
runtime; `npm run build` still produces the current web output and `make e2e`
still passes against it.

### Task 2.2 — Move the route guard client-side

**Do:** an `<AuthGuard>` client component wrapping the `(app)` layout: read the
Supabase session client-side, render a skeleton while resolving, redirect to
`/login?redirect=…` when absent. Keep `proxy.ts` for the web build.

Note in the code *why* this is not a downgrade: the backend enforces auth on
every gated endpoint (`requires(metric)`) and RLS enforces data access. The
middleware was a UX redirect, never the security boundary.

**Gate:** signed out, every tool route redirects to `/login` with no flash of
tool content; signed in, no redirect; a hard refresh mid-session does not bounce
you to login (the common failure — resolve the session before deciding).

### Task 2.3 — Auth deep links

`AuthForm.tsx` calls `signUp` with no `emailRedirectTo`, and email confirmation
is **on**. In a browser the link returns to the site. From an app, it opens a
browser that has no way back into the app.

**Do:** register a custom scheme (`listenup://`) and an Associated Domain
(universal links), pass `emailRedirectTo` pointing at it, and handle the
callback with Capacitor's `App.addListener("appUrlOpen")`.

**Gate:** on a real device, sign up → receive email → tap link → land back in
the app, signed in. Also verify password reset.

---

## Phase 3 — The Capacitor shell

### Task 3.1 — Install and configure

```bash
npm i @capacitor/core @capacitor/cli
npx cap init ListenUp com.<you>.listenup --web-dir=out
npm i @capacitor/ios @capacitor/android
BUILD_TARGET=app npm run build && npx cap add ios && npx cap add android
```

`capacitor.config.ts`: `webDir: "out"`, `server.androidScheme: "https"` (so the
WebView origin is a secure context — **`getUserMedia` requires one**).

**Do not** set `server.url` to your live site. It makes the app a remote
webview: offline breaks, updates become invisible to review, and it invites a
Guideline 4.2 rejection.

**Gate:** the app launches on both simulators and renders the marketing page.
**Plus, carried from Task 0.2:** on a real device build, an authenticated API
call and a WebSocket upgrade both succeed. The allow-list is unit-tested, but
only a device proves the WebView sends the origin we think it does.

### Task 3.2 — Point the app at the production backend

`lib/api.ts:6` falls back to `http://localhost:8000`. On a device that is the
*device's* localhost, and iOS App Transport Security blocks cleartext HTTP
anyway.

**Do:** require `NEXT_PUBLIC_BACKEND_URL` at build time for `BUILD_TARGET=app`
and fail the build if it is missing or not `https://`. Same for the WebSocket
origin (`wss://`).

**Gate:** a build with the variable unset fails with a clear message rather
than shipping an app that silently cannot reach anything.

### Task 3.3 — Permissions and capabilities

- **iOS** `Info.plist`: `NSMicrophoneUsageDescription` — write a real sentence,
  Apple rejects placeholders. `UIBackgroundModes: [audio]` if captions should
  survive backgrounding.
- **Android** `AndroidManifest.xml`: `RECORD_AUDIO`, `INTERNET`, and a
  foreground service with `microphone` type for background capture.
- Request the microphone at the moment of first use with an in-app explanation
  *before* the system prompt. A denied permission is permanent until the user
  goes to Settings, and this app is useless without it.

**Gate:** on real devices — grant, deny, and deny-then-enable-in-Settings all
produce sensible, non-dead-end UI.

### Task 3.4 — Native plugins: add the minimum

Only add what the WebView cannot do:

| need | plugin | required for v1 |
|---|---|---|
| Keep the screen on during a session | `@capacitor-community/keep-awake` | **yes** — the screen going dark mid-conversation is a product failure |
| Status/nav bar colour, safe areas | `@capacitor/status-bar` | yes |
| Splash screen | `@capacitor/splash-screen` | yes |
| Deep links | `@capacitor/app` | yes (Task 2.3) |
| Background audio | native config, no plugin | if backgrounding is supported |
| Push notifications | `@capacitor/push-notifications` | **no** — nothing to notify about yet |
| Custom audio capture | **write in Swift/Kotlin** | **only if Task 1.2 failed** |

**Gate:** every added plugin is used. An unused plugin is a permission on your
store listing you cannot justify.

### Task 3.5 — Read-aloud on device

`speechSynthesis` works in WKWebView, but the **voice inventory differs** from
desktop. Your code already handles this honestly — `browser_hint` resolution,
`distinctVoices()` reporting, and an explicit refusal with a message when no
Korean voice exists rather than reading Hangul in an English voice.

**Do:** re-run that resolution on real iOS and Android and record what each
resolves to, the way macOS/Windows/Android/Chrome inventories were recorded
before. Extend `browser_hint` lists with the iOS names.

**Gate:** on a real iPhone and Android phone, en and ko each resolve to a
correct-language voice, or refuse with the existing message. **Never** silently
read Korean in an English voice.

---

## Phase 4 — What the app can do that the web cannot

Do these *after* parity. They are also your Guideline 4.2 defence: an app that
only renders a website gets rejected; one that uses the microphone in the
background, keeps the screen awake, and integrates with the OS does not.

- **Background captioning.** The conversation continues when you glance at
  another app. The web version cannot do this at all.
- **Screen stays awake during a session.**
- **Share sheet** for a finished transcript — which requires transcript
  persistence, which does not exist yet (six migrations, none of them a
  conversation). This is the highest-value missing feature for students and
  it is a separate piece of work with a consent design.
- **Bluetooth / external microphone selection.** A lapel mic on the table would
  do more for your noise problem than any algorithm.

---

## Phase 5 — Store submission

### Task 5.1 — Accounts and identity
Apple Developer Program ($99/yr, ~24–48h approval — **start this now**, it is
pure waiting). Google Play Console ($25 once). Bundle id, signing keys, and
**back the Android keystore up somewhere you will still have in five years** —
losing it means never updating that listing again.

### Task 5.2 — Listing
Screenshots at every required size, privacy policy URL (**required** — you
process biometric data, so it must actually describe that), support URL, and
Apple's Privacy Nutrition Labels.

**Declare the voiceprints.** Speaker profiles are biometric data under BIPA and
GDPR. Apple's privacy labels have a category for it. Under-declaring biometric
collection is both a rejection risk and a legal one, and your users are two
protected classes.

### Task 5.3 — The rejection risks, named in advance
| guideline | risk | mitigation |
|---|---|---|
| **3.1.1 IAP** | Stripe for subscriptions | see Hard Problem 1 — decide before submitting |
| **4.2 Minimum functionality** | "this is a website" | Phase 4 native capabilities; mic use is central |
| **5.1.1 Data collection** | biometric voice data | consent flow already built; declare it fully |
| **5.1.2 Third-party data** | enrolling *another person's* voice | your consent gate already requires the enrolled person's consent — surface it in the listing |
| **2.1 Completeness** | reviewer cannot sign in | provide a demo account with data in App Store Connect notes |

**Expect one rejection.** Budget two weeks for review cycles, not two days.

---

## Testing — how each claim gets verified

| what | how | exists? |
|---|---|---|
| Static export renders identically | `make e2e` against the `out/` build | ✅ built |
| Phone layout, overflow, touch targets | `e2e/layout.spec.ts` + phone viewports | ✅ built, needs viewports + signed-in fixture |
| Contrast on device-sized screens | `e2e/contrast.spec.ts` | ✅ built |
| Audio path correctness | real device, WER vs desktop baseline | ⬜ Task 1.2 |
| Speaker ID under phone-captured audio | `scripts/eval_speaker_id.py` on real recordings | ✅ harness exists, needs a phone corpus |
| Native flows (permissions, deep links, background) | **Maestro** — YAML flows, far lighter than Appium | ⬜ new |

**Do not** try to drive the native app with Playwright. It is a browser tool.
Maestro is the right size for a solo project.

---

## Sequencing and honest estimate

| phase | work | calendar (solo, part-time) |
|---|---|---|
| 0 | **Deploy the backend, CORS, legal pages, monitoring, accounts** | **1–2 weeks** |
| 1 | Phone layout, **audio path**, mic constraints, touch | **1–2 weeks** |
| 2 | Static export, client auth guard, deep links | 3–5 days |
| 3 | Capacitor shell, permissions, plugins, voices | 1 week |
| 4 | Background audio, keep-awake, (transcripts) | 3–5 days |
| 5 | Listing, privacy, submission, one rejection | **2 weeks elapsed** |

**Realistic: 7–9 weeks to a live listing**, of which ~2 weeks is waiting on
Apple. The single variable that could double it is Task 1.2 — if the WebView
cannot deliver clean 16 kHz audio, a native capture plugin adds 1–2 weeks and
your first Swift/Kotlin.

---

## Explicitly out of scope

- **React Native / native rewrite.** Months, for UX gains you cannot yet
  justify against zero validated users.
- **Offline captioning.** Requires an on-device STT model. Different product.
- **Apple Watch / widgets.** After the phone app has users.
- **iPad-specific layout.** Ships working via responsive layout; optimise later.

---

## The uncomfortable note

This plan is sound engineering and it will produce a working app. It does not
change the fact that `docs/DISCOVERY.md` is still an empty template.

Five to seven weeks of packaging work is five to seven weeks not spent finding
out whether anyone wants this. **The two are not in conflict** — Phase 0 is
pure waiting on Apple, and Phase 1 makes the *web* app usable on a phone, which
is exactly what you need in order to hand it to a deaf person at a dinner table
and watch.

So: start the Apple enrolment, do Phase 1, and **use the Phase 1 output to run
the ten interviews while Phases 2–5 proceed.** If the interviews say something
different, you will have lost nothing — Phase 1 is work the product needs
either way.
