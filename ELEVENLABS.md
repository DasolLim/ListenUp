# ELEVENLABS — current state, and what a paid key unlocks

**Why we use it at all:** Korean voice quality, and a cloning API built around verified consent. Those were the two reasons it beat Google Cloud TTS and OpenAI TTS (INTRODUCTION §4). Everything below follows from that.

---

## 1. Where we are now — free tier

| | Status |
|---|---|
| `TTS_SERVICE` | `elevenlabs` |
| Preset cloud voices | ✅ Sarah, Liam, Matilda — each speaks **both** English and Korean (`eleven_multilingual_v2`) |
| Voice cloning | ❌ Paid only — the studio detects this and says so instead of failing at the end of a 30s recording |
| Tone dials (Warmth / Brightness / Evenness / Expressiveness) | ✅ Live — these are permanently dead on browser voices because `speechSynthesis` exposes no audio node |
| Commercial use | ❌ Free tier is non-commercial and carries attribution requirements |

**What the free tier is for:** answering one question — *is ElevenLabs' Korean meaningfully better than the browser voice for our use case?* macOS ships exactly one Korean voice (Yuna). If cloud Korean is clearly better, paying is justified. If it isn't, the browser tier is free, offline, and needs no key.

Compare them side by side on the same Korean sentence before spending anything.

---

## 2. Before any paid key — the spend guard

**This is a prerequisite, not a nice-to-have.**

`auto-speak defaults ON` (`lib/useSpeech.ts`), and live captions speak **every new final translation**. On a character-billed provider that means a conversation bills continuously:

```
conversation speech ≈ 870 characters/minute of translated output

  10,000 char allowance  →  11.5 minutes of conversation
  30,000                 →  34.5 minutes
 100,000                 →  114.9 minutes
```

Entry-tier allowances buy **tens of minutes per month**, not hours. The Redis cache only helps on repeated phrases, which live conversation rarely produces.

Minimum guard before enabling a paid key:

- [ ] Auto-speak defaults **OFF** when the cloud tier is active (keep it ON for the free browser tier — it costs nothing there)
- [ ] Per-session character cap, with honest copy when it's reached
- [ ] Log characters per request and per session (translation already does this; TTS does not)
- [ ] A visible usage readout somewhere in Settings

---

## 3. What a paid key unlocks immediately

Already built, gated only by the plan:

- **Voice cloning** — `clone_voice()` in `services/tts/elevenlabs.py`, the consent gate in `app/routes/tts.py`, migration `0003_custom_voices.sql` (applied), and the recording UI in `VoiceStudio`. 30s minimum, consent from the enrolled person, delete removes our row *and* the provider-side voice.
- **Cloned voices in every picker** — `GET /tts/voices` now returns a signed-in caller's recorded voices alongside the presets. (This was a dead end until recently: a voice could be created, listed and deleted but never spoken with.)

Nothing needs writing for these. Set the key, restart, record.

---

## 4. Feature opportunities, ordered by value to *this* product

### 4.1 Streaming synthesis — the biggest win

**Today:** `speak()` does one blocking POST and waits for the whole MP3 (`services/tts/elevenlabs.py`). For a long sentence that is a visible pause before anything is heard.

**With streaming:** audio starts playing while it is still being generated. Our latency budget is <1s mic-to-caption, and read-aloud currently sits outside that guarantee entirely.

Worth pairing with a **lower-latency model** for live captions while keeping the higher-quality multilingual model for the translate page — the trade-off differs by surface: live conversation wants speed, a translation you asked for wants quality.

### 4.2 Speak in the *original speaker's* voice

The most distinctive thing this product could do. ElevenLabs supports speech-to-speech (voice conversion), so a translation could be spoken in the voice and cadence of the person who actually said it.

For an interpreter product this is the difference between "a robot is translating" and "I can hear *them*, in my language." It also composes with speaker identity, which is already built: we know *who* is speaking, so we know which voice to use.

⚠️ Consent scope: converting to an enrolled person's voice is a new use of their biometric data. The existing consent text covers cloning for read-aloud; this likely needs its own consent version.

### 4.3 Word-level highlighting while speaking

ElevenLabs can return character/word timing alongside audio. That enables highlighting each word as it is spoken — genuinely useful for a hard-of-hearing user following along with residual hearing, and for anyone learning the language.

This is an accessibility feature that the browser tier cannot do well (`onboundary` support is inconsistent), so it is a real reason to be on cloud.

### 4.4 Pronunciation control

Names are the obvious failure case: enrolled speakers ("Mom", Korean names), place names, and the slang the Explain tool deals in. A pronunciation dictionary fixes mispronounced names permanently rather than per-request.

### 4.5 Voice design instead of recording

Generating a voice from a description removes the 30-second recording step for users who just want a *different* voice rather than a *specific person's* voice. Lower friction, and no biometric data involved at all — which makes it the safer default of the two.

### 4.6 Higher-fidelity cloning

Instant Voice Cloning is what the current code uses. Professional Voice Cloning needs more audio and provider-side verification but sounds materially closer to the person. Worth it only for voices used constantly — a family member, not a one-off.

---

## 5. Choosing a plan

Buy the **cheapest tier that unlocks cloning**, and only after the guard in §2 exists. Reasons:

- Character allowance is the binding constraint, not features, and you can raise it later without changing code
- TTS is not the moat — speaker identity is. This is the least differentiating paid dependency in the stack
- Everything in §4 is additive; none of it blocks launch

**Upgrade triggers** — move up a tier when one of these is actually true, not before:

- Characters run out during real use (measure first; the guard in §2 gives you the number)
- Cloning becomes something customers ask for by name
- A customer requires a **BAA** — biometric data means this is a real gate, and it lives on enterprise agreements, not Starter

---

## 6. Compliance, unchanged by plan

- A **cloned voice is biometric data**, exactly like the ECAPA embeddings. Same BIPA/GDPR obligations: consent from the person cloned, deletion, export, published retention schedule.
- **ElevenLabs puts the consent burden on us.** Our versioned consent records (`consent_text_version`, `consented_by`) are the evidence in a dispute — keep them immutable.
- Confirm in writing that **our audio is not used for model training**, and get a DPA. Neither is a settings toggle.
- Free tier is **non-commercial**. Do not put it in front of a paying customer.

---

## 7. Quick reference

```bash
# .env
TTS_SERVICE=elevenlabs
ELEVENLABS_API_KEY=sk_...
# optional — defaults to eleven_multilingual_v2 (English + Korean from one voice)
ELEVENLABS_MODEL=eleven_multilingual_v2
```

Restart the backend (the service is chosen by a cached factory), then verify:

```bash
curl -s localhost:8000/tts/voices | python3 -m json.tool | grep provider | sort -u
# expect "provider": "cloud"   — if you still see "browser", the env didn't load
```

Reverting is one line: unset `TTS_SERVICE` and browser voices take over again, free and offline.
