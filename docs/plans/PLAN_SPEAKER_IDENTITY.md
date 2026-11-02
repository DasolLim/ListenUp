# PLAN — speaker identity: accuracy and consistency for 1–5 speakers

Goal, in the user's words: **high accuracy and consistent identification of
enrolled and unenrolled speakers, 1–5 people.** Enrolled today are David, Mom
and Julie.

Four tasks, in order. Each is independently shippable and independently
revertible. **Do one at a time**, run its gate, commit, then move on
(CLAUDE.md §Conventions 1–2).

Task 1 exists so Tasks 2–4 are decided with numbers instead of opinion. It is
the only task that is *blocking*: everything after it is tuning, and tuning
without a metric is how thresholds get fitted to three wav files.

---

## Where this starts from

Already shipped (do not rebuild):

- `app/session_speakers.py` — per-session voice clustering, no enrolment
  required. Three bands: join at/above `SPEAKER_CLUSTER_THRESHOLD` (0.55), split
  below `SPLIT_FLOOR` (0.45), keep the label's voice in between.
- `SessionSpeakers.reconcile()` — retroactive re-clustering after every final
  turn; emits `speakerMerge`, and the client relabels captions already drawn.
- Identity bound to the **voice**, not the turn: `Voice.evidence` accumulates
  summed match similarity per profile; `Voice.identity()` names it once one
  profile clears `NAME_EVIDENCE` (0.85) and `NAME_EVIDENCE_MARGIN` (0.35).
- `SpeakerMapper` — monotonic numbering, never recycles a released number;
  `alias()` folds one label onto another and frees cap capacity.

Known-open, in priority order: **no way to measure any of this** (3 recordings,
2 people), single-scale embedding windows, no enrolment prompt at the moment of
need, no smoothing.

### Measured facts to build on (do not re-derive)

| | value | where measured |
|---|---|---|
| Real ECAPA, same person, two recordings | 0.957 | `sam1` vs `sam2` |
| Real ECAPA, different people | 0.388 (mock) / ~0.09 (real) | `sam1` vs `dan1` |
| Windows within one recording | 0.828 | 2 s windows of `sam1` |
| ECAPA embed, 0.75 s audio | **11 ms** | this machine, CPU |
| ECAPA embed, 1.5 s audio | **14 ms** | " |
| ECAPA embed, 3.0 s audio | **22 ms** | " |
| ECAPA reliability floor | 1.0 s window scores 0.633; 0.6 s scores 0.478 and fails | 2026-07-30 entry |

The embed timings matter for Task 2: three scales cost **~47 ms** per final
turn. `pump_segments` awaits `namer.identify()` *before* queueing the caption,
so this is on the caption latency path — but 47 ms against a <1 s budget is
affordable, so **no architectural decoupling is required**. Do not add an async
naming channel "for latency"; it is not needed and would be scope.

---

## Invariants — these hold for every task below

- **Gates green before a task is done.** Backend: `ruff check .` and `pytest`
  (currently **451 passing**). Frontend: `npm run typecheck`, `npm run lint`,
  `npm run build`, `npm run verify`.
- **Tests alongside the change, never after** (§Conventions 4). Every new test
  must be shown to **fail against the pre-change code** — revert the change,
  watch it fail, restore it. A test that passes both ways proves nothing. This
  has caught four vacuous tests in this area already; budget for it.
- **Mocks pinned by `conftest.py`.** No task may require live credentials to run
  the suite. Real-ECAPA tests are opt-in (see Task 1) and must skip cleanly when
  `speechbrain` or the model cache is absent.
- **Never run a one-off script outside pytest against the transcribe path.**
  `conftest.py` is the only thing pinning mocks; a standalone script inherits
  nothing and will hit the live AssemblyAI account. This has already cost two
  billed sessions.
- **Captions must never break.** Anything on the transcribe path fails *open*: an
  embedding, clustering or naming failure degrades identification and logs
  loudly, it never refuses to caption.
