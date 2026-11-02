# PHASE 1.5 — Frontend UI/UX Build (Sense-inspired)

**When:** Run this alongside/after `PHASE_1_FOUNDATION.md` (page structure exists) and before wiring live features. Follow Error Protocol (§8).

**Inputs Claude Code must read first:**
- `../product/INTRODUCTION.md` (scope + rules)
- `../design/DESIGN_SYSTEM.md` (exact tokens, palette, components) ← the source of truth for visuals
- Reference: https://dribbble.com/shots/26727739-Sense-AI-Powered-Meditation-App

**Goal:** A polished, glassmorphic, Sense-style frontend — matching the reference's palette, floating glass cards, coral orb, and layout — adapted to our accessibility/translation domain, and accessible (WCAG 2.1 AA).

---

## Use Claude Code Design Skills

At the start of this phase, instruct Claude Code:

> Before building UI, engage your frontend design skill (`frontend-design`). Approach this as a design lead delivering a distinctive, non-templated interface. Follow `../design/DESIGN_SYSTEM.md` exactly for palette, typography, glass components, and layout — the reference direction is pinned, so match it rather than inventing a new look. Where the design system leaves a gap, make a deliberate choice consistent with the Sense aesthetic. Prioritize precision in spacing, blur, and contrast (this is a minimal/premium direction — elegance comes from executing it cleanly).

If you have design-focused skills/plugins available (e.g. "UI-UX pro", "Impeccable"), enable them for this phase and have them review each screen against the reference screenshots. Take screenshots of your output and self-critique against the reference before calling a step done.

---

## Step 1.5.1 — Design tokens + global styles

**Prompt:**
> Implement `../design/DESIGN_SYSTEM.md` as real code: Tailwind theme extension + CSS variables for all color/type/radius/shadow tokens. Load Poppins (display) + Inter (body). Set the page background to the peach→lilac gradient. Add `[data-contrast="high"]` override tokens and `prefers-reduced-motion` handling globally.

**Verification Gate (RUN):**
- Tokens available as Tailwind classes + CSS vars.
- Gradient background renders.
- Fonts load (Poppins headings, Inter body).
- Toggling `data-contrast="high"` swaps to opaque high-contrast tokens.
- Build/typecheck pass.

---

## Step 1.5.2 — Core primitives (glass card, orb, pill, button)

**Prompt:**
> Build reusable components: `GlassCard`, `Orb` (coral radial-gradient sphere, ambient shimmer respecting reduced-motion), `Pill` (category/mode toggle), `Button` (primary coral / ghost glass), `IconButton` (search/bell/user/play/send), `ImageTile` (blurred gradient image + bottom-left label + bottom-right action). Match radii, blur, and shadows from the design system exactly.

**Verification Gate (RUN):**
- Each primitive renders per spec on the gradient bg.
- Glass blur + soft shadow visible; radii correct.
- Focus rings visible on all interactive primitives (keyboard tab).
- Reduced-motion disables orb animation.
- Screenshot-compare against reference cards — matches feel.

---

## Step 1.5.3 — App shell (sidebar + topbar + layout grid)

**Prompt:**
> Build the dashboard shell: left glass sidebar (brand orb + "Sense"/our name, GENERAL + OTHERS grouped nav per DESIGN_SYSTEM §6, active = white pill w/ coral icon), topbar (page title, search, bell, user), and the 3-zone responsive grid (sidebar / center / right rail). Wire nav links to existing routes from Phase 1.

**Verification Gate (RUN):**
- Layout matches reference structure.
- Active nav item styled as coral-icon white pill; others muted.
- Nav navigates to correct routes.
- Fully keyboard navigable; ARIA landmarks (nav, main, complementary).
- Responsive: collapses cleanly to tablet/mobile (sidebar → drawer).

---

## Step 1.5.4 — Dashboard/Home content

