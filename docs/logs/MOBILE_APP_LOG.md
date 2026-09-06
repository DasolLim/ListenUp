# MOBILE APP — implementation log

Companion to `../plans/PLAN_MOBILE_APP.md`. The plan says what to do; this says **what
actually happened**: what was verified, what was not, what broke, what is
waiting on a human, and every mutation run to prove a test could fail.

Appended to after each task. `../plans/PLAN_MOBILE_APP.md` carries a one-line verdict per
task; the detail lives here.

**Related:** `DEBUG_LOG.md` (unexpected errors across the whole project),
`CLAUDE.md` Decisions Log (why things are the way they are).

---

## Status at a glance

| task | status | commit | tests added | mutations |
|---|---|---|---|---|
| 0.1 Deploy the backend | ❌ **BLOCKED** | `e58ad71` | 8 | 3 ✅ |
| 0.2 CORS for Capacitor | ✅ **DONE** | `de77e8d` | 13 | 5 ✅ |
| 0.3 Legal pages | ❌ **BLOCKED** | `4b51d4a` | 16 browser | n/a |
| 0.4 Monitoring + spend ceiling | ✅ **DONE** | `fbfd253` | 15 | 6 ✅ |
| 0.5 Accounts | ❌ **BLOCKED** (your choice) | — | — | — |
| 1.1 Phone layout | ✅ **DONE** | `8b27e2f` | 6 browser | 4 ✅ |
| 1.2 Audio path (highest risk) | ❌ **BLOCKED** (device half) | `55477a4` | 18 + 2 browser | 4 ✅ |
| 1.3 Microphone constraints | ⬜ not started | | | |
| 1.4 Touch and gesture | ⬜ not started | | | |
| 2.1–2.3 Static export | ⬜ not started | | | |
| 3.1–3.5 Capacitor shell | ⬜ not started | | | |
| 4 Native capabilities | ⬜ not started | | | |
| 5 Store submission | ⬜ not started | | | |

**Suite state at the latest commit:** 553 backend tests · 115 frontend checks ·
64 browser checks · `make check` and `make e2e` both green.

---

## Waiting on you — nothing here is code

Ordered by what blocks the most.

1. **A lawyer must read the biometric section of `/privacy` and `/terms`.**
   Voiceprints collected from third parties — the account holder's mother, not
   the account holder — is the fact pattern BIPA suits are built on, and
   statutory damages are per violation. A comment at the top of each page says
   so. **This is now the single highest-consequence open item.**
2. **Google Translation auth for a container.** Local development uses `gcloud`
   Application Default Credentials because the org policy
   `iam.disableServiceAccountKeyCreation` blocks JSON key files (Decisions Log,
   2026-07-17). **ADC does not exist inside a container.** You need either a
   service-account key from a project without that policy, or Workload Identity
   Federation. It cannot be pasted into Railway, and meeting it at the end of a
   deploy will stop it dead.
3. **Railway project.** Root directory `backend/`, **≥2 GB memory** — torch plus
   the loaded ECAPA model is 1–1.5 GB resident, and a 512 MB instance OOMs as a
   restart loop rather than an error message.
4. **Pick a number for `DAILY_SPEND_CEILING_USD`.** Dollars you would be willing
   to lose to a bad day. Without it there is no limit on total provider spend —
   per-user allowances cap each account, not the total. Preflight warns, it does
   not guess.
5. **Upstash Redis** → `REDIS_URL`. Without it every cached phrase is billed
   again, raising COGS on already-thin margins.
6. **Two mailboxes that receive mail:** `privacy@listenup.app` and
   `hello@listenup.app` are published on the legal pages and do not exist.
7. **Sentry DSNs** — `SENTRY_DSN` (backend) and `NEXT_PUBLIC_SENTRY_DSN`
   (frontend). Both stacks are wired and inert without them.
8. **The remaining env vars** in `infra/README.md` §3.
9. **Docker**, if you want to verify the image before pushing — see *Tool setup*
   below. Optional; Railway builds server-side either way.
10. **A throwaway Supabase test user** (`E2E_EMAIL` / `E2E_PASSWORD`) so the
    browser suite can cover the five auth-gated tool pages. It covers public
    pages only today.
11. **A real iPhone and a real Android phone** for Task 1.2. The iOS Simulator
    fakes audio in exactly the way that would hide the bug.
12. **Apple Developer Program / Google Play Console** — deferred by you to the
    last step. Fine: nothing before Phase 5 needs it. Start it *during* Phase 3
    rather than after, because enrolment is 24–48 hours of pure waiting.
