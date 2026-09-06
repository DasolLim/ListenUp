"use client";

import { type ReactNode } from "react";
import GlassCard from "@/components/ui/GlassCard";

/**
 * Shared frame for both translate tools.
 *
 * Fixes the crowding the old layout had: mode pills, target language, voice
 * select, preview and auto-speak all sat above the input at equal weight, so a
 * user arriving mid-conversation had six things competing and no obvious first
 * step (docs/product/PRODUCT.md principle 5).
 *
 * The order here is the order of the task:
 *   1. title + what this tool does differently   (so the two tools are
 *      distinguishable, which they were not)
 *   2. how you're speaking / typing              (input mode)
 *   3. the input itself, and the action
 *   4. the result, with read-aloud attached to the output it speaks
 *
 * Read-aloud *settings* deliberately live on the dashboard instead: the voice
 * applies everywhere, so tuning it is an account job, not a per-translation one.
 */
export default function TranslateShell({
  title,
  tagline,
  modes,
  languageRow,
  children,
}: {
  title: string;
  /** One line on what this tool does that the other one doesn't. */
  tagline: string;
  modes: ReactNode;
  languageRow: ReactNode;
  children: ReactNode;
}) {
  return (
    <GlassCard strong className="flex flex-col gap-6 p-6">
      <header className="flex flex-col gap-1.5">
        <div className="flex flex-wrap items-center gap-2">
          <h2 className="font-display text-[22px] font-semibold text-ink">{title}</h2>
          <span className="rounded-full bg-white/70 px-2.5 py-0.5 text-[11px] font-semibold uppercase tracking-wide text-ink-soft"></span>
        </div>
        {/* Explanatory copy is the first thing to yield space on a phone: it is
            read once, while the transcript below it is read continuously. */}
        <p className="hidden max-w-xl text-sm leading-relaxed text-ink-soft sm:block">{tagline}</p>
      </header>

      {/* Setup row: how you input, and which language out. Quiet by design —
          these are settings, not the action. */}
      <div className="flex flex-wrap items-center justify-between gap-3 border-y border-white/40 py-3">
        {modes}
        {languageRow}
      </div>

      {children}
    </GlassCard>
  );
}
