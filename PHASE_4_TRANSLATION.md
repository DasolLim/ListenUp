# PHASE 4 — Translation (General + Enhanced + Combined Live)

**Prerequisite:** Phase 3 green. Reuse the tool shell + caption pipeline. Follow Error Protocol (§8).

**Goal:** General translation (Google v3), Enhanced cultural translation (OpenRouter LLM), and the headline **speaker-named multilingual live translation**.

---

## Step 4.1 — Google Cloud Translation v3 service + cache

**Prompt:**
> In `/backend/services/translate/`, build a Google Cloud Translation v3 service: text → translated text, with source auto-detect + target language param. Add a Redis cache keyed by (source_hash, target_lang) so repeated phrases cost nothing. Add a mock service for testing without API spend.

**Verification Gate (RUN):**
- Mock + real: text translates to target language.
- Second identical request → served from cache (verify cache hit, no API call).
- Unsupported/edge language → clear handled error.
- ruff + import checks pass.

---

## Step 4.2 — General translate UI

**Prompt:**
> Build the Translate → General page: text input + target-language picker → translated output. Add a voice→text→translate mode reusing the Phase 2 caption pipeline (transcribe, then translate finalized segments). Keep it accessible (WCAG 2.1 AA).

**Verification Gate (RUN):**
- Text mode translates correctly.
- Voice mode: speak → caption → translation appears.
- Keyboard + screen-reader accessible.
- Build/typecheck pass.

---

## Step 4.3 — OpenRouter enhanced (cultural) service

**Prompt:**
> In `/backend/services/openrouter/`, build an enhanced translation service calling an OpenRouter LLM. Prompt it to return STRICT JSON: `{translation, register, slang_notes:[{phrase, meaning, cultural_context, equivalent}]}`. Parse safely (strip code fences, handle malformed JSON with a retry/fallback). Cache results in Redis. Mock for testing. Make the model configurable via env.

**Verification Gate (RUN):**
- Given slang input → returns valid parsed JSON with notes.
- Malformed LLM output → handled (retry/fallback), never crashes.
- Cache hit on repeat.
- Model swappable via env.

**Error-check focus:** LLMs sometimes wrap JSON in prose/fences or return invalid JSON — parsing MUST be defensive.

---

## Step 4.4 — Enhanced translate UI + progressive enhancement

**Prompt:**
> Build Translate → Enhanced page. Implement progressive enhancement: show the fast Google v3 translation INSTANTLY, then asynchronously replace/augment with the OpenRouter result (register + slang notes) when it arrives. Never block the initial translation on the LLM. Display slang notes as expandable annotations.

**Verification Gate (RUN):**
- Fast translation appears first (<~300ms perceived).
- LLM annotation upgrades it a moment later without layout jank.
- If LLM fails → the fast translation still stands (graceful).

---

## Step 4.5 — Combined live: speaker-named multilingual translation ★

**Prompt:**
> Build the headline feature on the Enhanced Voice-to-Text/Translate flow: take the diarized + name-labeled caption stream (Phases 2–3), detect/attach each speaker's source language, translate each finalized segment to the user's chosen target language, and render captions as `Name (SourceLang): <translated text>`. Use progressive enhancement (Google instant → LLM annotate). Enforce the 4–5 speaker cap.

**Verification Gate (RUN):**
- Multi-speaker, mixed-language mock stream → each line labeled by speaker + translated to target.
- Names from Phase 3 profiles carry through.
- Instant translation, async cultural upgrade.
- Latency stays acceptable (measure p50/p95 end-to-end).

---

## Step 4.6 — Cost + cache audit

**Prompt:**
> Add lightweight per-request cost logging (STT minutes, Google chars, LLM tokens) to PostHog. Verify Redis caching meaningfully reduces repeat translation calls. Surface a simple dev dashboard/log of estimated cost per session.

**Verification Gate (RUN):**
- Cost events logged per request.
- Repeat-phrase sessions show high cache-hit ratio.
- Estimated session cost visible.

---

## Phase 4 Exit Criteria
- [ ] Google v3 general translation + Redis cache + mock.
- [ ] General UI: text + voice modes, accessible.
- [ ] OpenRouter enhanced service returns safe structured JSON.
- [ ] Enhanced UI with progressive enhancement (instant → LLM upgrade).
- [ ] ★ Combined live: speaker-named multilingual captions, cap enforced.
- [ ] Cost logging + cache effectiveness verified.
- [ ] Static checks green; all external calls have mocks + defensive parsing.

**Report:** demo — a mixed-language multi-speaker conversation rendered as speaker-named translated captions, with slang annotations appearing a beat after the instant translation.
