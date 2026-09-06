# START HERE — Frontend UI/UX (run after Phase 1)

**Status:** Phase 1 complete (pages, auth, WebSocket skeleton, observability all green).
**Now:** Build the glassmorphic **Sense-inspired** frontend UI/UX, then it's ready for Phase 2 live features.

---

## What Claude Code should read first (in this order)

1. `../product/INTRODUCTION.md` — scope, stack, rules, **Standard Error & Debugging Protocol (§8)**.
2. `../design/DESIGN_SYSTEM.md` — the visual source of truth (palette, glass components, tokens, layout).
3. `PHASE_1.5_FRONTEND_UI.md` — the step-by-step build (Steps 1.5.1 → 1.5.8), each with a Verification Gate.

**Reference design:** https://dribbble.com/shots/26727739-Sense-AI-Powered-Meditation-App

---

## Kickoff instruction (paste this to Claude Code)

> Phase 1 is complete. We're now building the frontend UI/UX.
>
> First, read `../product/INTRODUCTION.md`, `../design/DESIGN_SYSTEM.md`, and `PHASE_1.5_FRONTEND_UI.md` in full and confirm you understand the visual direction and the error protocol.
>
> Engage your **`frontend-design` skill** for this work. If you have design-quality skills/plugins available (e.g. "UI-UX pro", "Impeccable"), enable them and use them to review each screen against the reference screenshots. The Sense aesthetic is **pinned** — match `../design/DESIGN_SYSTEM.md` exactly (peach→lilac gradient, frosted glass cards, coral orb, Poppins + Inter, sidebar + center tiles + right caption rail). Don't invent a new look; where the spec leaves a gap, choose consistently with Sense.
>
> This is an **accessibility product** — the a11y overrides in `../design/DESIGN_SYSTEM.md §7` are non-negotiable and build-breaking if failed: WCAG 2.1 AA contrast on every text-on-glass surface, a high-contrast mode that swaps glass for opaque surfaces, caption font-size scaling, visible focus rings, and `prefers-reduced-motion` respected. Speaker bubbles must never rely on color alone — always pair the tint with a name label.
>
> Then build `PHASE_1.5_FRONTEND_UI.md` **one step at a time** (1.5.1 → 1.5.8). After each step: run the Standard Error & Debugging Protocol (§8) and the step's Verification Gate, screenshot your output and self-critique it against the reference, fix everything, commit, and report before moving on. Do not advance a step on a red gate. Do not skip ahead.
>
> Start with Step 1.5.1 (design tokens + global styles).

---

## Build order within this phase (from PHASE_1.5)

1. **1.5.1** Design tokens + global styles (gradient, fonts, high-contrast overrides)
2. **1.5.2** Core primitives (GlassCard, Orb, Pill, Button, IconButton, ImageTile)
3. **1.5.3** App shell (sidebar + topbar + 3-zone grid)
4. **1.5.4** Dashboard/Home content (our-domain feature tiles)
5. **1.5.5** Right-rail caption panel (per-speaker tinted glass bubbles + ARIA live region) ← signature
6. **1.5.6** Accessibility control bar (high-contrast + caption font-size)
7. **1.5.7** Marketing + auth pages styling (Home/About/Product/Login)
8. **1.5.8** Design + a11y QA (axe clean, AA contrast, screenshot-match)

---

## Definition of Done for this phase
- [ ] Every step's Verification Gate green.
- [ ] Matches the reference aesthetic (screenshot-compared).
- [ ] axe: zero critical/serious violations on every page.
- [ ] WCAG 2.1 AA contrast verified on all text-on-glass.
- [ ] High-contrast mode + caption font-size scaling + reduced-motion all working.
- [ ] Keyboard-navigable throughout; visible focus rings.
- [ ] Right-rail caption panel ready (ARIA live region) for Phase 2 to stream into.

**When done →** proceed to `PHASE_2_VOICE_TO_TEXT.md` (wire live captions into the styled right-rail panel).

---

## Guardrails (don't let these slip)
- One step at a time; run + verify before advancing.
- Glass must not break contrast — darken the glass behind text, don't lighten the text.
- Keep the coral accent sparing (orb, primary buttons, active nav, play/send only).
- Restraint: "remove one accessory" — cut decoration that doesn't serve the brief.
- Content/copy in our accessibility voice, not meditation copy.
