"use client";

import { useCallback, useEffect, useState } from "react";

/**
 * A language choice that survives a reload.
 *
 * Without this the target language resets to English on every visit, which
 * silently resets the chosen voice too (voice preferences are stored per
 * language). Someone who translates into Korean every day should not have to
 * re-pick Korean — and re-picking mid-conversation is exactly when they can't.
 *
 * Hydration-safe: the first render always uses `fallback`, and the stored value
 * is applied on the client afterwards, so server and client markup match.
 */
export function useStickyLanguage(
  storageKey: string,
  fallback = "en",
): [string, (next: string) => void] {
  const [value, setValue] = useState(fallback);

  useEffect(() => {
    const raf = requestAnimationFrame(() => {
      const stored = localStorage.getItem(storageKey);
      if (stored) setValue(stored);
    });
    return () => cancelAnimationFrame(raf);
  }, [storageKey]);

  const choose = useCallback(
    (next: string) => {
      setValue(next);
      localStorage.setItem(storageKey, next);
    },
    [storageKey],
  );

  return [value, choose];
}