- **Wrong name > no name is inverted here**: a wrong name is worse
  (INTRODUCTION §5.7). When a change trades split-risk against merge-risk,
  prefer the split — it is visible and correctable; a merge is neither.
- **Append a dated entry to the Decisions Log in `docs/logs/DECISIONS.md`** when a task lands,
  stating what was *measured*, not just what was built.
- **No adjacent refactors.** Each diff should read as one change.

---

## Task 1 — Evaluation harness (BLOCKING) — ✅ DONE 2026-08-17

Baseline in the decisions log. Two bugs found by building it: the display
label keyed on the provider label (production, fixed), and four TTS voices
rendering as the system default (harness, guarded). `trio-short-churn` is
the row Task 2 must move: 0.167 confusion, 0.67 split, 0.58 naming, 5 churn.

**Goal.** A single command that reports how good speaker identification actually
is, on sessions with known ground truth, using real ECAPA.

**Why first.** Every threshold in `session_speakers.py` is currently tuned
against 3 recordings of 2 people. The stated goal is 1–5 speakers, enrolled and
unenrolled. There is presently no way to know whether a change helps.

### Files

- `backend/scripts/build_speaker_corpus.py` (new) — generates the audio corpus.
- `backend/scripts/speaker_metrics.py` (new) — pure metric functions.
- `backend/scripts/eval_speaker_id.py` (new) — runs sessions, prints the table.
- `backend/tests/test_speaker_metrics.py` (new) — unit tests for the metrics.
- `backend/services/speaker_id/fixtures/` — corpus lands in a gitignored
  subdirectory; **do not commit generated audio**.

### Corpus

Ground truth is exact because sessions are *constructed*: a session is a list of
`(speaker_id, wav_path, start_s, end_s)`.

Sources, in order of preference:
1. The three real human fixtures (`sam1`, `sam2`, `dan1`) — 2 real people.
2. macOS `say` voices for breadth to 5 speakers. **25 English voices are
   installed but many are novelty** (Bells, Boing, Bubbles, Cellos, Wobble,
   Jester). Use human-like ones only: Samantha, Alex, Daniel, Karen, Moira,
   Tessa, Fred, Victoria.
3. Real recordings from the user, if supplied later — these supersede TTS.

**Validation guard, non-negotiable.** `say -v ?` lists voices that are not
installed and write ~0.02 s of silence while exiting 0. This has already
produced a fabricated 22.6% accuracy figure. Every generated clip must be
rejected unless it passes **both**: duration ≥ 80% of expected, and RMS above a
silence floor. Fail loudly on rejection; never silently skip.

State plainly in the output that TTS voices are a **proxy**: ECAPA may separate
synthetic voices more cleanly than real ones, so absolute numbers are an upper
bound and only the *comparison between runs* carries.

### Scenarios (minimum set)

| id | speakers | shape | what it probes |
|---|---|---|---|
| `solo` | 1 | 10 turns, one voice | the reported bug; any split is wrong |
| `pair` | 2 | alternating, 3–8 s turns | the common case |
| `pair-short` | 2 | alternating 1–2 s turns | the ECAPA reliability floor |
| `trio` | 3 | David/Mom/Julie-shaped | the user's actual setup |
| `five` | 5 | round-robin | the stated upper bound, and the 4-speaker cap |
| `dominant` | 3 | one speaker 80% of turns | evidence imbalance |
| `late-joiner` | 3 | third speaker enters at turn 8 | new voice mid-session |
| `pauses` | 2 | 20 s+ gaps between turns | churn triggered by pauses |

### Metrics (in `speaker_metrics.py`, pure, unit-tested)

Computed over **final turns only**, comparing displayed label to ground truth.

1. **Confusion rate** — fraction of turns whose displayed identity maps to the
   wrong true speaker. *The headline number.*
2. **Split rate** — `(distinct labels shown for a true speaker) − 1`, summed over
   speakers, divided by speaker count. `0` = nobody was fragmented. *This is the
   reported bug.*
