# CLAUDE.md — ListenUp

SaaS web app that makes spoken conversation **accessible** (speaker-named live captions for deaf/HoH users) and **culturally understandable** (translation that explains slang, register, nuance). Full context: `INTRODUCTION.md`. Build order: `PHASE_0` → `PHASE_5`, one step at a time.

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

## Conventions (INTRODUCTION §7)

1. One phase at a time; one step at a time within a phase.
2. Every step: run it → check the step's Verification Gate → fix → continue. No advancing on a red gate.
3. Error protocol (INTRODUCTION §8): static checks → runtime check → verify gate; read the full trace, state root cause in one sentence, fix, re-run; STOP after 2 failed attempts on the same error. Never mark a step done on a compile-only pass.
4. Tests alongside features, never after. Prefer mocks for external APIs.
5. Small commits after each verified step.
6. Log unexpected errors + resolutions in `DEBUG_LOG.md`.
7. Ask before destructive actions (deleting files, dropping tables, rewriting configs).
8. Report after each step: what was built, how verified, errors + fixes, what's next.

## Commands

- Frontend (`/frontend`): `npm run dev` · `npm run build` · `npm run lint` · `npm run typecheck`
- Backend (`/backend`): `source .venv/bin/activate` · `uvicorn app.main:app --reload --port 8000` · `ruff check .` · `pytest`

## Repo layout

```
/            CLAUDE.md, DEBUG_LOG.md, README.md, .env.example, CI config
/frontend    Next.js app
/backend     FastAPI app → /services (assemblyai, speaker_id, translate, openrouter — each with a mock), /routes, /db
/infra       deploy configs
/docs        discovery notes, non-code docs
```

## Decisions Log

_Append dated entries as decisions are made._

- **2026-07-16** — Phase 0 scaffold created; Next.js frontend and FastAPI backend initialized per PHASE_0_SETUP.md.
- **2026-07-16** — Supabase project "ListenUp" (`lutygmchbabmvomnjusl`, us-east-1, free tier). Auth via `@supabase/ssr` publishable key; Next.js 16 `proxy.ts` (middleware successor) refreshes sessions with `getClaims()` and guards `/voice-to-text/*` + `/translate/*`. Email confirmation is ON — signup shows a "check your email" notice.
- **2026-07-16** — Observability wired as env-guarded no-ops: Sentry via `instrumentation.ts` / `instrumentation-client.ts` (Next.js 16 conventions) + `sentry_sdk` in FastAPI; PostHog client-side with session recording disabled by default (privacy §6).
