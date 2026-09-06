# NEXT_STEPS — instrumentation, slang grounding, and the currency loop

Four tasks, in order. Each is independently shippable and independently
revertible. **Do one at a time**, run its verification gate, commit, then move on
(CLAUDE.md §Conventions 1–2).

Task 2 is the one that fixes a reported bug. Task 1 exists so Task 4 is decided
with data instead of opinion.

---

## Invariants — these hold for every task below

- **Gates must be green before a task is done.** Backend: `ruff check .` and
  `pytest` (currently **299 passing**). Frontend: `npm run typecheck`,
  `npm run lint`, `npm run build`.
- **Tests alongside the change, never after** (§Conventions 4). Every new test
  must be shown to **fail against the pre-change code** — revert the fix, watch
  it fail, restore it. A test that passes both ways is proving nothing.
- **Mocks for every external API.** No task here may require live credentials to
  run the suite. `tests/conftest.py` pins every service to a mock.
- **Captions must never break.** Anything on the transcribe path fails *open*: a
  metering, retrieval, or timing failure degrades the feature and logs loudly,
  it never refuses to caption. Someone may be using this to follow a medical
  appointment.
- **Append a dated entry to the Decisions Log in `CLAUDE.md`** when a task lands,
  stating what was measured, not just what was built.
- **Do not** refactor adjacent code, rename files, or "tidy" while in there.
  Diffs should read as one change.

---

## Task 1 — Instrument the three hot paths

**Why:** nothing currently reports where time goes in a real session. Korean
latency was diagnosed by a throwaway script against synthesised audio on one
machine. Task 4 cannot be decided honestly without this.

**Measure exactly three spans:**

| span | from → to | where |
|---|---|---|
| `stt_window` | audio window closed → segment emitted to the socket | `backend/services/assemblyai/batch.py` (`_transcribe`/`_drain`), and the streaming path in `backend/services/assemblyai/` |
| `translate_rt` | request received → response returned, per lane | `backend/app/routes/translate.py` (both `/translate` and `/translate/enhanced`) |
| `allowance` | start → end of the plan+usage resolution | `backend/app/routes/billing.py` (`caller_for_token`) |

**Approach**

- Add `backend/app/timing.py`: one small async context manager that records a
  duration and emits a structured log line. No new dependency.
- Log shape must be greppable and machine-parseable, e.g.
  `perf span=stt_window ms=812 language=ko mode=batch cached=false`.
- Record **language** on `stt_window`, **lane** (`fast`/`enhanced`) and `cached`
  on `translate_rt`, and `hit`/`miss` on `allowance` (the 15 s snapshot in
  `backend/app/usage.py` means most calls should be hits — if they are not, that
  is itself the finding).
- Also send to PostHog **only** when `NEXT_PUBLIC_POSTHOG_KEY` is configured,
  matching the existing env-guarded pattern. Never make telemetry a hard
  dependency.

**Do not** add an APM vendor, OpenTelemetry, or a metrics backend. This is
structured logging you can grep and aggregate; a vendor is a later decision that
this data should inform.

**Acceptance**

- [ ] A caption session with translation on produces at least one line per span.
- [ ] Timing failure (a raising logger, a missing key) never propagates to the
      caller — verified by a test that makes the recorder raise.
- [ ] Spans carry enough dimensions to answer "is Korean slower than English,
      and where" without another code change.
- [ ] Overhead is not measurable on the fast path (no I/O in the span itself).

**Verification**

- Unit tests for the context manager: records on success, records on exception,
  never swallows the original exception, never raises its own.
- Run a real session against mocks and paste the emitted `perf` lines into the
  Decisions Log entry.

---

## Task 2 — Ground the cultural translation in the slang KB

**Why — this is the reported bug.** `services/openrouter` builds its prompt from
model memory alone; it never touches the slang KB. Grep confirms no reference to
`get_slang_kb` anywhere under `services/openrouter/`. So caption slang handling
works only for terms that predate the model's training cutoff, and fails
*confidently* on anything newer — a plausible wrong meaning, which is worse than
an admission of ignorance.

`services/genz/kb.py` (`LocalSlangKB`) already does retrieval and is already
wired into `/genz/explain`. Reuse it. Do not build a second retriever.

**Approach**

1. In `backend/services/openrouter/real.py`, before building the prompt, retrieve
   the top-N matching terms for the source text from `get_slang_kb()`.
2. Inject them into the prompt as **grounding**, clearly framed as known
   definitions to prefer over the model's own recollection.
3. Extend the structured output so each slang note carries a
   **`grounded: bool`** (was it backed by a KB term) and keep the existing
   `confidence` semantics consistent with `services/genz/explainer.py` — known →
   high, unknown → low.
