# ERROR_FIXED — Defect Discovery, Diagnosis & Resolution Report

**Project:** ListenUp (accessible live captions + cultural translation)
**Scope:** Phases 0–5. Complements `DEBUG_LOG.md` (15 raw incident rows) — this document reports the *method*, not the ledger.
**Current quality state:** 131 backend tests passing · ruff / typecheck / lint / build green · axe 0 violations (both contrast modes).

---

## 1. Defect Management Workflow (Scrum SDLC)

- **Sprint unit = one phase step.** `PHASE_0 → PHASE_5`, one step at a time; no parallel work-in-progress.
- **Definition of Done (per step, non-negotiable):**
  - Feature implemented **+ tests written alongside it**, never after.
  - Static gates pass: `ruff` · `pytest` · `tsc --noEmit` · `eslint` · `next build`.
  - Step's **Verification Gate** passes. A red gate blocks advancement — no exceptions.
  - Accessibility check where UI changed (axe, both contrast modes). A11y failures are **build-breaking**, not backlog items.
  - Defect + resolution appended to `DEBUG_LOG.md`; decision rationale to `CLAUDE.md`.
- **Escalation rule:** stop after **2 failed attempts** on the same error; re-derive root cause instead of iterating blindly.
- **Regression policy:** every field-reported bug becomes a **failing test first**, then a fix.

---

## 2. Standard Debugging Playbook

Applied to every defect below, in order:

1. **Reproduce deterministically** — script the failure; no fixing from a description.
2. **Isolate the variable** — bisect payloads/params/inputs until one change flips the result.
3. **Read the whole trace** — state root cause in **one sentence** before touching code.
4. **Verify the assumption against the source of truth** — vendor type definitions (`lib.dom.d.ts`), API error bodies, live DB — not memory.
5. **Fix the class, not the instance** — prefer a change that makes the bug category impossible.
6. **Prove the test catches it** — revert the fix; confirm the new test *fails*. Guards against vacuous tests.
7. **Re-run full suite** — confirm no regression, then log.

---

## 3. Case Studies

### CS-1 — Speaker identity named the *previous* speaker (Critical, field-reported)

- **Symptom:** With 3 enrolled profiles, alternating speakers were labelled as the previously-spoken person "for a while" before self-correcting.
- **Identification:**
  - Built a **synthetic perfect-discriminator** harness (same-voice cosine `1.000`, cross-voice `~0.0`) to *isolate naming logic from embedding quality* — any failure is then provably logic, not the model.
  - Simulated 3 real diarization behaviours: stable labels, label reuse, label lag.
  - Instrumented state after the run: `attempts=1, done=True` after **five turns by three different people**.
- **Root cause:** Identity was resolved **once per diarization label and frozen** (`done=True`), making the *label* the identity. Streaming diarization reuses labels and attributes a new speaker's turn-start to the previous label, so every later turn returned the cached name **without re-examining audio**.
- **Fix:** Identify **every final turn from its own audio**.
  - `done` → `overridden` (tap-to-correct is now the *only* sticky name).
  - A match decides its turn outright, **including back to `None`** — a stale confident name is the bug.
  - Three sub-defects found during QA, each fixed as a rule in `turn_audio()`:
    1. Reaching back for extra audio blended two speakers → a turn that can stand alone is judged alone.
    2. Continuous speech makes *every* join look contiguous → borrow only across sub-0.75s gaps **and only audio nobody has been credited with** (`window_owners`).
    3. Refusing to judge <2s turns left fast dialogue 0% named → judge ≥1s turns but require an extra **0.10** confidence margin (weak evidence demands a stronger result, never stitched-on speech).
  - Contract repair: `speakerUpdate` now carries `fillOnly` — automatic naming may only fill *unnamed* bubbles, since one label now legitimately covers several people.
