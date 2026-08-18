/**
 * Merging the two translation lanes, and choosing what to read aloud.
 *
 * Pure, and in its own module with no React import, because the checks that
 * cover it used to reach in with a regex — `verify-translation-merge.mjs` cut
 * the hook out of the hook's file by matching `^export function
 * useLiveTranslation[\s\S]*$`, which worked only because these functions
 * happened to sit above it. Nothing enforced that ordering.
 */

import type { CaptionSegment } from "@/lib/captionStream";
import type { PaywallDetail } from "@/lib/plans";
import type { Summary } from "@/lib/stats";

export type SlangNote = {
  phrase: string;
  meaning: string;
  cultural_context: string;
  equivalent: string;
  // Was the definition supplied by our slang KB, or recalled by the model?
  // Optional because the mock and any pre-grounding cached payload omit them.
  grounded?: boolean;
  confidence?: "high" | "low";
};

export type LiveTranslation = {
  text: string;
  sourceLang: string | null;
  notes: SlangNote[];
  register: string | null;
};

export type TranslationStats = Summary;

export type TranslationCosts = {
  googleChars: number;
  llmTokens: number;
  requests: number;
  cacheHits: number;
};

/** Why translation stopped producing lines, when it did. */
export type TranslationFailure = {
  message: string;
  paywall: PaywallDetail | null;
};

const EMPTY_TRANSLATION: LiveTranslation = {
  text: "",
  sourceLang: null,
  notes: [],
  register: null,
};

/**
 * The two lanes race, and either can land first.
 *
 * The expected order is Google then the LLM, and the merge used to assume it:
 * the cultural result was dropped outright if the fast line had not arrived
 * yet, and the fast line overwrote whatever was there when it did. Both are
 * wrong under the order that actually happens often enough to notice — a cached
 * LLM answer returns in a few milliseconds while Google is still on the wire —
 * and the failure is silent and per-utterance, so one line keeps its slang
 * explanation and the next one loses it for good.
 *
 * These are pure so the orderings can be tested without a browser
 * (`npm run verify`). The invariant both directions share: **a cultural result
 * is never replaced by a plain one.**
 */
export function mergeFastLane(
  existing: LiveTranslation | undefined,
  body: { translation: string; detectedSourceLang: string | null }
): LiveTranslation {
  return {
    ...EMPTY_TRANSLATION,
    ...existing,
    // If something is already here, it can only have come from the cultural
    // lane, which is the better answer. Keep it and take only the source
    // language, which is the one thing the fast lane knows and it does not.
    text: existing?.text || body.translation,
    sourceLang: body.detectedSourceLang,
  };
}

export function mergeCulturalLane(
  existing: LiveTranslation | undefined,
  body: { translation?: string; register?: string; slangNotes?: SlangNote[] }
): LiveTranslation {
  const base = existing ?? EMPTY_TRANSLATION;
  return {
    ...base,
    // Progressive enhancement: the culturally-adapted line replaces the literal
    // one when it arrives, and stands alone when it arrives first.
    text: body.translation ?? base.text,
    notes: body.slangNotes ?? base.notes,
    register: body.register ?? base.register,
  };
}

/**
 * The newest line that is ready to be read aloud.
 *
 * "Ready" is the whole point: a line whose cultural pass has not settled still
 * shows the literal translation, and speaking it means the listener hears the
 * version this product exists to improve on while the reader sees the adapted
 * one. Interim lines are excluded because they are rewritten several times a
 * second, and speaking one would stutter.
 */
export function newestSpeakableLine(
  segments: CaptionSegment[],
  translations: Record<string, LiveTranslation>,
  isSettled: (id: string) => boolean
): CaptionSegment | undefined {
  return [...segments]
    .reverse()
    .find((s) => s.isFinal && translations[s.id] && isSettled(s.id));
}

