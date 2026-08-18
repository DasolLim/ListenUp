# MOBILE APP — implementation log

Companion to `PLAN_MOBILE_APP.md`. The plan says what to do; this says **what
actually happened**: what was verified, what was not, what broke, what is
waiting on a human, and every mutation run to prove a test could fail.

Appended to after each task. `PLAN_MOBILE_APP.md` carries a one-line verdict per
task; the detail lives here.

**Related:** `DEBUG_LOG.md` (unexpected errors across the whole project),
`CLAUDE.md` Decisions Log (why things are the way they are).

---

## Status at a glance

| task | status | commit | tests added | mutations |
|---|---|---|---|---|
| 0.1 Deploy the backend | ❌ **BLOCKED** | `e58ad71` | 8 | 3 ✅ |
| 0.2 CORS for Capacitor | ✅ **DONE** | `de77e8d` | 13 | 5 ✅ |
| 0.3 Legal pages | ⬜ not started | | | |
| 0.4 Monitoring + spend ceiling | ⬜ not started | | | |
| 0.5 Accounts | ⬜ **yours** | | | |
| 1.1 Phone layout | ⬜ not started | | | |
| 1.2 Audio path (highest risk) | ⬜ not started | | | |
| 1.3 Microphone constraints | ⬜ not started | | | |
| 1.4 Touch and gesture | ⬜ not started | | | |
| 2.1–2.3 Static export | ⬜ not started | | | |
| 3.1–3.5 Capacitor shell | ⬜ not started | | | |
| 4 Native capabilities | ⬜ not started | | | |
| 5 Store submission | ⬜ not started | | | |

**Suite state at the latest commit:** 533 backend tests · 97 frontend checks ·
40 browser checks · `make check` and `make e2e` both green.

---

## Waiting on you — nothing here is code

Ordered by what blocks the most.

1. **Google Translation auth for a container.** Local development uses `gcloud`
   Application Default Credentials because the org policy
   `iam.disableServiceAccountKeyCreation` blocks JSON key files (Decisions Log,
   2026-07-17). **ADC does not exist inside a container.** You need either a
   service-account key from a project without that policy, or Workload Identity
   Federation. This is the one credential that cannot be pasted into Railway,
   and meeting it at the end of a deploy will stop it dead.
2. **Railway project.** Root directory `backend/`, **≥2 GB memory** — torch plus
   the loaded ECAPA model is 1–1.5 GB resident, and a 512 MB instance OOMs as a
   restart loop rather than an error message.
3. **Upstash Redis** → `REDIS_URL`. Without it every cached phrase is billed
   again, which raises COGS on a product whose margins are already thin.
4. **The remaining env vars** in `infra/README.md` §3.
5. **Apple Developer Program** ($99/yr, ~24–48h) and **Google Play Console**
   ($25 once). Pure waiting — start it before you need it.
6. **A lawyer for the biometric section** of the privacy policy (Task 0.3).
   Voiceprints collected from third parties is the fact pattern BIPA suits are
   built on.
7. **A throwaway Supabase test user** (`E2E_EMAIL` / `E2E_PASSWORD`) so the
   browser suite can cover the five auth-gated tool pages. It currently covers
   public pages only.
8. **A real iPhone and a real Android phone.** Task 1.2 cannot be resolved
   without them, and the iOS Simulator fakes audio in exactly the way that
   would hide the bug.

---

## Unverified — the risk register

Things that are written and committed but have **never been run**. Each is a
place a first deploy can fail.

| what | why unverified | how you find out |
|---|---|---|
| `backend/Dockerfile` builds at all | **Docker is not installed on this machine** | first `railway up` |
| Layer caching (code push reuses torch) | " | build log on the second deploy |
| CPU-only torch wheel index resolves | " | first build; a failure here is loud |
| ECAPA weights bake into the image | " | first deploy's cold-start time |
| Container `HEALTHCHECK` | " | `docker ps` / Railway health status |
| `railway.json` is accepted | never sent to Railway | first deploy |
| Preflight fires on a real deploy | only unit-tested against a fake env | set `APP_ENV=production` with a key missing; it must refuse to boot |
| Capacitor WebView really sends the origins we allow | no device build exists yet | Task 3.1 gate |

**Every path the Dockerfile copies was checked to exist. That is the entire
verification it has had.**

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

## Cross-task defect register

Where the bugs came from, which is worth watching over time.

| # | found in | kind | defect |
|---|---|---|---|
| 1 | 0.1 | **product** | a production deploy missing credentials started healthy and served fixture data |
| 2 | 0.2 | **product** | Capacitor origins would have failed CORS preflight on the first device build |
| 3 | 0.2 | **my own tests** | parametrising over the constant under test made cases vanish rather than fail |
| 4 | 0.1 | **my own process** | a `cd` failure aborted a shell chain and an edit silently did not apply |
| 5 | 0.1 | **my own reporting** | stated 69 frontend checks; the real number is 97 |

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
