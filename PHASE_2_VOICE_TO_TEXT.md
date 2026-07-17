# PHASE 2 — ★ General Voice-to-Text (Live Captions + Diarization)

**Prerequisite:** Phase 1 green. This is the WEDGE — build it to "wow." Follow Error Protocol (§8) every step.

**Goal:** Live, multi-speaker captions from the mic, color-coded by speaker, accessible (WCAG 2.1 AA), with feedback + latency instrumentation.

---

## Step 2.1 — AssemblyAI service module (with mock)

**Prompt:**
> In `/backend/services/assemblyai/`, build a single STT service module that streams audio to AssemblyAI and yields transcript segments with diarization (speaker labels + timestamps + text). Define a clean internal interface `TranscriptionService` with methods to start/stream/stop. Also build a `MockTranscriptionService` that returns canned diarized segments from a local audio fixture — so the whole pipeline can be developed and tested WITHOUT spending API credits. Select mock vs real via env var.

**Verification Gate (RUN):**
- Unit test: mock service yields expected diarized segments.
- Real service: a short test audio file streams and returns segments (run once to confirm creds/format, then default back to mock).
- ruff + import checks pass.

**Error-check focus:** audio format/sample-rate mismatch is the #1 failure — assert 16kHz mono PCM (or AssemblyAI's required format) explicitly and log a clear error if wrong.

---

## Step 2.2 — WebSocket transcription gateway

**Prompt:**
> Add a `/ws/transcribe` FastAPI WebSocket endpoint: accepts audio chunks from the client, feeds them to the TranscriptionService (mock by default), and streams diarized segments back as JSON `{speaker, text, start, end, isFinal}`. Enforce a max of 4–5 speakers (INTRODUCTION §5) — if more are detected, collapse/label extras as "Other". Handle backpressure and disconnects cleanly.

**Verification Gate (RUN):**
- With mock: connect, stream fixture chunks, receive ordered diarized JSON.
- Abrupt disconnect mid-stream → clean teardown, no leaked tasks.
- >5 speakers in a fixture → capped correctly.

---

## Step 2.3 — Browser mic capture + chunked streaming

**Prompt:**
> On the Voice-to-Text General page, capture mic audio (getUserMedia), encode to the required format, and stream 100–250ms chunks over `/ws/transcribe`. Add Start/Stop controls. Request mic permission gracefully; handle denial with a clear message.

**Verification Gate (RUN):**
- Click Start → mic permission prompt → streaming begins.
- Deny permission → clear, non-crashing message.
- Chunk size verified ~100–250ms (log/measure).
- Stop → stream ends cleanly.

---

## Step 2.4 — Live caption UI (color-coded, chat bubbles)

**Prompt:**
> Render incoming segments as live captions: one chat-bubble lane per speaker, each speaker a distinct color, newest at bottom with autoscroll. Show interim (non-final) text in a lighter style, finalize on `isFinal`. Apply diarization smoothing: merge speaker flips shorter than ~1s (likely noise).

**Verification Gate (RUN):**
- Mock stream renders as multi-speaker bubbles, correctly colored.
- Interim text updates then finalizes smoothly (no flicker/duplication).
- Rapid <1s flips are smoothed.
- Autoscroll works; manual scroll-up pauses autoscroll.

---

## Step 2.5 — Accessibility pass (WCAG 2.1 AA)

**Prompt:**
> Make the tool fully accessible: keyboard operable (Start/Stop, controls), ARIA live region for captions so screen readers announce new text, high-contrast mode toggle, and adjustable caption font size. Verify color contrast ratios meet AA.

**Verification Gate (RUN):**
- Full keyboard-only operation works.
- Screen reader announces new captions (test with VoiceOver/NVDA).
- Contrast checks pass AA.
- Font-size + high-contrast toggles persist during a session.

**Note:** a11y failures here are build-breaking bugs, not polish.

---

## Step 2.6 — Feedback + latency instrumentation

**Prompt:**
> Add a thumbs up/down on caption quality (logged for WER tracking) and instrument end-to-end latency: timestamp mic-capture → caption-rendered, report p50/p95 to PostHog. Add a small dev-only latency readout.

**Verification Gate (RUN):**
- Thumbs events logged.
- Latency measured end-to-end (not just API time) and reported.
- p50 latency < ~1s on mock/local.

---

## Phase 2 Exit Criteria
- [ ] Mock pipeline works end-to-end without API spend.
- [ ] Real AssemblyAI path verified once (creds + format correct).
- [ ] Mic → chunked WS → diarized captions live on screen.
- [ ] Speaker cap 4–5 enforced.
- [ ] Multi-speaker color-coded bubbles + interim→final + smoothing.
- [ ] WCAG 2.1 AA verified (keyboard, screen reader, contrast, font/contrast toggles).
- [ ] Feedback + end-to-end latency instrumented; p50 < ~1s.
- [ ] All static checks green; disconnects handled everywhere.

**Report:** demo description of a 2–4 speaker conversation captioned live, plus verification evidence. This is the product's core — get a real deaf/HoH tester on it before Phase 3.
