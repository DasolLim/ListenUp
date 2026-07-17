const tints = [
  "var(--speaker-1)",
  "var(--speaker-2)",
  "var(--speaker-3)",
  "var(--speaker-4)",
] as const;

export type Caption = {
  id: string;
  speaker: string;
  /** Stable per-speaker index 0–3; anything beyond the cap uses the neutral tint. */
  speakerIndex: number;
  text: string;
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
      style={{ backgroundColor: tint }}
    >
      <p className="text-[12px] font-semibold uppercase tracking-wide text-ink-soft">
        {caption.speaker}
      </p>
      <p className="caption-text mt-0.5 text-ink">{caption.text}</p>
    </div>
  );
}
