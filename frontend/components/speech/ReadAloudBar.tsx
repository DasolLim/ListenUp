"use client";

import Link from "next/link";
import SpeakButton from "@/components/speech/SpeakButton";
import { type Voice } from "@/lib/useSpeech";

/**
 * Read-aloud control attached to a *result*, not to the input.
 *
 * The old placement asked users to configure a voice before any output existed.
 * This sits under the translation it speaks, states which voice will be used in
 * words, and links to the dashboard for anything more (voice choice, pitch,
 * speed) so the tool page stays uncluttered.
 */
export default function ReadAloudBar({
  text,
  voice,
  onSpeak,
  onStop,
  speaking,
  autoSpeak,
  onToggleAutoSpeak,
}: {
  text: string;
  voice: Voice | undefined;
  onSpeak: () => void;
  onStop: () => void;
  speaking: boolean;
  autoSpeak: boolean;
  onToggleAutoSpeak: () => void;
}) {
  if (!text) return null;

  return (
    <div className="flex flex-wrap items-center gap-x-3 gap-y-2 border-t border-white/50 pt-3">
      <SpeakButton onSpeak={onSpeak} onStop={onStop} speaking={speaking} label="the translation" />

      <p className="text-[13px] text-ink-soft">
        {speaking ? "Speaking" : "Read aloud"}
        {voice ? (
          <>
            {" in "}
            <span className="font-medium text-ink">{voice.label}</span>
          </>
        ) : null}
      </p>

      {/* Auto-speak is the interpreter mode: on, every new translation speaks
          itself, so nobody has to click per line mid-conversation. */}
      <button
        type="button"
        aria-pressed={autoSpeak}
        onClick={onToggleAutoSpeak}
        className={`inline-flex min-h-11 items-center rounded-full px-3.5 text-[13px] font-medium transition-colors ${
          autoSpeak
            ? "bg-accent-strong text-on-accent"
            : "pill-inactive text-ink-soft hover:text-ink"
        }`}
      >
        Speak automatically {autoSpeak ? "on" : "off"}
      </button>

      <Link
        href="/dashboard#voice-studio"
        className="inline-flex min-h-11 items-center text-[13px] text-ink-soft underline underline-offset-2 hover:text-ink"
      >
        Change voice
      </Link>
    </div>
  );
}
