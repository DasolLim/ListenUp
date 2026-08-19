"use client";

import posthog from "posthog-js";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import ConversationPane from "@/components/captions/ConversationPane";
import SessionHeader from "@/components/captions/SessionHeader";
import { PANE_HEIGHT_IDLE, PANE_HEIGHT_LIVE } from "@/lib/paneHeight";
import SpeakerCorrectionDialog from "@/components/captions/SpeakerCorrectionDialog";
import VoiceOrb from "@/components/captions/VoiceOrb";
import SpokenLanguagePicker from "@/components/SpokenLanguagePicker";
import { MicIcon, PauseIcon } from "@/components/shell/icons";
import Button from "@/components/ui/Button";
import GlassCard from "@/components/ui/GlassCard";
import VoicePicker from "@/components/speech/VoicePicker";
import { SpeechProvider, useAutoSpeak, useSharedSpeech } from "@/lib/SpeechProvider";
import { formatDate } from "@/lib/plans";
import { useSpeakerCorrection } from "@/lib/useSpeakerCorrection";
import { useStickyLanguage } from "@/lib/useStickyLanguage";
import { newestSpeakableLine, useLiveTranslation } from "@/lib/useLiveTranslation";
import { useTranscription } from "@/lib/useTranscription";

const BACKEND = process.env.NEXT_PUBLIC_BACKEND_URL ?? "http://localhost:8000";
const POSTHOG_ENABLED = Boolean(process.env.NEXT_PUBLIC_POSTHOG_KEY);

const statusCopy = {
  idle: "Ready when you are.",
  connecting: "Starting the microphone…",
  listening: "Listening — captions appear below.",
  paused: "Paused — the microphone is off. Your captions are kept.",
  stopped: "Stopped. Start again anytime.",
  error: "",
} as const;

