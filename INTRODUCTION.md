# INTRODUCTION — Read This First

You are Claude Code, building a SaaS web/app from the ground up. **Read this entire file before writing any code.** It defines the scope, stack, tools, conventions, and rules for the whole project. Every phase file (`PHASE_0` … `PHASE_5`) assumes you already understand this document.

---

## 1. What We're Building

A SaaS web/app that makes spoken conversation **accessible** and **culturally understandable**.

**Two core problems it solves:**
1. Existing captioning tools produce a wall of text — you can't tell **who said what**.
2. Existing translators translate **words, not meaning** — they miss slang, tone, culture.

**Target users:**
- Primary: deaf / hard-of-hearing people.
- Secondary: travelers, immigrants, international users.

**The differentiators (the moat) — protect these while building:**
1. **Speaker-named captions** — label each line with *who* said it, including saved friends/family by real name (not "Speaker 1").
2. **Cultural translation** — translate + explain slang, register, and cultural nuance.
3. **Killer combo:** speaker-named **multilingual live translation** (e.g. a deaf Korean immigrant sees each English speaker translated to Korean, labeled by person, in real time).

---

## 2. Products & Features

### Voice-to-Text
- **General:** real-time live captions; multi-speaker separation (diarization); color-coded chat-bubble UI.
- **Enhanced:**
  - Higher accuracy in busy multi-speaker settings.
  - **Speaker cap: 4–5** (accuracy over unlimited speakers — enforce this).
  - **Saved voice profiles:** user enrolls frequent contacts via 20–30s voice capture → app labels them **by name**.
  - **Tap-to-correct:** fixing a label improves that person's profile.

### Translation
- **General:** fast text→text and voice→text translation, wide language coverage.
- **Enhanced (cultural):** LLM returns translation + register (formal/casual) + slang/idiom notes (meaning, context, equivalent).
- **GenZ/slang:** explains modern internet slang/memes/abbreviations; shareable "translation cards."
- **Combined live:** multi-speaker + multi-language + live translation, labeled by speaker.

### App Pages
- Home (intro + mission + feature overview)
- Navbar: Home, About, Product
- Product (feature breakdown)
- About (mission detail)
- Login (sign in / register)
- Voice-to-Text → General + Enhanced tool pages
- Translate → General + Enhanced + GenZ pages

---

## 3. Tech Stack

**Frontend**
- Next.js 14+ (App Router), TypeScript, Tailwind CSS
- Deploy: Vercel
- Real-time: WebSockets (mic → backend → captions)

**Backend**
- FastAPI (Python), native WebSocket support
- Deploy: Railway / Render / Fly.io (no Kubernetes)

**Data / Auth / Storage**
- Supabase: Postgres, **pgvector** (speaker embeddings), Auth, Storage
- Redis: cache translations + slang lookups

**Ops**
- Sentry (errors), PostHog (analytics), GitHub Actions (CI/CD)

---

## 4. External Tools / AI / Libraries

| Job | Tool | Notes |
|---|---|---|
| Speech-to-text + diarization | **AssemblyAI** (Universal-2/3) | **Single STT provider.** Streaming + diarization + 99 languages. Chosen for accuracy on noisy audio. Wrap in ONE service module (swappable). |
| Speaker identification | **SpeechBrain ECAPA-TDNN** (`speechbrain/spkrec-ecapa-voxceleb`) | Open-source, CPU-fine, no per-call cost. 192-dim embeddings → pgvector. Puts *names* on AssemblyAI's anonymous labels. |
| Translation (general) | **Google Cloud Translation v3** | Wide coverage, cheap, <200ms. |
| Translation (enhanced/GenZ) | **OpenRouter** (LLM of choice) | Structured output: translation + register + slang notes. |
| Slang KB (Phase 5) | Postgres + pgvector RAG | Region/date-tagged, seeded from Urban Dictionary / KnowYourMeme + curation. |

**Division of labor to remember:** AssemblyAI answers *"who spoke when"* (Speaker 0/1/2). ECAPA-TDNN answers *"which real person is that"* (Mom/Dad). They run together, not as competitors.

---

## 5. Key Architecture Rules

