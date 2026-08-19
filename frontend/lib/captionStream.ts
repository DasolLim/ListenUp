/**
 * What the server can say about a transcript, applied to one.
 *
 * Four of these rules used to live inside the websocket `onmessage` handler in
 * `useTranscription`, which meant the only way to reach them was to open a
 * socket in a browser. Three of them are corrections to what is *already on
 * screen* — a name back-filled onto earlier lines, a merge that regroups two
 * halves of one voice — and that is exactly the class of mistake a reader who
 * cannot hear the original has no way to catch.
 *
 * Everything here is pure: one function takes the transcript and one message
 * and returns the next transcript. That is the whole interface, and it is what
 * lets `npm run verify` cover the rules in milliseconds.
 */

export type CaptionSegment = {
  id: string;
  speaker: string;
  speakerName: string | null;
  text: string;
  start: number;
  end: number;
  isFinal: boolean;
};

/** Everything `/ws/transcribe` sends. Narrowed on `type` below. */
export type CaptionMessage = {
  type: string;
  [key: string]: unknown;
};

// Diarization smoothing: a final segment shorter than this that flips to a new
// speaker and flips back is treated as noise and merged into the neighbour.
const SMOOTHING_WINDOW_S = 1.0;

/**
 * Build a segment from a `segment` frame.
 *
 * The id is scoped to the session because the provider's turn ids restart at
 * zero every time one begins. Consumers cache per-segment work against this id
 * — translations, "already spoken" — and those caches outlive a session, so a
 * bare turn id meant the first line of a new conversation silently inherited
 * the first line of the previous one's translation and was never re-requested.
 */
export function segmentFrom(
  message: CaptionMessage,
  sessionId: string,
  fallbackIndex: number
): CaptionSegment {
  const turnId = message.turnId as number | undefined;
  return {
    id: `turn-${sessionId}-${turnId ?? fallbackIndex}`,
    speaker: message.speaker as string,
    speakerName: (message.speakerName as string | null) ?? null,
    text: message.text as string,
    start: message.start as number,
    end: message.end as number,
    isFinal: message.isFinal as boolean,
  };
}

/**
 * Merge an incoming segment into the list, keyed on the provider's stable turn
 * id. Interim and final versions of one utterance share the id even when
 * diarization revises the speaker label or timestamps mid-turn — matching on
 * anything else (speaker/start) orphans interims as duplicate bubbles.
 */
function mergeSegment(list: CaptionSegment[], incoming: CaptionSegment): CaptionSegment[] {
  const index = list.findIndex((s) => s.id === incoming.id);
  if (index >= 0) {
    const next = [...list];
    // Never let a late interim overwrite an already-final turn.
    next[index] = list[index].isFinal && !incoming.isFinal ? list[index] : incoming;
    return next;
  }
  return [...list, incoming];
}

/** Merge speaker flips shorter than ~1s between same-speaker neighbours. */
function smooth(list: CaptionSegment[]): CaptionSegment[] {
  const finals = list.filter((s) => s.isFinal);
  if (finals.length < 3) return list;
  const flip = finals[finals.length - 2];
  const before = finals[finals.length - 3];
  const after = finals[finals.length - 1];
  if (
    flip.end - flip.start < SMOOTHING_WINDOW_S &&
    flip.speaker !== before.speaker &&
    before.speaker === after.speaker
  ) {
    return list.map((s) => (s.id === flip.id ? { ...s, speaker: before.speaker } : s));
  }
  return list;
}

/**
 * Apply one server message to the transcript.
 *
 * Messages that say nothing about the transcript (`ready`, `usage`, `paused`,
 * `error`) return it untouched, so a caller can hand every message here without
 * first deciding which ones matter — the decision lives in one place instead of
 * being re-derived at each call site.
 */
export function applyCaptionMessage(
  list: CaptionSegment[],
  message: CaptionMessage,
  sessionId: string,
  fallbackIndex: number
): CaptionSegment[] {
  switch (message.type) {
    case "segment":
      return smooth(mergeSegment(list, segmentFrom(message, sessionId, fallbackIndex)));

    case "speakerUpdate": {
      // A speaker was identified (or corrected) — relabel their past bubbles.
      //
      // `fillOnly` marks an automatic identification, which may only name
      // bubbles that are still unnamed: one diarization label can carry
      // different people across a session, so overwriting every bubble would
      // rewrite the earlier speaker's lines with the current speaker's name. A
      // manual correction arrives without the flag and overwrites, because the
      // user is explicitly fixing that label.
      const fillOnly = Boolean(message.fillOnly);
      const name = (message.speakerName as string | null) ?? null;
      return list.map((s) =>
        s.speaker === message.speaker && !(fillOnly && s.speakerName)
          ? { ...s, speakerName: name }
          : s
      );
    }

    case "speakerMerge":
      // Later audio showed two speakers were one person. Live diarization
      // decides with no lookahead, so its first call on a voice is made on
      // almost no evidence; this is the correction arriving once there is
      // enough. Rewriting the label rather than adding a name is deliberate —
      // the bubbles regroup and recolour, because grouping and colour key on
      // identity, so one person ends up as one thread instead of two.
      return list.map((s) => (s.speaker === message.from ? { ...s, speaker: message.to as string } : s));

    case "done":
      // Session over: anything still marked interim is as final as it gets.
      return list.map((s) => (s.isFinal ? s : { ...s, isFinal: true }));

    default:
      return list;
  }
}
