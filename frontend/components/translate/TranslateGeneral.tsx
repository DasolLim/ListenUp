"use client";

import { useEffect, useRef, useState } from "react";
import { MicIcon } from "@/components/shell/icons";
import Button from "@/components/ui/Button";
import SpeakButton from "@/components/speech/SpeakButton";
import ReadAloudBar from "@/components/speech/ReadAloudBar";
import TranslateShell from "@/components/translate/TranslateShell";
import { SpeechProvider, useAutoSpeak, useSharedSpeech } from "@/lib/SpeechProvider";
import { useStickyLanguage } from "@/lib/useStickyLanguage";
import Pill from "@/components/ui/Pill";
import SpokenLanguagePicker from "@/components/SpokenLanguagePicker";
import { useTranscription } from "@/lib/useTranscription";

const BACKEND = process.env.NEXT_PUBLIC_BACKEND_URL ?? "http://localhost:8000";

type Mode = "text" | "voice";

async function requestTranslation(text: string, targetLang: string) {
  const response = await fetch(`${BACKEND}/translate`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text, target_lang: targetLang }),
  });
  const body = await response.json();
  if (!response.ok) throw new Error(body.detail ?? "Translation failed.");
  return body as { translation: string; detectedSourceLang: string | null; cached: boolean };
}

