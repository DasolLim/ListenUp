"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import SpeakerCorrectionDialog from "@/components/captions/SpeakerCorrectionDialog";
import SpokenLanguagePicker from "@/components/captions/SpokenLanguagePicker";
import VoicePicker from "@/components/speech/VoicePicker";
import { MicIcon, PauseIcon } from "@/components/shell/icons";
import Button from "@/components/ui/Button";
import { formatDate } from "@/lib/plans";
import ConversationPane from "@/components/captions/ConversationPane";
import { PANE_HEIGHT_IDLE, PANE_HEIGHT_LIVE } from "@/lib/paneHeight";
import { useAutoSpeak, useSharedSpeech } from "@/lib/hooks/SpeechProvider";
import { useSpeakerCorrection } from "@/lib/hooks/useSpeakerCorrection";
import { useStickyFlag } from "@/lib/hooks/useStickyFlag";
import { useStickyLanguage } from "@/lib/hooks/useStickyLanguage";
import { newestSpeakableLine, useLiveTranslation } from "@/lib/hooks/useLiveTranslation";
import { useTranscription } from "@/lib/hooks/useTranscription";

const BACKEND = process.env.NEXT_PUBLIC_BACKEND_URL ?? "http://localhost:8000";

/** A cultural-pass model the user may choose, as the server describes it. */
type ModelTier = {
  key: string;
  label: string;
  blurb: string;
  usdPer1k: number;
  p50Ms: number;
  default: boolean;
};

/**
 * Spoken conversation, translated line by line.
 *
 * Built as a **pane**, not as a list that grows the page. The list version put
 * the newest line — the only one that matters while someone is still talking —
 * further below the fold with every sentence, so following the conversation
 * meant scrolling to chase it. A fixed pane inverts that: the newest line is
 * always in the same place, and history is what you scroll for.
 *
 * It reuses the live-captions vocabulary wholesale — turn grouping, speaker
 * tints and rails, the same bubble, the same jump-to-latest — because they are
 * the same object seen in two tools. A transcript that grouped turns one way
 * here and another way there would just be the same idea told twice, worse the
 * second time.
 *
 * Deliberately **not** the left/right alignment of a messaging app. That works
 * when one party is the reader; here there can be four speakers and the reader
 * is usually none of them, so identity is carried by a coloured rail and a name
 * printed once per run instead (globals.css, `.turn-group`).
 */