3. **Merge rate** — count of displayed labels that carry turns from more than one
   true speaker. *The dangerous error; must stay at 0.*
4. **Count error** — `|distinct labels shown − true speaker count|`.
5. **Name accuracy** (enrolled only) — fraction of an enrolled speaker's turns
   showing their correct name rather than a generic label.
6. **Name churn** (enrolled only) — number of times a speaker's displayed
   identity changes. Ideal is ≤1 (unnamed → named). *This is the David →
   Speaker 1 → David symptom.*
7. **Turns to first name** — how long an enrolled speaker waits to be named.

**The metrics themselves must be unit-tested** against hand-built cases with
known answers, including the degenerate ones (single speaker, all-wrong, perfect,
empty). A wrong metric is worse than no metric: this repo has already scored a
correct Korean transcript as 75% because the scorer counted `세 시`→`3시` as an
error.

### Running it

Two modes:

- `python scripts/eval_speaker_id.py` — mock embedder, fast, CI-safe, used to
  check the harness itself works.
- `SPEAKER_ID_SERVICE=real python scripts/eval_speaker_id.py` — real ECAPA. This
  is the mode whose numbers count.

Output: one row per scenario, plus a total. Write results to
`backend/scripts/eval_results/<date>.json` so runs are comparable.

### Tests

- `test_speaker_metrics.py`: each metric against hand-built ground truth,
  including perfect, all-wrong, single-speaker, and empty input.
- A guard test that the corpus builder **rejects silent clips** (feed it a
  0.02 s silent wav, assert it raises).

### Validation gate — Task 1 is done when

- `pytest` green (451 + new metric tests).
- Both eval modes run end to end without a live API call.
- A **baseline table is committed** to the decisions log (`docs/logs/DECISIONS.md`) with real
  ECAPA numbers for all 8 scenarios.
- The baseline explicitly records `merge rate = 0`; if it is not 0, stop and fix
  that before any further task.

**Do not tune any threshold in this task.** Measure only.

---

## Task 2 — Multi-scale embedding windows — ❌ TRIED AND REVERTED 2026-08-18

**Built, measured, reverted under this task's own gate.** Implemented exactly as
specified below (full + 1.5 s + 0.75 s centred views, scored max-over-views,
only the full window remembered), with 8 window tests and 3 scoring tests, all
three mutations caught.

**Result: zero change on all 12 scenarios**, for +11 ms (1 s turn) to +25 ms
(3 s+ turn) per final turn on the caption path.

**Why it cannot work as specified, and this is the part worth keeping.** Every
scale here is a *subset* of the turn's own audio, and for a fixed turn the full
window is always the most informative view. Taking the max over subsets
therefore returns the full window's score essentially always. The short-turn
weakness is *too little audio*, and sub-windows have strictly less of it — a
1.0 s turn yields a 0.75 s view, which measures 0.478 against a 0.55 threshold.

Multi-scale works in NeMo's MSDD because it drives **segmentation**: short
windows locate speaker boundaries at fine temporal resolution while long ones
identify, and the scales are fused with learned weights across a whole
recording. It is not a way to get more out of one already-bounded turn.

**Where the evidence actually points.** Sub-windows can only help when the full
window is *contaminated* — two speakers inside one turn. The useful version of
this idea is therefore not multi-scale scoring but **contamination detection**:
embed the first and second halves, and when they disagree strongly, treat the
turn as untrustworthy rather than as evidence for anybody. That is a different
feature, it needs a scenario the eval does not yet model (mid-turn speaker
change), and it should be specified on its own before anyone builds it.

Original specification retained below for the record.

### Original specification

**Goal.** Cut the confusion and split rates on short turns by embedding each turn
at several window lengths instead of one.

**Why.** Measured: a 1.0 s window scores 0.633 for the right person while 0.6 s
scores 0.478 and fails. Short turns are where naming fails and where evidence
accumulates too slowly to name a voice. Long windows discriminate better; short
windows locate boundaries better. Single-scale forces a trade; multi-scale does
not. This is the core of NVIDIA NeMo's MSDD.