- **One STT tool.** Do NOT build a multi-provider abstraction system. Wrap AssemblyAI in a single service module with a clean interface + a mock for testing.
- **Speaker ID runs locally** (ECAPA-TDNN, CPU). No GPU at MVP.
- **Translation routing:** Google (general/coverage) vs OpenRouter LLM (enhanced/slang), Redis-cached.
- **Progressive enhancement for live translation:** show fast Google MT instantly → async LLM slang upgrade. Never block the live caption on the LLM.
- **Audio chunking:** send 100–250ms chunks over WebSocket. Do NOT buffer long.
- **Latency budget:** end-to-end (mic → caption on screen) target < ~1s.
- **Never force a wrong name:** below match confidence → keep the generic label.
- **Speaker cap 4–5:** enforce in code and UI copy.

---

## 6. Non-Negotiable Constraints

- **Accessibility (WCAG 2.1 AA):** full keyboard nav, screen-reader/ARIA support, high-contrast mode, adjustable caption font size. This is an accessibility product — treat a11y failures as build-breaking bugs.
- **Biometric/privacy law (BIPA / GDPR / Quebec Law 25):** Saved voice profiles are biometric data. Require explicit consent from the **enrolled person** (not just the account holder), plus deletion + export. Build the consent gate in the SAME phase as enrollment (Phase 3). Do not defer.
- **Privacy defaults:** do NOT store audio by default; transcripts opt-in; encryption at rest; clear retention policy.
- **Cost awareness:** STT minutes + LLM tokens scale per-user. Always build a mock/stub path so features can be developed and tested without burning API credits.

---

## 7. How We Work Together (Claude Code Conventions)

1. **One phase at a time.** Each `PHASE_N.md` file is built in the numbered order inside it. Do not skip ahead.
2. **One step at a time within a phase.** After each step: run it, verify against the step's **Verification Gate**, fix errors, then continue.
3. **Error checking is mandatory.** Every step includes runtime/execution checks. Do not proceed on a red gate. See §8.
4. **Tests alongside features**, never after. Prefer a mock for any external API.
5. **Small commits.** After each verified step, commit with a clear message.
6. **Keep `CLAUDE.md` updated** at repo root as decisions are made.
7. **Ask before destructive actions** (deleting files, dropping tables, rewriting configs).
8. **Report** at the end of each step: what you built, how you verified it, what errors appeared and how you fixed them, and what's next.

---

## 8. Standard Error & Debugging Protocol (applies to EVERY step)

Run this loop for each build step in every phase:

1. **Build** the step.
2. **Static checks:**
   - Frontend: `tsc --noEmit` (typecheck) + `eslint` + `next build` must pass.
   - Backend: `python -m py_compile` / import check + `ruff`/`flake8` + `mypy` (if configured).
3. **Runtime check:** actually run the code path (start server, hit endpoint, open page). Capture logs.
4. **Verify** against the step's Verification Gate (explicit expected result).
5. **If errors:**
   - Read the full stack trace / console output — do not guess.
   - State the root cause in one sentence before fixing.
   - Fix, then re-run from step 2.
   - If the same error persists after 2 fix attempts, STOP and report the error + what you tried, don't thrash.
6. **Log** unexpected errors and resolutions in `DEBUG_LOG.md` at repo root.
7. Only advance when the gate is green.

**Never** mark a step complete on a compile-only pass — it must run.

---

## 9. Repo Layout (target)

```
/                      # root: CLAUDE.md, DEBUG_LOG.md, README.md, CI config
/frontend              # Next.js app
/backend               # FastAPI app
  /services            # assemblyai/, speaker_id/, translate/, openrouter/  (each with a mock)
  /routes
  /db
/infra                 # deploy configs
```

---

## 10. Build Order (phase map)

- **PHASE_0** — Discovery notes + repo/CI/CLAUDE.md setup
- **PHASE_1** — Foundation: pages, auth, FastAPI skeleton, observability
- **PHASE_2** — ★ General Voice-to-Text (live captions + diarization) — the wedge
- **PHASE_3** — ★ Enhanced V2T: saved voice profiles (ECAPA-TDNN + pgvector + consent)
- **PHASE_4** — Translation (Google v3 general + OpenRouter enhanced + combined live)
- **PHASE_5** — GenZ / slang translator + shareable cards

Build Phase 2 to "wow" quality before investing in polish elsewhere. Start with PHASE_0.
