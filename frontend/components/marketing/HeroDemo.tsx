"use client";

import { useEffect, useState } from "react";
import Orb from "@/components/ui/Orb";

// The product's actual output, shown as the hero: speaker-named tinted bubbles.
const script = [
  { speaker: "Mom", tint: "var(--speaker-1)", text: "Are you coming over for dinner on Sunday?" },
  { speaker: "You", tint: "var(--speaker-3)", text: "Yes! I'll bring dessert. What time?" },
  { speaker: "Dad", tint: "var(--speaker-2)", text: "Six o'clock. Grandma's joining too." },
] as const;

const STEP_MS = 1300;
const HOLD_MS = 2600;

export default function HeroDemo() {
  const [shown, setShown] = useState(1);

  useEffect(() => {
    const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (reduced) {
      // static: reveal everything, no loop (deferred so it isn't a sync effect setState)
      const raf = requestAnimationFrame(() => setShown(script.length));
      return () => cancelAnimationFrame(raf);
    }
    let timer: ReturnType<typeof setTimeout>;
    const tick = (next: number) => {
      if (next > script.length) {
        timer = setTimeout(() => {
          setShown(1);
          timer = setTimeout(() => tick(2), STEP_MS);
        }, HOLD_MS);
        return;
      }
      setShown(next);
      timer = setTimeout(() => tick(next + 1), STEP_MS);
    };
    timer = setTimeout(() => tick(2), STEP_MS);
    return () => clearTimeout(timer);
  }, []);

  return (
    <div className="glass-card glass-strong w-full max-w-md p-5 sm:p-6" aria-hidden="true">
      <div className="flex items-center justify-between">
        <span className="flex items-center gap-2.5">
          <Orb size="sm" />
          <span className="font-display text-[15px] font-semibold">Live captions</span>
        </span>
        <span className="flex items-center gap-1.5 rounded-full bg-white/60 px-2.5 py-1 text-[12px] font-medium text-ink-soft">
          <span className="h-1.5 w-1.5 rounded-full bg-accent-strong" />
          00:12
        </span>
      </div>

      <div className="mt-4 flex min-h-64 flex-col justify-end gap-2.5">
        {script.slice(0, shown).map((line) => (
          <div
            key={line.speaker + line.text}
            className="bubble-glass rounded-2xl px-4 py-2.5"
            style={{ backgroundColor: line.tint }}
          >
            <p className="text-[11px] font-semibold uppercase tracking-wide text-ink-soft">
              {line.speaker}
            </p>
            <p className="mt-0.5 text-[15px] leading-snug text-ink">{line.text}</p>
          </div>
        ))}
      </div>
    </div>
  );
}
