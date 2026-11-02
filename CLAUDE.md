# CLAUDE.md — ListenUp

SaaS web app that makes spoken conversation **accessible** (speaker-named live captions for deaf/HoH users) and **culturally understandable** (translation that explains slang, register, nuance). Full context: `docs/product/INTRODUCTION.md` (all docs indexed in `docs/README.md`). Build order: `PHASE_0` → `PHASE_5`, one step at a time.

## Stack

- **Frontend:** Next.js 14+ (App Router), TypeScript, Tailwind CSS → Vercel. Real-time via WebSockets.
- **Backend:** FastAPI (Python), native WebSockets → Railway/Render/Fly.io. No Kubernetes.
- **Data/Auth:** Supabase (Postgres, pgvector, Auth, Storage). Redis for translation/slang cache.
- **Ops:** Sentry (errors), PostHog (analytics), GitHub Actions (CI).

## External tools — single responsibility each

| Tool | Job | Rule |
|---|---|---|
| AssemblyAI | Streaming STT + diarization ("who spoke *when*": Speaker 0/1/2) | **Single STT provider.** One service module + mock. No multi-provider abstraction. |
| SpeechBrain ECAPA-TDNN | Speaker ID ("which *real person*": Mom/Dad). 192-dim embeddings → pgvector | Runs locally, CPU only. No per-call cost. |
| Google Translation v3 | General translation (coverage, <200ms, cheap) | Redis-cached. |
| OpenRouter LLM | Enhanced/GenZ translation (register + slang notes, structured output) | Redis-cached. Never blocks live captions. |
| Browser `speechSynthesis` | Text-to-speech, default tier | Free, offline, no key. Male + female for en/ko. Server only *describes* voices; the client renders. |
| ElevenLabs | Premium TTS + consent-gated voice cloning | Opt-in via `TTS_SERVICE=elevenlabs`. Redis-cached audio. Chosen for Korean quality + a verified-consent cloning API. |

AssemblyAI and ECAPA-TDNN run **together**, not as competitors.

## Architecture rules (INTRODUCTION §5)

1. One STT tool, wrapped in one service module with a clean interface + mock.
2. Speaker ID runs locally on CPU — no GPU at MVP.
3. Translation routing: Google = general; OpenRouter = enhanced/slang.
4. Progressive enhancement: show fast Google MT instantly → async LLM slang upgrade. Never block the live caption on the LLM.
5. Audio chunking: 100–250ms chunks over WebSocket. Do not buffer long.
6. Latency budget: mic → caption on screen < ~1s end-to-end.
7. Never force a wrong name: below match confidence → keep the generic label.
8. Speaker cap 4–5 — enforce in code and in UI copy.

## Non-negotiable constraints (INTRODUCTION §6)

- **WCAG 2.1 AA** — keyboard nav, ARIA/screen-reader support, high-contrast mode, adjustable caption font size. A11y failures are build-breaking bugs.
- **Biometric privacy (BIPA / GDPR / Quebec Law 25)** — voice profiles are biometric data. Explicit consent from the **enrolled person** (not just the account holder) + deletion + export, built in the same phase as enrollment (Phase 3).
- **Privacy defaults** — no audio stored by default; transcripts opt-in; encryption at rest; clear retention policy.
- **Cost awareness** — every external API has a mock/stub path; develop and test without burning credits.

## Design system (docs/design/DESIGN_SYSTEM.md) — STRICT

- **Every UI change must follow `docs/design/DESIGN_SYSTEM.md`** — Sense-inspired glassmorphism (peach→lilac gradient, frosted glass cards, coral orb, Poppins display + Inter body). The look is pinned: match it, don't reinvent. Use the `frontend-design` skill (plus UI-UX pro / Impeccable if available) for any significant UI work.
- Tokens live in `frontend/app/globals.css` (CSS vars + Tailwind v4 `@theme inline`). Primitives in `frontend/components/ui/` (GlassCard, Orb, Pill, Button, IconButton, ImageTile). Never hardcode colors — use tokens (`text-ink`, `text-ink-soft`, `--accent`, speaker tints, `-strong` state colors for text).
- Coral accent is spent sparingly: orb, primary buttons, active nav icon, play/send. Everything else stays quiet glass.
- A11y overrides are build-breaking (§7): AA contrast on all text-on-glass (darken the glass, not lighten the text; state text uses `--*-strong`), `[data-contrast="high"]` must be styled for every new surface, captions scale via `--caption-scale` only, visible coral focus rings, `prefers-reduced-motion` respected, speaker tints always paired with name labels.
- Gotcha: write only the standard `backdrop-filter` — hand-adding `-webkit-backdrop-filter` makes Lightning CSS drop the standard property (see DEBUG_LOG 1.5.2). After moving routes, `rm -rf frontend/.next` before typechecking.

## Conventions (INTRODUCTION §7)

1. One phase at a time; one step at a time within a phase.
2. Every step: run it → check the step's Verification Gate → fix → continue. No advancing on a red gate.
3. Error protocol (INTRODUCTION §8): static checks → runtime check → verify gate; read the full trace, state root cause in one sentence, fix, re-run; STOP after 2 failed attempts on the same error. Never mark a step done on a compile-only pass.
4. Tests alongside features, never after. Prefer mocks for external APIs.
5. Small commits after each verified step.
6. Log unexpected errors + resolutions in `docs/logs/DEBUG_LOG.md`.
7. Ask before destructive actions (deleting files, dropping tables, rewriting configs).
8. Report after each step: what was built, how verified, errors + fixes, what's next.

## Commands

