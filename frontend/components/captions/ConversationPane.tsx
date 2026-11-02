"use client";

import { useState, type ReactNode } from "react";
import SpeakerBubble from "@/components/captions/SpeakerBubble";
import SpeakerName from "@/components/captions/SpeakerName";
import SpeakerNamingNudge from "@/components/captions/SpeakerNamingNudge";
import { useSharedSpeech } from "@/lib/hooks/SpeechProvider";
import type { CaptionSegment } from "@/lib/captionStream";
import type { LiveTranslation } from "@/lib/translationMerge";
import { RAILS, identityColor, linePosition, stamp, turnGroups } from "@/lib/turnGroups";
import { useChatScroll } from "@/lib/hooks/useChatScroll";

const NO_TRANSLATIONS: Record<string, LiveTranslation> = {};

/**
 * The transcript pane: a conversation, not a log.
 *
 * Live captions and Translate's voice mode are the same conversation seen from
 * two tools, and this is the shape they share — a fixed-height pane anchored at
 * the bottom, turns grouped by *identity* so label churn cannot split one
 * person, the name printed once per run with a rail in their colour, and a
 * floating jump-to-latest counting finalised lines only.
 *
 * It was already meant to be shared: `turnGroups`, `useChatScroll` and
 * `SpeakerBubble` were extracted for exactly that. But the *composition* was
 * copied, so both surfaces carried their own ~120 lines of identical markup
 * plus their own copies of the scroll wiring, the screen-reader announcement
 * and the naming-nudge gate. Two transcripts that grouped turns differently
 * would be one idea told twice, and the second telling would be the worse one —
 * which is a risk a copy runs every time either side is edited.
 *
 * What genuinely differs between the two is passed in: how tall the pane is,
 * what it is called, what it says when empty, and what sits above or below the
 * conversation.
 */