### Files

- `backend/app/naming.py` — `turn_audio()` gains a sibling `turn_windows()`.
- `backend/app/session_speakers.py` — scoring a turn becomes max-over-scales.
- `backend/tests/test_naming.py`, `test_session_speakers.py`.

### Design

Produce up to three windows per final turn, from the audio `turn_audio()`
already selects:

- **full** — the whole turn, capped at `MAX_MATCH_AUDIO_S`.
- **1.5 s** centred, if the turn is longer than that.
- **0.75 s** centred, if the turn is longer than that.

Rules:

- Windows shorter than the turn are **centred**, not taken from the start:
  turn-initial audio is where diarization most often bleeds in the previous
  speaker.
- A turn shorter than a scale simply does not produce that scale. Never pad.
- All produced embeddings go into the voice's gallery, so `Voice.similarity()`
  (already max-over-gallery) naturally benefits.
- Scoring a turn against a voice is **max over the turn's scales**, then the
  existing three-band rule is unchanged.

**Cost: ~47 ms per final turn** (11 + 14 + 22 measured). On the caption path,
affordable against the <1 s budget. Interim identification keeps its existing
bounded path (`MAX_INTERIM_EMBEDS_PER_TURN`) — **do not** multi-scale interims,
they run several times a second.

Gallery pressure: three embeddings per turn instead of one will hit
`GALLERY_CAP` (12) three times faster. Raise it to ~24 **or** store only the
best-scoring scale in the gallery. Prefer the latter; measure both in Task 1's
harness and keep the one that wins.

### Tests

- Window generation: a 5 s turn produces 3 scales; a 1.0 s turn produces 1; a
  0.5 s turn produces none and falls back to the existing short-turn path.
- Windows are centred, not head-anchored (assert offsets).
- No padding: every produced window's length equals its nominal scale.
- Interim path is untouched — assert interim embeds per turn still respect
  `MAX_INTERIM_EMBEDS_PER_TURN`.
- **Mutation**: force single-scale, confirm the scale tests fail.

### Validation gate — Task 2 is done when

- `pytest` green.
- Eval harness re-run with real ECAPA shows, versus the Task 1 baseline:
  - **confusion rate down**, or unchanged on `pair`/`trio` and down on
    `pair-short`;
  - **merge rate still 0** — a merge regression blocks the task regardless of
    other gains;
  - p50 caption lag (`stt_window` span, `stage=caption`) up by **no more than
    100 ms**.
- The before/after table goes in the decisions log. If the numbers do not move,
  say so and revert — a change that costs 47 ms and buys nothing is a
  regression.

---

## Task 3 — Enrolment as an anchor — ✅ DONE 2026-08-18

One shared `SpeakerNamingNudge` in both transcripts. Verified in a browser:
absent before anyone speaks, present after two settled turns with unnamed
speakers, dismissed for good, enrolment link reaches `/settings`, 0 axe
violations in both contrast modes, no overflow at 390/834/1440, desktop pane
bottom still above the fold (884/900).

### Original specification

**Goal.** Get the primary user enrolled, because a known voice is a fixed
reference instead of a cluster that must be discovered.

**Why.** This is what enterprise gets free from participant identity and per-
channel audio. It is also the cheapest item here: enrolment already exists in
`components/profiles/VoiceProfiles.tsx`, reachable only from Settings, with no
prompt at the moment of need. The Translate voice pane has **no enrolment
affordance at all**.

### Files

- `frontend/components/translate/VoiceConversation.tsx` — add the nudge.
- `frontend/components/captions/LiveCaptions.tsx` — already has a naming hint at
  ~line 434; make the two consistent.
- No backend change.

### Design

- Show the nudge only when it would help: a session is running, at least one
  speaker is unnamed, and it has not been dismissed this session. Never during
  the first few seconds, and never more than once.