export default function VoiceConversation({
  target,
  setTarget,
  languages,
}: {
  target: string;
  /** So the same-language dead end can be fixed from where it is noticed. */
  setTarget: (code: string) => void;
  /** Code → display name, for the "translated from" label. */
  languages: Record<string, string>;
}) {
  const [spoken, setSpoken] = useState("en");
  const { status, error, limit, allowanceWarning, segments, start, stop, pause, resume, correct } =
    useTranscription({ language: spoken });

  // Naming works here for the same reason it works in live captions: it is the
  // same conversation, and the person reading is the only one who knows that
  // "Speaker 2" is Mom. Leaving the label inert in one tool and correctable in
  // the other would be a difference nobody could infer.
  const correction = useSpeakerCorrection(correct);

  // The same hook live captions use, rather than a second copy of "translate
  // each finalised line". The copy this replaced dropped every error on the
  // floor, so an exhausted allowance looked exactly like a tool that had
  // stopped working for no reason.
  // Slang explanations are metered, so they are a choice rather than a
  // default the user discovers on their bill. The tier lives beside the switch
  // because "is this on" and "how much does it cost" are one decision.
  const [explain, setExplain] = useStickyFlag("listenup-voice-explain", true);
  const [tier, setTier] = useStickyLanguage("listenup-voice-tier", "balanced");
  const [tiers, setTiers] = useState<ModelTier[]>([]);

  useEffect(() => {
    const controller = new AbortController();
    fetch(`${BACKEND}/translate/models`, { signal: controller.signal })
      .then((r) => r.json())
      .then((body) => setTiers(body?.tiers ?? []))
      .catch(() => undefined);
    return () => controller.abort();
  }, []);

  const { translations, failure, culturalFailure, isSettled } = useLiveTranslation(
    segments,
    target,
    true,
    { enabled: explain, tier }
  );
  const speech = useSharedSpeech();

  // Auto-speak the newest finalised translation, keyed on segment id rather
  // than on the text: the same sentence can legitimately be said twice in a
  // conversation, and both times deserve to be read out.
  //
  // Waits for the cultural pass to settle. The two lanes race, and speaking on
  // first arrival read out the literal translation while the screen showed the
  // adapted one — audibly the wrong version of the sentence, and the only
  // version the person opposite ever gets.
  const latestSpoken = newestSpeakableLine(segments, translations, isSettled);
  useAutoSpeak(
    latestSpoken ? latestSpoken.id : "",
    latestSpoken ? (translations[latestSpoken.id]?.text ?? "") : ""
  );

  // Google echoes the input when the detected source already matches the
  // target, so the line under "Original" is identical to the line above it and
  // the tool reads as broken. Detected from what came back rather than from the
  // spoken-language picker, because the picker says what the mic is set to and
  // this says what was actually heard.
  const echoing = Object.values(translations).some((t) => t.sourceLang && t.sourceLang === target);

  // The first supported language that isn't the current target — with en/ko
  // that is simply "the other one", and it stays correct if the list grows.
  const otherLanguage = Object.keys(languages).find((code) => code !== target) ?? null;

  const live = status === "listening" || status === "connecting";
  const paused = status === "paused";

  const statusLine = paused
    ? "Paused. Nothing is being captured."
    : status === "connecting"
      ? "Starting the microphone…"
      : status === "listening"
        ? "Listening. Every finished sentence is translated below."
        : status === "stopped"
          ? "Stopped. Starting again begins a new conversation."
          : "Speak, and each sentence is translated as you go.";

  return (
    <div className="flex flex-col gap-3">
      {/* Status and the action sit on one line, and the two configure controls
          share the next. Four stacked rows pushed the pane far enough down the
          page that its bottom edge — where the newest line lives — fell below
          the fold, which is the exact complaint this pane exists to answer.
          Controls that configure recede; the control that acts leads. */}
      <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-2">
        <p role="status" className="text-sm text-ink-soft">
          {statusLine}
        </p>

        <div className="flex flex-wrap items-center gap-2">
          {/* Pause and Stop answer different questions, so they are never the
              same button wearing two labels: pause keeps the conversation and
              the mic can come back; stop ends the session. Coral marks whichever
              is the one obvious next step — start when idle, resume when held. */}
          {paused ? (
            <Button onClick={resume} className="flex items-center gap-2">
              <MicIcon />
              Resume
            </Button>
          ) : live ? (
            <Button variant="ghost" onClick={pause} className="flex items-center gap-2">
              <PauseIcon />
              Pause
            </Button>
          ) : (
            <Button onClick={start} className="flex items-center gap-2">
              <MicIcon />
              Start speaking
            </Button>
          )}
          {(live || paused) && (
            <Button variant="ghost" onClick={stop}>
              Stop
            </Button>
          )}
        </div>
      </div>

      <div className="flex flex-wrap items-center gap-x-5 gap-y-2 border-y border-white/40 py-2">
        <SpokenLanguagePicker value={spoken} onChange={setSpoken} disabled={live || paused} />

        {/* Explanations are the expensive half of this tool, so the switch says
            what it spends rather than only what it does. Off means the request
            is never sent — not sent and hidden. */}
        <div className="flex min-w-0 flex-wrap items-center gap-2">
          <button
            type="button"
            role="switch"
            aria-checked={explain}
            onClick={() => setExplain(!explain)}
            className={`inline-flex min-h-11 items-center gap-2 rounded-full px-3.5 text-[13px] font-medium transition-colors ${
              explain
                ? "bg-accent-strong text-on-accent"
                : "pill-inactive text-ink-soft hover:text-ink"
            }`}
          >
            <span
              aria-hidden="true"
              className={`size-2 rounded-full ${explain ? "bg-on-accent" : "bg-ink-faint"}`}
            />
            Explain slang {explain ? "on" : "off"}
          </button>

          {explain && tiers.length > 0 && (
            <>
              <label htmlFor="voice-tier" className="sr-only">
                Explanation model
              </label>
              <select
                id="voice-tier"
                value={tier}
                onChange={(event) => setTier(event.target.value)}
                // A select is as wide as its longest option, which overflowed
                // a 390px viewport. Clamped rather than truncated in the copy,
                // so the cost stays readable where there is room for it.
                className="glass-strong min-h-11 min-w-0 max-w-full rounded-xl border border-white/60 px-3 text-sm text-ink shadow-glass outline-none"
              >
                {tiers.map((option) => (
                  <option key={option.key} value={option.key}>
                    {option.label} — {option.blurb}
                  </option>
                ))}
              </select>
            </>
          )}
        </div>
        {speech.voices.length > 0 && (
          <VoicePicker
            id="voice-conversation-voice"
            voices={speech.voices}
            voiceId={speech.voiceId}
            onChoose={speech.chooseVoice}
            onPreview={(text, id) => speech.speak(text, id)}
            onStop={speech.stop}
            speaking={speech.speaking}
            autoSpeak={speech.autoSpeak}
            onToggleAutoSpeak={speech.toggleAutoSpeak}
            language={target}
          />
        )}
      </div>

      {error && (
        <p
          role="alert"
          className="rounded-xl border border-error bg-white/70 px-4 py-3 text-sm text-error-strong"
        >
          {error}
        </p>
      )}

      {/* Running out of caption hours is not a malfunction, so it does not get
          the error treatment. Before this pane existed the translate tool
          showed nothing at all in this case. */}
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

      {allowanceWarning && !limit && (
        <p
          role="status"
          className="rounded-xl border border-warning bg-white/70 px-4 py-2.5 text-[13px] leading-relaxed text-ink"
        >
          {Math.round(allowanceWarning.remaining / 60)} minutes of captions left this billing period
          {allowanceWarning.resetsAt && `, resetting ${formatDate(allowanceWarning.resetsAt)}`}.
        </p>
      )}

      {/* The spoken language and the target are the same, so there is nothing to
          translate and the pane is showing the input twice. Said plainly, with
          both ways out, because the silent version of this looks like a
          translator that has stopped working. */}
      {echoing && !failure && (
        <div
          role="status"
          className="flex flex-col gap-2 rounded-xl border border-warning bg-white/70 px-4 py-3 text-[13px] leading-relaxed text-ink"
        >
          <p>
            You&apos;re translating {languages[target] ?? target} into {languages[target] ?? target}
            , so these lines come back unchanged.
          </p>
          {/* The fix, where the problem is noticed. Offered rather than applied
              silently: the target is the user's setting, and changing it under
              them mid-conversation is its own surprise. */}
          <div className="flex flex-wrap items-center gap-3">
            {otherLanguage && (
              <button
                type="button"
                onClick={() => setTarget(otherLanguage)}
                className="btn-primary inline-flex min-h-11 w-fit items-center rounded-full px-5 text-sm font-semibold text-on-accent"
              >
                Translate to {languages[otherLanguage] ?? otherLanguage} instead
              </button>
            )}
            <Link
              href="/explain"
              className="inline-flex min-h-11 items-center underline underline-offset-2"
            >
              Or explain a term without translating
            </Link>
          </div>
        </div>
      )}

      {/* The literal lane is fine; the cultural one stopped. That distinction is
          the whole message: the user can see words on screen, so "translation
          stopped" would be visibly untrue, and saying nothing leaves them
          assuming the slang explanations were never a feature. */}
      {culturalFailure && !failure && (
        <div
          role="status"
          className="flex flex-col gap-2 rounded-xl border border-warning bg-white/70 px-4 py-3 text-sm text-ink"
        >
          <p className="leading-relaxed">
            Lines are being translated, but slang and register explanations aren&apos;t running.{" "}
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

      {/* Transcription is still running; translation is what stopped. Saying
          which one matters, because "not on your plan" and "used it up" need
          different answers from the reader. */}
      {failure && (
        <div
          role="status"
          className="flex flex-col gap-2 rounded-xl border border-warning bg-white/70 px-4 py-3 text-sm text-ink"
        >
          <p className="leading-relaxed">
            Your words are still being transcribed, but translation stopped. {failure.message}
            {failure.paywall?.resetsAt && ` It resets ${formatDate(failure.paywall.resetsAt)}.`}
          </p>
          {failure.paywall && (
            <Link
              href="/settings"
              className="btn-primary inline-flex min-h-11 w-fit items-center rounded-full px-5 text-sm font-semibold text-on-accent"
            >
              {failure.paywall.upgradeTo === "pro" ? "Upgrade to Pro" : "See plans"}
            </Link>
          )}
        </div>
      )}

      <ConversationPane
        segments={segments}
        translations={translations}
        languages={languages}
        label="Spoken conversation and translations"
        // Sized so the pane's *bottom* edge stays on screen on a laptop: the
        // newest line is the one that matters live, and a pane whose foot falls
        // below the fold recreates the page-chasing this replaced, only
        // smaller. Measured at 1280×900 with the chrome above it, and
        // retrimmed when the explanations switch and model picker were added —
        // the fold guarantee has to survive controls being added above it.
        height={live || paused ? PANE_HEIGHT_LIVE : PANE_HEIGHT_IDLE}
        noun="line"
        active={live || paused}
        correcting={Boolean(correction.correcting)}
        onCorrect={(speaker) => void correction.open(speaker)}
        empty={
          <div className="m-auto flex max-w-sm flex-col items-center gap-2 px-4 text-center">
            <p className="text-sm font-medium text-ink">
              {live ? "Go ahead — say something." : "Nothing spoken yet."}
            </p>
            <p className="text-[13px] leading-relaxed text-ink-soft">
              Each sentence you finish appears here in {languages[target] ?? target}, with the
              original underneath and a note on any slang. The newest one stays at the bottom, so
              you never have to chase it.
            </p>
          </div>
        }
        footer={
          // Sits in the flow at the end of the transcript rather than floating
          // over it: while paused the last thing said is the thing being looked
          // at, and a state this consequential should not cover it. Never
          // colour alone — it says "Paused".
          paused ? (
            <p className="mt-1 flex items-center gap-2 rounded-xl border border-white/60 bg-white/55 px-3.5 py-2 text-[13px] text-ink">
              <span aria-hidden="true" className="size-2 rounded-full bg-ink-faint" />
              <span>
                <span className="font-semibold">Paused.</span>
                {/* A string expression, not JSX text: JSX trims the leading
                    space off a text node that opens after an element, and this
                    rendered as "Paused.The microphone". Writing `{" "}` fixes it
                    until Prettier reflows the line and removes it again, so the
                    space lives inside the literal. */}
                {" The microphone is off and nothing is being sent. Resume when you're ready."}
              </span>
            </p>
          ) : null
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
    </div>
  );
}
