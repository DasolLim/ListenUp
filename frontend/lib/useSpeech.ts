"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { postJson } from "@/lib/api";
import { authHeader } from "@/lib/auth/token";

const BACKEND = process.env.NEXT_PUBLIC_BACKEND_URL ?? "http://localhost:8000";

export type Voice = {
  id: string;
  label: string;
  language: string;
  gender: "female" | "male" | "neutral";
  provider: "browser" | "cloud" | "custom";
  browser_hint: string;
  owner_name: string;
};

const VOICE_PREF_KEY = "listenup-voice";
const AUTOSPEAK_KEY = "listenup-autospeak";
const SHAPE_KEY = "listenup-voice-shape";

/**
 * How a voice sounds, on top of which voice it is.
 *
 * `SpeechSynthesisUtterance` exposes exactly three audio parameters — pitch,
 * rate and volume. There is no timbre, warmth or emotion knob in the Web Speech
 * API, so anything beyond these three has to be built from them rather than
 * requested from the browser:
 *
 * - `pitch`  — lower reads more masculine, higher more feminine. The closest
 *   thing to a gender dial that actually exists.
 * - `rate`   — an accessibility control in its own right; slower is easier to
 *   follow.
 * - `volume` — genuinely useful here, because read-aloud competes with the room
 *   the conversation is happening in.
 * - `pauses` — *derived*, not a browser parameter. Sentences are spoken as
 *   separate utterances with a real gap between them, which is what makes
 *   speech sound unhurried instead of merely slow. Rate alone drawls; a pause
 *   gives the listener a boundary to catch up on.
 *
 * `pauses` is deliberately the only invented dimension. A "warmth" slider that
 * silently mapped to pitch would be a lie about what the device can do.
 */
export type VoiceShape = {
  pitch: number;
  rate: number;
  volume: number;
  pauses: number;
  /** Low-frequency weight, in dB. Web Audio only — see `TONE_DIMENSIONS`. */
  bass: number;
  /** High-frequency weight, in dB. Web Audio only. */
  treble: number;
  /** Dynamic-range compression, 0–1. Evens out loud/quiet parts. Web Audio only. */
  clarity: number;
  /** Provider-side expressiveness, 0–1. ElevenLabs only (inverse of stability). */
  expressiveness: number;
};

export const DEFAULT_SHAPE: VoiceShape = {
  pitch: 1,
  rate: 1,
  volume: 1,
  pauses: 0,
  bass: 0,
  treble: 0,
  clarity: 0,
  expressiveness: 0.5,
};

/**
 * Which dimensions can actually affect which tier.
 *
 * This is the honest core of voice shaping. `speechSynthesis` speaks straight to
 * the sound card: it exposes no AudioNode, no MediaStream, and no output
 * routing, so **no Web Audio effect can touch a browser voice**. Cloud voices
 * arrive as audio bytes, which we *can* route through a filter graph.
 *
 * Rather than hide the difference, the UI reads this map and disables what a
 * tier cannot do, with the reason stated. A tone slider that silently did
 * nothing would be worse than no slider.
 */
export const DIMENSION_SUPPORT: Record<keyof VoiceShape, ("browser" | "cloud")[]> = {
  pitch: ["browser"], // cloud pitch is baked in by the provider at render time
  rate: ["browser"],
  volume: ["browser", "cloud"],
  pauses: ["browser", "cloud"],
  bass: ["cloud"],
  treble: ["cloud"],
  clarity: ["cloud"],
  expressiveness: ["cloud"],
};

/** True when `dimension` does something audible for a voice of `provider`. */
export function supportsDimension(dimension: keyof VoiceShape, provider?: string): boolean {
  const tier = provider === "browser" || !provider ? "browser" : "cloud";
  return DIMENSION_SUPPORT[dimension].includes(tier);
}
// Web Speech allows pitch 0–2 and rate 0.1–10, but the extremes are unusable
// (chipmunk / unintelligible), so the UI stays inside a range that always
// produces speech a person can follow. `pauses` is in milliseconds of added
// silence between sentences; past ~1.2s it reads as a fault rather than a pace.
export const SHAPE_LIMITS = {
  pitch: { min: 0.5, max: 1.8 },
  rate: { min: 0.6, max: 1.6 },
  volume: { min: 0.2, max: 1 },
  pauses: { min: 0, max: 1200 },
  // ±12 dB is a wide but musical range; beyond it a shelf filter starts to
  // sound broken rather than warm.
  bass: { min: -12, max: 12 },
  treble: { min: -12, max: 12 },
  clarity: { min: 0, max: 1 },
  expressiveness: { min: 0, max: 1 },
};

