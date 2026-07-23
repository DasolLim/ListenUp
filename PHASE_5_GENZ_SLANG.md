# PHASE 5 — GenZ / Slang Translator + Shareable Cards

**Prerequisite:** Phase 4 green. Follow Error Protocol (§8). This feature doubles as a marketing engine.

**Goal:** Explain modern slang/memes/abbreviations with cultural context, backed by a curated knowledge base, with shareable "translation cards."

---

## Step 5.1 — Slang knowledge base schema + seed

**Prompt:**
> Create a slang KB in Postgres + pgvector: `slang_terms` (id, term, meaning, origin, region, first_seen_date, example, embedding vector, created_at). Build a seed pipeline that can ingest entries (from Urban Dictionary / KnowYourMeme exports or a manual CSV) with region + date tags. Embed each term's text for retrieval. Start with a small curated seed set.

**Verification Gate (RUN):**
- Migration applies; pgvector column works.
- Seed pipeline ingests a sample CSV → rows + embeddings present.
- Vector similarity query returns relevant terms.

---

## Step 5.2 — RAG retrieval + LLM explanation

**Prompt:**
> Build a GenZ explanation service: given input text, retrieve the most relevant slang terms from the KB (vector search), inject them as context into an OpenRouter LLM prompt, and return a structured explanation: `{term, plain_meaning, origin, first_seen, region, example, adult_friendly_explanation}`. Fall back gracefully if the KB has no match (LLM-only with a lower-confidence flag). Cache results.

**Verification Gate (RUN):**
- Known slang → explanation grounded in KB context.
- Unknown slang → LLM-only answer flagged lower-confidence, no crash.
- Structured JSON parsed defensively (same discipline as Phase 4.3).
- Cache hit on repeat.

---

## Step 5.3 — GenZ UI

**Prompt:**
> Build Translate → GenZ page: input a word/phrase → show the structured explanation (meaning, origin, first-seen, region, example, adult-friendly note). Keep it accessible (WCAG 2.1 AA). Handle empty/low-confidence states clearly.

**Verification Gate (RUN):**
- Explanation renders cleanly for known + unknown terms.
- Low-confidence state is visually clear.
- Keyboard + screen-reader accessible.
- Build/typecheck pass.

---

## Step 5.4 — Shareable translation cards

**Prompt:**
> Add a "share card" generator: render an explanation as a clean, branded image/card (e.g. via an HTML→image approach or an SVG template) suitable for social sharing, with a copy/download button. No external branding/IP; original design only.

**Verification Gate (RUN):**
- Generate a card from an explanation → correct content, readable.
- Download/copy works.
- No layout breakage on long terms.

---

## Step 5.5 — KB maintenance hooks

**Prompt:**
> Add a lightweight admin/ingest path to add or update slang entries over time (slang ages fast). Log which terms users search that AREN'T in the KB (gap list) to guide future curation.

**Verification Gate (RUN):**
- Add a new term → immediately retrievable.
- Searched-but-missing terms are logged to a gap list.

---

## Phase 5 Exit Criteria
- [x] Slang KB schema + seed pipeline + vector retrieval. _(migration 0002 pgvector applied live + RPC verified; 32-term seed; hashing embedder; local KB retrieval)_
- [x] RAG + LLM explanation with graceful unknown-term fallback. _(known → grounded high; unknown → LLM-only low + gap-logged; KB fallback when LLM down)_
- [x] GenZ UI accessible + handles low-confidence. _(axe clean incl. high-contrast; verified/unverified states)_
- [x] Shareable cards generate + download. _(canvas → PNG, copy/download, long-term wrap verified)_
- [x] KB maintenance + gap logging. _(/genz/terms add/update auth API; /genz/gaps backlog)_
- [x] Static checks green; defensive JSON parsing; caching verified. _(ruff+mypy+eslint+tsc clean; 61 backend tests; cache hit test)_

**Status: COMPLETE (2026-07-22).** Demo: `explain("rizz")` → grounded high w/ KB origin/first-seen; `explain("menty b")` → low-confidence LLM answer, logged to the gap list for curation.

**Report:** demo — explain a current slang term end-to-end and produce a shareable card. Note the gap-list as the seed for ongoing curation.

---

## Post-Phase-5: Hardening Checklist (before public launch)
- [ ] End-to-end WCAG 2.1 AA audit with a real assistive-tech user.
- [ ] Privacy: audio not stored by default; transcripts opt-in; encryption at rest; retention policy documented.
- [ ] Biometric consent + deletion + export verified across all profiles.
- [ ] Cost model → free-tier limits (e.g. 30 min/day) enforced.
- [ ] Load/latency test end-to-end (mic → caption) at p95 under target.
- [ ] Sentry/PostHog dashboards reviewed; alerting on error spikes.
- [ ] All external services have mocks + graceful degradation on outage.
- [ ] `DEBUG_LOG.md` reviewed; recurring issues addressed at the root.