- **Verification:**

  | Harness | Metric | Before | After |
  |---|---|---|---|
  | Synthetic, 910 turns, 5 diarization × noise/quiet-mic/short-turn | Wrong-name rate | 0.55% | **0.00%** |
  | " | Accuracy | 92.7% | **99.8%** |
  | " | Short turns (0.8–1.8s) named | 0% | **96.7%** |
  | **Real ECAPA**, human fixtures (same 0.907 / cross 0.088) | Accuracy | 75.0% | **100.0%** |
  | " | Wrong names | 6 | **0** |

  - +6 unit tests; **confirmed non-vacuous** — 3 fail when the frozen behaviour is restored.

### CS-2 — Enhanced captions never used enrolled names (Critical)

- **Symptom:** Always "Speaker N"; enrolled profiles never matched.
- **Root cause — three compounding faults**, which is why single-cause hunting failed:
  1. Test profiles held **mock** embeddings (L2=√192) incompatible with real ECAPA → cosine ≈ 0, never matched.
  2. Ambiguity margin compared against the raw runner-up, so a **duplicate enrollment of the same person** read as "too close to call".
  3. 2s audio + give-up-after-3-attempts was too fragile for real mic/diarization.
- **Fix:** purge mock profiles; margin now compares against the best **differently-named** profile (guards *different people*, not duplicates); threshold 0.6 → 0.55; more audio + retry-on-growth; added `naming_attempt` / `speaker_match` logs.
- **Verification:** real STT + ECAPA E2E naming at 0.88–0.91 similarity.
- **Lesson:** *fixture/runtime parity* — test data generated under a mock silently invalidates a real-model path.

### CS-3 — Prompt fixes had no effect (cache masking)

- **Symptom:** Cultural translation kept returning literal output after repeated prompt rewrites.
- **Identification:** Changes appeared inert → suspected caching before prompt quality; confirmed by cache-key inspection.
- **Root cause:** Redis cache key lacked a **prompt version**, so stale pre-fix results were served indefinitely.
- **Fix:** `PROMPT_VERSION` added to the cache key; prompt rewritten slang-for-slang with few-shot en↔ko; model upgraded to gpt-4o.
- **Verification:** 10/10 en↔ko slang cases adapted correctly.
- **Lesson:** **any input that changes output must be in the cache key.** Re-applied later as a *preventive* control (see CS-4).

### CS-4 — Test passed alone, failed in suite (test-quality defect)

