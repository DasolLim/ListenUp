# Claude Code Build Prompts — How to Use

A phased, error-checked build plan for the accessibility + translation SaaS. Feed these to Claude Code in order.

## Files (in order)
1. **INTRODUCTION.md** — read first. Scope, stack, tools, rules, error protocol. Claude Code should read this before anything.
2. **PHASE_0_SETUP.md** — repo, CI, CLAUDE.md, observability stubs.
3. **PHASE_1_FOUNDATION.md** — pages, auth, WebSocket skeleton.
4. **PHASE_2_VOICE_TO_TEXT.md** — ★ live captions + diarization (the wedge).
5. **PHASE_3_VOICE_PROFILES.md** — ★ saved voice profiles (ECAPA-TDNN + consent).
6. **PHASE_4_TRANSLATION.md** — Google v3 + OpenRouter + combined live translation.
7. **PHASE_5_GENZ_SLANG.md** — slang translator + shareable cards + launch hardening.

## How to run it
1. Start a Claude Code session in your empty repo.
2. Paste (or point it to) **INTRODUCTION.md** first: _"Read this fully before building. Confirm you understand the scope, stack, and error protocol."_
3. Then work **one phase file at a time**, and **one step at a time within it**.
4. After each step, make Claude Code run the **Verification Gate** and the **Error Protocol (§8)** before continuing.
5. Don't advance a phase until its **Exit Criteria** checkboxes are all green.

## Why it's structured this way
- **One phase/step at a time** → smaller diffs, easier debugging, fewer cascading errors.
- **Verification Gates** → every step must actually *run*, not just compile.
- **Mocks for every external API** → build/test without burning AssemblyAI / Google / OpenRouter credits.
- **Compliance built into the relevant phase** (consent in Phase 3, a11y throughout) → not a risky cleanup at the end.

## Recommended pace
- Phase 2 (core) to "wow" quality before polishing anything else.
- Get a real deaf/HoH tester on Phase 2 before starting Phase 3.