function LiveCaptionsInner(props: { targetLang: string; setTargetLang: (v: string) => void }) {
  const [spoken, setSpoken] = useStickyLanguage("listenup-spoken-captions");
  const {
    status,
    error,
    limit,
    allowanceWarning,
    segments,
    latency,
    start,
    stop,
    pause,
    resume,
    correct,
    getAudioLevel,
    getVoiceSignal,
    sessionId,
  } = useTranscription({ language: spoken });
  const [feedbackSent, setFeedbackSent] = useState(false);
  const correction = useSpeakerCorrection(correct);
  const [languages, setLanguages] = useState<Record<string, string>>({});
  const { targetLang, setTargetLang } = props;
  const [translateOn, setTranslateOn] = useState(false);
  const {
    translations,
    stats: translationStats,
    costs,
    failure: translationFailure,
    culturalFailure,
    isSettled,
    reset: resetTranslations,
  } = useLiveTranslation(segments, targetLang, translateOn);
  const speech = useSharedSpeech();

  // Only finalised captions count as "new". Interim text is retargeted several
  // times a second, so counting it would run the unread badge up while one
  // sentence is still being spoken.
  const finalsCount = segments.filter((s) => s.isFinal).length;
  // Auto-speak the newest FINAL translated line. Keyed on the segment id rather
  // than the text, because the same sentence can legitimately be said twice in a
  // conversation and both should be read out. Interims are skipped: they change
  // mid-sentence, so speaking one would stutter.
  // Settled, not merely translated: the fast and cultural lanes race, and
  // speaking whichever lands first reads out the literal version while the
  // bubble shows the adapted one.
  const latestSpoken = newestSpeakableLine(segments, translations, isSettled);
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
  const paused = status === "paused";

  // Speaking wins over listening: the mic stays open while a translation is read
  // aloud, so without this the orb would react to the room and look identical to
  // "you are talking".
  const orbState: "idle" | "thinking" | "listening" | "speaking" = speech.speaking
    ? "speaking"
    : status === "connecting"
      ? "thinking"
      : status === "listening"
        ? "listening"
        : "idle";

  // Watch for a live microphone that is receiving nothing. Sampled on an
  // interval rather than per frame: this drives copy, not motion, and a state
  // update every frame would re-render the transcript continuously.
  const [silent, setSilent] = useState(false);
  useEffect(() => {
    if (status !== "listening") return;
    let quietSince = performance.now();
    const timer = setInterval(() => {
      if (getAudioLevel() > 0.04) quietSince = performance.now();
      setSilent(performance.now() - quietSince > 6000);
    }, 500);
    // Cleared on the way out rather than on the way in, so a session that ended
    // silent can't flash the warning over the first half-second of the next one.
    return () => {
      clearInterval(timer);
      setSilent(false);
    };
  }, [status, getAudioLevel]);

  return (
    <GlassCard strong className="flex flex-col gap-4 p-6">
      <SessionHeader
        title="Live captions"
        status={statusCopy[status]}
        // Collapses while a session runs or is paused. See SessionHeader: the
        // expanded chrome put the transcript's bottom edge below the fold on a
        // phone, which is the complaint the pane was rebuilt to fix.
        compact={listening || paused}
        orb={
          listening ? (
            <VoiceOrb getSignal={getVoiceSignal} state={orbState} className="size-16 shrink-0" />
          ) : null
        }
        setup={
          <>
            <SpokenLanguagePicker
              id="live-spoken"
              value={spoken}
              onChange={setSpoken}
              disabled={listening}
            />
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
            {translateOn && (
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
            )}
          </>
        }
        actions={
          <>
            {paused ? (
              <Button onClick={resume} className="flex items-center gap-2">
                <MicIcon />
                Resume
              </Button>
            ) : listening ? (
              <Button variant="ghost" onClick={pause} className="flex items-center gap-2">
                <PauseIcon />
                Pause
              </Button>
            ) : (
              <Button onClick={start} className="flex items-center gap-2">
                <MicIcon />
                Start captions
              </Button>
            )}
            {(listening || paused) && (
              <Button variant="ghost" onClick={handleStop}>
                Stop
              </Button>
            )}
          </>
        }
      />
      {error && (
        <p
          role="alert"
          className="rounded-xl border border-error bg-white/70 px-4 py-3 text-sm text-error-strong"
        >
          {error}
        </p>
      )}

      {/* Running out of caption hours is not a malfunction, so it does not get
          the error treatment. It says what ran out, when it comes back, and
          what upgrading changes — with the upgrade as one link, not a funnel. */}
      {limit && (
        <div
          role="status"
          className="flex flex-col gap-2 rounded-xl border border-warning bg-white/70 px-4 py-3 text-sm text-ink"
        >
          <p className="leading-relaxed">
            {limit.message}
            {limit.resetsAt && ` It resets ${formatDate(limit.resetsAt)}.`}
          </p>
          <Link
            href="/settings"
            className="btn-primary inline-flex min-h-11 w-fit items-center rounded-full px-5 text-sm font-semibold text-on-accent"
          >
            {limit.upgradeTo === "pro" ? "Upgrade to Pro" : "See plans"}
          </Link>
        </div>
      )}

      {/* The 80% notice: early enough to be useful, quiet enough to ignore. */}
      {allowanceWarning && !limit && (
        <p
          role="status"
          className="rounded-xl border border-warning bg-white/70 px-4 py-2.5 text-[13px] leading-relaxed text-ink"
        >
          {Math.round(allowanceWarning.remaining / 60)} minutes of captions left this billing period
          {allowanceWarning.resetsAt && `, resetting ${formatDate(allowanceWarning.resetsAt)}`}.
        </p>
      )}

      {/* Translation stopped producing lines. Captions themselves are fine, so
          this is a notice beside them rather than an error over them — and it
          says which, because "translated captions aren't on your plan" and
          "you've used this month's" need different answers. */}
      {translateOn && translationFailure && (
        <div
          role="status"
          className="flex flex-col gap-2 rounded-xl border border-warning bg-white/70 px-4 py-3 text-sm text-ink"
        >
          <p className="leading-relaxed">
            Captions are still running, but translation stopped. {translationFailure.message}
            {translationFailure.paywall?.resetsAt &&
              ` It resets ${formatDate(translationFailure.paywall.resetsAt)}.`}
          </p>
          {translationFailure.paywall && (
            <Link
              href="/settings"
              className="btn-primary inline-flex min-h-11 w-fit items-center rounded-full px-5 text-sm font-semibold text-on-accent"
            >
              {translationFailure.paywall.upgradeTo === "pro" ? "Upgrade to Pro" : "See plans"}
            </Link>
          )}
        </div>
      )}

      {/* Captions and their translations are fine; the cultural layer is not.
          Kept separate from the notice above because the user can see
          translated text, so claiming translation stopped would be visibly
          untrue — what they have lost is the explanation of the slang in it. */}
      {translateOn && culturalFailure && !translationFailure && (
        <div
          role="status"
          className="flex flex-col gap-2 rounded-xl border border-warning bg-white/70 px-4 py-3 text-sm text-ink"
        >
          <p className="leading-relaxed">
            Captions are translated, but slang and register explanations aren&apos;t running.{" "}
            {culturalFailure.message}
            {culturalFailure.paywall?.resetsAt &&
              ` It resets ${formatDate(culturalFailure.paywall.resetsAt)}.`}
          </p>
          {culturalFailure.paywall && (
            <Link
              href="/settings"
              className="btn-primary inline-flex min-h-11 w-fit items-center rounded-full px-5 text-sm font-semibold text-on-accent"
            >
              {culturalFailure.paywall.upgradeTo === "pro" ? "Upgrade to Pro" : "See plans"}
            </Link>
          )}
        </div>
      )}

      <ConversationPane
        segments={segments}
        // Empty when translation is off, so the bubbles show the original only.
        translations={translateOn ? translations : undefined}
        label="Live captions"
        height={listening || paused ? PANE_HEIGHT_LIVE : PANE_HEIGHT_IDLE}
        noun="caption"
        active={status === "listening" || paused}
        correcting={Boolean(correction.correcting)}
        onCorrect={(speaker) => void correction.open(speaker)}
        banner={
          silent ? (
            <p
              role="status"
              className="rounded-2xl border border-warning bg-white/70 px-4 py-2.5 text-[13px] leading-relaxed text-ink"
            >
              <span className="font-semibold">No sound is reaching the microphone.</span> Captions
              are running, but nothing has been picked up for a few seconds — check the right
              microphone is selected and unmuted.
            </p>
          ) : null
        }
        empty={
          error ? null : (
            <div className="m-auto flex max-w-sm flex-col items-center gap-5 text-center">
              <VoiceOrb
                getSignal={getVoiceSignal}
                state={orbState}
                className="size-40 sm:size-44"
              />
              <p className="text-sm text-ink-soft">
                {listening
                  ? "Listening — speak and captions appear here. Each person gets their own colour, up to 4 speakers plus “Other”."
                  : "Start captions and speak. Each person gets their own colour and label, up to 4 speakers plus “Other”."}
              </p>
            </div>
          )
        }
      />

      {correction.correcting && (
        <SpeakerCorrectionDialog
          label={correction.correcting}
          options={correction.options}
          onApply={correction.apply}
          onCancel={correction.cancel}
        />
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
