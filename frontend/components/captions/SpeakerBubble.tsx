const tints = [
  "var(--speaker-1)",
  "var(--speaker-2)",
  "var(--speaker-3)",
  "var(--speaker-4)",
] as const;

export type BubbleTranslation = {
  text: string;
  sourceLang: string | null;
  notes: { phrase: string; meaning: string; cultural_context: string; equivalent: string }[];
};

export type Caption = {
  id: string;
  speaker: string;
  /** Real person's name when voice-matched (enhanced mode). */
  speakerName?: string | null;
  /** Stable per-speaker index 0–3; anything beyond the cap uses the neutral tint. */
  speakerIndex: number;
  text: string;
  /** Interim (not yet final) text renders in a lighter style. */
  interim?: boolean;
  /** Live translation (combined mode): rendered as the main caption line. */
  translated?: BubbleTranslation | null;
};

/**
 * One caption line. The tint distinguishes speakers visually, but the name
 * label is always present — color is never the only signal (DESIGN_SYSTEM §7).
 * In enhanced mode the label is a button: tap to correct who's speaking.
 */
export default function SpeakerBubble({
  caption,
  onCorrectClick,
}: {
  caption: Caption;
  onCorrectClick?: (speakerLabel: string) => void;
}) {
  const tint = tints[caption.speakerIndex] ?? "var(--speaker-other)";
  const baseLabel = caption.speakerName ?? caption.speaker;
  const labelText = caption.translated?.sourceLang
    ? `${baseLabel} (${caption.translated.sourceLang.toUpperCase()})`
    : baseLabel;
  return (
    <div
      className="bubble-glass rounded-2xl px-4 py-3"
      data-interim={caption.interim || undefined}
      style={{ backgroundColor: tint }}
    >
      {onCorrectClick ? (
        <button
          type="button"
          onClick={() => onCorrectClick(caption.speaker)}
          aria-label={`Correct speaker: currently ${labelText}`}
          title="Tap to correct who's speaking"
          className="rounded text-[12px] font-semibold uppercase tracking-wide text-ink-soft underline decoration-dotted underline-offset-2 hover:text-ink"
        >
          {labelText}
        </button>
      ) : (
        <p className="text-[12px] font-semibold uppercase tracking-wide text-ink-soft">
          {labelText}
        </p>
      )}
      {/* Interims de-emphasize via italics + ellipsis, never lighter text —
          lighter grays fall below AA on the tinted glass (DESIGN_SYSTEM §7). */}
      <p className={`caption-text mt-0.5 text-ink ${caption.interim ? "italic" : ""}`}>
        {caption.translated ? caption.translated.text : caption.text}
        {caption.interim && (
          <>
            <span aria-hidden="true">…</span>
            <span className="sr-only"> (still transcribing)</span>
          </>
        )}
      </p>
      {caption.translated && (
        <p className="mt-0.5 text-[13px] text-ink">
          <span className="sr-only">Original: </span>
          {caption.text}
        </p>
      )}
      {caption.translated && caption.translated.notes.length > 0 && (
        <details className="mt-1.5 rounded-xl border border-white/60 bg-white/50 px-3 py-2">
          <summary className="cursor-pointer text-[13px] font-medium text-ink">
            {caption.translated.notes.length} slang note
            {caption.translated.notes.length > 1 ? "s" : ""}
          </summary>
          <ul className="mt-1 flex flex-col gap-1 text-[13px] text-ink">
            {caption.translated.notes.map((note) => (
              <li key={note.phrase}>
                <strong>“{note.phrase}”</strong> — {note.meaning}
                {note.equivalent ? ` (≈ ${note.equivalent})` : ""}
              </li>
            ))}
          </ul>
        </details>
      )}
    </div>
  );
}