function TranslateGeneralInner(props: { target: string; setTarget: (v: string) => void }) {
  const [mode, setMode] = useState<Mode>("text");
  const [languages, setLanguages] = useState<Record<string, string>>({});
  const { target, setTarget } = props;
  const speech = useSharedSpeech();

  const [input, setInput] = useState("");
  const [output, setOutput] = useState<{ text: string; source: string | null } | null>(null);

  // Keyed on the text: a repeat translation of the same phrase stays quiet.
  useAutoSpeak(output?.text ?? "", output?.text ?? "");

  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  // voice mode
  const [spoken, setSpoken] = useStickyLanguage("listenup-spoken-general");
  const { status, error: micError, segments, start, stop } = useTranscription({
    language: spoken,
  });
  const [voiceTranslations, setVoiceTranslations] = useState<Record<string, string>>({});
  const requested = useRef<Set<string>>(new Set());

  useEffect(() => {
    const controller = new AbortController();
    fetch(`${BACKEND}/translate/languages`, { signal: controller.signal })
      .then((r) => r.json())
      .then(setLanguages)
      .catch(() => undefined);
    return () => controller.abort();
  }, []);

  // translate each finalized caption once
  useEffect(() => {
    for (const segment of segments) {
      if (!segment.isFinal || requested.current.has(segment.id)) continue;
      requested.current.add(segment.id);
      requestTranslation(segment.text, target)
        .then((result) =>
          setVoiceTranslations((map) => ({ ...map, [segment.id]: result.translation }))
        )
        .catch(() => undefined);
    }
  }, [segments, target]);

  async function translateText() {
    if (!input.trim()) return;
    setBusy(true);
    setError(null);
    try {
      const result = await requestTranslation(input.trim(), target);
      setOutput({ text: result.translation, source: result.detectedSourceLang });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Translation failed.");
    } finally {
      setBusy(false);
    }
  }

  const listening = status === "listening" || status === "connecting";

  return (
    <TranslateShell
      title="Translate"
      tier="General"
      tagline="Fast, literal translation between English and Korean. Type it or speak it."
      modes={
        <div className="flex gap-2" role="group" aria-label="Input mode">
          <Pill active={mode === "text"} onClick={() => setMode("text")}>
            Text
          </Pill>
          <Pill active={mode === "voice"} onClick={() => setMode("voice")}>
            Voice
          </Pill>
        </div>
      }
      languageRow={
        <div className="flex items-center gap-2">
          <label htmlFor="target-lang" className="text-sm font-medium text-ink">
            Translate to
          </label>
          <select
            id="target-lang"
            value={target}
            onChange={(e) => setTarget(e.target.value)}
            className="glass-strong min-h-11 rounded-xl border border-white/60 px-3 text-sm text-ink shadow-glass outline-none"
          >
            {Object.entries(languages).map(([code, name]) => (
              <option key={code} value={code}>
                {name}
              </option>
            ))}
          </select>
        </div>
      }
    >


      {mode === "text" ? (
        <form
          className="flex flex-col gap-4"
          onSubmit={(e) => {
            e.preventDefault();
            translateText();
          }}
        >
          <div className="flex flex-col gap-1">
            <label htmlFor="source-text" className="text-sm font-medium">
              Text to translate
            </label>
            <textarea
              id="source-text"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              rows={4}
              maxLength={5000}
              placeholder="Type or paste anything…"
              className="glass-strong resize-y rounded-xl border border-white/60 px-3.5 py-2.5 text-ink shadow-glass outline-none placeholder:text-ink-faint"
            />
          </div>
          <div>
            <Button type="submit" disabled={busy || !input.trim()}>
              {busy ? "Translating…" : "Translate"}
            </Button>
          </div>
          {error && (
            <p role="alert" className="rounded-xl border border-error bg-white/70 px-4 py-3 text-sm text-error-strong">
              {error}
            </p>
          )}
          <div aria-live="polite">
            {output && (
              <div className="rounded-2xl border border-white/60 bg-white/60 p-4">
                <p className="text-[12px] font-semibold uppercase tracking-wide text-ink-soft">
                  {languages[target] ?? target}
                  {output.source ? ` · from ${languages[output.source] ?? output.source}` : ""}
                </p>
                <p className="caption-text mt-1 text-ink">{output.text}</p>
                <ReadAloudBar
                  text={output.text}
                  voice={speech.voices.find((v) => v.id === speech.voiceId)}
                  onSpeak={() => speech.speak(output.text)}
                  onStop={speech.stop}
                  speaking={speech.speaking}
                  autoSpeak={speech.autoSpeak}
                  onToggleAutoSpeak={speech.toggleAutoSpeak}
                />
              </div>
            )}
          </div>
        </form>
      ) : (
        <div className="flex flex-col gap-4">
          <SpokenLanguagePicker value={spoken} onChange={setSpoken} disabled={listening} />
          <div className="flex items-center gap-3">
            {listening ? (
              <Button variant="ghost" onClick={stop}>
                Stop
              </Button>
            ) : (
              <Button onClick={start} className="flex items-center gap-2">
                <MicIcon />
                Start speaking
              </Button>
            )}
            <p role="status" className="text-sm text-ink-soft">
              {listening
                ? "Listening — captions translate as you pause."
                : "Speak, and each finished sentence is translated."}
            </p>
          </div>
          {micError && (
            <p role="alert" className="rounded-xl border border-error bg-white/70 px-4 py-3 text-sm text-error-strong">
              {micError}
            </p>
          )}
          <div role="log" aria-live="polite" aria-label="Spoken captions and translations" className="flex flex-col gap-2.5">
            {segments.map((segment) => (
              <div key={segment.id} className="bubble-glass rounded-2xl bg-white/50 px-4 py-3">
                <p className="text-[12px] font-semibold uppercase tracking-wide text-ink-soft">
                  {segment.speakerName ?? segment.speaker}
                </p>
                <p className={`text-sm text-ink-soft ${segment.isFinal ? "" : "italic"}`}>
                  {segment.text}
                </p>
                {voiceTranslations[segment.id] && (
                  <div className="mt-1 flex items-start justify-between gap-2">
                    <p className="caption-text min-w-0 flex-1 text-ink">
                      {voiceTranslations[segment.id]}
                    </p>
                    <SpeakButton
                      onSpeak={() => speech.speak(voiceTranslations[segment.id])}
                      onStop={speech.stop}
                      speaking={speech.speaking}
                      label="the translation"
                    />
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      )}
    </TranslateShell>
  );
}

/**
 * The language lives in the wrapper so `SpeechProvider` can be given the target
 * before the tool renders: the shared engine needs to know which language's
 * voices to load, and that is the same value the tool translates into.
 */
export default function TranslateGeneral() {
  const [target, setTarget] = useStickyLanguage("listenup-target-general", "ko");
  return (
    <SpeechProvider language={target}>
      <TranslateGeneralInner target={target} setTarget={setTarget} />
    </SpeechProvider>
  );
}
