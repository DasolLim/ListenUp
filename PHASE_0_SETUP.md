# PHASE 0 — Discovery & Project Setup

**Prerequisite:** You have read `INTRODUCTION.md`. Follow the Standard Error & Debugging Protocol (§8) for every step.

**Goal:** A clean, deployable skeleton repo with CI, conventions, and observability scaffolding — before any feature code.

---

## Step 0.1 — Repo scaffold

**Prompt to Claude Code:**
> Create the repo structure per INTRODUCTION §9: root files (`README.md`, `CLAUDE.md`, `DEBUG_LOG.md`, `.gitignore`, `.env.example`), a `/frontend` folder, a `/backend` folder, and `/infra`. Do not add feature code yet. Initialize git.

**Verification Gate:**
- Folder tree matches §9.
- `git status` clean after initial commit.
- `.env.example` lists every key we'll need (AssemblyAI, Google, OpenRouter, Supabase, Redis, Sentry, PostHog) with placeholder values — no real secrets.

---

## Step 0.2 — CLAUDE.md (living rules file)

**Prompt:**
> Create `CLAUDE.md` at repo root summarizing: stack, external tools + their single-responsibility, architecture rules (INTRODUCTION §5), non-negotiable constraints (§6), and conventions (§7). Add a "Decisions Log" section (empty, dated entries to be appended). Keep it under ~150 lines.

**Verification Gate:**
- File exists, readable, matches INTRODUCTION.
- Contains a "Decisions Log" heading.

---

## Step 0.3 — Frontend init (Next.js + TS + Tailwind)

**Prompt:**
> In `/frontend`, initialize Next.js 14+ App Router with TypeScript and Tailwind. Configure ESLint + Prettier. Add npm scripts: `dev`, `build`, `lint`, `typecheck` (`tsc --noEmit`). No pages beyond the default yet.

**Verification Gate (RUN these):**
- `npm run typecheck` → passes.
- `npm run lint` → passes.
- `npm run build` → succeeds.
- `npm run dev` → default page loads at localhost with no console errors.

---

## Step 0.4 — Backend init (FastAPI)

**Prompt:**
> In `/backend`, create a FastAPI app with a virtualenv/requirements setup. Add a `/health` route returning `{"status":"ok"}`. Configure `ruff` and (optional) `mypy`. Add a `run` script/uvicorn command.

**Verification Gate (RUN these):**
- `ruff check .` → passes.
- Server starts with uvicorn, no errors.
- `curl localhost:8000/health` → `{"status":"ok"}`.

---

## Step 0.5 — CI (GitHub Actions)

**Prompt:**
> Add a GitHub Actions workflow that on push/PR runs: frontend typecheck + lint + build, and backend ruff + a placeholder pytest. Fail the job on any error.

**Verification Gate:**
- Workflow file valid YAML.
- Locally simulate each CI command; all pass.
- (If pushed) CI is green.

---

## Step 0.6 — Observability stubs

**Prompt:**
> Add Sentry init to both frontend and backend (guarded by env var so it's a no-op without a DSN). Add PostHog init on the frontend (no-op without a key). Do not send real events yet — just wire the SDKs safely.

**Verification Gate:**
- App runs with AND without the env vars set (no crashes either way).
- Typecheck/lint/build still pass.

---

## Step 0.7 — Discovery notes (non-code)

**Prompt:**
> Create `/docs/DISCOVERY.md` with a template for user-interview notes (deaf/HoH users): current tools used, top frustrations, must-have features, quotes → user stories. Leave it ready for me to fill in.

**Verification Gate:**
- File exists with the template sections.

---

## Phase 0 Exit Criteria
- [ ] Repo tree per §9, initial commit clean.
- [ ] `CLAUDE.md` + `DEBUG_LOG.md` present.
- [ ] Frontend: typecheck + lint + build + dev all green.
- [ ] Backend: ruff green, `/health` returns ok.
- [ ] CI defined and passing locally.
- [ ] Sentry/PostHog wired as safe no-ops.

**Report before moving to Phase 1:** confirm each checkbox with the command output you used to verify it.