13. **A real bundle id** to replace `com.<you>.listenup` before `npx cap init`.

---

## Unverified — the risk register

Things that are written and committed but have **never been run**. Each is a
place a first deploy can fail.

| what | why unverified | how you find out |
|---|---|---|
| ~~`backend/Dockerfile` builds at all~~ | **✅ VERIFIED** — builds for `linux/amd64`, 475 MB | — |
| ~~CPU-only torch wheel index resolves~~ | **✅ VERIFIED** — and it is why the image is 475 MB rather than the 2–3 GB a CUDA torch would cost | — |
| ~~ECAPA weights bake into the image~~ | **✅ VERIFIED** — `ECAPA weights cached` in the build log; startup downloads nothing | — |
| ~~Layer caching (code push reuses torch)~~ | **✅ VERIFIED** — a code-only change leaves every pip and model layer `CACHED` | — |
| ~~Container `HEALTHCHECK`~~ | **✅ VERIFIED** — healthy 6 s after start; the container's own healthcheck fires | — |
| ~~Preflight fires on a real deploy~~ | **✅ VERIFIED** — `APP_ENV=production` exits 3 and names all 8 problems | — |
| `railway.json` is accepted | never sent to Railway | first deploy |
| Capacitor WebView really sends the origins we allow | no device build exists yet | Task 3.1 gate |

**Updated 2026-08-18: the image now builds and three of these rows are closed.
Getting there cost three real defects — see the register below. The build is the
single highest-yield check in this whole plan so far.**

---

## Task 0.1 — Deploy the backend — ❌ BLOCKED (`e58ad71`)

### Delivered
- `backend/Dockerfile` — CPU-only torch wheels (the default PyPI torch pulls the
  whole CUDA runtime, over a gigabyte this CPU-only app can never use);
  dependency layers before `app/` so a code push reuses them; ECAPA weights
  baked in at build so the first request after a deploy does not wait on an
  80 MB HuggingFace download, and a HuggingFace outage is not a ListenUp outage.
- `backend/.dockerignore`, `backend/railway.json`
- `infra/README.md` — the deploy checklist. That directory is now real;
  `CLAUDE.md`'s repo layout had been claiming it existed.
- `backend/app/preflight.py` — refuses to start a misconfigured production deploy.

### The defect this task fixed
Every provider falls back to a mock when its variable is unset — correct for
development (INTRODUCTION §6), and the most dangerous default in production. A
deploy missing `ASSEMBLYAI_API_KEY` **started cleanly, returned `/health` 200,
and served the first real user a fixture conversation.** Nothing errored. The
failure would have surfaced days later as "the captions are nonsense".

Preflight now reports every problem at once — finding one missing variable per
restart is a miserable way to deploy — and each problem carries its remedy.
Warnings stay warnings: a missing `REDIS_URL` costs money, it does not stop a
deploy.

### Not implemented / blocked
Everything in **Waiting on you** items 1–4. None of it is code.

### Test failures and errors hit
| what | cause | resolution |
|---|---|---|
| Edit silently did not apply | `cd backend && …` ran while already in `backend/`; the `&&` chain aborted, so the heredoc never executed — but the *following* line still ran and reported the old state | re-ran without the `cd`; **caught only because mypy still reported the error it was supposed to fix** |
| `ruff` E501 in `test_preflight.py` | 104-char assertion line | split across two statements |
| Test count looked wrong (520 vs expected 492) | stale assumption about the baseline | measured HEAD directly: 512 → 520, correctly +8 |
| **Reported "69 frontend checks" in the task report** | stale reading; `verify` runs four scripts, not three | actual number is **97**. Corrected in the next report. Changed no decision |

### Mutations run — 3, all confirmed to fail
| mutation | result |
|---|---|
| Preflight never reports a mock left on | 1 test fails |
| Credentials not required for a real provider | 2 fail |
| Warnings promoted to errors | 2 fail |

### Gate remaining
`wss://` session from a phone on cellular produces captions · `/health` green ·
a redeploy does not re-download the model.

---

## Task 0.2 — CORS for Capacitor origins — ✅ DONE (`de77e8d`)

### Delivered
`backend/app/cors.py`. Both Capacitor WebView origins are allowed —
`capacitor://localhost` (iOS) and `https://localhost` (Android) — as
**constants, not configuration**: nobody chooses them and no deploy changes
them, so requiring an operator to know the value would only be a way to get it
wrong. `EXTRA_CORS_ORIGINS` covers what genuinely is a deployment choice, such
as Vercel preview hostnames.

