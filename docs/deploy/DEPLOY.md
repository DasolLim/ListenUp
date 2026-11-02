# Deploying ListenUp

The backend is a FastAPI service with a CPU-only ECAPA-TDNN model loaded at
startup. It holds long-lived WebSockets, so it needs a real container host —
**not** a serverless platform. Railway is the chosen host; Render and Fly work
the same way.

The frontend deploys separately to Vercel and is unaffected by any of this.

---

## 1. Redis (do this first — it is what makes repeats free)

Create an [Upstash](https://upstash.com) Redis database and copy the `rediss://`
URL. The translation and TTS caches fall back to per-process memory without it,
which means every repeated phrase is billed again on every instance. This is a
cost decision, not a reliability one, which is why preflight treats a missing
`REDIS_URL` as a warning rather than an error.

## 2. Railway service

1. New Project → Deploy from GitHub repo.
2. **Set the service root directory to `backend/`.** `railway.json` and the
   `Dockerfile` both live there; without this Railway looks at the repo root and
   finds a Next.js app.
3. Railway reads `railway.json` and builds the Dockerfile. Health check is
   `/health` with a 120 s timeout — the first boot loads the model.
4. **Memory: at least 2 GB.** Torch plus the loaded ECAPA model sits around
   1–1.5 GB resident. A 512 MB instance will OOM during startup and the symptom
   is a restart loop, not an error message.
5. Generate a public domain. That hostname is `NEXT_PUBLIC_BACKEND_URL` for the
   frontend, as `https://…` (and `wss://…` for the socket).

## 3. Environment variables

The app **refuses to start** if any of the errors below apply — see
`app/preflight.py`. That is deliberate: every provider silently falls back to a
mock, so a deploy missing `ASSEMBLYAI_API_KEY` would otherwise start cleanly,
report healthy, and serve the first real user a fixture conversation.

### Required — the deploy will not boot without these

| variable | value | where it comes from |
|---|---|---|
| `APP_ENV` | `production` | **this is what turns preflight on** |
| `FRONTEND_ORIGIN` | `https://<your-vercel-domain>` | must not be localhost |
| `SUPABASE_URL` | project URL | Supabase → Settings → API |
| `SUPABASE_ANON_KEY` | publishable key | Supabase → Settings → API |
| `TRANSCRIPTION_SERVICE` | `real` | |
| `ASSEMBLYAI_API_KEY` | key | assemblyai.com dashboard |
| `SPEAKER_ID_SERVICE` | `real` | mock here means naming is meaningless |
| `TRANSLATION_SERVICE` | `google` | |
| `GOOGLE_CLOUD_PROJECT_ID` | project id | see the ADC note below |
| `ENHANCED_TRANSLATION_SERVICE` | `real` | |
| `OPENROUTER_API_KEY` | key | openrouter.ai |
| `GENZ_EXPLAINER_SERVICE` | `real` | |

### Strongly recommended

| variable | why |
|---|---|
| `REDIS_URL` | without it, cached phrases are billed again (§1) |
| `DAILY_SPEND_CEILING_USD` | **the only thing standing between you and an unbounded provider bill.** Per-user allowances cap each account; nothing caps the total. Set it to a number of dollars you would be willing to lose to a bad day. **Per instance** — the ledger is in-process, so if you ever raise `numReplicas` above 1, divide this by the replica count |
| `EXTRA_CORS_ORIGINS` | comma-separated extra origins, e.g. Vercel preview hostnames. The two Capacitor WebView origins are always allowed and need no configuration (`app/cors.py`) |
| `SENTRY_DSN` | without it, backend errors exist only in logs nobody reads |

### Optional

| variable | default | note |
|---|---|---|
| `TTS_SERVICE` | `browser` | free tier, correct default. `elevenlabs` needs `ELEVENLABS_API_KEY` |
| `SUPABASE_SERVICE_ROLE_KEY` | — | only for the Stripe webhook path |
| `STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET` | — | **not needed for v1**, which ships free-tier-only |
| `SPEAKER_*` | see `session_speakers.py` | tuning constants; leave them alone |

**Google Translation auth is the awkward one.** Local development uses `gcloud`
Application Default Credentials, because the org policy
`iam.disableServiceAccountKeyCreation` blocks JSON key files (decisions log,
2026-07-17). ADC does not exist inside a container, so production needs either a
service-account key from a project without that policy, or Workload Identity
Federation. **Resolve this before the first deploy** — it is the one credential
that cannot simply be pasted into Railway.

## 4. Verify

```bash
curl https://<your-domain>/health          # {"status":"ok"}
```

Then, from a phone on **cellular** (not your wifi — that is the point):

1. Open the deployed frontend, start a captions session.
2. Confirm captions appear, and that they respond to what you say rather than
   replaying a fixture. If they look like a scripted conversation, a mock is
   still switched on and `APP_ENV` is not `production`.

## 5. Redeploys must not re-download the model

The ECAPA weights are baked into the image (`Dockerfile`, the `SPEAKER_ID_SERVICE=real
python -c …` step). Push a code-only change and confirm the build log reuses the
cached torch and model layers. If it does not, the layer order has been
disturbed — dependencies must be installed before `app/` is copied.