- Copy states the benefit, not the mechanism: naming a voice once means it is
  recognised next time. Follow ../product/PRODUCT.md voice — plain, second person, no
  cuteness.
- Route to enrolment without losing the session: link out, do not modal over a
  live transcript.
- Tap-to-correct already pins the **voice** (shipped), so a correction now
  survives diarization churn. Say so in the copy: correcting once is worth it.

### Tests

- `npm run verify` unaffected.
- Browser: nudge appears with an unnamed speaker, does not appear when everyone
  is named, dismisses, does not return in the same session.
- axe: 0 violations across the pane's states, both contrast modes.
- Responsive: 390/834/1440, no horizontal overflow, pane bottom stays above the
  fold on desktop (this has regressed twice — re-check after adding chrome).

### Validation gate — Task 3 is done when

Gates green, axe clean, and the nudge verified in a real browser run (not a
screenshot inspection) at all three widths.

---

## Task 4 — Transition-penalised smoothing — ❌ TRIED AND REVERTED 2026-08-18

Built with 4 tests and three mutations caught, then reverted: **no change at
any value (0.0 / 0.03 / 0.05 / 0.10 / 0.20), on clean audio or under noise.**

**Why, and it is a design trap rather than a tuning miss.** A test showed the
obvious implementation is unsafe: adding the bonus to the score that clears the
merge threshold means a large enough nudge merges two different people. Making
it safe means confining the bonus to *ranking* and thresholding on raw
similarity — but which branch `assign` takes is decided by raw scores and by the
label's own voice, so the ranking almost never changes the outcome. The safe
version is inert and the unsafe version does harm. There is no useful middle.

**What the attempt did leave behind**, both kept:

- `trio-runs-short` — real conversation comes in runs, not strict alternation,
  and every other scenario alternated on every turn. A suite made only of those
  cannot see anything that acts on "who spoke last".
- `--noise` — clean fixtures leave real ECAPA a ~0.09/0.9 gap, far too wide for
  any tie-break to matter, and nothing like one microphone in a room.

**The finding that matters more than the feature: under `--noise 0.5` the
merge-free invariant fails (2 merges), and enrolled naming collapses to 0.00.**
That is the first thing the harness has caught the system doing wrong, and it is
much closer to the user's real conditions than the clean corpus. It should be
the next task.

### Original specification

**Goal.** Stop one ambiguous turn from flipping a speaker, without preventing
genuine speaker changes.

**Why.** A cheap approximation of VB-HMM resegmentation, which is what research
systems use to remove exactly this flicker. **Note: no smoothing exists today** —
an earlier claim in conversation that `SMOOTHING_WINDOW_S` existed was wrong.

### Files

- `backend/app/session_speakers.py` — `assign()` scoring.
- `backend/tests/test_session_speakers.py`.

### Design

Add a **stickiness bonus** to the voice that owned the previous final turn:

```
score(voice) = similarity(voice, embedding) + (STICKINESS if voice is previous else 0)
```

- `STICKINESS` default ~0.05, env-tunable as `SPEAKER_STICKINESS`.
- Applies only to the *join* decision. It must **not** lower `SPLIT_FLOOR`:
  positive evidence of a different person still splits, or this reintroduces the
  merge error in a new place.
- Decays to zero after a long gap (reuse `CONTIGUOUS_GAP_S` semantics): a pause
  is exactly when the speaker is most likely to have changed, so stickiness
  across a pause is backwards.

### Tests

- A borderline turn from the previous speaker stays with them.
- A clearly-different turn still splits, stickiness notwithstanding.
- Stickiness does not apply after a long gap.
- Stickiness cannot promote a voice past `SPLIT_FLOOR` protection.
- **Mutation**: set `STICKINESS = 0`, confirm the borderline test fails; set it
  to 0.5, confirm the split test fails. Both directions matter.

### Validation gate — Task 4 is done when

- `pytest` green.
- Eval harness: **name churn down**, merge rate still 0, confusion rate not
  worse. If stickiness trades confusion for churn, keep churn — but say so with
  the numbers.