A `*` anywhere now raises at startup. The obvious reason is that this API
carries bearer tokens and biometric data. The less obvious one matters more:
**Starlette silently drops credentials when the origin list is a wildcard**, so
reaching for `*` to kill a stubborn CORS error would appear to work while
breaking authentication in a way nobody would connect back to CORS.

### Two findings

**1. The WebSocket needed no change, and could not have.** CORS middleware does
not apply to WebSockets — browsers send no preflight for them — so
`/ws/transcribe` has always accepted any origin. That is **not** an exposure
here: the socket authenticates on a token in its *first message* rather than on
a cookie, so a hostile page cannot open a session it has no token for. There is
now a test pinning that, because "it works" and "it works for a good reason" are
different claims.

**2. A defect in my own tests, found by mutation.** The integration checks
parametrised over `CAPACITOR_ORIGINS` — the very constant under test — so
emptying it produced **zero cases** and they *skipped instead of failing*:

```
M1 (before): 1 failed, 7 passed, 2 skipped
M1 (after):  6 failed, 7 passed, 0 skipped
```

A test that disappears when the code breaks is worse than no test, because it is
still counted. The origins are now written out literally, with one test
asserting the literals still match the constant so the two cannot drift.

### What's deferred (not blocked)
The gate's *"from a real device build"* clause needs a build, which does not
exist until Phase 3. **Carried into Task 3.1's gate** rather than left dangling
here — the allow-list is unit-tested, but only a device proves the WebView sends
the origin we think it does.

### Mutations run — 5, all confirmed to fail
| mutation | result |
|---|---|
| Drop both Capacitor origins | 6 tests fail |
| Allow only iOS (ships broken on Android) | 1 fails |
| Let the wildcard through | 1 fails |
| **Rules correct, middleware still wired to the old single origin** | 4 fail |
| Re-run of mutation 1 after fixing the skip defect | 6 fail, 0 skip |

The fourth mattered most: correct rules and a middleware actually using them are
separate claims, and only the wiring mutation tests the second one.

---

## Task 0.3 — Legal pages — ❌ BLOCKED (`4b51d4a`)

### Delivered
`/privacy` and `/terms` on the web build, plus `components/marketing/LegalPage.tsx`.
Linked from a new **Legal** column in the site footer and from **Settings** —
somebody looking for how to withdraw a consent they gave is already signed in,
and sending them to the marketing site to find it would be the wrong way round.

### Why this is not boilerplate
Every claim was checked against `backend/db/migrations/` and the code rather
than taken from a template. Three things came out differently than a template
would have said:

- **Transcripts are not stored at all.** Six migrations, none of them a
  conversation. The project has described transcripts as "opt-in" elsewhere;
  on the page that has to be true, that would have been a false statement.
- **A voice profile is 192 numbers**, not a recording, and cannot be played
  back. Worth stating plainly — it is the difference between what the product
  does and what people fear it does.
- **Slang lookups are logged with no link to an account.** `slang_gap_log` has
  no user column, so the page says so rather than hedging.

The terms carry two clauses that should not be softened without advice: you must
have permission before enrolling somebody else's voice, and **an emergency
clause** — a deaf user relying on an imperfect caption in a safety-critical
moment is a foreseeable use of an accessibility tool, so the terms say plainly
not to.

### Not implemented / blocked
1. **Legal review of the biometric section.** The pages carry a source comment
   marking this; users do not see it.
2. `privacy@listenup.app` and `hello@listenup.app` must become real.
3. App Store Connect: privacy policy URL and Privacy Nutrition Labels
   **declaring biometric collection**.

### Verification
Browser suite grew **40 → 56 checks**, all green: both pages axe-clean in both
contrast modes, AA measured from rendered pixels against the gradient, no
horizontal overflow at 390/834/1440, touch targets hit-tested.

### Mutations run
None. There is no logic here to mutate — the verification is the rendered-page
suite, which is the right instrument for two static documents.

---

## Task 0.4 — Monitoring and a spend circuit-breaker — ✅ DONE

### Delivered
`backend/app/spend.py`. A daily ceiling in dollars, denominated in the units the
app already meters, with rates sourced from `../product/SUBSCRIPTION.md` §10 and pinned by
a test — a ceiling computed from drifted rates would refuse sessions at the
wrong moment while looking perfectly reasonable.

