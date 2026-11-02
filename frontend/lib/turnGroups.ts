import type { CaptionSegment } from "@/lib/hooks/useTranscription";

/**
 * Turn grouping for a live transcript, shared by every surface that renders one.
 *
 * This started life inside the live-captions component. It moved here when the
 * translate tool's voice mode needed the same treatment: a transcript that
 * grouped turns one way in one tool and another way in the other would be two
 * dialects of the same idea, and the second one written would quietly be the
 * worse one. It is also pure, which is the other reason to lift it out — the
 * grouping rules are the part worth testing, and they can be tested here
 * without rendering anything.
 */

/** Saturated identity colours for the turn rail (see globals.css). */
export const RAILS = [
  "var(--speaker-1-rail)",
  "var(--speaker-2-rail)",
  "var(--speaker-3-rail)",
  "var(--speaker-4-rail)",
] as const;

/** Speaker tints are capped at four, matching the backend's named-speaker cap. */
export const SPEAKER_TINTS = 4;

/** A pause long enough to be worth marking in the transcript. */
export const TURN_GAP_S = 20;

export type TurnGroup = {
  key: string;
  speaker: string;
  speakerName: string | null;
  lines: CaptionSegment[];
  gapBefore: boolean;
  gapLabel: string;
};

/** Elapsed time into the session, as a transcript reader would cite it. */
export function stamp(seconds: number): string {
  const total = Math.max(0, Math.round(seconds));
  const minutes = Math.floor(total / 60);
  return `${minutes}:${String(total % 60).padStart(2, "0")}`;
}

export function gapLabel(seconds: number): string {
  if (seconds >= 3600) return `${Math.round(seconds / 3600)} hr later`;
  if (seconds >= 60) return `${Math.round(seconds / 60)} min later`;
  return `${Math.round(seconds)} sec later`;
}

/**
 * Collapse consecutive lines from one person into a single turn.
 *
 * Messaging threads group this way because a name repeated on every line is
 * noise once the answer stops changing — and here it costs the vertical space
 * the words themselves need. Grouping is keyed on *identity* (the matched name
 * when there is one) rather than the raw diarization label, so a label that
 * churns mid-conversation doesn't split one person's turn in half.
 */
export function turnGroups(segments: CaptionSegment[]): TurnGroup[] {
  const groups: TurnGroup[] = [];
  for (const segment of segments) {
    const identity = segment.speakerName ?? segment.speaker;
    const current = groups[groups.length - 1];
    const previous = current?.lines[current.lines.length - 1];
    const gap = previous ? segment.start - previous.end : 0;

    if (current && (current.speakerName ?? current.speaker) === identity && gap < TURN_GAP_S) {
      current.lines.push(segment);
      continue;
    }
    groups.push({
      key: segment.id,
      speaker: segment.speaker,
      speakerName: segment.speakerName,
      lines: [segment],
      gapBefore: Boolean(previous) && gap >= TURN_GAP_S,
      gapLabel: previous ? gapLabel(gap) : "",
    });
  }
  return groups;
}

/**
 * Stable colour per identity: assign the four speaker tints in first-appearance
 * order, keyed on the name when known.
 *
 * One person keeps one colour even if the diarization label churns, and a
 * bubble recolours if it later gains a name — which is the point, because the
 * colour is answering "who is talking" for a reader who cannot hear the answer.
 */
export function identityColor(segments: CaptionSegment[]): (key: string) => number {
  const indexes = new Map<string, number>();
  let next = 0;
  for (const segment of segments) {
    const key = segment.speakerName ?? segment.speaker;
    if (!indexes.has(key)) {
      indexes.set(key, next % SPEAKER_TINTS);
      next += 1;
    }
  }
  return (key: string) => indexes.get(key) ?? 0;
}

/** Where a line sits in its speaker's run, for corner and spacing shape. */
export function linePosition(index: number, total: number): "only" | "first" | "middle" | "last" {
  if (total === 1) return "only";
  if (index === 0) return "first";
  if (index === total - 1) return "last";
  return "middle";
}