- **Symptom:** New TTS expressiveness test green in isolation, red in the full run.
- **Identification:** Ordering-dependent → suspected shared state; traced to a **process-wide singleton cache**: the first call was served from another test's entry and never reached the provider.
- **Fix:** unique UUID phrase per run → **order-independent** (chosen over resetting globals, which hides coupling rather than removing it).
- **Bug found *because* of the flake:** expressiveness was absent from the cache key — the first rendered setting would replay for every later one (CS-3's lesson, caught proactively). Regression test asserts both.

### CS-5 — Stale field list silently disabled clamping (caught by gate, not by eye)

- **Symptom:** None observable. `tsc` failed after adding 4 shape dimensions.
- **Root cause:** `clampShape` enumerated fields **by hand**; new dimensions reached the audio graph unclamped.
- **Fix:** derive from `SHAPE_LIMITS` keys — **eliminates the bug class**, not the instance.
- **Lesson:** a typed gate converted a latent runtime defect into a compile-time failure. Prefer derived structures over parallel hand-maintained lists.

### CS-6 — Platform/API assumptions (bisect-driven, representative)

| Defect | Root cause | Fix |
|---|---|---|
| Korean STT returned nothing (400) | Async API **deprecated singular `speech_model`**; requires `speech_models` as a **list**. Isolated by bisecting the payload param-by-param | Send `speech_models: ["universal-2"]` → Korean accuracy 0% → 90% |
| Glass blur not applied | Lightning CSS merged hand-written `backdrop-filter` + `-webkit-` pair and emitted only the `-webkit-` form | Write only the standard property; never hand-prefix |
| Captions drifted into Chinese | Default streaming model natively code-switches 18 languages | Pinned `universal-streaming-english` |
| White-on-coral 2.75:1 (a11y, build-breaking) | Ambient brand coral was never AA-safe as an interactive background | Split tokens: `--accent-strong #B84A22` for interactive use |
| Browser voice cache empty forever | `getVoices()` is async; cached once at mount, and Chrome doesn't reliably fire `voiceschanged` | Re-read live at call time; mount effect only primes |

---

## 4. QA Strategy

- **Test pyramid**
  - **Unit / integration:** 131 backend tests across 18 modules; external APIs always mocked (cost control, INTRODUCTION §6).
  - **Property-style QA harnesses:** parameterised sweeps (diarization × noise × turn-length × speaker-count) measuring **accuracy and wrong-name rate**, not just pass/fail.
  - **Real-model gates:** run against real ECAPA / real STT / real LLM before declaring a phase done — mocks prove logic, not behaviour.
  - **Accessibility:** axe on every page, both contrast modes; 44px touch-target audit.
- **Key QA principles applied**
  - **Isolate the variable under test** — a perfect-discriminator mock proves a logic bug is logic (CS-1).
  - **Prove the test fails without the fix** — no vacuous green (CS-1).
  - **Order-independent tests** — no reliance on suite sequence (CS-4).
  - **Measure the harmful metric directly** — "wrong-name rate" drove CS-1, since accuracy alone hides *confidently wrong* output.
  - **Mock/runtime parity** — mock-generated data must never leak into real-model paths (CS-2).

---

## 5. Defect Metrics

| Category | Count | Notes |
|---|---|---|
| Logged incidents (`DEBUG_LOG.md`) | 15 | Root-caused and resolved |
| Critical (wrong user-facing output) | 4 | CS-1, CS-2, CS-3, Chinese drift |
| Vendor/API contract breaks | 3 | Deprecated field, code-switching default, CSS compiler |
| Accessibility (build-breaking) | 2 | Contrast, touch targets |
| Test-quality defects | 2 | Suite pollution, fixture/runtime mismatch |
| Found by automated gate before runtime | 2 | CS-5 (typecheck), CS-4 (suite ordering) |
| **Defects with multiple compounding causes** | **2** | CS-1 (4), CS-2 (3) — single-cause assumptions were the main time sink |

---

## 6. Preventive Controls Adopted

- Cache keys must include **every** output-affecting input (prompt version, model, voice, expressiveness).
- Derive structures from a single source of truth; never maintain parallel field lists.
- `.env` loads via `os.environ.setdefault` so shell overrides win; tests pin mocks in `conftest.py`.
- Never force a name below confidence — **generic beats confidently wrong** (INTRODUCTION §5.7); enforced in code and asserted in tests.
- `rm -rf frontend/.next` after any route restructure (stale generated types).
- Capability honesty: if a tier can't do something, **disable it and state why** rather than shipping an inert control.

---

## 7. Open Items

- **Cloned voices unusable (found, not yet fixed).** `_voice_from_row` in `app/routes/tts.py` has **no callers**; `GET /tts/voices` never queries `custom_voices`, so a saved custom voice can be created and listed but never selected to speak. Currently masked because cloning is disabled (no ElevenLabs key). ~10-line fix.
- **No frontend test infrastructure.** No runner, no test deps, zero test files; CI runs only typecheck/lint/build. Speech-provider regressions would ship silently. Recommend Vitest + `@testing-library/react`.
- **CS-1 not yet validated in a live 3-person session.** Real-ECAPA evidence comes from ~5s fixtures (24 turns). The new `speaker_named ... was=X` log lines make a live audit straightforward.
- **Cross-platform voice matching verified by simulation only** (macOS/Windows/Android/Chrome inventories), not on real Windows/Android hardware.
