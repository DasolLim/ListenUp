# PHASE 1 — Foundation (Pages, Auth, WebSocket Skeleton)

**Prerequisite:** Phase 0 exit criteria all green. Follow Error Protocol (§8) every step.

**Goal:** A user can register, log in, and navigate the app. Backend has a working WebSocket round-trip. Boring but solid.

---

## Step 1.1 — Page structure & Navbar

**Prompt:**
> Build the App Router pages: Home, About, Product, Login, plus nested routes `/voice-to-text` (with `/general` and `/enhanced`) and `/translate` (with `/general`, `/enhanced`, `/genz`). Add a shared Navbar (Home, About, Product) and a login icon linking to Login. Use placeholder content. Make Home briefly state the mission + list features with links to the tool pages.

**Verification Gate (RUN):**
- `npm run build` succeeds.
- Every route renders, no 404s, no console errors.
- Navbar links + feature links navigate correctly.
- Keyboard-tab through the nav works (a11y baseline).

---

## Step 1.2 — Supabase Auth

**Prompt:**
> Integrate Supabase Auth in the frontend: register, login, logout, session persistence, and protected routes (tool pages require auth; marketing pages are public). Build clean Login/Register UI. Read Supabase keys from env. Handle and display auth errors gracefully.

**Verification Gate (RUN):**
- Register a test user → succeeds.
- Log out / log in → session persists across refresh.
- Visiting a tool page while logged out → redirected to Login.
- Invalid credentials → friendly error, no crash.
- Typecheck + build pass.

**Error-check focus:** watch for hydration mismatches (SSR vs client session), and env-var-missing crashes — both must fail gracefully.

---

## Step 1.3 — Backend WebSocket skeleton

**Prompt:**
> In FastAPI, add a `/ws/echo` WebSocket endpoint that accepts a connection and echoes back any message. Add CORS for the frontend origin. Add structured logging on connect/disconnect/message.

**Verification Gate (RUN):**
- Connect from a small test client (or browser console) → messages echo back.
- Connect + abrupt disconnect → server logs cleanly, no unhandled exception.
- Backend ruff + import checks pass.

---

## Step 1.4 — Frontend ↔ Backend WebSocket wiring

**Prompt:**
> Add a minimal frontend WebSocket client hook that connects to `/ws/echo`, sends a test message, and displays the echo. Put a temporary debug widget on the Voice-to-Text General page. Handle connection errors and auto-reconnect.

**Verification Gate (RUN):**
- Page connects, sends, shows echo.
- Kill the backend → frontend shows a connection-error state, attempts reconnect, no crash.
- Restart backend → reconnects.

---

## Step 1.5 — Observability live

**Prompt:**
> Wire a real (guarded) Sentry error capture on both ends and one PostHog page-view event. Trigger a deliberate test error behind a dev-only button to confirm Sentry receives it, then remove the button.

**Verification Gate:**
- Test error appears in Sentry (or logs locally if no DSN).
- Page-view event fires (or no-ops cleanly without a key).
- Build/lint/typecheck pass.

---

## Phase 1 Exit Criteria
- [ ] All routes render; Navbar + feature links work.
- [ ] Register/login/logout + protected routes functional.
- [ ] `/ws/echo` round-trips; disconnects handled cleanly.
- [ ] Frontend WS client connects, errors + reconnects gracefully.
- [ ] Observability wired and verified.
- [ ] Typecheck + lint + build green on frontend; ruff green on backend.

**Report:** confirm each with evidence (command output, screenshot description, or log lines). Append any non-trivial bug + fix to `DEBUG_LOG.md`.
