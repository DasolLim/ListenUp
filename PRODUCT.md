# Product

## Register

product

<!-- The signal is split: marketing surfaces at /, /about, /product; app tools
     at /dashboard, /voice-to-text/*, /translate/*. The 2026-07-19 decision
     unified them into one responsive product rather than "website + separate
     app". `product` is the default because the tool surfaces are where users
     spend their time. Marketing pages may override to `brand` per task. -->

## Users

**Primary: deaf and hard-of-hearing people.** In live, often unplanned conversations: a family dinner, a group of coworkers, a doctor's appointment. Frequently on a phone, held at an angle, in a room with background noise and more than one person talking. The job: know *who* said *what*, fast enough to reply while it still matters.

**Secondary: travelers, immigrants, international users.** Currently English ↔ Korean only. Their job differs in an important way: they often understand the words but miss the *meaning* (the slang, the register, whether that was a joke or an insult). A literal translation can be technically correct and socially useless.

A third mode now matters as much: **the interpreter case.** With text-to-speech, one person speaks, the other *hears* their own language. Neither has to read the screen. That makes the product a participant in the conversation, not a document to consult.

Shared context that shapes every screen: users are mid-conversation, splitting attention between a screen and a human face. Reading time is borrowed from the conversation itself. Nobody is leisurely browsing.

## Product Purpose

Makes spoken conversation **accessible** (speaker-named live captions) and **culturally understandable** (translation that explains slang, register, and nuance), and now **audible in both directions** (translated text read aloud).

It exists because two categories of tool both fail the same way; they flatten a conversation:

1. Captioning tools produce a wall of text with no speaker attribution. In a group you lose track of who said what within seconds.
2. Translators convert words, not meaning. Slang, tone, and culture fall through the gaps.

**The moat (protect these):** speaker-named captions with real names, not "Speaker 1"; cultural translation that explains rather than just converts; and the combination, speaker-named multilingual live translation, spoken aloud, in real time.

**Success looks like:** a user stops asking "wait, who said that?", stops nodding along to something they didn't understand, and stops reading translations out loud to the person across the table.

## Brand Personality

**Trustworthy, warm, un-clinical.** A capable companion, not a medical device and not a wellness app.

Voice: plain, direct, second person. Names things by what the user controls ("Voice profiles", not "embedding management"). States what happened and what to do next. Never cute about failure, never apologetic, never clinical.

Emotional goal: the feeling to produce is *relief*, someone finally handled the hard part. Not *calm*, and not *clinical competence*.

## Anti-references

- **Wellness / meditation apps.** Pastel serenity and decoration that outranks legibility. This product is used in stressful live moments; ambience fights the one thing a caption tool cannot trade away.
- **Medical and assistive-tech clinical look.** Institutional blues, hospital whites, feature tables. Being an accessibility product must not mean looking like a diagnosis.
- **"AI product" tropes.** Dark backgrounds with neon accents, gradient text, hero-metric layouts. The intelligence should be evident in the output, not advertised by the chrome.
- **Control panels that show every option at once.** The current translate pages fail this: mode pills, language selects, voice selects, and auto-speak toggles all compete at the same visual weight. A user mid-conversation should see one obvious next step.

## Design Principles

1. **Legibility is the product, not a constraint on it.** Functional text (captions, translations, body copy) must stay readable on its ground, verified against real hex values. Accessibility failures are build-breaking bugs.
2. **Every color teaches something.** A hue means one thing app-wide: which person is speaking, or which tool you're in. Color is never the only carrier of meaning; always paired with a name or a word.
3. **Show the output, don't describe the capability.** Demos beat feature lists; the aha is never gated behind a login.
4. **Never force a wrong answer.** Below match confidence, keep the generic label. A wrong name is worse than no name, and a confident wrong translation is worse than a hedged one.
5. **One obvious next step per screen.** Controls that configure should recede; controls that act should lead. Progressive disclosure over exhaustive panels, because attention is borrowed from a live conversation.
6. **Practice what you preach.** An accessibility product that ships an inaccessible interface has failed at its own thesis. Keyboard nav, screen readers, high contrast, and caption scaling are table stakes, and they must be *reachable*, not merely implemented.

## Accessibility & Inclusion

**WCAG 2.1 AA is the floor, and failures are build-breaking** (INTRODUCTION §6). Verified by computed contrast against actual hex values, never by eye.

- **Deaf / HoH primary audience** — captions are the core function, not an accommodation layer. Speaker attribution is part of the accessibility.
- **Text-to-speech is an accessibility feature in both directions**: it serves the hearing person opposite a deaf user, and it serves anyone who finds reading a translation aloud awkward. Rate control genuinely aids comprehension.
- **High-contrast mode** via `[data-contrast="high"]`, styled for every surface.
- **Adjustable caption size** (S/M/L/XL) scaling captions independently of UI chrome, via `--caption-scale`.
- **Keyboard navigation** with visible focus rings on every interactive element, never removed.
- **Screen readers** — ARIA roles/labels/states; decorative visuals are `aria-hidden`; interim caption state announced as text, not implied by styling.
- **Reduced motion** — `prefers-reduced-motion` respected globally.
- **Color blindness** — speaker and tool colors are always paired with text labels.
- **Touch targets** at least 44px on the primary axis at 390px width.
- **Biometric privacy** (BIPA / GDPR / Quebec Law 25) — voice profiles *and cloned voices* are biometric data. Explicit consent from the person recorded, not just the account holder, plus deletion and export. A cloned voice can say words its owner never said, so consent is enforced at the API, not the UI.
