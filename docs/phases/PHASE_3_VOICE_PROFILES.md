# PHASE 3 — ★ Enhanced V2T: Saved Voice Profiles (ECAPA-TDNN)

**Prerequisite:** Phase 2 green. This is the key differentiator: captions labeled by NAME. Follow Error Protocol (§8).

**Goal:** Users enroll frequent contacts (20–30s voice) → the app labels those people by name in live captions, with consent + compliance built in.

**Compliance is part of THIS phase, not later** (INTRODUCTION §6).

---

## Step 3.1 — pgvector schema + consent records

**Prompt:**
> In Supabase, enable pgvector and create tables: `speaker_profiles` (id, owner_user_id, display_name, created_at), `speaker_embeddings` (id, profile_id, embedding vector(192), created_at), and `consent_records` (id, profile_id, consented_by, consent_text_version, consented_at, revoked_at). Add RLS so users only access their own profiles. Write migration files.

**Verification Gate (RUN):**
- Migration applies cleanly.
- pgvector extension enabled; `vector(192)` column accepted.
- RLS: a user cannot read another user's profiles (test with two users).

---

## Step 3.2 — ECAPA-TDNN embedding service

**Prompt:**
> In `/backend/services/speaker_id/`, integrate SpeechBrain ECAPA-TDNN (`speechbrain/spkrec-ecapa-voxceleb`). Build a function: audio (16kHz mono) → 192-dim embedding. Load the model once at startup (not per request). Runs on CPU. Add a mock that returns deterministic fake vectors for testing without loading the model.

**Verification Gate (RUN):**
- Model loads once at startup; startup logs confirm.
- Same voice clip → near-identical embedding across runs (cosine ~1.0).
- Two different voices → clearly lower cosine similarity.
- Mock path works for CI (no model download).

**Error-check focus:** first model download can fail/timeout — cache it, and give a clear error if the download or a bad audio format occurs.

---

## Step 3.3 — Enrollment flow + consent gate

**Prompt:**
> Build an enrollment UI: user names the person, records/upserts 20–30s of that person's voice via a guided script, and MUST check a consent box (recording the enrolled person's consent) before saving. On save: send audio to the embedding service → store embedding + consent_record. Block saving without consent. Support delete-profile (removes embeddings + records) and export-profile-data.

**Verification Gate (RUN):**
- Cannot save without consent checkbox → blocked with clear message.
- Successful enroll → embedding + consent_record persisted.
- Delete → all related rows removed (verify in DB).
- Export → returns the profile's stored data.
- <20s recording → warns/blocks with guidance.

---

## Step 3.4 — Runtime name-matching

**Prompt:**
> Extend the transcription pipeline: for each diarized speaker segment, buffer ~3–5s of that speaker's audio, compute an ECAPA-TDNN embedding, and cosine-match against the user's saved profiles. If best match > threshold (start ~0.6, make configurable), relabel that speaker with the person's name; otherwise keep the generic label. NEVER assign a name below threshold. Cache the speaker↔name mapping for the session so we don't re-embed every segment.

**Verification Gate (RUN):**
- Enrolled voice in a test stream → labeled by name.
- Unenrolled voice → stays "Speaker N" (no false name).
- Borderline/low-similarity → generic label (verify threshold behavior).
- Per-session caching: name assigned once, reused (check it's not re-embedding every segment).

**Error-check focus:** enrollment-vs-runtime audio mismatch (mic/noise) drops accuracy — log similarity scores during testing to tune the threshold on realistic audio, not clean clips.

---

## Step 3.5 — Tap-to-correct feedback loop

**Prompt:**
> Let the user tap a caption's speaker label and correct it (pick an existing profile or mark unknown). On correction, append the corrected segment's embedding to that profile (so each profile becomes several averaged embeddings → more robust). Update the session mapping immediately.

**Verification Gate (RUN):**
- Correcting a label updates current + future segments in the session.
- New embedding appended to the profile (verify row added).
- Profile now matches that person more reliably on a repeat clip.

---

## Step 3.6 — Speaker cap + edge cases

**Prompt:**
> Enforce the 4–5 speaker cap in the enhanced path too. Handle: overlapping speech (label uncertain rather than guessing), a person with a "sick"/altered voice (should still often match via multiple stored embeddings), and profiles across sessions.

**Verification Gate (RUN):**
- >5 speakers → capped/labeled "Other".
- Overlap segment → uncertain label, not a confident wrong name.
- Multi-embedding profile matches an altered-voice clip better than a single-embedding one.

---

## Phase 3 Exit Criteria
- [ ] pgvector schema + RLS + consent tables live and isolated per user.
- [ ] ECAPA-TDNN embeds consistently; mock path for CI.
- [ ] Enrollment blocked without consent; delete + export work.
- [ ] Runtime name-matching labels enrolled people, never forces wrong names.
- [ ] Tap-to-correct improves profiles over time.
- [ ] Speaker cap + edge cases handled.
- [ ] Static checks green; similarity thresholds tuned on realistic audio.

**Report:** demo — enrolled "Mom/Dad" appear by name in live captions; an unknown speaker stays generic; a correction sticks. Confirm consent gate + deletion work.
