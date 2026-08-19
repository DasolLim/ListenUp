"use client";

import Link from "next/link";

/**
 * The prompt that turns "Speaker 2" into "Mom".
 *
 * Naming is the moat: enterprise meeting tools get identity free from
 * per-participant channels and logins, and cannot name anyone at all in a
 * single-microphone conversation in a room. This product can — but only if
 * someone tells it who is talking once, and until now the way to do that lived
 * in Settings with nothing pointing at it from the moment it would help.
 *
 * Two routes, because they suit different moments. Tapping a name works
 * immediately and needs no setup; enrolling a voice profile makes the
 * recognition automatic next time. The copy leads with the benefit rather than
 * the mechanism (PRODUCT.md voice: plain, second person, no cuteness).
 *
 * Dismissible, and shown at most once per session. A hint that keeps returning
 * while somebody is trying to follow a conversation stops being a hint.
 */
export default function SpeakerNamingNudge({ onDismiss }: { onDismiss: () => void }) {
  return (
    <div
      role="status"
      className="flex flex-wrap items-center gap-x-3 gap-y-1.5 rounded-2xl border border-white/60 bg-white/50 px-4 py-2.5 text-[13px] leading-relaxed text-ink-soft"
    >
      <p className="min-w-0 flex-1">
        {"Tap a speaker’s name to say who they are. It sticks for the rest of the "}
        {"conversation, even if the microphone loses track of them, and "}
        <Link href="/settings" className="text-ink underline underline-offset-2">
          a voice profile
        </Link>
        {" lets ListenUp recognise them on its own next time."}
      </p>
      <button
        type="button"
        onClick={onDismiss}
        className="min-h-11 shrink-0 rounded-full px-3 text-[13px] text-ink-soft hover:text-ink"
      >
        Got it
      </button>
    </div>
  );
}
