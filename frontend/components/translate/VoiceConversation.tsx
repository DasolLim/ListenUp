"use client";

import Link from "next/link";
import { useState } from "react";
import SpeakerBubble from "@/components/captions/SpeakerBubble";
import SpeakerCorrectionDialog from "@/components/captions/SpeakerCorrectionDialog";
import SpeakerName from "@/components/captions/SpeakerName";
import SpokenLanguagePicker from "@/components/SpokenLanguagePicker";
import VoicePicker from "@/components/speech/VoicePicker";
import { MicIcon, PauseIcon } from "@/components/shell/icons";
import Button from "@/components/ui/Button";
import { formatDate } from "@/lib/plans";
import { useAutoSpeak, useSharedSpeech } from "@/lib/SpeechProvider";
import { RAILS, identityColor, linePosition, stamp, turnGroups } from "@/lib/turnGroups";
import { useChatScroll } from "@/lib/useChatScroll";
import { useSpeakerCorrection } from "@/lib/useSpeakerCorrection";
import { useLiveTranslation } from "@/lib/useLiveTranslation";
import { useTranscription } from "@/lib/useTranscription";

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
  languages,
}: {
  target: string;
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
  const { translations, failure, culturalFailure } = useLiveTranslation(segments, target, true);
  const speech = useSharedSpeech();

  // Only finalised captions count as "new": interim text is rewritten several
  // times a second, and counting it would run the unread badge up while one
  // sentence is still being spoken.
  const finalCount = segments.filter((s) => s.isFinal).length;
  const { containerRef, watchContent, pinned, unread, onScroll, jumpToLatest } = useChatScroll({
    finalCount,
  });

  const latestFinal = [...segments].reverse().find((s) => s.isFinal) ?? null;

  // Auto-speak the newest finalised translation, keyed on segment id rather
  // than on the text: the same sentence can legitimately be said twice in a
  // conversation, and both times deserve to be read out.
  const latestSpoken = [...segments].reverse().find((s) => s.isFinal && translations[s.id]);
  useAutoSpeak(
    latestSpoken ? latestSpoken.id : "",
    latestSpoken ? (translations[latestSpoken.id]?.text ?? "") : ""
  );

  // Google echoes the input when the detected source already matches the
  // target, so the line under "Original" is identical to the line above it and
  // the tool reads as broken. Detected from what came back rather than from the
  // spoken-language picker, because the picker says what the mic is set to and
  // this says what was actually heard.
  const echoing = Object.values(translations).some(
    (t) => t.sourceLang && t.sourceLang === target
  );

  const live = status === "listening" || status === "connecting";
  const paused = status === "paused";
  const colorOf = identityColor(segments);

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
        <p
          role="status"
          className="rounded-xl border border-warning bg-white/70 px-4 py-2.5 text-[13px] leading-relaxed text-ink"
        >
          You&apos;re translating {languages[target] ?? target} into{" "}
          {languages[target] ?? target}, so these lines come back unchanged. Pick a different
          target language above, or{" "}
          <Link href="/explain" className="underline underline-offset-2">
            explain a term
          </Link>{" "}
          to unpack slang without translating.
        </p>
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

      {/* `aria-live` deliberately does NOT sit on the transcript: that region
          holds the in-progress line, rewritten several times a second, so a
          screen reader would talk over itself continuously. This carries only
          the newest settled line, announced once. */}
      <p className="sr-only" role="status" aria-live="polite" aria-atomic="true">
        {latestFinal
          ? `${latestFinal.speakerName ?? latestFinal.speaker}: ${
              translations[latestFinal.id]?.text ?? latestFinal.text
            }`
          : ""}
      </p>

      {/* Sized so the pane's *bottom* edge stays on screen on a laptop: the
          newest line is the one that matters live, and a pane whose foot falls
          below the fold recreates the page-chasing this replaced, only smaller.
          Measured at 1280×900 with the chrome above it. */}
      <div className="relative h-[clamp(15rem,42dvh,28rem)]">
        <div
          ref={containerRef}
          onScroll={onScroll}
          role="log"
          aria-label="Spoken conversation and translations"
          className="flex h-full flex-col overflow-y-auto overscroll-contain px-0.5"
        >
          {segments.length === 0 ? (
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
          ) : (
            // `mt-auto` sits a short conversation at the bottom, so the first
            // line appears where the next one will rather than at the top of an
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
                          onCorrect={
                            live || paused
                              ? () => void correction.open(group.speaker)
                              : undefined
                          }
                        />
                        {source && (
                          <span className="text-[11px] uppercase tracking-wide text-ink-faint">
                            {languages[source] ?? source}
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

              {/* Sits in the flow at the end of the transcript rather than
                  floating over it: while paused the last thing said is the
                  thing being looked at, and a state this consequential should
                  not cover it. Never colour alone — it says "Paused". */}
              {paused && (
                <p className="mt-1 flex items-center gap-2 rounded-xl border border-white/60 bg-white/55 px-3.5 py-2 text-[13px] text-ink">
                  <span aria-hidden="true" className="size-2 rounded-full bg-ink-faint" />
                  <span>
                    <span className="font-semibold">Paused.</span>
                    {/* A string expression, not JSX text: JSX trims the leading
                        space off a text node that opens after an element, and
                        this rendered as "Paused.The microphone". Writing `{" "}`
                        fixes it until Prettier reflows the line and removes it
                        again, so the space lives inside the literal. */}
                    {" The microphone is off and nothing is being sent. Resume when you're ready."}
                  </span>
                </p>
              )}
            </div>
          )}
        </div>

        {/* Floats over the transcript instead of sitting below it, so showing or
            hiding it never resizes the pane being read. */}
        {!pinned && (
          <button
            type="button"
            onClick={jumpToLatest}
            aria-label={
              unread > 0
                ? `${unread} new line${unread === 1 ? "" : "s"}, jump to latest`
                : "Jump to latest line"
            }
            className="btn-ghost absolute inset-x-0 bottom-2 mx-auto flex min-h-11 w-fit items-center gap-2 rounded-full px-4 text-sm text-ink shadow-glass"
          >
            {unread > 0 && (
              // Paired with the count in words — never colour alone (§7).
              <span aria-hidden="true" className="size-2 rounded-full bg-accent-strong" />
            )}
            {unread > 0 ? `${unread} new line${unread === 1 ? "" : "s"}` : "Jump to latest"}
          </button>
        )}
      </div>

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