Three decisions worth keeping:

- **Unset means off.** A default would be a number nobody chose silently
  deciding when captions stop working. Preflight warns instead.
- **It refuses the next start, never a live session** — the same trade
  `CaptionSession` already makes for the per-user allowance, because a cap that
  fires mid-sentence can fire in a medical appointment. The refusal carries
  `reason: "service_capacity"` and copy saying nothing is wrong with your
  account, because a user may have hours of allowance left and be refused
  anyway.
- **It fails open.** Every failure inside the ledger is swallowed and an
  unanswerable ledger reports "not over". An hour of unnoticed overspend is
  recoverable; a deaf user unable to follow a conversation because a counter
  broke is not.

Sentry alerts **once per day**, not once per refused session — an alert that
fires on every attempt buries itself.

### The defect this task found — and did not fix
**An anonymous caption session is completely unmetered.** `CaptionSession.open()`
treats the token as optional, so a client that sends none gets a real provider
connection with no allowance check — per-user metering only runs when `_who`
exists. The frontend never does this (the route is auth-guarded), but the API is
public.

The ledger deliberately records **outside** the `_who` guard so the global
ceiling at least sees that spend, and a test pins it. **The underlying hole is
open**: fixing it means deciding whether unauthenticated captioning is a feature
(a free trial with no signup) or an oversight. That is a product decision, not a
bug fix, and it belongs in its own task.

### Deliberately not done
Translation spend is **recorded but never refused**. Live captions push every
finished line through `/translate`, so refusing there would strip translations
out of a conversation already in progress — the mid-session cut this feature
exists to avoid. The ceiling closes the loop by refusing the next session.

### Not implemented / blocked
`DAILY_SPEND_CEILING_USD` and both Sentry DSNs are yours to set. Also: **the
ledger is in-process**, which is correct at `numReplicas: 1` and wrong above it —
two instances would each allow the full ceiling. `infra/README.md` says to
divide if you scale out.

### Test failures and errors hit
| what | cause | resolution |
|---|---|---|
| A websocket test hung for 2 minutes | my drain loop waited for a `closed` message the socket never sends; it sends `done` | matched the existing `test_ws_transcribe` pattern |
| `assert "your" not in message` failed | a crude proxy for "does not blame the user" — it tripped on *"nothing is wrong with **your** account"*, which is the reassurance the copy exists to give | replaced with assertions on the substance: the reassurance must be present, and `allowance` / `upgrade` / `your limit` must not |
| **Mutation M2 was not caught** | the mid-session test stopped the session immediately, so an injected cut in `push_audio` was never reached | the test now streams audio *after* crossing the ceiling; M2 fails |

### Mutations run — 6, all confirmed to fail
| mutation | result |
|---|---|
| No ceiling check when opening a session | 1 fails |
| **The ceiling also cuts live sessions** | 1 fails *(only after the test was fixed — see above)* |
| Record only for signed-in users (restore the anonymous blind spot) | 1 fails |
| The safe wrapper stops swallowing | 1 fails |
| `over_ceiling()` fails closed instead of open | 1 fails |
| No daily reset | 1 fails |

---

## Task 0.5 — Accounts — ❌ BLOCKED (your choice)

Deferred: the Apple Developer Program is your last step before production.

Nothing is lost by this. Phases 1–4 all run without a developer account —
building, testing on a simulator, and running on your own device via a free
provisioning profile all work. Only Phase 5 needs it.

**One caution:** enrolment is 24–48 hours of pure waiting. Start it *during*
Phase 3, not after, or it becomes two idle days at the end.

**Still needed before Task 3.1:** a real bundle id to replace
`com.<you>.listenup`.

---

## Tool setup — Docker

You asked whether an MCP server could set this up. **There is no Docker MCP
available in this environment** — I checked the tool list. So: manual, and it is
short.

### Do you actually need it?

**No, strictly.** Railway builds the image server-side from the `Dockerfile`, so
you can deploy without ever installing Docker.

**But it is worth 20 minutes**, because this image installs torch and downloads
model weights. A build failure costs a full push-wait-fail cycle on Railway,
and the four things listed in *Unverified* above have never been run. Building
once locally converts them from unknowns into facts.

### What we installed, and why not the obvious one

**`brew install --cask orbstack` fails on this machine.** Homebrew 6.0.11 does
not recognise a `run` install step the OrbStack cask uses:

```
Error: unknown install step: run
```