4. **Log a gap** when the model emits a note for a phrase the KB did not supply,
   via the same `slang_gap_log` path `/genz/explain` uses. That is what makes
   Task 3 possible.
5. **Bump `PROMPT_VERSION`.** The Redis cache key includes it (see the
   2026-07-21 Decisions Log entry), so a prompt change must invalidate cached
   output or you will serve pre-grounding answers indefinitely.

**Do not** change the two-lane architecture, the `ENHANCED_COST_RATIO` metering
weight, or the response shape the frontend already consumes beyond adding
fields.

**Acceptance**

- [ ] A phrase present in the KB produces a note marked `grounded: true` whose
      meaning matches the KB entry.
- [ ] A phrase absent from the KB still returns a translation, marks the note
      `grounded: false` with lower confidence, and writes a gap-log entry.
- [ ] Retrieval failure (KB unavailable) degrades to today's ungrounded
      behaviour and logs — translation must not fail because retrieval did.
- [ ] Cached responses from the previous `PROMPT_VERSION` are not served.
- [ ] Notes remain written **in the target language** (the 2026-07-23 rule).

**Verification**

- Unit tests with a stub KB: grounded hit, ungrounded miss, KB raising.
- Re-run the real-service QA harness pattern from the 2026-08-09 entry
  (en↔ko, 3 iterations) and report: translated-to-target rate, notes-in-target
  rate, and the new grounded-vs-ungrounded split. Prior baseline to beat or
  hold: **18/18 language, 51/51 notes localised**.

---

## Task 3 — Close the currency loop

**Why:** `slang_gap_log` (migration `0002_slang_kb.sql`) already records terms
users hit that could not be confidently explained. Nothing consumes it, so the
corpus never grows. This is the mechanism by which "stays current" actually
happens — no model update will do it for you.

**Approach**

- A script under `backend/scripts/` (alongside the existing `seed_slang.py`),
  run manually or on a schedule — **not** in the request path.
- Read unresolved gaps, resolve each into a KB entry, write it back through the
  existing `LocalSlangKB.add_term` / curation API in `app/routes/genz.py`.
- Resolution source is a decision to make explicitly and record: web search at
  ingest time is the only thing that keeps up with new coinage, and it is
  affordable here precisely *because* it is a batch job rather than per-request.
- **A human approval step is required before a term goes live.** This corpus
  feeds STT biasing, translation, and explanations; an auto-ingested wrong
  definition would propagate to all three. Write to a pending state and require
  promotion.

**Acceptance**

- [ ] Running the job against a seeded gap log produces pending entries, not
      live ones.
- [ ] Promotion moves a term into the KB and it is then retrievable.
- [ ] Re-running is idempotent — no duplicates.
- [ ] The job never runs during a request.

---

## Task 4 — Revisit `MIN_WINDOW_S`, with the data from Task 1

**Do not start this until Task 1 has a week of real sessions.**

`MIN_WINDOW_S = 2.0` in `backend/services/assemblyai/batch.py` is the floor on
Korean caption latency: Korean has no streaming model, so audio is buffered into
utterance windows. Lowering it cuts latency and gives the recogniser less
context, which costs accuracy.

**Approach**

- Sweep the value (e.g. 2.0 / 1.6 / 1.2) against a **fixed Korean audio set**,
  measuring both latency (`stt_window` from Task 1) and character-level accuracy
  after normalising spacing and Sino-Korean numerals — the harness lesson from
  the 2026-08-09 entry: an unnormalised scorer reported 75% where the true figure
  was 87–100%.
- Report the curve. Pick a point and **state the trade in the Decisions Log**.
- One sample is not a measurement. Use several utterances, and prefer human
  speech over TTS where possible — synthesised speech flatters a recogniser.

**Acceptance**

- [ ] A latency-vs-accuracy table across at least three values.
- [ ] The chosen value is justified against that table, not asserted.
- [ ] `test_batch_ordering.py` and `test_batch_silence.py` still pass.

---

## Explicitly out of scope

- Switching web framework. FastAPI is correct for this workload; Flask is sync
  and Django's value (ORM/admin/auth/migrations) is unused here — Supabase RLS is
  the enforcement layer.
- Replacing Google Translate with an LLM. It is the biggest **cost** lever
  (~$1.04 of the $1.40 translated hour) but it is not an accuracy fix, and it
  should be prototyped behind a flag against Task 1's data — a separate piece.
- Moving the usage snapshot to Redis. Needed **before running more than one
  worker** (`CACHE_TTL_S` in `backend/app/usage.py` is per-process, so N workers
  give N×15 s of possible overshoot). Not an accuracy or latency item; do it as
  part of deployment work.
- Transcript persistence / infinite scroll. Requires consent, encryption at rest
  and a retention policy (INTRODUCTION §6) — a feature, not a scroll change.
