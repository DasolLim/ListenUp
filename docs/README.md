# ListenUp docs

All non-code documentation. Only `CLAUDE.md` (working rules) and `README.md` (how
to run it) stay at the repo root; everything else lives here. New docs go in the
folder whose question they answer — *what and why* (product), *how it looks*
(design), *what to build next* (phases, plans), *how to ship it* (deploy), *what
happened* (logs), *one external tool* (integrations).

## product/ — what we're building and why

| File | What it holds |
|---|---|
| [INTRODUCTION.md](product/INTRODUCTION.md) | Scope, stack, architecture rules, the Standard Error & Debugging Protocol (§8). **Read first.** |
| [PRODUCT.md](product/PRODUCT.md) | Product principles and voice — the copy rules the UI is held to. |
| [SUBSCRIPTION.md](product/SUBSCRIPTION.md) | Tiers, allowances, and the cost model (§10) the backend meters against. |
| [DISCOVERY.md](product/DISCOVERY.md) | User-interview template for deaf/HoH users (still to be filled in). |

## design/ — the visual source of truth

| File | What it holds |
|---|---|
| [DESIGN_SYSTEM.md](design/DESIGN_SYSTEM.md) | Tokens, glass components, a11y overrides (§7). **All UI work must follow it strictly.** |

## phases/ — the build plan, in order

| File | What it holds |
|---|---|
| [PHASE_0_SETUP.md](phases/PHASE_0_SETUP.md) | Repo, CI, observability stubs. |
| [PHASE_1_FOUNDATION.md](phases/PHASE_1_FOUNDATION.md) | Pages, auth, WebSocket skeleton. |
| [START_HERE_FRONTEND_UI.md](phases/START_HERE_FRONTEND_UI.md) | How to run the 1.5 UI build. |
| [PHASE_1.5_FRONTEND_UI.md](phases/PHASE_1.5_FRONTEND_UI.md) | The glassmorphic UI build, step by step. |
| [PHASE_2_VOICE_TO_TEXT.md](phases/PHASE_2_VOICE_TO_TEXT.md) | ★ Live captions + diarization (the wedge). |
| [PHASE_3_VOICE_PROFILES.md](phases/PHASE_3_VOICE_PROFILES.md) | Saved voice profiles (ECAPA-TDNN + consent). |
| [PHASE_4_TRANSLATION.md](phases/PHASE_4_TRANSLATION.md) | Google v3 + OpenRouter + combined live. |
| [PHASE_5_GENZ_SLANG.md](phases/PHASE_5_GENZ_SLANG.md) | GenZ slang translator + launch hardening. |

## plans/ — work not yet done

| File | What it holds |
|---|---|
| [NEXT_STEPS.md](plans/NEXT_STEPS.md) | The running shortlist. |
| [PLAN_SPEAKER_IDENTITY.md](plans/PLAN_SPEAKER_IDENTITY.md) | Speaker-ID accuracy tasks and their gates. |
| [PLAN_MOBILE_APP.md](plans/PLAN_MOBILE_APP.md) | Mobile app plan. |
| [MIGRATION_PLAN.md](plans/MIGRATION_PLAN.md) | Supabase Auth → Clerk cutover (§2). |

## deploy/ — shipping it

| File | What it holds |
|---|---|
| [DEPLOY.md](deploy/DEPLOY.md) | Backend hosting checklist: Redis, the container host, every env var, post-deploy checks. Blueprint is `render.yaml` at the repo root; Railway config is `backend/railway.json`. |

## logs/ — what actually happened

| File | What it holds |
|---|---|
| [DECISIONS.md](logs/DECISIONS.md) | The decisions log — dated, newest first, the *why* behind the code. Append here when a decision lands. |
| [DEBUG_LOG.md](logs/DEBUG_LOG.md) | Unexpected errors and their resolutions, across the whole project. |
| [MOBILE_APP_LOG.md](logs/MOBILE_APP_LOG.md) | Per-task record for the mobile work. |
| [error_fixed.md](logs/error_fixed.md) | Phases 0–5 debugging *method*, not the ledger. |

## integrations/

| File | What it holds |
|---|---|
| [ELEVENLABS.md](integrations/ELEVENLABS.md) | Premium TTS + consent-gated voice cloning. |

## screenshots/

Reference and QA screenshots. `readme/` holds the current images used by the root README (captured from a production build on mocks).
