"use client";

import { useEffect, useRef, useState } from "react";
import { ApiError, postJson } from "@/lib/api";
import type { CaptionSegment } from "@/lib/captionStream";
import { summarise } from "@/lib/stats";
import {
  mergeCulturalLane,
  mergeFastLane,
  type LiveTranslation,
  type SlangNote,
  type TranslationCosts,
  type TranslationFailure,
  type TranslationStats,
} from "@/lib/translationMerge";

export {
  mergeCulturalLane,
  mergeFastLane,
  newestSpeakableLine,
} from "@/lib/translationMerge";
export type {
  LiveTranslation,
  SlangNote,
  TranslationStats,
  TranslationCosts,
  TranslationFailure,
} from "@/lib/translationMerge";

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
          setStats(summarise(timings.current));
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