/**
 * Clamp every stored/incoming value into its usable range.
 *
 * Derived from `SHAPE_LIMITS` rather than listing fields by hand: a new
 * dimension is otherwise silently left unclamped, which is exactly the bug that
 * lets a hand-edited localStorage value reach the audio graph.
 */
function clampShape(next: Partial<VoiceShape>, base: VoiceShape): VoiceShape {
  const merged = { ...base, ...next };
  const out = {} as VoiceShape;
  for (const key of Object.keys(SHAPE_LIMITS) as (keyof VoiceShape)[]) {
    const { min, max } = SHAPE_LIMITS[key];
    const value = Number(merged[key]);
    out[key] = Number.isFinite(value)
      ? Math.min(max, Math.max(min, value))
      : DEFAULT_SHAPE[key];
  }
  return out;
}

/**
 * Split text into sentence-sized chunks for the pause dimension.
 *
 * Only used when `pauses > 0`, so the default path still speaks one utterance
 * and behaves exactly as before. Splitting on terminators keeps abbreviations
 * from fragmenting badly, and any chunk-free result falls back to the whole
 * string so text without punctuation is never dropped.
 */
export function splitSentences(text: string): string[] {
  const parts = text
    .split(/(?<=[.!?。！？…]|다\.|요\.)\s+/u)
    .map((part) => part.trim())
    .filter(Boolean);
  return parts.length > 0 ? parts : [text];
}

/**
 * Picks the OS voice that best matches a curated entry.
 *
 * `browser_hint` is a `|`-separated preference list, most specific first, so a
 * Mac with Yuna uses Yuna while Windows falls through to Heami. Any voice for
 * the right *language* is an acceptable second choice: a different Korean voice
 * still reads Korean correctly.
 *
 * Returns `undefined` when the device ships no voice for the language at all.
 * That case must not be silent — leaving `utterance.voice` unset makes the
 * browser read Hangul with an English voice, which sounds like gibberish. The
 * caller surfaces it instead.
 */
function pickBrowserVoice(
  voice: Voice,
  available: SpeechSynthesisVoice[],
  taken: Set<string> = new Set(),
): SpeechSynthesisVoice | undefined {
  const forLanguage = available.filter((v) => v.lang.toLowerCase().startsWith(voice.language));
  const hints = voice.browser_hint.split("|").filter(Boolean);

  // First pass: honour the hint order but skip OS voices already claimed by
  // another catalogue entry. Offering three female voices that all resolve to
  // Samantha would make the picker lie about what it's giving you.
  for (const pass of [true, false]) {
    for (const hint of hints) {
      const match = forLanguage.find(
        (v) =>
          v.name.toLowerCase().includes(hint.toLowerCase()) && (!pass || !taken.has(v.name)),
      );
      if (match) return match;
    }
    // Second pass drops the de-duplication: a repeat is still far better than
    // no voice, and on a device with a single Korean voice it is the only
    // possible answer.
    const fresh = forLanguage.find((v) => !taken.has(v.name));
    if (pass && fresh) return fresh;
  }
  return forLanguage[0];
}

/**
 * Resolve the whole catalogue at once so each entry claims a distinct OS voice.
 *
 * Done as a batch rather than per-voice because de-duplication is only
 * meaningful with knowledge of the other entries; resolving one voice in
 * isolation cannot know what the others took.
 */
export function resolveVoiceMap(
  catalogue: Voice[],
  available: SpeechSynthesisVoice[],
): Map<string, SpeechSynthesisVoice> {
  const taken = new Set<string>();
  const resolved = new Map<string, SpeechSynthesisVoice>();
  // Named voices claim first; the "System default" entries intentionally have no
  // hint and should take whatever is left rather than a specific voice.
  const ordered = [...catalogue].sort((a, b) => b.browser_hint.length - a.browser_hint.length);
  for (const voice of ordered) {
    const os = pickBrowserVoice(voice, available, taken);
    if (os) {
      resolved.set(voice.id, os);
      if (voice.browser_hint) taken.add(os.name);
    }
  }
  return resolved;
}

/**
 * Route cloud audio through a tone-shaping graph.
 *
 * Only reachable for audio we hold as bytes. Browser voices cannot be processed
 * at all (`speechSynthesis` exposes no output node), which is why the tone
 * dimensions are gated on provider rather than offered everywhere.
 *
 * Graph: source → bass shelf → treble shelf → compressor → gain → speakers.
 * Shelf filters (not peaking) because they weight a whole region — that is what
 * "warmer" and "brighter" mean to a listener. The compressor is exposed as
 * "clarity" because that is its audible effect on speech: quiet consonants come
 * up relative to loud vowels, so words survive a noisy room.
 *
 * Returns a teardown function, or null when Web Audio is unavailable.
 */
