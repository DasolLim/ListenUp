"use client";

import { useEffect, useRef, useState } from "react";
import type { CaptionSegment } from "@/lib/useTranscription";

const BACKEND = process.env.NEXT_PUBLIC_BACKEND_URL ?? "http://localhost:8000";

export type SlangNote = {
  phrase: string;
  meaning: string;
  cultural_context: string;
  equivalent: string;
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

function percentile(sorted: number[], p: number): number {
  if (!sorted.length) return 0;
  return sorted[Math.max(0, Math.min(sorted.length - 1, Math.ceil((p / 100) * sorted.length) - 1))];
}

/** Translates each finalized caption once (instant Google lane), then
 * augments with LLM slang notes asynchronously — captions never wait. */
export function useLiveTranslation(
  segments: CaptionSegment[],
  targetLang: string,
  enabled: boolean
) {
  const [translations, setTranslations] = useState<Record<string, LiveTranslation>>({});
  const [stats, setStats] = useState<TranslationStats>(null);
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
      fetch(`${BACKEND}/translate`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text: segment.text, target_lang: targetLang }),
      })
        .then(async (r) => {
          if (!r.ok) throw new Error();
          const body = await r.json();
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
        .catch(() => undefined);

      // Slow lane: cultural annotations; never blocks the fast line.
      fetch(`${BACKEND}/translate/enhanced`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text: segment.text, target_lang: targetLang }),
      })
        .then(async (r) => {
          if (!r.ok) return;
          const body = await r.json();
          setCosts((c) => ({ ...c, llmTokens: c.llmTokens + (body.tokens ?? 0) }));
          if (!body.slangNotes?.length) return;
          setTranslations((map) => {
            const existing = map[segment.id];
            if (!existing) return map;
            return {
              ...map,
              [segment.id]: { ...existing, notes: body.slangNotes, register: body.register },
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
    setCosts({ googleChars: 0, llmTokens: 0, requests: 0, cacheHits: 0 });
  };

  return { translations, stats, costs, reset };
}
