"use client";

import { type ReactNode } from "react";

/**
 * The chrome above a transcript: who is listening, and what you can do about it.
 *
 * Shared by live captions and Translate's voice mode so the two cannot drift,
 * and — more to the point — so a QA page can render it. Both tool pages are
 * auth-gated, which is why the pane itself already lives on `/design`; the
 * chrome had the same problem and the same fix.
 *
 * **`compact` is the feature, not a style.** On a 390x844 phone the expanded
 * header pushed the transcript's bottom edge 166px below the fold, so a user
 * had to scroll before the "newest line never moves" guarantee applied at all —
 * the original complaint, reappearing on the device where captions matter most.
 *
 * What collapses is chosen by what a running session can still use. The spoken
 * language picker is already `disabled` while listening, so displaying it costs
 * height to show something inert. The rest stays reachable behind one
 * disclosure rather than being removed: a translation target or a voice is
 * still worth changing mid-conversation, and dropping a control to win layout
 * is not a trade this product makes.
 */
export default function SessionHeader({
  title,
  status,
  compact,
  orb,
  setup,
  actions,
}: {
  title: string;
  status: string;
  /** True while a session is running or paused. */
  compact: boolean;
  /** The level meter, when there is one. */
  orb?: ReactNode;
  /** Controls that configure the *next* session: languages, voices, toggles. */
  setup?: ReactNode;
  /** Start / pause / stop. Always visible — these are why you looked up. */
  actions?: ReactNode;
}) {
  return (
    <div className={compact ? "flex flex-col gap-2" : "flex flex-col gap-3"}>
      <div
        className={
          compact ? "flex items-center gap-2" : "flex flex-wrap items-center justify-between gap-3"
        }
      >
        <div
          className={compact ? "flex min-w-0 flex-1 items-center gap-2" : "flex items-center gap-3"}
        >
          {/* Measured, not styled to taste: at 64px the orb alone drove the
              header to 189px on a 390px phone and pushed the transcript off
              screen. The level meter is a "your mic is working" signal, which
              a smaller circle carries just as well. */}
          <div className={compact ? "[&>*]:size-8" : undefined}>{orb}</div>
          <div className="min-w-0">
            {/* The heading stays in the accessibility tree while a session runs
                — a screen-reader user still needs to know which tool this is —
                but stops spending 30px of a phone screen on a fact the person
                reading their own conversation already knows. */}
            <h2 className={compact ? "sr-only" : "font-display text-[22px] font-semibold"}>
              {title}
            </h2>
            <p
              role="status"
              className={
                compact ? "truncate text-[13px] text-ink-soft" : "mt-0.5 text-sm text-ink-soft"
              }
            >
              {status}
            </p>
          </div>
        </div>
        <div
          className={
            compact ? "flex shrink-0 items-center gap-2" : "flex flex-wrap items-center gap-2"
          }
        >
          {actions}
        </div>
      </div>

      {setup ? (
        compact ? (
          <details>
            <summary className="inline-flex min-h-11 cursor-pointer list-none items-center text-[13px] text-ink-soft hover:text-ink">
              Session settings
            </summary>
            <div className="mt-2 flex flex-wrap items-center gap-2 border-t border-white/40 pt-2">
              {setup}
            </div>
          </details>
        ) : (
          <div className="flex flex-wrap items-center gap-2">{setup}</div>
        )
      ) : null}
    </div>
  );
}