function applyToneGraph(
  audio: HTMLAudioElement,
  shape: VoiceShape,
): (() => void) | null {
  const Ctor =
    typeof window !== "undefined"
      ? (window.AudioContext ??
        (window as unknown as { webkitAudioContext?: typeof AudioContext }).webkitAudioContext)
      : undefined;
  if (!Ctor) return null;

  // A flat graph is pure overhead and risks a pointless CORS/context failure,
  // so skip it entirely when nothing is being shaped.
  const flat = shape.bass === 0 && shape.treble === 0 && shape.clarity === 0;
  if (flat) return null;

  try {
    const context = new Ctor();
    const source = context.createMediaElementSource(audio);

    const bass = context.createBiquadFilter();
    bass.type = "lowshelf";
    bass.frequency.value = 250;
    bass.gain.value = shape.bass;

    const treble = context.createBiquadFilter();
    treble.type = "highshelf";
    treble.frequency.value = 3200;
    treble.gain.value = shape.treble;

    const compressor = context.createDynamicsCompressor();
    // Interpolate from "off" to a firm speech compressor. At clarity 0 the
    // threshold sits below the signal so it never engages.
    compressor.threshold.value = -24 * shape.clarity;
    compressor.ratio.value = 1 + 11 * shape.clarity;
    compressor.knee.value = 12;
    compressor.attack.value = 0.003;
    compressor.release.value = 0.25;

    // Compression lowers peaks; give some back so "clarity" doesn't read as
    // "quieter", which is the opposite of the intent.
    const makeup = context.createGain();
    makeup.gain.value = 1 + 0.5 * shape.clarity;

    source.connect(bass);
    bass.connect(treble);
    treble.connect(compressor);
    compressor.connect(makeup);
    makeup.connect(context.destination);

    return () => {
      try {
        source.disconnect();
        void context.close();
      } catch {
        // Already torn down; nothing to recover.
      }
    };
  } catch {
    // A failed graph must never silence the audio: the element still plays
    // unprocessed because createMediaElementSource only rewires on success.
    return null;
  }
}

/** Human-readable language name for user-facing copy. */
function languageName(code: string) {
  return code === "ko" ? "Korean" : "English";
}

/**
 * Speaking translated text aloud, so the other person hears their own language
 * instead of the user reading it out.
 *
 * Two tiers behind one call: browser voices render locally via
 * `speechSynthesis` (free, offline, instant), cloud voices come back as audio
 * from the backend. `speak()` hides the difference.
 */
