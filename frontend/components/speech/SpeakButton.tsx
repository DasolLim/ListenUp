"use client";

/**
 * Reads one line of text aloud. Placed next to any translated output, so the
 * other person can hear their own language instead of the user reading it out.
 */
export default function SpeakButton({
  onSpeak,
  onStop,
  speaking,
  label,
  className = "",
}: {
  onSpeak: () => void;
  onStop: () => void;
  speaking: boolean;
  /** What is being spoken, for the accessible name (e.g. the speaker's name). */
  label?: string;
  className?: string;
}) {
  const accessibleName = speaking
    ? `Stop speaking${label ? ` ${label}` : ""}`
    : `Speak${label ? ` ${label}` : ""} aloud`;

  return (
    <button
      type="button"
      onClick={speaking ? onStop : onSpeak}
      aria-label={accessibleName}
      title={accessibleName}
      className={`inline-flex h-11 w-11 shrink-0 items-center justify-center rounded-full border border-line text-ink-soft transition-colors hover:text-coral ${className}`}
    >
      {speaking ? (
        // Stop: a square reads as "stop" without relying on colour.
        <svg width="15" height="15" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
          <rect x="6" y="6" width="12" height="12" rx="2" />
        </svg>
      ) : (
        <svg
          width="17"
          height="17"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          strokeLinecap="round"
          strokeLinejoin="round"
          aria-hidden="true"
        >
          <path d="M11 5 6 9H3v6h3l5 4V5Z" />
          <path d="M15.5 8.5a5 5 0 0 1 0 7" />
          <path d="M18.5 5.5a9 9 0 0 1 0 13" />
        </svg>
      )}
    </button>
  );
}
