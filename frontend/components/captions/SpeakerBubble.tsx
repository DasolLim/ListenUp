const tints = [
  "var(--speaker-1)",
  "var(--speaker-2)",
  "var(--speaker-3)",
  "var(--speaker-4)",
] as const;

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
};

/**
 * One caption line. The tint distinguishes speakers visually, but the name
 * label is always present — color is never the only signal (DESIGN_SYSTEM §7).
 */
export default function SpeakerBubble({ caption }: { caption: Caption }) {
  const tint = tints[caption.speakerIndex] ?? "var(--speaker-other)";
  return (
    <div
      className="bubble-glass rounded-2xl px-4 py-3"
      data-interim={caption.interim || undefined}
      style={{ backgroundColor: tint }}
    >
      <p className="text-[12px] font-semibold uppercase tracking-wide text-ink-soft">
        {caption.speakerName ?? caption.speaker}
      </p>
      {/* Interims de-emphasize via italics + ellipsis, never lighter text —
          lighter grays fall below AA on the tinted glass (DESIGN_SYSTEM §7). */}
      <p className={`caption-text mt-0.5 text-ink ${caption.interim ? "italic" : ""}`}>
        {caption.text}
        {caption.interim && (
          <>
            <span aria-hidden="true">…</span>
            <span className="sr-only"> (still transcribing)</span>
          </>
        )}
      </p>
    </div>
  );
}