export function useSpeech(language: string) {
  const [voices, setVoices] = useState<Voice[]>([]);
  const [voiceId, setVoiceId] = useState<string>("");
  const [autoSpeak, setAutoSpeak] = useState(false);
  const [speaking, setSpeaking] = useState(false);
  const [shape, setShape] = useState<VoiceShape>(DEFAULT_SHAPE);
  const [error, setError] = useState<string | null>(null);
  const osVoices = useRef<SpeechSynthesisVoice[]>([]);
  const audioRef = useRef<HTMLAudioElement | null>(null);
  // Monotonic id for the current speak() call. A sentence chain checks this
  // before continuing, so a newer call (or stop()) abandons the older one.
  const speakRun = useRef(0);
  const pauseTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  /**
   * Keep a warm copy of the OS voice list.
   *
   * `getVoices()` is asynchronous in most browsers: the first call often returns
   * an empty array, and Chrome does not reliably fire `voiceschanged`. Caching a
   * snapshot at mount therefore risks caching *nothing* forever, so this only
   * primes the cache. `speak()` re-reads the list at call time (see
   * `currentOsVoices`), which is the value that actually decides the voice.
   */
  useEffect(() => {
    if (typeof window === "undefined" || !("speechSynthesis" in window)) return;
    const load = () => {
      const list = window.speechSynthesis.getVoices();
      if (list.length > 0) osVoices.current = list;
    };
    load();
    window.speechSynthesis.addEventListener("voiceschanged", load);
    return () => window.speechSynthesis.removeEventListener("voiceschanged", load);
  }, []);

  // A pending sentence timer must not outlive the component, or it fires into a
  // unmounted surface and speaks after the user navigated away.
  useEffect(
    () => () => {
      speakRun.current += 1;
      if (pauseTimer.current !== null) clearTimeout(pauseTimer.current);
    },
    [],
  );

  /** The freshest voice list available right now, preferring a live read. */
  const currentOsVoices = useCallback((): SpeechSynthesisVoice[] => {
    if (typeof window === "undefined" || !("speechSynthesis" in window)) return [];
    const live = window.speechSynthesis.getVoices();
    if (live.length > 0) {
      osVoices.current = live;
      return live;
    }
    return osVoices.current;
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    // Send the token when there is one: the endpoint is public for preset
    // voices, but a signed-in caller also gets back the voices they recorded.
    // Without the header a cloned voice never reaches any picker.
    authHeader()
      .then((headers) =>
        fetch(`${BACKEND}/tts/voices?language=${encodeURIComponent(language)}`, {
          headers,
          signal: controller.signal,
        })
      )
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error("voices"))))
      .then((body: { voices: Voice[] }) => {
        setVoices(body.voices);
        const stored = localStorage.getItem(`${VOICE_PREF_KEY}-${language}`);
        const valid = stored && body.voices.some((v) => v.id === stored);
        setVoiceId(valid ? stored! : (body.voices[0]?.id ?? ""));
      })
      .catch(() => undefined);
    return () => controller.abort();
  }, [language]);

  useEffect(() => {
    const raf = requestAnimationFrame(() => {
      // Default ON. Reading a translation aloud is the whole point of the
      // feature; requiring a click per line defeats the interpreter use case.
      // An explicit "off" is respected, an absent preference is not.
      setAutoSpeak(localStorage.getItem(AUTOSPEAK_KEY) !== "off");
    });
    return () => cancelAnimationFrame(raf);
  }, []);

  // Shape is stored per voice: "Miles, a bit deeper and slower" is a different
  // preference from "Aria at default", and switching voices should recall it.
  useEffect(() => {
    if (!voiceId) return;
    const raf = requestAnimationFrame(() => {
      const raw = localStorage.getItem(`${SHAPE_KEY}-${voiceId}`);
      if (!raw) {
        setShape(DEFAULT_SHAPE);
        return;
      }
      try {
        // Clamped on read as well as write: a preference stored by an older
        // build has no volume/pauses keys, and a hand-edited value could sit
        // outside the usable range.
        setShape(clampShape(JSON.parse(raw) as Partial<VoiceShape>, DEFAULT_SHAPE));
      } catch {
        setShape(DEFAULT_SHAPE);
      }
    });
    return () => cancelAnimationFrame(raf);
  }, [voiceId]);

  const adjustShape = useCallback(
    (next: Partial<VoiceShape>) => {
      setShape((prev) => {
        const merged = clampShape(next, prev);
        if (voiceId) localStorage.setItem(`${SHAPE_KEY}-${voiceId}`, JSON.stringify(merged));
        return merged;
      });
    },
    [voiceId],
  );

  const resetShape = useCallback(() => {
    setShape(DEFAULT_SHAPE);
    if (voiceId) localStorage.removeItem(`${SHAPE_KEY}-${voiceId}`);
  }, [voiceId]);

  const chooseVoice = useCallback(
    (id: string) => {
      setVoiceId(id);
      localStorage.setItem(`${VOICE_PREF_KEY}-${language}`, id);
    },
    [language],
  );

  const toggleAutoSpeak = useCallback(() => {
    setAutoSpeak((prev) => {
      const next = !prev;
      localStorage.setItem(AUTOSPEAK_KEY, next ? "on" : "off");
      return next;
    });
  }, []);

  const stop = useCallback(() => {
    // Invalidate any in-flight sentence chain before cancelling. Without this,
    // a queued sentence's timer would fire after `cancel()` and start speaking
    // again — the pause dimension turns one utterance into several, so "stop"
    // has to mean the whole sequence.
    speakRun.current += 1;
    if (pauseTimer.current !== null) {
      clearTimeout(pauseTimer.current);
      pauseTimer.current = null;
    }
    if (typeof window !== "undefined" && "speechSynthesis" in window) {
      window.speechSynthesis.cancel();
    }
    audioRef.current?.pause();
    audioRef.current = null;
    setSpeaking(false);
  }, []);

  /**
   * How many *actually different* OS voices back the catalogue right now.
   *
   * The catalogue offers six named voices per language, but a device only has
   * what it has: macOS ships a single Korean voice, so all six Korean entries
   * resolve to Yuna. Offering six identical-sounding options — including "male"
   * ones that are audibly female — is the picker lying about the device. The UI
   * uses this to say so plainly instead.
   */
  const distinctVoices = useCallback(() => {
    const available = currentOsVoices();
    if (available.length === 0 || voices.length === 0) return null;
    const resolved = resolveVoiceMap(voices, available);
    const named = voices.filter((v) => v.browser_hint);
    const unique = new Set(named.map((v) => resolved.get(v.id)?.name).filter(Boolean));
    return { unique: unique.size, offered: named.length };
  }, [currentOsVoices, voices]);

  const speak = useCallback(
    async (text: string, overrideVoiceId?: string) => {
      const trimmed = text.trim();
      const id = overrideVoiceId ?? voiceId;
      if (!trimmed || !id) return;

      stop(); // never let two lines talk over each other
      const run = speakRun.current; // stop() just bumped this; own it
      setError(null);
      const voice = voices.find((v) => v.id === id);

      // Browser tier: no network call at all.
      if (!voice || voice.provider === "browser") {
        if (typeof window === "undefined" || !("speechSynthesis" in window)) {
          setError("This browser can't speak text aloud.");
          return;
        }

        let osVoice: SpeechSynthesisVoice | undefined;
        if (voice) {
          const available = currentOsVoices();
          osVoice = resolveVoiceMap(voices, available).get(voice.id);
          if (!osVoice && available.length > 0) {
            // The device has voices, but none for this language. Speaking anyway
            // would read the text with a wrong-language voice (Hangul in an
            // English voice is unintelligible), so refuse and say why. The
            // translation itself is already on screen, so nothing is lost.
            setError(
              `This device has no ${languageName(language)} voice installed, so it can't read ` +
                `${languageName(language)} aloud. The text above is still correct.`,
            );
            return;
          }
        }

        const build = (chunk: string) => {
          const utterance = new SpeechSynthesisUtterance(chunk);
          utterance.lang = language === "ko" ? "ko-KR" : "en-US";
          utterance.pitch = shape.pitch;
          utterance.rate = shape.rate;
          utterance.volume = shape.volume;
          if (osVoice) utterance.voice = osVoice;
          return utterance;
        };

        // No added pauses: one utterance, exactly as before.
        if (shape.pauses <= 0) {
          const utterance = build(trimmed);
          utterance.onend = () => setSpeaking(false);
          utterance.onerror = () => setSpeaking(false);
          setSpeaking(true);
          window.speechSynthesis.speak(utterance);
          return;
        }

        // Pauses on: speak sentence by sentence with real silence between, which
        // is what makes speech sound unhurried rather than just slow.
        const sentences = splitSentences(trimmed);
        setSpeaking(true);
        const sayFrom = (index: number) => {
          if (speakRun.current !== run) return; // superseded by a newer call
          if (index >= sentences.length) {
            setSpeaking(false);
            return;
          }
          const utterance = build(sentences[index]);
          const next = () => {
            if (speakRun.current !== run) return;
            if (index + 1 >= sentences.length) {
              setSpeaking(false);
              return;
            }
            pauseTimer.current = setTimeout(() => sayFrom(index + 1), shape.pauses);
          };
          utterance.onend = next;
          utterance.onerror = () => setSpeaking(false);
          window.speechSynthesis.speak(utterance);
        };
        sayFrom(0);
        return;
      }

      // Cloud / custom tier: fetch audio and play it.
      setSpeaking(true);
      try {
        // postJson attaches the caller's token. Cloud voices are Pro-only and
        // metered, so an unauthenticated call is a 401 — which is exactly how
        // read-aloud stopped working the moment a cloud provider was enabled.
        const body = await postJson<{
          speak_locally?: boolean;
          audio_base64?: string;
          mime_type?: string;
        }>("/tts/speak", {
          text: trimmed,
          voice_id: id,
          // Expressiveness is rendered by the provider, so it has to travel with
          // the request rather than being applied on playback.
          expressiveness: shape.expressiveness,
        });
        if (body.speak_locally || !body.audio_base64) {
          setSpeaking(false);
          return;
        }
        const audio = new Audio(`data:${body.mime_type};base64,${body.audio_base64}`);
        // Volume applies to cloud audio too; pitch and rate are baked into what
        // the provider rendered, but tone is ours to shape on the way out.
        audio.volume = shape.volume;
        audioRef.current = audio;
        const teardown = applyToneGraph(audio, shape);
        const finish = () => {
          teardown?.();
          setSpeaking(false);
        };
        audio.onended = finish;
        audio.onerror = finish;
        await audio.play();
      } catch (err) {
        setSpeaking(false);
        setError(err instanceof Error ? err.message : "Couldn't speak that.");
      }
    },
    [currentOsVoices, language, shape, stop, voiceId, voices],
  );

  return {
    voices,
    voiceId,
    distinctVoices,
    chooseVoice,
    speak,
    stop,
    speaking,
    autoSpeak,
    toggleAutoSpeak,
    shape,
    adjustShape,
    resetShape,
    error,
  };
}
