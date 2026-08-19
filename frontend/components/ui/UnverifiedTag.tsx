/**
 * Marks a slang note the model recalled rather than one our KB supplied.
 *
 * The model's slang knowledge is frozen at its training cutoff, so it is
 * reliable on established terms and confidently wrong on recent ones. A wrong
 * meaning delivered with the same certainty as a right one is the failure this
 * tag exists to prevent — the reader can see which is which and go check.
 *
 * Shown only on the unverified case: tagging every note "verified" would make
 * the page noisy and train people to ignore the label, which costs the signal
 * exactly when it matters. Colour never carries the meaning alone (DESIGN_SYSTEM
 * §7) — the word "unverified" does, and the tint only reinforces it.
 */
export default function UnverifiedTag({ className = "" }: { className?: string }) {
  return (
    <span
      className={`inline-flex shrink-0 items-center rounded-full bg-white/80 px-2 py-0.5 text-[11px] font-medium text-warning-strong ${className}`}
    >
      unverified
      <span className="sr-only">
        {" "}
        — this explanation is the model’s best guess and isn’t in our verified slang
        dictionary yet
      </span>
    </span>
  );
}
