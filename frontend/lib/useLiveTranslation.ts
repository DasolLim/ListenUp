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

/**
 * Translates each finalized caption once (instant Google lane), then augments
 * with LLM slang notes asynchronously — captions never wait.
 *
 * Both lanes go through `postJson`, which attaches the caller's token. They are
 * metered endpoints, so an unauthenticated call is a 401 — and until this was
 * fixed both lanes swallowed that into an empty result, so translation simply
 * never appeared and nothing on screen said why.
 */
export function useLiveTranslation(
  segments: CaptionSegment[],
  targetLang: string,
  enabled: boolean
) {
  const [translations, setTranslations] = useState<Record<string, LiveTranslation>>({});
  const [stats, setStats] = useState<TranslationStats>(null);
  const [failure, setFailure] = useState<TranslationFailure | null>(null);
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
            [segment.id]: {
              text: body.translation,
              sourceLang: body.detectedSourceLang,
              notes: [],
              register: null,
            },
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

      // Slow lane: the LLM's culturally-adapted translation plus slang notes.
      // Never blocks the fast line, and its failures stay quiet — the Google
      // translation is already on screen, so there is nothing to explain.
      postJson<{
        translation?: string;
        register?: string;
        slangNotes?: SlangNote[];
        tokens?: number;
      }>("/translate/enhanced", { text: segment.text, target_lang: targetLang })
        .then((body) => {
          setCosts((c) => ({ ...c, llmTokens: c.llmTokens + (body.tokens ?? 0) }));
          if (!body.translation && !body.slangNotes?.length) return;
          setTranslations((map) => {
            const existing = map[segment.id];
            if (!existing) return map;
            return {
              ...map,
              [segment.id]: {
                ...existing,
                // Upgrade the fast Google line to the LLM's culturally-adapted
                // translation once it arrives (progressive enhancement).
                text: body.translation ?? existing.text,
                notes: body.slangNotes ?? existing.notes,
                register: body.register ?? existing.register,
              },
            };
          });
        })
        .catch(() => undefined);
    }
  }, [segments, targetLang, enabled]);

  const reset = () => {
    requested.current = new Set();
    timings.current = [];
    setTranslations({});
    setStats(null);
    setFailure(null);
    setCosts({ googleChars: 0, llmTokens: 0, requests: 0, cacheHits: 0 });
  };

  return { translations, stats, costs, failure, reset };
}