- **`make check`** — the fast loop: types, lint and unit tests across both stacks (~20s). Keep it green.
- **`make e2e`** — the browser loop: boots backend (on mocks) + frontend, checks a11y, contrast, layout.
- **`make all`** — both. `make help` lists the rest.
- Frontend (`/frontend`): `npm run dev` · `build` · `lint` · `typecheck` · `verify` · `e2e` · `e2e:ui`
- Backend (`/backend`): `source .venv/bin/activate` · `uvicorn app.main:app --reload --port 8000` · `ruff check .` · `mypy` · `pytest`

> A script that imports test helpers does **not** inherit `tests/conftest.py`, which is the only thing pinning mocks. Running one by hand has already burned two billed AssemblyAI sessions. Go through the targets above.

## Testing — work test-first, and decide these three things explicitly

Write the failing test, make it pass, then improve the design. The point is not
ceremony; it is that a test written afterwards tends to assert what the code
already does. Three of this repo's tests were caught passing **vacuously** —
named for a guard they never reached — and each was found by deleting the code
and watching the test stay green. **Mutate anything you rely on.** A test that
cannot fail is worse than no test, because it is counted.

**1. What is a unit here?** Bigger than a function. The unit is a *decision the
product makes*: "an ambiguous turn joins the nearest voice", "read-aloud speaks
the text on screen", "the caption pane's newest line never moves". Those cross
several functions on purpose — the bugs in this repo have lived in the seams
(a display layer that undid a correct split, two translation lanes racing), and
a test per function would have passed through every one of them. Test one
function alone when it holds real logic worth pinning — the metrics in
`speaker_metrics.py` are unit-tested against hand-built cases precisely because
a wrong scorer is worse than no scorer.

**2. What to mock.** Mock what costs money, what needs a key, and what is not
deterministic — every external tool has a mock by constraint (§6). Mock
**nothing else**. In particular do not mock our own layers to test our own
layers: the speaker evaluation drives the real `assign → reconcile →
SpeakerMapper` path and only the *provider's diarization labels* are scripted,
because the labels are the input whose misbehaviour the whole subsystem exists
to survive. Where a mock hides the thing under test, use the real one — a cache
test that ran against the mock cache passed under mutation, because the mock's
key is its own.

**3. What behaviour to test.** What a user would notice, stated as an
invariant, not as an implementation. `merge count must be 0` (two people never
share a label) outlives any threshold; `SPEAKER_CLUSTER_THRESHOLD == 0.55` is
a copy of the source. Prefer the properties that survive a rewrite: a cultural
result is never replaced by a plain one; a display number never moves under a
reader; a folded label releases its slot.

**Which loop answers which question:**

| loop | catches | cost |
|---|---|---|
| `mypy` / `tsc` | wrong shapes, unchecked `Any`, an untyped def opting its body out | instant |
| `pytest` / `npm run verify` | decisions and invariants, on mocks | seconds |
| `make e2e` | facts only a rendered page knows | minutes cold |

The browser loop is not optional polish: every bug this project shipped and had
reported back was invisible to the first two. And it earns its cost only for
what a browser alone knows — computed contrast, real geometry, hit areas, and
what actually went over the wire. Re-asserting a class name in a browser is a
slower unit test.

**Two harness rules, both learned the hard way.** *Verify the harness before
trusting a bad number*: a Korean accuracy run read 22.6% from a corpus that was
95% silence, and five reported speaker merges were two real voices wearing five
names. *A green run needs a reason*: a contrast suite stayed green while the
page rendered unstyled, so rendered assertions now refuse to run when the
design tokens did not load.

## Repo layout

```
/                     CLAUDE.md, README.md, Makefile, .env.example, render.yaml (Render reads it from the root)
/frontend             Next.js app — framework-mandated files (proxy.ts, instrumentation*.ts, configs) stay at its root
  /app                routes: (marketing) public site, (app) signed-in tools
  /components         by feature: captions, translate, speech, billing, profiles, marketing, auth, design (QA gallery);
                      shell = app chrome (Navbar, A11yBar, Reveal, icons); ui = design-system primitives
  /lib                pure logic only — no React import, so the node verify harness loads it as-is (keep it flat)
    /hooks            React hooks + SpeechProvider
    /auth, /supabase  auth helpers
  /scripts            node verify checks (`npm run verify`)
  /e2e                Playwright browser loop
/backend              FastAPI app; railway.json + Dockerfiles at its root (it is the deploy service root)
  /app                core modules + /routes (one file per HTTP/WS surface)
  /services           one package per external tool, each with base / real / mock / factory
  /db/migrations      numbered SQL migrations
  /scripts            eval + curation harnesses (eval_results/ holds committed runs)
  /tests              by domain, mirroring app/services: captions, speakers, translation, genz, speech, billing, core
/docs                 all non-code docs — index in docs/README.md
  /product            INTRODUCTION, PRODUCT, SUBSCRIPTION, DISCOVERY
  /design             DESIGN_SYSTEM
  /phases             PHASE_0 → PHASE_5, START_HERE_FRONTEND_UI
  /plans              PLAN_*, MIGRATION_PLAN, NEXT_STEPS
  /deploy             DEPLOY (backend hosting checklist + env vars)
  /logs               DECISIONS, DEBUG_LOG, MOBILE_APP_LOG, error_fixed
  /integrations       ELEVENLABS
  /screenshots
```

## Decisions Log

Lives in [`docs/logs/DECISIONS.md`](docs/logs/DECISIONS.md), newest first. **Append a dated
entry there** when a decision lands — what changed, why, how it was verified, and what
it ruled out — and read the relevant entries before re-opening a settled choice.
