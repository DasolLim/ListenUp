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

## Design system (DESIGN_SYSTEM.md) — STRICT

- **Every UI change must follow `DESIGN_SYSTEM.md`** — Sense-inspired glassmorphism (peach→lilac gradient, frosted glass cards, coral orb, Poppins display + Inter body). The look is pinned: match it, don't reinvent. Use the `frontend-design` skill (plus UI-UX pro / Impeccable if available) for any significant UI work.
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
- **2026-07-16** — Phase 1.5 complete: Sense-inspired UI implemented per DESIGN_SYSTEM.md. Route groups `(marketing)` (public Navbar) / `(app)` (sidebar+topbar shell); `/dashboard` added + protected; `/design` is the primitive gallery for QA. A11y bar (high-contrast + caption size) global. axe clean (0 violations) on all 13 pages incl. high-contrast.
- **2026-07-16** — Supabase project "ListenUp" (`lutygmchbabmvomnjusl`, us-east-1, free tier). Auth via `@supabase/ssr` publishable key; Next.js 16 `proxy.ts` (middleware successor) refreshes sessions with `getClaims()` and guards `/voice-to-text/*` + `/translate/*`. Email confirmation is ON — signup shows a "check your email" notice.
- **2026-07-22** — Phase 5 complete (GenZ slang translator + shareable cards). New `services/genz` package: curated 32-term slang KB (Gen-Z + Korean net-slang, seed CSV) + **local dependency-free text embedder** (deterministic char-n-gram hashing, 256-dim, no download, CI-safe; optional MiniLM via `TEXT_EMBEDDER=real`) + `LocalSlangKB` (cosine + lexical retrieval, runtime ingest, gap log). Migration `0002_slang_kb.sql` ships the **production pgvector** schema (`slang_terms` vector(256) + HNSW, `slang_gap_log`, public-read/authenticated-write RLS, `match_slang_terms()` RPC) — applied live + RPC verified (bussin>no cap>ghosted); runtime defaults to the local KB so gates run without credentials. **RAG explainer** (`GENZ_EXPLAINER_SERVICE` mock|real, default mock): retrieve KB terms → ground gpt-4o → structured `{term, plain_meaning, origin, first_seen, region, example, adult_friendly_explanation, confidence, grounded_terms}`; known → high, unknown → low + gap-logged, LLM-down → KB fallback, never crashes; defensive JSON + Redis cache (namespace `genz`). UI `/translate/genz` (glass design, verified/unverified states, axe-clean incl. high-contrast) + **canvas share cards** (1080² branded PNG, copy/download). Curation API `/genz/terms` (add/update, auth) + `/genz/gaps`. 61 backend tests; prod build green.
- **2026-07-21** — Enhanced naming consistency: identity is now voice-driven, not diarization-label-driven. **Session adaptation (online enrollment):** confident runtime matches are added to an in-memory per-profile gallery (capped, `SPEAKER_GALLERY_CAP`), so a person's later turns — even under a churned diarization label — re-match fast against how they sound *this session*. Lowered `MIN_MATCH_AUDIO_S` 3→2 (gallery makes 2s reliable), retry-on-growth. Ambiguity margin compares vs best *differently-named* profile (duplicate enrollments no longer read as ambiguous). Frontend colors bubbles by **identity** (name when known) so one person = one color through label churn. Proven: same voice under 3 raw labels → 6/6 turns named (unit test `test_identity_survives_label_churn` + real-ECAPA gate). Earlier same day: deleted mock-era test profiles (incompatible with real ECAPA), threshold 0.6→0.55, added `naming_attempt` logs.
- **2026-07-19** — Unified into one responsive product (not website + separate app). Dropped the `(app)` Sidebar/Topbar shell; every page (marketing + dashboard + tools) now shares the top `Navbar` — reads as a web nav on desktop, collapses to the app-style drawer (with a signed-in **Tools** group) on mobile. Nav order: Home, About, Product, Dashboard, Log in/Log out ("Open app" removed). Dashboard redesigned as a simple hub (featured Live Captions tile + tool grid, gradient washes). New `Reveal` (IntersectionObserver, ease-out) fades sections/tiles up on scroll — reduced-motion + no-JS keep content visible (`.reveal-armed` only added client-side when motion allowed); `Section` reveals by default. Removed `Sidebar`/`Topbar`/`CaptionPanel`. axe clean on all pages incl. dashboard + high-contrast; verified 390/834/1440.
- **2026-07-21** — Voice→cultural QA + STT slang biasing. Added `keyterms_prompt` (curated Gen-Z/Korean-relevant slang list) to the real AssemblyAI connection so the English model stops mangling neologisms ("bussin"→"Busan" city). QA over 3 rounds (real STT + gpt-4o, en→ko): STT ~95% (100% on normal speech + real-word slang; neologisms weaker, partly TTS artifact), translation 24/24 accurate and robust to STT slips (recovers "goes to me"→잠수타다), consistent across repeated sentences. AssemblyAI free tier rate-limits rapid session creation (1008); real single-session use unaffected and the app degrades gracefully on a mid-session close.
- **2026-07-21** — Cultural translation accuracy overhaul. Prompt now renders slang **slang-for-slang in the translation itself** (few-shot en↔ko), not literal-plus-notes; accurate meanings (the tea=썰, 갓생=disciplined productive life). Cache key gained `PROMPT_VERSION` (prompt changes now invalidate cached output). Default model **openai/gpt-4o** (4o-mini misread nuanced slang like "lowkey"/ironic "coping"; env-overridable). Combined-live now surfaces the LLM's adapted translation (was Google-literal + notes only). QA 10/10 en↔ko incl. unseen slang.
- **2026-07-21** — Scope focus: translation is **English ↔ Korean only** (all features). `SUPPORTED_LANGUAGES` (backend `services/translate/base.py`) is the single source of truth → every picker + validation follows; other targets 400. Mock detects Korean by Hangul. Defaults set to `ko`. Copy made honest (no "90+/wide coverage"). Widening later is only that list; Google v3 + OpenRouter already support more.
- **2026-07-19** — Marketing website redesign (still pinned to DESIGN_SYSTEM.md). Split registers: the **website** `(marketing)` is now a proper brand experience (narrative home: hero → problem → moat walkthrough → how-it-works → CTA, plus `SiteFooter`), while the **app** `(app)` keeps the dashboard shell as the product experience. New primitives in `components/marketing/` (`Section`/`Eyebrow`/`SectionHeading`, `SiteFooter`, `HeroDemo`). Signature: `HeroDemo` animates real speaker-named tinted bubbles (reduced-motion → static). `Navbar` rebuilt responsive (`md:` inline links + auth + CTA; hamburger→glass drawer below) — fixes a mobile overflow bug; `AuthButton` inlined into it and removed. axe clean on all 4 marketing pages incl. high-contrast; verified at 390/834/1440.
- **2026-07-18** — Phase 4 complete. `/translate` (Google v3 via ADC + httpx, no client lib) + `/translate/enhanced` (OpenRouter, strict-JSON prompt, fence/prose-tolerant parser, 1 retry, 502 fallback → fast lane stands). Redis cache (`listenup:g:*`/`listenup:llm:*`, 7d TTL, memory fallback, hit-ratio 0.8 verified live) — repeated phrases bill 0 chars. Combined live ★: per-final client-side enrichment (`useLiveTranslation`) — Google instant (p50 ~8ms mock), LLM notes async, `Name (LANG): translated` bubbles with original + expandable notes. Cost: per-request logs, session estimate in dev readout, guarded PostHog `session_cost`. Tests pin all four service mocks in conftest.
- **2026-07-18** — Phase 3 complete. Supabase: `speaker_profiles`/`speaker_embeddings` (vector(192))/`consent_records`, owner-only RLS (two-user verified); backend does profile CRUD with the **user's JWT** so RLS is the enforcement layer (no service-role key). ECAPA-TDNN local CPU (load-once, 0.05s/embed; real: same-voice 0.907 vs cross 0.088) + spectral mock for CI with equivalent threshold behavior at 0.6. Enrollment: 20–30s guided, hard consent gate (`consent_text_version 2026-07-18.v1`), delete cascade + JSON export, 4-profile cap. Naming: session audio buffer → lazy embed (≥2s, ≤3 attempts) → threshold 0.6 + 0.05 ambiguity margin (`SPEAKER_MATCH_THRESHOLD`/`_MARGIN`); retroactive `speakerUpdate`; tap-to-correct appends `source=correction` embeddings (repeat-run auto-match verified at 1.000). `.env` loads via `os.environ.setdefault` — shell env wins; tests pin mocks in conftest.
- **2026-07-17** — Real AssemblyAI v3 streaming verified once with `ASSEMBLYAI_API_KEY` (TTS speech fixture → accurate transcript, interim→final turns, speaker labels). All Phase 2 exit criteria now green; default remains `TRANSCRIPTION_SERVICE=mock`. Note: diarization needs real human voices to split speakers well; turn granularity tunable via `min/max_turn_silence`.
- **2026-07-17** — Google Cloud Translation v3 verified with a live `translateText` call (en→ko). Project `project-056afdd8-59ad-48c6-a52`; auth via **gcloud ADC** (`gcloud auth application-default login`), not a service-account JSON — org policy `iam.disableServiceAccountKeyCreation` blocks key files. `GOOGLE_CLOUD_PROJECT_ID` in root `.env`; requests need the `x-goog-user-project` header/quota project. Deploy-time auth TBD in Phase 4.
- **2026-07-17** — Phase 2 built mock-first: `TranscriptionService` interface + `MockTranscriptionService` (paced fixtures) + real AssemblyAI v3 streaming client (`speaker_labels`/`max_speakers`; **live check pending an ASSEMBLYAI_API_KEY**). `/ws/transcribe` caps speakers at 4 named + "Other". Mic → 16 kHz AudioWorklet → 200 ms chunks. Caption UI: interim (italic + ellipsis, full-contrast ink) → final, <1s flip smoothing, autoscroll + jump-to-latest. E2E latency instrumented (mock p50 ≈ 11 ms); thumbs feedback → `/feedback/captions` structured log.
- **2026-07-17** — AA fix: interactive coral split from ambient coral (`--accent-strong #B84A22`, gradient `#C4502A→#A63F19`, focus rings, accent icons) — white-on-light-coral failed 4.5:1. Documented in DESIGN_SYSTEM §2.
- **2026-07-16** — Observability wired as env-guarded no-ops: Sentry via `instrumentation.ts` / `instrumentation-client.ts` (Next.js 16 conventions) + `sentry_sdk` in FastAPI; PostHog client-side with session recording disabled by default (privacy §6).
