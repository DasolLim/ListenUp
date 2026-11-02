"use client";

import { useState } from "react";
import ConversationPane from "@/components/captions/ConversationPane";
import { SpeechProvider } from "@/lib/hooks/SpeechProvider";
import type { CaptionSegment } from "@/lib/captionStream";
import type { LiveTranslation } from "@/lib/translationMerge";

/**
 * The transcript pane, on the gradient, with a conversation in it.
 *
 * The pane is shared by live captions and Translate's voice mode, and both of
 * those pages are auth-gated, so nothing rendered ever reached the browser
 * loop — `a11y.spec.ts` pointed at an `app.spec.ts` that does not exist. That
 * left the most complex surface in the product covered only by a type checker,
 * while the facts that matter about it are all rendered ones: contrast of pale
 * ink on a tinted bubble, the 44px correction target, no sideways scroll on a
 * phone.
 *
 * The fixture exercises every branch the markup has: two speakers, a run of
 * consecutive lines, a named speaker and an unnamed one, an interim line, a
 * translated line with slang notes, and a long enough gap to draw a divider.
 */

export const SEGMENTS: CaptionSegment[] = [
  {
    id: "t1",
    speaker: "Speaker 1",
    speakerName: "Mom",
    text: "Are you coming over for dinner on Sunday?",
    start: 0,
    end: 2.6,
    isFinal: true,
  },
  {
    id: "t2",
    speaker: "Speaker 1",
    speakerName: "Mom",
    text: "Your brother is bringing the kids.",
    start: 2.8,
    end: 4.9,
    isFinal: true,
  },
  {
    id: "t3",
    speaker: "Speaker 2",
    speakerName: null,
    text: "That sounds bussin, no cap.",
    start: 5.4,
    end: 7.2,
    isFinal: true,
  },
  {
    id: "t4",
    speaker: "Speaker 1",
    speakerName: "Mom",
    text: "I'll text you the time",
    // A gap wide enough to draw the "later" divider.
    start: 1830,
    end: 1832,
    isFinal: false,
  },
];

export const TRANSLATIONS: Record<string, LiveTranslation> = {
  t3: {
    text: "그거 진짜 맛있겠다, 찐이야.",
    sourceLang: "en",
    register: "slang-heavy",
    notes: [
      {
        phrase: "bussin",
        meaning: "정말 맛있다",
        cultural_context: "주로 음식에 대해 쓰임",
        equivalent: "존맛",
        grounded: true,
        confidence: "high",
      },
    ],
  },
};

export default function ConversationPaneSample() {
  const [correcting, setCorrecting] = useState(false);
  return (
    <SpeechProvider language="ko">
      <ConversationPane
        segments={SEGMENTS}
        translations={TRANSLATIONS}
        languages={{ en: "English", ko: "Korean" }}
        label="Conversation pane reference"
        height="h-[clamp(18rem,55vh,34rem)]"
        noun="caption"
        active
        correcting={correcting}
        onCorrect={() => setCorrecting(true)}
        empty={<p className="m-auto text-sm text-ink-soft">Nothing spoken yet.</p>}
      />
    </SpeechProvider>
  );
}
