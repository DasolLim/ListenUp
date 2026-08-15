import SpeakButton from "@/components/speech/SpeakButton";
import UnverifiedTag from "@/components/ui/UnverifiedTag";
import type { SlangNote } from "@/lib/useLiveTranslation";

const tints = [
  "var(--speaker-1)",
  "var(--speaker-2)",
  "var(--speaker-3)",
  "var(--speaker-4)",
] as const;

export type BubbleTranslation = {
  text: string;
  sourceLang: string | null;
  // The shared shape rather than a third inline copy — the copies had already
  // drifted once, and a note field the bubble doesn't declare is a field the
  // bubble silently cannot render.
  notes: SlangNote[];
};

export type Caption = {
  id: string;
  speaker: string;
  /** Real person's name when voice-matched. */
  speakerName?: string | null;
  /** Stable per-speaker index 0–3; anything beyond the cap uses the neutral tint. */
  speakerIndex: number;
  text: string;
  /** Still being spoken: dashed edge + blinking caret, never lighter text. */
  interim?: boolean;
  /** Live translation: rendered as the main caption line. */
  translated?: BubbleTranslation | null;
};

/**
 * One line in a conversation turn.
 *
 * The name is drawn by the *group*, not here, so a run of lines from one person
 * says their name once — the way a messaging thread does. Repeating "Mom" on
 * every line is noise when the answer hasn't changed, and it costs the vertical
 * space the actual words need.
 *
 * Colour still never carries meaning alone (DESIGN_SYSTEM §7): the group prints
 * the name above the run, so the tint and rail only ever reinforce a label that
 * is already there.
 */
export default function SpeakerBubble({
  caption,
  position = "only",
  onSpeak,
  onStopSpeaking,
  speaking = false,
}: {
  caption: Caption;
  /** Where this line sits in its speaker's run, for corner and spacing shape. */
  position?: "only" | "first" | "middle" | "last";
  /** Present only when this line has a translation worth reading aloud. */
  onSpeak?: () => void;
  onStopSpeaking?: () => void;
  speaking?: boolean;
}) {
  const tint = tints[caption.speakerIndex] ?? "var(--speaker-other)";
  const continues = position === "middle" || position === "last";
  const leads = position === "first" || position === "middle";

  return (
    <div
      className={`bubble-glass rounded-2xl px-4 py-2.5 ${continues ? "bubble-cont" : ""} ${
        leads ? "bubble-lead" : ""
      }`}
      data-interim={caption.interim || undefined}
      style={{ backgroundColor: tint }}
    >
      <div className="flex items-start justify-between gap-2">
        {/* An in-progress line is marked by italics, a dashed bubble edge and a
            blinking caret — never by fading the text. Lighter ink on a tinted
            bubble falls below AA (DESIGN_SYSTEM §7), and this is the line being
            said right now, so it is the one that most needs to be legible. */}
        <p className={`caption-text min-w-0 flex-1 text-ink ${caption.interim ? "italic" : ""}`}>
          {caption.translated ? caption.translated.text : caption.text}
          {caption.interim && (
            <>
              <span aria-hidden="true" className="interim-caret" />
              <span className="sr-only"> (still transcribing)</span>
            </>
          )}
        </p>
        {onSpeak && (
          <SpeakButton
            onSpeak={onSpeak}
            onStop={onStopSpeaking ?? (() => undefined)}
            speaking={speaking}
            label={`the translation of ${caption.speakerName ?? caption.speaker}'s line`}
          />
        )}
      </div>

      {/* The words as spoken, under the words as translated. Indented and
          quieter so the eye lands on the language the reader asked for, with
          the original available without a tap — checking a translation you
          half-recognise is the common case, and hiding it behind a control
          makes that a chore. */}
      {caption.translated && (
        <p className="mt-1 border-l-2 border-white/60 pl-2.5 text-[13px] leading-relaxed text-ink-soft">
          <span className="sr-only">Original: </span>
          {caption.text}
        </p>
      )}

      {caption.translated && caption.translated.notes.length > 0 && (
        <details className="group mt-2 rounded-xl border border-white/60 bg-white/55 px-3 py-2">
          <summary className="flex cursor-pointer list-none items-center gap-1.5 text-[12px] font-semibold text-ink">
            <span
              aria-hidden="true"
              className="inline-block transition-transform group-open:rotate-90"
            >
              ›
            </span>
            {caption.translated.notes.length} phrase
            {caption.translated.notes.length > 1 ? "s" : ""} worth explaining
          </summary>
          <ul className="mt-2 flex flex-col gap-2 text-[13px] leading-relaxed text-ink">
            {caption.translated.notes.map((note) => (
              <li key={note.phrase} className="flex flex-col gap-0.5">
                <span className="flex flex-wrap items-center gap-1.5">
                  <span className="font-semibold text-accent-strong">{note.phrase}</span>
                  {note.confidence === "low" && <UnverifiedTag />}
                </span>
                <span>{note.meaning}</span>
                {note.equivalent && (
                  <span className="text-ink-soft">Closest equivalent: {note.equivalent}</span>
                )}
              </li>
            ))}
          </ul>
        </details>
      )}
    </div>
  );
}
