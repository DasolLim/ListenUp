"use client";

import { useCallback, useEffect, useRef, useState } from "react";

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
 * Browser TTS exposes pitch and rate, and nothing else — there is no real
 * male↔female morph available from any provider. Pitch is the honest dial:
 * lower reads more masculine, higher more feminine, so one preset voice covers
 * a range. Rate is an accessibility control in its own right, since slower
 * speech is easier to follow.
 */
export type VoiceShape = { pitch: number; rate: number };

export const DEFAULT_SHAPE: VoiceShape = { pitch: 1, rate: 1 };
// Web Speech allows pitch 0–2 and rate 0.1–10, but the extremes are unusable
// (chipmunk / unintelligible), so the UI stays inside a range that always
// produces speech a person can follow.
export const SHAPE_LIMITS = { pitch: { min: 0.5, max: 1.8 }, rate: { min: 0.6, max: 1.6 } };

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
): SpeechSynthesisVoice | undefined {
  const forLanguage = available.filter((v) => v.lang.toLowerCase().startsWith(voice.language));
  for (const hint of voice.browser_hint.split("|").filter(Boolean)) {
    const match = forLanguage.find((v) => v.name.toLowerCase().includes(hint.toLowerCase()));
    if (match) return match;
  }
  return forLanguage[0];
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
    fetch(`${BACKEND}/tts/voices?language=${encodeURIComponent(language)}`, {
      signal: controller.signal,
    })
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
        const parsed = JSON.parse(raw) as VoiceShape;
        setShape({
          pitch: Number(parsed.pitch) || 1,
          rate: Number(parsed.rate) || 1,
        });
      } catch {
        setShape(DEFAULT_SHAPE);
      }
    });
    return () => cancelAnimationFrame(raf);
  }, [voiceId]);

  const adjustShape = useCallback(
    (next: Partial<VoiceShape>) => {
      setShape((prev) => {
        const merged = { ...prev, ...next };
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
    if (typeof window !== "undefined" && "speechSynthesis" in window) {
      window.speechSynthesis.cancel();
    }
    audioRef.current?.pause();
    audioRef.current = null;
    setSpeaking(false);
  }, []);

  const speak = useCallback(
    async (text: string, overrideVoiceId?: string) => {
      const trimmed = text.trim();
      const id = overrideVoiceId ?? voiceId;
      if (!trimmed || !id) return;

      stop(); // never let two lines talk over each other
      setError(null);
      const voice = voices.find((v) => v.id === id);

      // Browser tier: no network call at all.
      if (!voice || voice.provider === "browser") {
        if (typeof window === "undefined" || !("speechSynthesis" in window)) {
          setError("This browser can't speak text aloud.");
          return;
        }
        const utterance = new SpeechSynthesisUtterance(trimmed);
        utterance.lang = language === "ko" ? "ko-KR" : "en-US";
        utterance.pitch = shape.pitch;
        utterance.rate = shape.rate;
        if (voice) {
          const available = currentOsVoices();
          const os = pickBrowserVoice(voice, available);
          if (os) {
            utterance.voice = os;
          } else if (available.length > 0) {
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
        utterance.onend = () => setSpeaking(false);
        utterance.onerror = () => setSpeaking(false);
        setSpeaking(true);
        window.speechSynthesis.speak(utterance);
        return;
      }

      // Cloud / custom tier: fetch audio and play it.
      setSpeaking(true);
      try {
        const response = await fetch(`${BACKEND}/tts/speak`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ text: trimmed, voice_id: id }),
        });
        const body = await response.json();
        if (!response.ok) throw new Error(body.detail ?? "Couldn't speak that.");
        if (body.speak_locally || !body.audio_base64) {
          setSpeaking(false);
          return;
        }
        const audio = new Audio(`data:${body.mime_type};base64,${body.audio_base64}`);
        audioRef.current = audio;
        audio.onended = () => setSpeaking(false);
        audio.onerror = () => setSpeaking(false);
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
