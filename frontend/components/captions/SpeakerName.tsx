"use client";

/**
 * The name above a turn — a button when it can be corrected, plain text when it
 * can't.
 *
 * Shared by both transcript surfaces so the affordance cannot drift between
 * them. It carries a non-obvious detail that is easy to lose in a copy: the
 * label is 12px uppercase, so its own box is about 18px tall, well under the
 * 44px minimum for a touch target (docs/product/PRODUCT.md). Growing the text would cost a
 * quarter of the pane's reading height across a few turns, so the *pointer*
 * target is expanded instead, with a pseudo-element that reaches 13px above and
 * below without occupying any layout space.
 *
 * That matters more here than the size rule alone suggests: this is the control
 * that turns "Speaker 2" into "Mom", on a phone, mid-conversation.
 *
 * `z-10` is load-bearing, not decoration: `.bubble-glass` carries a
 * `backdrop-filter`, which makes it paint as though positioned, so the
 * neighbouring bubbles covered the invisible band and swallowed the taps it
 * exists to catch. The band is only as wide as the label and the bubbles have
 * nothing interactive beneath it.
 */
export default function SpeakerName({
  label,
  onCorrect,
}: {
  label: string;
  /** Omitted when the session is over and there is nothing to correct. */
  onCorrect?: () => void;
}) {
  const type = "text-[12px] font-semibold uppercase tracking-wide text-ink-soft";

  if (!onCorrect) return <p className={type}>{label}</p>;

  return (
    <button
      type="button"
      onClick={onCorrect}
      aria-label={`Correct speaker: currently ${label}`}
      title="Tap to correct who's speaking"
      className={`relative z-10 rounded underline decoration-dotted underline-offset-2 before:absolute before:inset-x-0 before:-inset-y-[13px] before:content-[''] hover:text-ink ${type}`}
    >
      {label}
    </button>
  );
}
