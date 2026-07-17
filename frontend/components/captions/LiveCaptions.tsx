"use client";

import { useEffect, useRef, useState } from "react";
import SpeakerBubble from "@/components/captions/SpeakerBubble";
import { MicIcon } from "@/components/shell/icons";
import Button from "@/components/ui/Button";
import GlassCard from "@/components/ui/GlassCard";
import { useTranscription } from "@/lib/useTranscription";

const statusCopy = {
  idle: "Ready when you are.",
  connecting: "Starting the microphone…",
  listening: "Listening — captions appear below.",
  stopped: "Stopped. Start again anytime.",
  error: "",
} as const;

const SPEAKER_TINT_ORDER = ["Speaker 1", "Speaker 2", "Speaker 3", "Speaker 4"];
const AUTOSCROLL_SLACK_PX = 48;

export default function LiveCaptions() {
  const { status, error, segments, latency, start, stop } = useTranscription();
  const logRef = useRef<HTMLDivElement>(null);
  const [pinnedToBottom, setPinnedToBottom] = useState(true);

  // Autoscroll to newest caption unless the reader scrolled up on purpose.
  useEffect(() => {
    const log = logRef.current;
    if (log && pinnedToBottom) log.scrollTop = log.scrollHeight;
  }, [segments, pinnedToBottom]);

  function handleScroll() {
    const log = logRef.current;
    if (!log) return;
    const fromBottom = log.scrollHeight - log.scrollTop - log.clientHeight;
    setPinnedToBottom(fromBottom < AUTOSCROLL_SLACK_PX);
  }

  const listening = status === "listening" || status === "connecting";

  return (
    <GlassCard strong className="flex h-full min-h-120 flex-col gap-4 p-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="font-display text-[22px] font-semibold">Live captions</h2>
          <p role="status" className="mt-0.5 text-sm text-ink-soft">
            {statusCopy[status]}
          </p>
        </div>
        <div className="flex items-center gap-2">
          {listening ? (
            <Button variant="ghost" onClick={stop}>
              Stop
            </Button>
          ) : (
            <Button onClick={start} className="flex items-center gap-2">
              <MicIcon />
              Start captions
            </Button>
          )}
        </div>
      </div>

      {error && (
        <p role="alert" className="rounded-xl border border-error bg-white/70 px-4 py-3 text-sm text-error-strong">
          {error}
        </p>
      )}

      <div
        ref={logRef}
        onScroll={handleScroll}
        role="log"
        aria-live="polite"
        aria-label="Live captions"
        className="flex min-h-0 flex-1 flex-col gap-2.5 overflow-y-auto scroll-pt-2"
      >
        {segments.length === 0 && !error && (
          <p className="m-auto max-w-sm text-center text-sm text-ink-faint">
            Start captions and speak — each person gets their own colored bubble with a label,
            up to 4 speakers plus “Other”.
          </p>
        )}
        {segments.map((segment) => (
          <SpeakerBubble
            key={segment.id}
            caption={{
              id: segment.id,
              speaker: segment.speaker,
              speakerIndex: SPEAKER_TINT_ORDER.indexOf(segment.speaker),
              text: segment.text,
              interim: !segment.isFinal,
            }}
          />
        ))}
      </div>

      {!pinnedToBottom && (
        <button
          type="button"
          onClick={() => {
            setPinnedToBottom(true);
            const log = logRef.current;
            if (log) log.scrollTop = log.scrollHeight;
          }}
          className="btn-ghost self-center rounded-full px-4 py-1.5 text-sm text-ink"
        >
          Jump to latest
        </button>
      )}

      {process.env.NODE_ENV === "development" && latency && (
        <p data-testid="latency-readout" className="text-[12px] tabular-nums text-ink-faint">
          latency p50 {Math.round(latency.p50)} ms · p95 {Math.round(latency.p95)} ms ·{" "}
          {latency.count} finals
        </p>
      )}
    </GlassCard>
  );
}
