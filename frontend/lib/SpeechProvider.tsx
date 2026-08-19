"use client";

import { createContext, useContext, useEffect, useRef, type ReactNode } from "react";
import { useSpeech } from "@/lib/useSpeech";

type Speech = ReturnType<typeof useSpeech>;

const SpeechContext = createContext<Speech | null>(null);

/**
 * One speech engine for the whole app.
 *
 * Before this, every surface that could speak called `useSpeech()` itself:
 * live captions, both translate tools, and the GenZ explainer. Four independent
 * instances meant four separate voice selections, four copies of the shape
 * state, and no coordination — the voice you chose in one tool did not apply in
 * another, and two surfaces could talk over each other.
 *
 * `language` is the *target* language of whatever is being read aloud, so the
 * provider is mounted per surface with that surface's target rather than once at
 * the root: reading a Korean translation needs Korean voices even though the UI
 * chrome is English.
 */
export function SpeechProvider({
  language,
  children,
}: {
  language: string;
  children: ReactNode;
}) {
  const speech = useSpeech(language);
  return <SpeechContext.Provider value={speech}>{children}</SpeechContext.Provider>;
}

/**
 * The shared speech engine.
 *
 * Throws when used outside a provider rather than silently falling back to a
 * private instance: a component that thinks it is sharing state but is not
 * produces exactly the drift this provider exists to remove.
 */
export function useSharedSpeech(): Speech {
  const speech = useContext(SpeechContext);
  if (speech === null) {
    throw new Error("useSharedSpeech must be used inside a <SpeechProvider>.");
  }
  return speech;
}

/**
 * Speak `text` once, automatically, when auto-speak is on.
 *
 * This logic was written three times by hand (live captions keyed on segment id,
 * both translate tools keyed on the text) and each copy tracked "already spoken"
 * differently. One implementation keyed on a caller-supplied identity is the
 * whole feature.
 *
 * `key` identifies the utterance: pass the text for translations, or a segment
 * id for captions where the same sentence can legitimately repeat. Passing an
 * empty key disables it, which is how a surface opts out when auto-speak should
 * not apply (e.g. translation is off).
 */
export function useAutoSpeak(key: string, text: string) {
  const speech = useSharedSpeech();
  const spoken = useRef<Set<string>>(new Set());

  useEffect(() => {
    if (!speech.autoSpeak || !key || !text) return;
    if (spoken.current.has(key)) return;
    spoken.current.add(key);
    void speech.speak(text);
  }, [key, text, speech]);
}
