"use client";

import { useEffect, useRef, useState } from "react";
import { ApiError, postJson } from "@/lib/api";
import type { PaywallDetail } from "@/lib/plans";
import type { CaptionSegment } from "@/lib/useTranscription";

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

export type TranslationStats = { count: number; p50: number; p95: number } | null;

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

function percentile(sorted: number[], p: number): number {
  if (!sorted.length) return 0;
  return sorted[Math.max(0, Math.min(sorted.length - 1, Math.ceil((p / 100) * sorted.length) - 1))];
}

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

/**
 * Translates each finalized caption once (instant Google lane), then augments
 * with LLM slang notes asynchronously — captions never wait.
 *
 * Both lanes go through `postJson`, which attaches the caller's token. They are
 * metered endpoints, so an unauthenticated call is a 401 — and until this was
 * fixed both lanes swallowed that into an empty result, so translation simply
 * never appeared and nothing on screen said why.
 */
/** Which cultural-pass model to use. The server owns tier -> model. */
export type CulturalOptions = {
  /** Off skips `/translate/enhanced` entirely — no call, no spend, no notes. */
  enabled: boolean;
  tier: string;
};

export function useLiveTranslation(
  segments: CaptionSegment[],
  targetLang: string,
  enabled: boolean,
  cultural: CulturalOptions = { enabled: true, tier: "balanced" }
) {
  const [translations, setTranslations] = useState<Record<string, LiveTranslation>>({});
  const [stats, setStats] = useState<TranslationStats>(null);
  const [failure, setFailure] = useState<TranslationFailure | null>(null);
  const [culturalFailure, setCulturalFailure] = useState<TranslationFailure | null>(null);
  // Segments whose cultural pass has finished — succeeded, failed, or was never
  // going to run. Read-aloud waits for this rather than speaking the first
  // answer to arrive: the two lanes race, so speaking on arrival meant the
  // listener heard the literal machine translation while the reader saw the
  // culturally adapted one. In the interpreter case the person opposite hears
  // the version this product exists to improve on.
  const [settled, setSettled] = useState<Record<string, true>>({});
  const [costs, setCosts] = useState<TranslationCosts>({
    googleChars: 0,
    llmTokens: 0,
    requests: 0,
    cacheHits: 0,
  });
  const requested = useRef<Set<string>>(new Set());
  const timings = useRef<number[]>([]);

  useEffect(() => {
    if (!enabled) return;
    for (const segment of segments) {
      // One attempt per line, ever. That also settles what toggling the
      // cultural pass mid-conversation does: it applies to what is said next,
      // and does not go back and re-explain lines already on screen. Anything
      // else would spend money on old lines the moment a switch is flipped.
      if (!segment.isFinal || requested.current.has(segment.id)) continue;
      requested.current.add(segment.id);
      const t0 = performance.now();

      // Fast lane: Google (cached server-side), render on arrival.
      postJson<{
        translation: string;
        detectedSourceLang: string | null;
        characters?: number;
        cached?: boolean;
      }>("/translate", { text: segment.text, target_lang: targetLang })
        .then((body) => {
          timings.current.push(performance.now() - t0);
          setCosts((c) => ({
            ...c,
            googleChars: c.googleChars + (body.characters ?? 0),
            requests: c.requests + 1,
            cacheHits: c.cacheHits + (body.cached ? 1 : 0),
          }));
          const sorted = [...timings.current].sort((a, b) => a - b);
          setStats({
            count: sorted.length,
            p50: percentile(sorted, 50),
            p95: percentile(sorted, 95),
          });
          setTranslations((map) => ({
            ...map,
            [segment.id]: mergeFastLane(map[segment.id], {
              translation: body.translation,
              detectedSourceLang: body.detectedSourceLang,
            }),
          }));
        })
        .catch((err) => {
          // Surface it once. A caption that silently stops being translated is
          // indistinguishable from a broken product; "you've used this month's
          // translated captions" is something the user can act on.
          if (err instanceof ApiError) {
            setFailure({ message: err.message, paywall: err.paywall });
          } else {
            setFailure({ message: "Couldn't reach the translation service.", paywall: null });
          }
        });

      // Slow lane, and only if the user wants it. Skipping the request rather
      // than discarding the answer is the point: this lane is metered, so a
      // user who does not want slang notes should not be paying for them out
      // of an allowance they would rather spend on captions.
      if (!cultural.enabled) continue;

      // Slow lane: the LLM's culturally-adapted translation plus slang notes.
      //
      // Never blocks the fast line, but its failures are no longer silent. They
      // used to be, on the reasoning that the literal translation was already on
      // screen so there was nothing to say — which is exactly backwards for this
      // product. Explaining the slang IS the feature; a user who sees plain
      // translations of "LARPing" and "spill the tea" with no notes cannot tell
      // an outage, an exhausted allowance and a sentence with nothing to explain
      // apart, and every one of those needs a different response from them.
      postJson<{
        translation?: string;
        register?: string;
        slangNotes?: SlangNote[];
        tokens?: number;
      }>("/translate/enhanced", {
        text: segment.text,
        target_lang: targetLang,
        tier: cultural.tier,
      })
        .then((body) => {
          setCosts((c) => ({ ...c, llmTokens: c.llmTokens + (body.tokens ?? 0) }));
          setSettled((done) => ({ ...done, [segment.id]: true }));
          if (!body.translation && !body.slangNotes?.length) return;
          setTranslations((map) => ({
            ...map,
            [segment.id]: mergeCulturalLane(map[segment.id], body),
          }));
        })
        .catch((err) => {
          // Settle on failure too, or a line whose cultural pass 502s would
          // never be read aloud at all.
          setSettled((done) => ({ ...done, [segment.id]: true }));
          if (err instanceof ApiError) {
            setCulturalFailure({ message: err.message, paywall: err.paywall });
          } else {
            setCulturalFailure({
              message: "Couldn't reach the cultural translation service.",
              paywall: null,
            });
          }
        });
    }
  }, [segments, targetLang, enabled, cultural.enabled, cultural.tier]);

  const reset = () => {
    requested.current = new Set();
    timings.current = [];
    setTranslations({});
    setStats(null);
    setFailure(null);
    setCulturalFailure(null);
    setSettled({});
    setCosts({ googleChars: 0, llmTokens: 0, requests: 0, cacheHits: 0 });
  };

  // `failure` is the literal translation lane; `culturalFailure` is the slang
  // and register lane. Kept apart because they fail independently and mean
  // different things: one leaves the user with nothing, the other leaves them
  // with words but no meaning.
  // Derived rather than stored for the disabled case: with no cultural pass
  // there is nothing to wait for, and writing that into state from inside the
  // effect would be a synchronous setState on every render pass.
  const isSettled = (id: string) => !cultural.enabled || Boolean(settled[id]);

  return { translations, stats, costs, failure, culturalFailure, isSettled, reset };
}
