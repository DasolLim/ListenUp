"use client";

import { useCallback, useEffect, useState } from "react";

/**
 * A boolean preference that survives a reload.
 *
 * The sibling of `useStickyLanguage`, for switches rather than choices. It
 * exists because the settings it holds cost money: a user who turned slang
 * explanations off to save their allowance should not find them back on after
 * a refresh, quietly spending again.
 *
 * Reads on mount rather than during render so the server and the first client
 * paint agree — `localStorage` does not exist on the server, and a value read
 * during render is a hydration mismatch waiting to happen.
 */
export function useStickyFlag(key: string, fallback: boolean) {
  const [value, setValue] = useState(fallback);

  useEffect(() => {
    // Applied after paint, matching `useStickyLanguage`: the first render must
    // use `fallback` so server and client markup agree, and deferring keeps the
    // read out of the effect body synchronously.
    const raf = requestAnimationFrame(() => {
      try {
        const stored = window.localStorage.getItem(key);
        if (stored === "true" || stored === "false") setValue(stored === "true");
      } catch {
        // Private browsing, or storage disabled. The default stands.
      }
    });
    return () => cancelAnimationFrame(raf);
  }, [key]);

  const update = useCallback(
    (next: boolean) => {
      setValue(next);
      try {
        window.localStorage.setItem(key, String(next));
      } catch {
        // Not being able to remember the choice must not stop the user making it.
      }
    },
    [key]
  );

  return [value, update] as const;
}
