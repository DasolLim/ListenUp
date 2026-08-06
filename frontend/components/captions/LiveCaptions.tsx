"use client";

import posthog from "posthog-js";
import { useSearchParams } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";
import SpeakerBubble from "@/components/captions/SpeakerBubble";
import VoiceOrb from "@/components/captions/VoiceOrb";
import SpokenLanguagePicker from "@/components/SpokenLanguagePicker";
import { MicIcon } from "@/components/shell/icons";
import Button from "@/components/ui/Button";
import GlassCard from "@/components/ui/GlassCard";
import VoicePicker from "@/components/speech/VoicePicker";
import { SpeechProvider, useAutoSpeak, useSharedSpeech } from "@/lib/SpeechProvider";
import { useStickyLanguage } from "@/lib/useStickyLanguage";
import { useLiveTranslation } from "@/lib/useLiveTranslation";
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

const AUTOSCROLL_SLACK_PX = 48;

type ProfileOption = { id: string; display_name: string };

function LiveCaptionsInner(props: {
  enhanced?: boolean;
  targetLang: string;
  setTargetLang: (v: string) => void;
}) {
  const { enhanced = false } = props;
  const [spoken, setSpoken] = useStickyLanguage("listenup-spoken-captions");
  const { status, error, segments, latency, start, stop, correct, getAudioLevel, sessionId } =
    useTranscription({
      enhanced,
      language: spoken,
    });
  const logRef = useRef<HTMLDivElement>(null);
  const [pinnedToBottom, setPinnedToBottom] = useState(true);
  // Transcript length when the reader scrolled away; null while pinned.
  const [unreadAnchor, setUnreadAnchor] = useState<number | null>(null);
  const [feedbackSent, setFeedbackSent] = useState(false);
  const [profileOptions, setProfileOptions] = useState<ProfileOption[]>([]);
  const [correcting, setCorrecting] = useState<string | null>(null);
  const [languages, setLanguages] = useState<Record<string, string>>({});
  const { targetLang, setTargetLang } = props;
  const [translateOn, setTranslateOn] = useState(false);
  const {
    translations,
    stats: translationStats,
    costs,
    reset: resetTranslations,
  } = useLiveTranslation(segments, targetLang, translateOn);
  const speech = useSharedSpeech();

  // Auto-speak the newest FINAL translated line. Keyed on the segment id rather
  // than the text, because the same sentence can legitimately be said twice in a
  // conversation and both should be read out. Interims are skipped: they change
  // mid-sentence, so speaking one would stutter.
  const latestSpoken = [...segments].reverse().find((s) => s.isFinal && translations[s.id]);
  useAutoSpeak(
    translateOn && latestSpoken ? latestSpoken.id : "",
    latestSpoken ? (translations[latestSpoken.id]?.text ?? "") : ""
  );

  // STT duration = audio timeline processed (last segment's end timestamp).
  // Rough per-session cost: AssemblyAI ~$0.15/hr, Google $20/M chars, 4o-mini ~$0.60/M tokens.
  const sttSeconds = segments.length ? Math.max(...segments.map((s) => s.end)) : 0;
  const estCostUsd =
    (sttSeconds / 3600) * 0.15 + (costs.googleChars / 1e6) * 20 + (costs.llmTokens / 1e6) * 0.6;

  useEffect(() => {
    const controller = new AbortController();
    fetch(`${BACKEND}/translate/languages`, { signal: controller.signal })
      .then((r) => r.json())
      .then(setLanguages)
      .catch(() => undefined);
    return () => controller.abort();
  }, []);

  async function openCorrection(speakerLabel: string) {
    if (profileOptions.length === 0) {
      const { authHeader } = await import("@/lib/auth/token");
      const headers = await authHeader();
      if (headers.Authorization) {
        const response = await fetch(`${BACKEND}/profiles`, { headers });
        if (response.ok) setProfileOptions(await response.json());
      }
    }
    setCorrecting(speakerLabel);
  }

  function applyCorrection(profileId: string | null) {
    if (correcting) correct(correcting, profileId);
    setCorrecting(null);
  }

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
      posthog.capture("session_cost", {
        stt_seconds: Math.round(sttSeconds),
        google_chars: costs.googleChars,
        llm_tokens: costs.llmTokens,
        translate_requests: costs.requests,
        translate_cache_hits: costs.cacheHits,
        est_cost_usd: Number(estCostUsd.toFixed(5)),
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

  const scrollToLatest = useCallback((smooth: boolean) => {
    const log = logRef.current;
    if (!log) return;
    // Streaming text is retargeted many times a second, so only a deliberate
    // jump animates — smooth-scrolling every interim update reads as jitter.
    const reduced =
      typeof window !== "undefined" &&
      window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
    log.scrollTo({
      top: log.scrollHeight,
      behavior: smooth && !reduced ? "smooth" : "auto",
    });
  }, []);

  // Follow the newest caption, unless the reader scrolled up to read history —
  // then hold their position, the way a message thread does. Yanking someone
  // back mid-sentence loses the line they were on.
  useEffect(() => {
    if (pinnedToBottom) scrollToLatest(false);
  }, [segments, pinnedToBottom, scrollToLatest]);

  // How many captions have arrived since the reader scrolled away, derived from
  // the transcript length at that moment rather than counted in an effect.
  const unread = unreadAnchor === null ? 0 : Math.max(0, segments.length - unreadAnchor);

  function handleScroll() {
    const log = logRef.current;
    if (!log) return;
    const fromBottom = log.scrollHeight - log.scrollTop - log.clientHeight;
    const atBottom = fromBottom < AUTOSCROLL_SLACK_PX;
    setPinnedToBottom(atBottom);
    setUnreadAnchor((anchor) => (atBottom ? null : (anchor ?? segments.length)));
  }

  // Arriving from the floating "Start captions" control: open the microphone on
  // landing so the tap that navigated here is also the tap that starts
  // listening. Guarded by a ref because the effect must never re-fire and
  // restart a session the user has deliberately stopped.
  const searchParams = useSearchParams();
  const autoStarted = useRef(false);
  useEffect(() => {
    if (searchParams.get("start") !== "1" || autoStarted.current) return;
    autoStarted.current = true;
    void start();
  }, [searchParams, start]);

  const listening = status === "listening" || status === "connecting";

  // Nudge toward naming only when it would actually help: someone is speaking,
  // they're unnamed, and there is a name to give them. Enrolment used to be a
  // separate destination in the nav, which is the wrong moment — you discover
  // you want it while looking at "Speaker 1", not while browsing tools.
  const hasUnnamedSpeaker = segments.some((segment) => segment.isFinal && !segment.speakerName);

  // Stable color per identity: assign the 4 speaker tints in first-appearance
  // order, keyed on the name when known. One person keeps one color even if the
  // diarization label churns; a bubble recolors if it later gains a name.
  const identityIndexMap = new Map<string, number>();
  let nextColor = 0;
  for (const s of segments) {
    const key = s.speakerName ?? s.speaker;
    if (!identityIndexMap.has(key)) {
      identityIndexMap.set(key, nextColor % 4);
      nextColor += 1;
    }
  }
  const identityColor = (key: string) => identityIndexMap.get(key) ?? 0;

  return (
    <GlassCard strong className="flex flex-col gap-4 p-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          {/* Reacts to how loudly the room is speaking, so it doubles as a
              "your mic is working" signal — the thing you most want confirmed
              when captions are the reason you're in the conversation. */}
          {listening && (
            <VoiceOrb getLevel={getAudioLevel} active={listening} className="size-11 shrink-0" />
          )}
          <div>
            <h2 className="font-display text-[22px] font-semibold">Live captions</h2>
            <p role="status" className="mt-0.5 text-sm text-ink-soft">
              {statusCopy[status]}
            </p>
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <SpokenLanguagePicker
            id="live-spoken"
            value={spoken}
            onChange={setSpoken}
            disabled={listening}
          />
          {
            <>
              <label className="flex items-center gap-2 text-sm text-ink">
                <input
                  type="checkbox"
                  checked={translateOn}
                  onChange={(e) => {
                    setTranslateOn(e.target.checked);
                    if (!e.target.checked) resetTranslations();
                  }}
                  className="h-4 w-4 accent-accent-strong"
                />
                Translate to
              </label>
              <select
                id="live-target"
                aria-label="Live caption target language"
                value={targetLang}
                onChange={(e) => setTargetLang(e.target.value)}
                disabled={!translateOn}
                className="glass-strong min-h-11 rounded-xl border border-white/60 px-3 text-sm text-ink shadow-glass outline-none disabled:opacity-50"
              >
                {Object.entries(languages).map(([code, name]) => (
                  <option key={code} value={code}>
                    {name}
                  </option>
                ))}
              </select>
            </>
          }
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

      {translateOn && (
        <div className="flex flex-wrap items-center gap-3 border-t border-white/40 pt-3">
          <VoicePicker
            id="live-voice"
            voices={speech.voices}
            voiceId={speech.voiceId}
            onChoose={speech.chooseVoice}
            onPreview={(text, id) => speech.speak(text, id)}
            onStop={speech.stop}
            speaking={speech.speaking}
            autoSpeak={speech.autoSpeak}
            onToggleAutoSpeak={speech.toggleAutoSpeak}
            language={targetLang}
          />
        </div>
      )}

      {error && (
        <p
          role="alert"
          className="rounded-xl border border-error bg-white/70 px-4 py-3 text-sm text-error-strong"
        >
          {error}
        </p>
      )}

      {/* The transcript is a fixed pane, not a growing list: captions scroll
          inside it while the controls above and below stay where the user left
          them. Sizing to content instead made the page grow with every line, so
          the newest caption — the only one that matters live — kept sliding
          below the fold. */}
      <div className="relative h-[clamp(18rem,55vh,34rem)]">
        <div
          ref={logRef}
          onScroll={handleScroll}
          role="log"
          aria-live="polite"
          aria-label="Live captions"
          className="flex h-full flex-col overflow-y-auto overscroll-contain px-0.5"
        >
          {hasUnnamedSpeaker && status === "listening" && !correcting && (
            <p className="rounded-2xl border border-white/60 bg-white/50 px-4 py-2.5 text-[13px] leading-relaxed text-ink-soft">
              Tap a speaker&apos;s name to say who they are — ListenUp will recognise them next
              time.
            </p>
          )}

          {segments.length === 0 && !error ? (
            <p className="m-auto max-w-sm text-center text-sm text-ink-soft">
              Start captions and speak — each person gets their own colored bubble with a label, up
              to 4 speakers plus “Other”.
            </p>
          ) : (
            // `mt-auto` sits a short transcript at the bottom, so the first
            // caption appears where the next one will, rather than at the top of
            // an empty pane with the conversation drifting downward.
            <div className="mt-auto flex flex-col gap-2.5">
              {segments.map((segment) => (
                <SpeakerBubble
                  key={segment.id}
                  caption={{
                    id: segment.id,
                    speaker: segment.speaker,
                    speakerName: segment.speakerName,
                    // Color by identity (name when known), so one person keeps one
                    // color even when diarization churns the underlying speaker label.
                    speakerIndex: identityColor(segment.speakerName ?? segment.speaker),
                    text: segment.text,
                    interim: !segment.isFinal,
                    translated: translateOn ? (translations[segment.id] ?? null) : null,
                  }}
                  onCorrectClick={status === "listening" ? openCorrection : undefined}
                  onSpeak={
                    translateOn && translations[segment.id]
                      ? () => speech.speak(translations[segment.id].text)
                      : undefined
                  }
                  onStopSpeaking={speech.stop}
                  speaking={speech.speaking}
                />
              ))}
            </div>
          )}
        </div>

        {/* Floats over the transcript instead of sitting below it, so showing or
            hiding it never resizes the pane the user is reading. */}
        {!pinnedToBottom && (
          <button
            type="button"
            onClick={() => {
              setPinnedToBottom(true);
              setUnreadAnchor(null);
              scrollToLatest(true);
            }}
            className="btn-ghost absolute inset-x-0 bottom-2 mx-auto flex min-h-11 w-fit items-center gap-2 rounded-full px-4 text-sm text-ink shadow-glass"
          >
            {unread > 0 && (
              // Paired with the count in words — never colour alone (§7).
              <span aria-hidden="true" className="size-2 rounded-full bg-accent-strong" />
            )}
            {unread > 0 ? `${unread} new caption${unread === 1 ? "" : "s"}` : "Jump to latest"}
          </button>
        )}
      </div>

      {correcting && (
        <div
          role="dialog"
          aria-label={`Who is ${correcting}?`}
          className="glass-card glass-strong flex flex-wrap items-center gap-2 rounded-2xl p-4"
        >
          <p className="mr-1 text-sm font-medium text-ink">Who is {correcting}?</p>
          {profileOptions.map((option) => (
            <button
              key={option.id}
              type="button"
              onClick={() => applyCorrection(option.id)}
              className="pill-active rounded-full px-4 py-1.5 text-sm font-medium text-ink shadow-glass"
            >
              {option.display_name}
            </button>
          ))}
          <button
            type="button"
            onClick={() => applyCorrection(null)}
            className="pill-inactive rounded-full px-4 py-1.5 text-sm text-ink-soft hover:text-ink"
          >
            Not sure / unknown
          </button>
          <button
            type="button"
            onClick={() => setCorrecting(null)}
            className="ml-auto rounded-full px-3 py-1.5 text-sm text-ink-soft hover:text-ink"
          >
            Cancel
          </button>
        </div>
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
                  <svg
                    width="16"
                    height="16"
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="1.8"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    aria-hidden="true"
                  >
                    <path d="M7 11v9m0-9 4-7.5a2 2 0 0 1 2 2V9h5.2a2 2 0 0 1 2 2.4l-1.2 6A2 2 0 0 1 17 19H7m0-8H4a1 1 0 0 0-1 1v6a1 1 0 0 0 1 1h3" />
                  </svg>
                </button>
                <button
                  type="button"
                  onClick={() => sendFeedback("down")}
                  aria-label="Captions had problems"
                  className="btn-ghost flex h-9 w-9 items-center justify-center rounded-full text-ink"
                >
                  <svg
                    width="16"
                    height="16"
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="1.8"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    aria-hidden="true"
                  >
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
          {translationStats &&
            ` · translate p50 ${Math.round(translationStats.p50)} ms · p95 ${Math.round(translationStats.p95)} ms`}
          {translateOn &&
            ` · est cost $${estCostUsd.toFixed(4)} (${costs.googleChars} chars · ${costs.llmTokens} tokens · ${costs.cacheHits}/${costs.requests} cached)`}
        </p>
      )}
    </GlassCard>
  );
}

/**
 * The caption target language lives here so `SpeechProvider` receives it before
 * the log renders: the shared engine loads voices for the language it will read.
 */
export default function LiveCaptions() {
  const [targetLang, setTargetLang] = useStickyLanguage("listenup-target-captions", "ko");
  return (
    <SpeechProvider language={targetLang}>
      <LiveCaptionsInner targetLang={targetLang} setTargetLang={setTargetLang} />
    </SpeechProvider>
  );
}