- Chosen `STICKINESS` value justified by a small sweep (e.g. 0.0 / 0.03 / 0.05 /
  0.10) recorded in the decisions log, not picked by intuition.

---

## Task 5 — The ambiguous band on an unseen label — ✅ DONE 2026-08-18

Not in the original plan. Task 1's harness left one scenario failing —
`trio-short-churn` at 0.167 confusion / 0.67 split / 5 churn — and Tasks 2 and 4
were both attempts to move it that were built, measured and reverted. Tracing
the scenario turn by turn instead of tuning found a one-line cause.

**All three of one speaker's ambiguous turns were creating new voices.** The
middle band (`SPLIT_FLOOR` ≤ score < threshold) had two different answers
depending on the *label*: a label already carrying a voice kept it, a label the
provider had not used before fell through and created a speaker. With a
churning provider every label is new, so ambiguity always resolved to "another
person" — the label acting as the tie-break, which is the assumption
`SessionSpeakers` exists to remove.

The asymmetry is not justified by the audio. Measured on real ECAPA:

| window | same speaker | different speakers |
|---|---|---|
| full sentence | 0.696 – 0.907 | 0.088 – 0.272 |
| 1.0 s | 0.342 – 0.721 | 0.083 – 0.242 |

A short window makes a voice a noisier sample of *itself*; it barely moves how
much it resembles anyone else. So a score above the floor is weak evidence of
sameness and still strong evidence of not-difference, and continuity is the
right answer to it whether or not the label is familiar.

**Result (real ECAPA, 5 speakers, 3 enrolled, clean):** `trio-short-churn`
0.167 → **0.000** confusion, 0.67 → **0.00** split, 5 → **3** churn, 0.58 →
**0.75** naming. Confusion and split are now **0.000 across all 13 scenarios**,
merges **0**. The residual 3 churn is one unnamed→named upgrade per speaker,
which is the designed floor — never force a wrong name (INTRODUCTION §5.7).

A margin rule was measured first and rejected: on the later turns the two
nearest voices were *both* the same person at 0.585/0.557 and 0.529/0.527, so a
margin requirement would have blocked the correct join. The small gap was
evidence of the earlier fragmentation, not of ambiguity.

Both halves of the rule mutate-fail (deleting it, and dropping the floor guard
so it joins whatever is nearest — 1 and 8 tests). **484 backend tests.**

*Six reconciliation tests had to be repaired rather than passing: they forced a
split by raising the merge bar and using a fresh label, which is exactly the
recipe this rule now defeats, so they could no longer reach the code they name.
One of the six — the label-remap test — had already been passing vacuously with
one voice. They now raise the split floor as well, via a fixture that says why.*

---

## Explicitly out of scope

- **VB-HMM / VBx resegmentation** — needs frame-level posteriors the pipeline
  does not produce. Weeks of work.
- **EEND** — replaces the embed-then-cluster stack and wants a GPU, which
  contradicts the CPU-only constraint.
- **Overlap detection** — a real slice of diarization error, but a separate
  model and a separate project.
- **Raising the 4-speaker cap to 5** — tempting given the 1–5 goal, but it needs
  a fifth speaker tint and rail in `globals.css` plus AA-contrast verification.
  Do it as its own change, with the design system in hand, not folded into Task 2.

---

## Honest ceiling

Published DER on hard conversational audio is 15–20% for state-of-the-art
systems; clean two-speaker telephone reaches 2–5%. Enterprise meeting products
appear near-perfect mostly because per-participant channels make attribution
*metadata* rather than inference — a problem this product cannot avoid with one
microphone. For 1–5 speakers taking clean turns in a quiet room, considerably
better than 15% is reachable. Two people talking over each other is not.

The number that matters for this product is not DER. It is **name churn**: a
deaf user following a conversation needs David to stay David. That is the metric
to optimise, and it is the one enterprise products mostly do not even attempt
for in-person audio.
