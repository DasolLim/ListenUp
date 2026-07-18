# ListenUp

A SaaS web app that makes spoken conversation **accessible** (live speaker-named captions for deaf/HoH users) and **culturally understandable** (translation that carries slang, register, and nuance).

## Status

| Phase | Scope | Status |
|---|---|---|
| 0 | Repo, CI, CLAUDE.md, observability stubs | ✅ Complete |
| 1 | Pages, Supabase Auth, WebSocket skeleton | ✅ Complete |
| 1.5 | Sense-inspired glassmorphic UI (DESIGN_SYSTEM.md) | ✅ Complete |
| 2 | ★ Live captions + diarization (the wedge) | ✅ Complete — mock end-to-end + real AssemblyAI path verified once |
| 3 | ★ Saved voice profiles (ECAPA-TDNN + consent) | ✅ Complete — enrollment w/ consent gate, live name-matching, tap-to-correct |
| 4 | Translation (Google v3 + OpenRouter + combined live) | ✅ Complete — incl. ★ speaker-named multilingual live captions |
| 5 | GenZ slang translator + launch hardening | — |

## Run it

**Frontend** (Next.js 16 + TypeScript + Tailwind v4, in `/frontend`):

```bash
cd frontend
npm install
npm run dev        # http://localhost:3000
npm run typecheck && npm run lint && npm run build   # CI checks
```

Requires `frontend/.env.local` with `NEXT_PUBLIC_SUPABASE_URL` and `NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY` (see `.env.example`). Without them the app runs with auth disabled and says so.

**Backend** (FastAPI, in `/backend`):

```bash
cd backend
python3 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt
./run.sh           # http://localhost:8000 — /health, /ws/echo
.venv/bin/ruff check . && .venv/bin/mypy app && .venv/bin/python -m pytest
```

CI (GitHub Actions) runs all of the above on push/PR.

## Build plan documents (in order)

1. **INTRODUCTION.md** — scope, stack, architecture rules, Standard Error & Debugging Protocol (§8). Read first.
2. **PHASE_0_SETUP.md** → **PHASE_1_FOUNDATION.md** — done.
3. **DESIGN_SYSTEM.md** — 🎨 the visual source of truth (tokens, glass components, a11y overrides). **All UI work must follow it strictly.** See also START_HERE_FRONTEND_UI.md + PHASE_1.5_FRONTEND_UI.md (done).
4. **PHASE_2_VOICE_TO_TEXT.md** → **PHASE_5_GENZ_SLANG.md** — next up, one phase at a time.

## Conventions

- One phase, one step at a time; every step must pass its **Verification Gate** (run, not just compile) per INTRODUCTION §8.
- `CLAUDE.md` — living rules + decisions log. `DEBUG_LOG.md` — unexpected errors and fixes.
- Every external API (AssemblyAI, Google, OpenRouter) gets a mock so features build/test without burning credits.
- Accessibility failures are build-breaking: WCAG 2.1 AA, keyboard nav, high-contrast mode, caption font scaling.

## Recommended pace

- Phase 2 (core captions) to "wow" quality before polishing anything else.
- Get a real deaf/HoH tester on Phase 2 before starting Phase 3.
