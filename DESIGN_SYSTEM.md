# DESIGN SYSTEM — Visual Spec (Sense-inspired)

> Feed this to Claude Code alongside `PHASE_1_FOUNDATION.md`. It defines the exact look, tokens, and component styling for the frontend. Derived from the "Sense — AI-Powered Meditation App" reference.
> **Reference:** https://dribbble.com/shots/26727739-Sense-AI-Powered-Meditation-App

---

## 1. Design Thesis

**Aesthetic:** Soft **glassmorphism** on a warm pastel gradient. Floating rounded cards with frosted-glass blur, generous whitespace, calm and premium. The feeling is *"a calm, human, trustworthy assistant"* — which fits an accessibility product that must feel safe and effortless, not clinical.

**Why it fits this product (not just borrowed):** Our users (deaf/HoH, immigrants, travelers) often deal with stressful communication moments. A calm, low-cognitive-load, high-contrast-where-it-counts interface reduces anxiety. The frosted cards separate *speakers* and *tools* into clear floating "surfaces" — which maps perfectly onto our speaker-labeled captions.

**One risk we take (the signature):** the live-caption panel uses the same floating **frosted chat-bubble surfaces** as the reference's AI chat panel — each speaker is a distinct tinted glass bubble. That's the memorable element.

---

## 2. Color Tokens

Warm peach/cream → lilac gradient background, with a coral/orange accent.

```css
:root {
  /* Background gradient (page) */
  --bg-gradient: linear-gradient(135deg, #F3E9E2 0%, #F0E6E9 45%, #E9DDF0 75%, #D9C9EC 100%);
  --bg-base: #F2ECE7;          /* fallback flat bg */

  /* Glass surfaces */
  --glass-bg: rgba(255, 255, 255, 0.55);
  --glass-bg-strong: rgba(255, 255, 255, 0.72);
  --glass-border: rgba(255, 255, 255, 0.6);
  --glass-shadow: 0 8px 32px rgba(60, 45, 80, 0.10);

  /* Accent (coral/orange orb) */
  --accent: #E8804F;           /* primary coral */
  --accent-strong: #DD6B3A;
  --accent-soft: #F4A87E;
  --accent-gradient: linear-gradient(145deg, #F5A97C 0%, #E8804F 55%, #D65E34 100%);

  /* Text */
  --text-primary: #2B2622;     /* near-black warm */
  --text-secondary: #6B6259;   /* muted warm gray */
  --text-tertiary: #9A9089;    /* captions/meta */
  --text-on-accent: #FFFFFF;

  /* Speaker bubble tints (live captions) — assign per speaker */
  --speaker-1: rgba(232, 128, 79, 0.14);   /* coral */
  --speaker-2: rgba(120, 170, 130, 0.14);  /* sage green */
  --speaker-3: rgba(150, 140, 220, 0.14);  /* lilac */
  --speaker-4: rgba(230, 180, 90, 0.14);   /* amber */
  --speaker-other: rgba(140, 140, 150, 0.12);

  /* States */
  --success: #6FB08A;
  --warning: #E0A951;
  --error: #D96C6C;

  /* High-contrast mode overrides (a11y) — see §7 */
}
```

**Rule:** the coral accent is used *sparingly* — the orb logo, primary buttons, play buttons, active nav pill, send button. Everything else stays quiet glass + warm neutrals. Spend boldness in one place.

> **A11y adjustment (2026-07-17, per §7):** the light coral `#E8804F` fails AA for white button text (2.75:1) and the 3:1 non-text minimum. **Interactive** coral therefore uses the orb's burnt-coral shadow range: `--accent-strong: #B84A22` (5.2:1 with white) and `--accent-gradient: #C4502A → #B84A22 → #A63F19` (≥4.7:1), also used for focus rings and accent icons. **Ambient** coral (orb, speaker tints, washes, `--accent-soft`) keeps the original tones. Never put white text on flat `--accent`.

---

## 3. Typography

The reference uses a clean geometric sans with a heavy display weight for headings.

```css
:root {
  --font-display: 'Poppins', 'Inter', system-ui, sans-serif;  /* headings, big + bold */
  --font-body: 'Inter', system-ui, sans-serif;                /* body, UI */
}
```

- **Display (Poppins):** used for page titles ("Dashboard"), greeting ("Good Morning Andrew"), card labels ("Meditate", "Music"). Weights 600–800. Big and confident.
- **Body (Inter):** everything else — nav, captions, meta, chat text. Weights 400–500.

**Type scale:**
| Role | Size | Weight | Font |
|---|---|---|---|
| Page title | 44px | 800 | Poppins |
| Greeting/hero | 34px | 700 | Poppins |
| Card label | 22px | 600 | Poppins |
| Section heading | 18px | 600 | Poppins |
| Body / chat | 15px | 400 | Inter |
| Nav item | 15px | 500 | Inter |
| Meta / caption | 13px | 400 | Inter |

_Note: David has used Poppins before (FormFixer). Consistent choice, not arbitrary._

---

## 4. Core Visual Primitives

**Glass card (the workhorse):**
```css
.glass-card {
  background: var(--glass-bg);
  backdrop-filter: blur(24px) saturate(140%);
  -webkit-backdrop-filter: blur(24px) saturate(140%);
  border: 1px solid var(--glass-border);
  border-radius: 28px;
  box-shadow: var(--glass-shadow);
}
```