export default function ConversationPane({
  segments,
  translations = NO_TRANSLATIONS,
  languages,
  label,
  height,
  noun,
  active,
  correcting,
  onCorrect,
  banner,
  empty,
  footer,
}: {
  segments: CaptionSegment[];
  /** Empty when translation is off; bubbles then show the original only. */
  translations?: Record<string, LiveTranslation>;
  /** Language code → display name for the "translated from" label. */
  languages?: Record<string, string>;
  /** Accessible name for the log region. */
  label: string;
  /** Tailwind height for the pane. The fold guarantee differs per surface. */
  height: string;
  /** What a line is called, for the unread counter. */
  noun: "caption" | "line";
  /** Listening or paused: naming can be offered and corrections applied. */
  active: boolean;
  correcting: boolean;
  onCorrect: (speaker: string) => void;
  /** Above the conversation, inside the scroller (e.g. a silent-mic warning). */
  banner?: ReactNode;
  empty: ReactNode;
  /** In the flow at the end of the conversation (e.g. the paused notice). */
  footer?: ReactNode;
}) {
  const speech = useSharedSpeech();

  // Only finalised captions count as "new". Interim text is rewritten several
  // times a second, so counting it would run the unread badge up while one
  // sentence is still being spoken.
  const finalCount = segments.filter((s) => s.isFinal).length;
  const { containerRef, watchContent, pinned, unread, onScroll, jumpToLatest } = useChatScroll({
    finalCount,
  });

  const latestFinal = [...segments].reverse().find((s) => s.isFinal) ?? null;
  const colorOf = identityColor(segments);

  // Nudge toward naming only when it would actually help: someone is speaking,
  // and they're unnamed. Held back until a couple of turns have settled —
  // offering to name people before anyone has finished speaking is advice about
  // nothing, and it would flash on screen in the first second of every session.
  // Dismissible once: a hint that keeps returning while someone is trying to
  // follow a conversation has stopped being a hint.
  const [nudgeDismissed, setNudgeDismissed] = useState(false);
  const showNudge =
    !nudgeDismissed &&
    active &&
    !correcting &&
    finalCount >= 2 &&
    segments.some((s) => s.isFinal && !s.speakerName);

  return (
    <>
      {/* Announcements for screen readers.
          `aria-live` deliberately does NOT sit on the transcript itself: that
          region holds the in-progress line, which is rewritten several times a
          second, so a screen reader would talk over itself continuously. This
          carries only the most recent finalised line — each announced once,
          when it settles. */}
      <p className="sr-only" role="status" aria-live="polite" aria-atomic="true">
        {latestFinal
          ? `${latestFinal.speakerName ?? latestFinal.speaker}: ${
              translations[latestFinal.id]?.text ?? latestFinal.text
            }`
          : ""}
      </p>

      {/* A fixed pane, not a growing list: lines scroll inside it while the
          controls above and below stay where the user left them. Sizing to
          content instead made the page grow with every line, so the newest line
          — the only one that matters live — kept sliding below the fold. */}
      <div className={`relative ${height}`}>
        <div
          ref={containerRef}
          onScroll={onScroll}
          role="log"
          aria-label={label}
          className="flex h-full flex-col overflow-y-auto overscroll-contain px-0.5"
        >
          {banner}

          {showNudge && <SpeakerNamingNudge onDismiss={() => setNudgeDismissed(true)} />}

          {segments.length === 0 ? (
            empty
          ) : (
            // `mt-auto` sits a short conversation at the bottom, so the first
            // line appears where the next one will, rather than at the top of an
            // empty pane with everything drifting downward.
            <div ref={watchContent} className="mt-auto flex flex-col gap-2.5">
              {turnGroups(segments).map((group) => {
                const index = colorOf(group.speakerName ?? group.speaker);
                const label = group.speakerName ?? group.speaker;
                const source = translations[group.lines[0].id]?.sourceLang ?? null;
                return (
                  <div key={group.key} className="flex flex-col gap-2.5">
                    {group.gapBefore && (
                      <p className="turn-divider my-1" aria-hidden="true">
                        {group.gapLabel}
                      </p>
                    )}
                    <div
                      className="group/turn turn-group flex flex-col gap-0.5"
                      style={{
                        ["--turn-rail" as string]: RAILS[index] ?? "var(--speaker-other-rail)",
                      }}
                    >
                      {/* The name is said once per run, not once per line. */}
                      <div className="mb-0.5 flex items-baseline gap-2">
                        <SpeakerName
                          label={label}
                          onCorrect={active ? () => onCorrect(group.speaker) : undefined}
                        />
                        {source && (
                          <span className="text-[11px] uppercase tracking-wide text-ink-faint">
                            {languages?.[source] ?? source}
                          </span>
                        )}
                        {/* On hover or focus rather than always: a stamp on
                            every turn is noise live, but "when was that said"
                            matters when scrolling back. */}
                        <time
                          className="numeric text-[11px] text-ink-faint opacity-0 transition-opacity group-hover/turn:opacity-100 group-focus-within/turn:opacity-100 motion-reduce:transition-none"
                          dateTime={`PT${Math.round(group.lines[0].start)}S`}
                        >
                          {stamp(group.lines[0].start)}
                        </time>
                      </div>
                      {group.lines.map((segment, i) => (
                        <SpeakerBubble
                          key={segment.id}
                          position={linePosition(i, group.lines.length)}
                          caption={{
                            id: segment.id,
                            speaker: segment.speaker,
                            speakerName: segment.speakerName,
                            // Colour by identity (name when known), so one
                            // person keeps one colour even when diarization
                            // churns the label.
                            speakerIndex: index,
                            text: segment.text,
                            interim: !segment.isFinal,
                            translated: translations[segment.id] ?? null,
                          }}
                          onSpeak={
                            translations[segment.id]
                              ? () => speech.speak(translations[segment.id].text)
                              : undefined
                          }
                          onStopSpeaking={speech.stop}
                          speaking={speech.speaking}
                        />
                      ))}
                    </div>
                  </div>
                );
              })}

              {footer}
            </div>
          )}
        </div>

        {/* Floats over the transcript instead of sitting below it, so showing or
            hiding it never resizes the pane being read. */}
        {!pinned && (
          <button
            type="button"
            onClick={jumpToLatest}
            // The visible text says how many; the label also says what tapping
            // does, which the count alone leaves to inference.
            aria-label={
              unread > 0
                ? `${unread} new ${noun}${unread === 1 ? "" : "s"}, jump to latest`
                : `Jump to latest ${noun}`
            }
            className="btn-ghost absolute inset-x-0 bottom-2 mx-auto flex min-h-11 w-fit items-center gap-2 rounded-full px-4 text-sm text-ink shadow-glass"
          >
            {unread > 0 && (
              // Paired with the count in words — never colour alone (§7).
              <span aria-hidden="true" className="size-2 rounded-full bg-accent-strong" />
            )}
            {unread > 0 ? `${unread} new ${noun}${unread === 1 ? "" : "s"}` : "Jump to latest"}
          </button>
        )}
      </div>
    </>
  );
}
