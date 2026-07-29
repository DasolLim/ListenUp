"use client";

import { useEffect, useState } from "react";

const SIZES = [
  { key: "S", scale: 0.875 },
  { key: "M", scale: 1 },
  { key: "L", scale: 1.25 },
  { key: "XL", scale: 1.5 },
] as const;

type SizeKey = (typeof SIZES)[number]["key"];

function apply(contrast: boolean, size: SizeKey) {
  const root = document.documentElement;
  if (contrast) root.setAttribute("data-contrast", "high");
  else root.removeAttribute("data-contrast");
  const scale = SIZES.find((s) => s.key === size)?.scale ?? 1;
  root.style.setProperty("--caption-scale", String(scale));
}

/**
 * Persistent accessibility controls: high-contrast mode + caption text size.
 * Choices persist for the session (sessionStorage) and apply on every page.
 * Reduced motion needs no control — the media query is honored globally.
 */
export default function A11yBar() {
  const [contrast, setContrast] = useState(false);
  const [size, setSize] = useState<SizeKey>("M");

  useEffect(() => {
    // Deferred so hydration completes with the default UI before stored
    // preferences are applied (and to keep setState out of the sync effect body).
    const raf = requestAnimationFrame(() => {
      const storedContrast = sessionStorage.getItem("a11y-contrast") === "high";
      const storedSize = (sessionStorage.getItem("a11y-caption-size") as SizeKey) || "M";
      setContrast(storedContrast);
      setSize(storedSize);
      apply(storedContrast, storedSize);
    });
    return () => cancelAnimationFrame(raf);
  }, []);

  function toggleContrast() {
    const next = !contrast;
    setContrast(next);
    sessionStorage.setItem("a11y-contrast", next ? "high" : "normal");
    apply(next, size);
  }

  function chooseSize(next: SizeKey) {
    setSize(next);
    sessionStorage.setItem("a11y-caption-size", next);
    apply(contrast, next);
  }

  return (
    <section
      aria-label="Accessibility options"
      className="glass-card glass-strong fixed bottom-4 right-4 z-40 flex items-center gap-3 rounded-full px-4 py-2"
    >
      <button
        type="button"
        aria-pressed={contrast}
        onClick={toggleContrast}
        className={`inline-flex min-h-11 items-center rounded-full px-3.5 text-[13px] font-medium transition-colors ${
          contrast ? "bg-(--text-primary) text-white" : "pill-inactive text-ink-soft hover:text-ink"
        }`}
      >
        High contrast {contrast ? "on" : "off"}
      </button>

      <div role="group" aria-label="Caption text size" className="flex items-center gap-1">
        {SIZES.map((option) => (
          <button
            key={option.key}
            type="button"
            aria-pressed={size === option.key}
            aria-label={`Caption size ${option.key}`}
            onClick={() => chooseSize(option.key)}
            className={`inline-flex min-h-11 min-w-11 items-center justify-center rounded-full text-[13px] font-semibold transition-colors ${
              size === option.key
                ? "bg-accent-strong text-on-accent"
                : "pill-inactive text-ink-soft hover:text-ink"
            }`}
          >
            {option.key}
          </button>
        ))}
      </div>
    </section>
  );
}