**Prompt:**
> Build the Home/Dashboard center: hero feature tiles adapted to OUR domain — **Voice-to-Text**, **Translate**, **GenZ**, plus **My Sessions** — as blurred-gradient ImageTiles with labels + action arrows, linking to the tool pages. Add a "Recommended" row with mode/language Pills (e.g. Live / Enhanced / GenZ). Keep copy in our accessibility voice, not meditation copy.

**Verification Gate (RUN):**
- Tiles render Sense-style, link correctly.
- Copy is domain-appropriate (accessibility/translation).
- Contrast AA on all tile labels (labels sit on busy images — verify legibility, add scrim if needed).
- Responsive reflow works.

---

## Step 1.5.5 — Right-rail assistant / caption panel (signature)

**Prompt:**
> Build the right-rail glass panel modeled on the reference chat panel: brand orb + greeting ("Good Morning, {name}"), a scrollable conversation area using **per-speaker tinted glass chat bubbles** (DESIGN_SYSTEM speaker tints), an active-session pill ("Live Captioning · 00:42" style), and an "Ask Anything" input with mic + send buttons. For now use placeholder content; this becomes the live caption surface in Phase 2.

**Verification Gate (RUN):**
- Panel matches reference chat aesthetic.
- Speaker bubbles use distinct tints AND always show a name/label (never color-only).
- Input + mic + send render; focus states correct.
- ARIA live region set up on the conversation area (ready for live captions).
- Contrast AA on all chat text.

---

## Step 1.5.6 — Accessibility control bar

**Prompt:**
> Add a persistent, easily reachable a11y control: high-contrast toggle, caption font-size selector (S/M/L/XL), and reduced-motion is auto-respected. Persist choices for the session. Ensure captions scale independently of the rest of the UI.

**Verification Gate (RUN):**
- High-contrast toggle swaps entire UI to opaque high-contrast tokens; still looks intentional.
- Font-size selector scales captions only, live.
- Choices persist across navigation within the session.
- All controls keyboard + screen-reader operable.

---

## Step 1.5.7 — Marketing pages styling (Home intro, About, Product, Login)

**Prompt:**
> Apply the same design language to the public pages: Home (mission + feature overview with glass cards), About (mission detail), Product (feature breakdown), Login/Register (glass card centered on gradient). Consistent type + tokens. Keep copy plain, warm, and specific (see INTRODUCTION voice).

**Verification Gate (RUN):**
- All public pages visually consistent with the app shell.
- Login/register forms accessible (labels, errors in-voice, focus order).
- Build/typecheck/lint pass.
- Screenshot-compare all pages for consistency.

---

## Step 1.5.8 — Design QA pass

**Prompt:**
> Do a full design + a11y QA: screenshot every page, compare against the reference screenshots and DESIGN_SYSTEM. Fix inconsistencies in spacing, radius, blur, shadow, and color. Run an automated a11y check (axe) on every page and fix all violations. Verify AA contrast on every text-on-glass instance. Apply "remove one accessory" — cut any decoration not serving the brief.

**Verification Gate (RUN):**
- axe: zero critical/serious violations on all pages.
- All text-on-glass passes AA.
- Visual consistency confirmed via screenshots.
- Reduced-motion + keyboard + high-contrast all verified once more.

---

## Phase 1.5 Exit Criteria
- [ ] Design tokens + gradient + fonts implemented, high-contrast override works.
- [ ] Glass primitives + coral orb match reference.
- [ ] App shell (sidebar/topbar/grid) matches reference structure, keyboard-navigable.
- [ ] Dashboard tiles adapted to our domain, legible on imagery.
- [ ] Right-rail caption panel with per-speaker tinted bubbles + ARIA live region.
- [ ] A11y control bar (contrast + caption font-size) working + persistent.
- [ ] Marketing + auth pages consistent + accessible.
- [ ] Design/a11y QA: axe clean, AA contrast everywhere, screenshots match.

**Report:** attach before/after screenshots vs the reference, and the axe results per page. Note anything intentionally diverged from the reference for our accessibility needs (e.g. high-contrast mode).