- **Border radius:** cards 24–32px, buttons/pills fully rounded (`border-radius: 999px`), image tiles 20–24px.
- **Shadows:** soft, diffuse, low-opacity, warm-tinted. Never hard/dark.
- **Blur:** cards float above the gradient with real backdrop blur.
- **Spacing:** generous — 24–32px padding inside cards, 20–24px gaps between.

**The coral orb:** a signature 3D-ish gradient sphere used as the brand mark + AI assistant avatar. Render as a radial-gradient circle with a soft inner highlight.
```css
.orb {
  background: radial-gradient(circle at 35% 30%, #FBC9A8, #E8804F 55%, #C9522B 100%);
  border-radius: 50%;
  box-shadow: 0 4px 16px rgba(200, 90, 45, 0.35), inset 0 2px 6px rgba(255,255,255,0.5);
}
```

**Image tiles:** meditation-style cards use soft blurred abstract gradient imagery (peach, sage, lilac washes) with a label bottom-left and an action button bottom-right.

---

## 5. Layout Structure

Matches the reference dashboard:

```
┌────────────────────────────────────────────────────────────────┐
│  [orb] Sense        Dashboard            [search] [bell] [user]  │
│                                                                  │
│  GENERAL          ┌──────────────┐  ┌──────┐   ┌─────────────┐  │
│  ▸ Dashboard      │  Meditate    │  │Sleep │   │  [orb]      │  │
│    My Sessions    │  (big tile)  │  └──────┘   │ Good Morning│  │
│    Popular        │              │  ┌────┐┌───┐│  Andrew...  │  │
│    Community      └──────────────┘  │Move││Mus││             │  │
│    Download                         └────┘└───┘│  chat panel │  │
│                                                │  ...        │  │
│  OTHERS           Recommended  [Mind][Foc][Rel]│ [Ask...] 🎤 │  │
│    Premium        ┌────┐ ┌────┐ ┌────┐         └─────────────┘  │
│    Shared         │card│ │card│ │card│                          │
│    Saved                                                        │
│    Logout                                                       │
└────────────────────────────────────────────────────────────────┘
```

- **Left sidebar:** glass panel, "GENERAL" + "OTHERS" grouped nav, active item = white pill with coral icon.
- **Center:** hero tiles (feature cards) + a "Recommended" row with category pills (Mindfulness / Focus / Relaxation).
- **Right rail:** the AI assistant chat panel (glass) with greeting, conversation, a "now playing"-style pill, and an "Ask Anything" input with mic + send.

**Adapt for OUR product** (not a meditation app):
- Feature tiles become: **Voice-to-Text**, **Translate**, **GenZ**, **My Sessions**.
- Right chat panel becomes the **live caption / assistant panel**.
- "Now playing" pill becomes an **active-session** pill (e.g. "Live Captioning · 00:42").
- Category pills become **language / mode** pills.
- Keep the exact visual language; swap the content to our domain.

---

## 6. Sidebar Nav (map to our app)

```
GENERAL
  ▸ Dashboard
    Voice-to-Text
    Translate
    Community
    Downloads / History
OTHERS
    Premium Access
    Saved Phrases
    Shared Sessions
    Logout
```

Active item: white glass pill, coral icon, dark text. Inactive: transparent, muted icon + text.

---

## 7. Accessibility Overrides (NON-NEGOTIABLE)

Glassmorphism can KILL contrast. Our product is an accessibility tool — this must not slip.

- **Text contrast:** all body/caption text must meet **WCAG AA (4.5:1)** against the glass surface. Test every text-on-glass combo. If a caption fails, darken the glass (`--glass-bg-strong`) behind text, don't lighten the text.
- **High-contrast mode toggle:** replaces glass with solid opaque surfaces (`#FFFFFF` / `#1A1714`), removes blur, boosts text to `#000`/`#FFF`, thickens borders. Provide `[data-contrast="high"]` overrides for every token.
- **Caption font-size control:** live captions must scale (S/M/L/XL) independent of the rest of the UI.
- **Focus states:** visible coral focus ring (`outline: 2px solid var(--accent); outline-offset: 2px`) on every interactive element. Never remove outlines.
- **Reduced motion:** respect `prefers-reduced-motion` — disable orb animation, card hover transforms, and any ambient motion.
- **Don't rely on color alone** for speaker distinction — pair each speaker's tint with the speaker's **name/label** always.

---

## 8. Motion (restrained)

- Orb: very slow ambient rotation/shimmer (disabled under reduced-motion).
- Cards: gentle lift on hover (`translateY(-2px)` + slightly stronger shadow).
- Captions: new bubble fades + slides up 6px. Nothing bouncy.
- Page load: soft stagger-fade of cards (respect reduced-motion).

Keep it minimal — over-animation reads as AI-generated and adds cognitive load for our audience.

---

## 9. What to Reuse vs Change

**Reuse exactly:** glass cards, gradient bg, coral orb, rounded pills, sidebar structure, right-rail chat panel pattern, soft shadows, type hierarchy.

**Change for our domain:** all copy and imagery (accessibility/translation, not meditation), feature tile labels, the chat panel becomes live captions, high-contrast + font-scaling are first-class (a meditation app doesn't need them; we absolutely do).