Brew rolled the whole thing back correctly — the app was moved to
`/Applications`, then removed again — so nothing was left half-installed. This
is a **cask-format incompatibility**, not a problem with OrbStack or with the
machine, and `brew install --cask docker` would risk the same class of failure.

**Colima works, because it is a *formula* rather than a cask** and takes an
entirely different install path. It is CLI-only, free, open source, and more
than adequate for building one image.

```bash
brew install colima docker
colima start --memory 6 --cpu 4 --disk 60
docker info          # expect a Server Version, not "Cannot connect"
```

Installed here: Docker CLI 29.7.2 against Colima's daemon 29.5.2, 4 CPUs,
5.77 GiB. **6 GB is not padding** — installing torch in a 4 GB VM is where these
builds die, and the error does not say so.

If you later want a GUI, download OrbStack directly from
[orbstack.dev](https://orbstack.dev/) rather than through brew; the `.dmg`
avoids the cask machinery entirely.

**Stopping and starting:** `colima stop` frees the memory when you are not
building; `colima start` brings it back with the same settings. Nothing runs at
login unless you ask for it with `brew services start colima`.

### One caveat about what a local build proves

This machine is **arm64**; Railway builds **amd64**. A native build here
verifies the Dockerfile's logic — layer order, the CPU wheel index, the model
bake, the healthcheck — but not architecture-specific packaging. Building
`--platform linux/amd64` gives exact parity at the cost of qemu emulation, which
turns a 15-minute torch install into something much longer. Worth doing once
before the first real deploy; not worth doing on every change.

### Then verify our image — and it found a real bug on the first run

```bash
cd backend
docker build --platform linux/amd64 -t listenup-backend .
```

**The first build failed**, which is the whole reason to do this locally:

```
ERROR: Could not find a version that satisfies the requirement torchaudio>=2.13
       (from versions: ... 2.10.0, 2.11.0)
```

`requirements-ml.txt` asked for a version of torchaudio **that does not
exist**. torchaudio's numbering lags torch's — torch 2.13 pairs with torchaudio
**2.11**, which is the newest published. The pin was unsatisfiable on every
platform and **would have failed the first Railway deploy identically.**

It went unnoticed for two reasons, both worth knowing: the local virtualenv was
built before the pin drifted and already had 2.11.0 sitting in it, and **CI
never installs `requirements-ml.txt`** — the file says so in its own first line.
So nothing in the project had ever tried to resolve it.

`tests/test_requirements.py` now checks every pin against what is actually
installed, which catches an aspirational pin offline, with no network and no
container, and skips cleanly where the ML extras are absent.

### The remaining verification commands

The first three of these have now been run here. Keep them: they are the four
questions a container has to answer before it is worth deploying.

```bash
cd backend

# 1. Does it start and serve health?
docker run -d --name lu -p 8100:8000 listenup-backend
curl localhost:8100/health          # {"status":"ok"} — took 6s here

# 2. Are the weights REALLY baked in? Run with no network at all.
#    This is the check that caught the symlink defect; `du -sh` on the cache
#    directory is not enough, because symlinks look like a populated folder.
docker run --rm --network none -e SPEAKER_ID_SERVICE=real listenup-backend \
  python -c "from services.speaker_id import get_speaker_embedder; \
             get_speaker_embedder().load(); print('loaded offline')"

# 3. Does preflight refuse a broken production config?
docker run --rm -e APP_ENV=production listenup-backend
#    Expect: refuses to start, lists every missing variable with its remedy.

# 4. Does a code change reuse the torch layer?
touch app/main.py && docker buildx build --platform linux/amd64 -t listenup-backend --load .
#    Expect: CACHED on the pip layers.
```

**Check 2 is the one worth internalising.** The build printed
`ECAPA weights cached` and the directory existed, so every cheap check said
yes. Only loading the model *as the runtime user, with the network cut* showed
that the weights were symlinks into a directory that user could not read.

---

## Cross-task defect register

Where the bugs came from, which is worth watching over time.

| # | found in | kind | defect |
|---|---|---|---|
| 1 | 0.1 | **product** | a production deploy missing credentials started healthy and served fixture data |
| 2 | 0.2 | **product** | Capacitor origins would have failed CORS preflight on the first device build |
| 3 | 0.2 | **my own tests** | parametrising over the constant under test made cases vanish rather than fail |
| 4 | 0.1 | **my own process** | a `cd` failure aborted a shell chain and an edit silently did not apply |
| 5 | 0.1 | **my own reporting** | stated 69 frontend checks; the real number is 97 |
| 6 | 0.4 | **product — OPEN** | an anonymous caption session is unmetered: `open()` treats the token as optional, so no allowance is checked and a real provider connection is made. The ledger sees the spend; the hole itself is not closed |
| 7 | 0.4 | **my own tests** | the mid-session test never sent audio after crossing the ceiling, so an injected cut was never reached and mutation M2 passed |
| 8 | 0.4 | **my own tests** | `assert "your" not in message` was a crude proxy that tripped on the reassurance the copy exists to give |
| 9 | tooling | **product** | `requirements-ml.txt` pinned `torchaudio>=2.13`, a version that does not exist. Unsatisfiable on every platform; would have failed the first Railway deploy. Found by the first local Docker build |
| 10 | tooling | **my own process** | the first background build reported "exit code 0" because I ended the command with `tail`, so the shell's status masked the build's. The log said `EXIT=1` |
| 11 | tooling | **product — FATAL** | `stripe` is imported at module scope by `app/routes/billing.py` and declared in **no requirements file**, nor pulled in transitively. The container could not start at all. CI would fail collection for the same reason and has evidently never run on this code |
| 12 | tooling | **product** | `pydantic` and `websockets` are imported directly but were relying on arriving via `fastapi` and `uvicorn[standard]`. Works today, breaks the day either upstream swaps them |
| 13 | tooling | **product** | shell-form `CMD` left the shell as PID 1, so `SIGTERM` never reached uvicorn — a redeploy would hard-kill live caption sessions instead of draining them, in an app whose central promise is never to cut a session mid-sentence. Found by the build's own `JSONArgsRecommended` warning |
| 14 | tooling | **my own process** | repeated defect #4: `cd backend` inside a command whose session was *already* in `backend/`, aborting the chain. Now using absolute paths for background commands |
| 18 | 1.2 | **product — would have broken every iOS session** | `useTranscription` declared `sampleRate: 16000` on the wire as a constant and **nothing ever read `context.sampleRate` back**. Any browser refusing the requested rate sent 48 kHz audio labelled 16 kHz — nonsense captions and meaningless embeddings, reading like a bad model rather than a bad number |
| 19 | 1.2 | **product** | the worklet batched a fixed 3200 samples, which is 200 ms only at 16 kHz. At 48 kHz that is 66 ms, tripling the socket message rate and breaking the 100–250 ms chunk constraint |
| 20 | 1.2 | **my own tests** | the diagnostic panel carried its own copy of the capture pipeline, so deleting the resampling from live captions left the browser check green. It was measuring a parallel implementation. Fixed by extracting one shared graph |
| 16 | 1.1 | **product** | `/login`'s inline `Register` button was **54x20**, half the required touch height. Found only once the probe stopped accepting a hit on an ancestor |
| 17 | 1.1 | **my own tests — the worst so far** | the touch-target check had only ever inspected controls **above the fold**. `elementFromPoint` works on the visible viewport, so everything below was silently skipped — most of `/design` at phone height, including the icon buttons the rule exists for. It read as page-wide and was first-screen only. A mutation shrinking `IconButton` to 40x40 passed **three times** before this was found |
| 15 | tooling | **product — FATAL, fixed** | the model bake looked like it worked and did not. SpeechBrain writes **symlinks** into the HuggingFace cache rather than copying weights into `savedir`, so `/opt/models/ecapa` held 24 KB of links into `/root`, and the non-root runtime user got `Permission denied` loading them. With `SPEAKER_ID_SERVICE=real` — which preflight *requires* in production — `lifespan` calls `load()` at startup, so Railway would have crash-looped. Fixed by setting `HF_HOME` inside the image and running the bake **as the runtime user** |

---

## How to append a task to this log

Keep the shape, because the shape is the point:

```markdown
## Task N.N — <name> — ✅ DONE / ❌ BLOCKED (`<commit>`)

### Delivered
### The defect this task fixed        (if any)
### Not implemented / blocked         (say who it is blocked on)
### Test failures and errors hit      (including your own mistakes)
### Mutations run — N, all confirmed to fail
### Gate remaining / deferred
```

Two rules that keep it honest:

- **A task is only ✅ if its gate was actually run.** "Implemented" is not the
  same claim as "verified", and this repo has already shipped a contrast suite
  that stayed green against an unstyled page.
- **Record your own errors, not just the code's.** Rows 3–5 above are mine. A
  log that only contains the product's failures is a log nobody learns the
  process from.
