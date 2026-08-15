"use client";

import type { ProfileOption } from "@/lib/useSpeakerCorrection";

/**
 * "Who is Speaker 2?" — the enrolled people, plus an honest way out.
 *
 * Inline rather than a modal: the answer is in the transcript directly above
 * it, so covering the conversation to ask about the conversation would take
 * away the only thing that makes the question answerable.
 */
export default function SpeakerCorrectionDialog({
  label,
  options,
  onApply,
  onCancel,
}: {
  /** The speaker being named, as the transcript currently labels them. */
  label: string;
  options: ProfileOption[];
  onApply: (profileId: string | null) => void;
  onCancel: () => void;
}) {
  return (
    <div
      role="dialog"
      aria-label={`Who is ${label}?`}
      className="glass-card glass-strong flex flex-wrap items-center gap-2 rounded-2xl p-4"
    >
      <p className="mr-1 text-sm font-medium text-ink">Who is {label}?</p>
      {options.map((option) => (
        <button
          key={option.id}
          type="button"
          onClick={() => onApply(option.id)}
          className="pill-active min-h-11 rounded-full px-4 text-sm font-medium text-ink shadow-glass"
        >
          {option.display_name}
        </button>
      ))}

      {/* Enrolling nobody is the common first-run state, and an empty row of
          buttons explains nothing. */}
      {options.length === 0 && (
        <p className="text-sm text-ink-soft">
          No voice profiles yet — enrol someone to name them automatically.
        </p>
      )}

      {/* Not a cancel: it clears a wrong name. A wrong name is worse than none
          (INTRODUCTION §7), so unsaying one has to be as easy as saying it. */}
      <button
        type="button"
        onClick={() => onApply(null)}
        className="pill-inactive min-h-11 rounded-full px-4 text-sm text-ink-soft hover:text-ink"
      >
        Not sure / unknown
      </button>
      <button
        type="button"
        onClick={onCancel}
        className="ml-auto min-h-11 rounded-full px-3 text-sm text-ink-soft hover:text-ink"
      >
        Cancel
      </button>
    </div>
  );
}
