"use client";

import posthog from "posthog-js";
import { useEffect, useRef, useState } from "react";
import SpeakerBubble from "@/components/captions/SpeakerBubble";
import { MicIcon } from "@/components/shell/icons";
import Button from "@/components/ui/Button";
import GlassCard from "@/components/ui/GlassCard";
import { useTranscription } from "@/lib/useTranscription";

const BACKEND = process.env.NEXT_PUBLIC_BACKEND_URL ?? "http://localhost:8000";
const POSTHOG_ENABLED = Boolean(process.env.NEXT_PUBLIC_POSTHOG_KEY);

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
  const { status, error, segments, latency, start, stop, sessionId } = useTranscription();
  const logRef = useRef<HTMLDivElement>(null);
  const [pinnedToBottom, setPinnedToBottom] = useState(true);
  const [feedbackSent, setFeedbackSent] = useState(false);

  const finalsCount = segments.filter((s) => s.isFinal).length;

  function handleStop() {
    stop();
    if (POSTHOG_ENABLED) {
      // End-to-end latency (mic capture → caption rendered), per session.
      posthog.capture("caption_session_ended", {
        finals: finalsCount,
        latency_p50_ms: latency?.p50,
        latency_p95_ms: latency?.p95,
      });
    }
  }

  async function sendFeedback(rating: "up" | "down") {
    setFeedbackSent(true);
    if (POSTHOG_ENABLED) posthog.capture("caption_feedback", { rating });
    try {
      await fetch(`${BACKEND}/feedback/captions`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          session_id: sessionId.current || "unknown",
          rating,
          final_captions: finalsCount,
          latency_p50_ms: latency?.p50 ?? null,
          latency_p95_ms: latency?.p95 ?? null,
        }),
      });
    } catch {
      // Feedback must never break the tool; the PostHog event (if any) still counts.
    }
  }

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
            <Button variant="ghost" onClick={handleStop}>
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
          <p className="m-auto max-w-sm text-center text-sm text-ink-soft">
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

      {status === "stopped" && finalsCount > 0 && (
        <div className="flex items-center justify-between gap-3 rounded-2xl border border-white/60 bg-white/50 px-4 py-3">
          {feedbackSent ? (
            <p role="status" className="text-sm text-ink">
              Thanks — your feedback helps captions improve.
            </p>
          ) : (
            <>
              <p className="text-sm text-ink">How were the captions?</p>
              <div className="flex gap-2">
                <button
                  type="button"
                  onClick={() => sendFeedback("up")}
                  aria-label="Captions were good"
                  className="btn-ghost flex h-9 w-9 items-center justify-center rounded-full text-ink"
                >
                  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                    <path d="M7 11v9m0-9 4-7.5a2 2 0 0 1 2 2V9h5.2a2 2 0 0 1 2 2.4l-1.2 6A2 2 0 0 1 17 19H7m0-8H4a1 1 0 0 0-1 1v6a1 1 0 0 0 1 1h3" />
                  </svg>
                </button>
                <button
                  type="button"
                  onClick={() => sendFeedback("down")}
                  aria-label="Captions had problems"
                  className="btn-ghost flex h-9 w-9 items-center justify-center rounded-full text-ink"
                >
                  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                    <path d="M17 13V4m0 9-4 7.5a2 2 0 0 1-2-2V15H5.8a2 2 0 0 1-2-2.4l1.2-6A2 2 0 0 1 7 5h10m0 8h3a1 1 0 0 0 1-1V6a1 1 0 0 0-1-1h-3" />
                  </svg>
                </button>
              </div>
            </>
          )}
        </div>
      )}

      {process.env.NODE_ENV === "development" && latency && (
        <p data-testid="latency-readout" className="text-[12px] tabular-nums text-ink-soft">
          latency p50 {Math.round(latency.p50)} ms · p95 {Math.round(latency.p95)} ms ·{" "}
          {latency.count} finals
        </p>
      )}
    </GlassCard>
  );
}
