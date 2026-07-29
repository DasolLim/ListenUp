"use client";

import { useEffect, useRef, useState } from "react";
import { MicIcon } from "@/components/shell/icons";
import Button from "@/components/ui/Button";
import ReadAloudBar from "@/components/speech/ReadAloudBar";
import TranslateShell from "@/components/translate/TranslateShell";
import { SpeechProvider, useAutoSpeak, useSharedSpeech } from "@/lib/SpeechProvider";
import { useStickyLanguage } from "@/lib/useStickyLanguage";
import Pill from "@/components/ui/Pill";
import SpokenLanguagePicker from "@/components/SpokenLanguagePicker";
import { useTranscription } from "@/lib/useTranscription";

const BACKEND = process.env.NEXT_PUBLIC_BACKEND_URL ?? "http://localhost:8000";

type Mode = "text" | "voice";

type SlangNote = {
  phrase: string;
  meaning: string;
  cultural_context: string;
  equivalent: string;
};

// One cultural-translation result (both text and voice modes produce these).
type Enhanced = {
  fast: string | null; // Google, instant
  fastSource: string | null;
  upgraded: string | null; // LLM cultural adaptation, arrives later
  register: string | null;
  notes: SlangNote[];
  checked: boolean; // LLM lane resolved (success or fail)
};

const EMPTY: Enhanced = {
  fast: null,
  fastSource: null,
  upgraded: null,
  register: null,
  notes: [],
  checked: false,
};

/**
 * Fire both lanes for one piece of text: fast Google translation, then the LLM
 * cultural upgrade. Identical for typed and spoken input, so voice→text matches
 * text→text accuracy exactly (same endpoints, same model, same prompt).
 */
function culturalTranslate(
  text: string,
  target: string,
  cb: {
    onFast: (translation: string, source: string | null) => void;
    onUpgrade: (translation: string | null, register: string | null, notes: SlangNote[]) => void;
    onError?: (message: string) => void;
  }
) {
  fetch(`${BACKEND}/translate`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text, target_lang: target }),
  })
    .then(async (r) => {
      const body = await r.json();
      if (!r.ok) throw new Error(body.detail);
      cb.onFast(body.translation, body.detectedSourceLang);
    })
    .catch((err) => cb.onError?.(err instanceof Error ? err.message : "Translation failed."));

  fetch(`${BACKEND}/translate/enhanced`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text, target_lang: target }),
  })
    .then(async (r) => {
      if (!r.ok) throw new Error("llm unavailable");
      const body = await r.json();
      cb.onUpgrade(body.translation ?? null, body.register ?? null, body.slangNotes ?? []);
    })
    .catch(() => cb.onUpgrade(null, null, [])); // fast translation still stands
}

function ResultCard({
  result,
  target,
  languages,
}: {
  result: Enhanced;
  target: string;
  languages: Record<string, string>;
}) {
  const speech = useSharedSpeech();
  const shown = result.upgraded ?? result.fast;

  // Keyed on the text, so when `upgraded` replaces `fast` the better version is
  // what gets spoken rather than the interim one.
  useAutoSpeak(shown ?? "", shown ?? "");
  if (!shown) return null;
  return (
    <div className="rounded-2xl border border-white/60 bg-white/60 p-4">
      <div className="flex flex-wrap items-center gap-2">
        <p className="text-[12px] font-semibold uppercase tracking-wide text-ink-soft">
          {languages[target] ?? target}
          {result.fastSource ? ` · from ${languages[result.fastSource] ?? result.fastSource}` : ""}
        </p>
        {result.register && (
          <span className="rounded-full bg-white/80 px-2.5 py-0.5 text-[11px] font-medium text-ink-soft">
            register: {result.register}
          </span>
        )}
        {!result.checked && (
          <span role="status" className="text-[11px] text-ink-soft">
            checking for slang…
          </span>
        )}
      </div>
      <p className="caption-text mt-1.5 text-ink">{shown}</p>
      {result.notes.length > 0 && (
        <div className="mt-2 flex flex-col gap-2">
          {result.notes.map((note) => (
            <details
              key={note.phrase}
              className="rounded-xl border border-white/60 bg-white/50 px-3.5 py-2.5"
            >
              <summary className="cursor-pointer text-sm font-medium text-ink">
                “{note.phrase}” — {note.meaning}
              </summary>
              <div className="mt-2 flex flex-col gap-1 text-sm text-ink-soft">
                {note.cultural_context && <p>{note.cultural_context}</p>}
                {note.equivalent && (
                  <p>
                    Closest equivalent: <span className="text-ink">{note.equivalent}</span>
                  </p>
                )}
              </div>
            </details>
          ))}
        </div>
      )}

      <ReadAloudBar
        text={shown}
        voice={speech.voices.find((v) => v.id === speech.voiceId)}
        onSpeak={() => speech.speak(shown)}
        onStop={speech.stop}
        speaking={speech.speaking}
        autoSpeak={speech.autoSpeak}
        onToggleAutoSpeak={speech.toggleAutoSpeak}
      />
    </div>
  );
}

function TranslateEnhancedInner(props: { target: string; setTarget: (v: string) => void }) {
  const [mode, setMode] = useState<Mode>("text");
  const [languages, setLanguages] = useState<Record<string, string>>({});
  const { target, setTarget } = props;

  // text mode
  const [input, setInput] = useState("");
  const [textResult, setTextResult] = useState<Enhanced>(EMPTY);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const seqRef = useRef(0);

  // voice mode: one cultural result per finalized caption
  const [spoken, setSpoken] = useState("en");
  const { status, error: micError, segments, start, stop } = useTranscription({
    language: spoken,
  });
  const [voiceResults, setVoiceResults] = useState<Record<string, Enhanced>>({});
  const requested = useRef<Set<string>>(new Set());

  useEffect(() => {
    const controller = new AbortController();
    fetch(`${BACKEND}/translate/languages`, { signal: controller.signal })
      .then((r) => r.json())
      .then(setLanguages)
      .catch(() => undefined);
    return () => controller.abort();
  }, []);

  // Voice: run the SAME cultural pipeline on each finalized caption.
  useEffect(() => {
    for (const segment of segments) {
      if (!segment.isFinal || requested.current.has(segment.id)) continue;
      requested.current.add(segment.id);
      culturalTranslate(segment.text, target, {
        onFast: (translation, source) =>
          setVoiceResults((map) => ({
            ...map,
            [segment.id]: { ...(map[segment.id] ?? EMPTY), fast: translation, fastSource: source },
          })),
        onUpgrade: (translation, register, notes) =>
          setVoiceResults((map) => ({
            ...map,
            [segment.id]: {
              ...(map[segment.id] ?? EMPTY),
              upgraded: translation ?? map[segment.id]?.upgraded ?? null,
              register: register ?? map[segment.id]?.register ?? null,
              notes: notes.length ? notes : (map[segment.id]?.notes ?? []),
              checked: true,
            },
          })),
      });
    }
  }, [segments, target]);

  function runText() {
    const text = input.trim();
    if (!text) return;
    const seq = ++seqRef.current;
    setError(null);
    setTextResult(EMPTY);
    setBusy(true);
    culturalTranslate(text, target, {
      onFast: (translation, source) => {
        if (seqRef.current !== seq) return;
        setTextResult((s) => ({ ...s, fast: translation, fastSource: source }));
        setBusy(false);
      },
      onUpgrade: (translation, register, notes) => {
        if (seqRef.current !== seq) return;
        setTextResult((s) => ({
          ...s,
          upgraded: translation ?? s.upgraded,
          register: register ?? s.register,
          notes: notes.length ? notes : s.notes,
          checked: true,
        }));
      },
      onError: (message) => {
        if (seqRef.current !== seq) return;
        setError(message);
        setBusy(false);
      },
    });
  }

  const listening = status === "listening" || status === "connecting";

  return (
    <TranslateShell
      title="Cultural translation"
      tier="Enhanced"
      tagline="Slang, tone, and register explained, not just the words. Slower than General, because a model reads the nuance."
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
          <label htmlFor="enhanced-target" className="text-sm font-medium text-ink">
            Translate to
          </label>
          <select
            id="enhanced-target"
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
        <>
          <form
            className="flex flex-col gap-4"
            onSubmit={(e) => {
              e.preventDefault();
              runText();
            }}
          >
            <div className="flex flex-col gap-1">
              <label htmlFor="enhanced-text" className="text-sm font-medium">
                Text to translate (slang welcome)
              </label>
              <textarea
                id="enhanced-text"
                value={input}
                onChange={(e) => setInput(e.target.value)}
                rows={3}
                maxLength={5000}
                placeholder="That movie was straight fire, no cap."
                className="glass-strong resize-y rounded-xl border border-white/60 px-3.5 py-2.5 text-ink shadow-glass outline-none placeholder:text-ink-faint"
              />
            </div>
            <div>
              <Button type="submit" disabled={busy || !input.trim()}>
                {busy ? "Translating…" : "Translate"}
              </Button>
            </div>
          </form>

          {error && (
            <p role="alert" className="rounded-xl border border-error bg-white/70 px-4 py-3 text-sm text-error-strong">
              {error}
            </p>
          )}
          <div aria-live="polite">
            <ResultCard result={textResult} target={target} languages={languages} />
          </div>
        </>
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
                ? "Listening — each finished sentence is culturally translated."
                : "Speak, and every sentence gets the same slang-aware translation."}
            </p>
          </div>
          {micError && (
            <p role="alert" className="rounded-xl border border-error bg-white/70 px-4 py-3 text-sm text-error-strong">
              {micError}
            </p>
          )}
          <div
            role="log"
            aria-live="polite"
            aria-label="Spoken captions and cultural translations"
            className="flex flex-col gap-3"
          >
            {segments.map((segment) => (
              <div key={segment.id} className="flex flex-col gap-2">
                <div className="bubble-glass rounded-2xl bg-white/50 px-4 py-3">
                  <p className="text-[12px] font-semibold uppercase tracking-wide text-ink-soft">
                    {segment.speakerName ?? segment.speaker}
                  </p>
                  <p className={`text-sm text-ink-soft ${segment.isFinal ? "" : "italic"}`}>
                    {segment.text}
                  </p>
                </div>
                {voiceResults[segment.id] && (
                  <ResultCard
                    result={voiceResults[segment.id]}
                    target={target}
                    languages={languages}
                  />
                )}
              </div>
            ))}
          </div>
        </div>
      )}
    </TranslateShell>
  );
}

/** Language lives here so the shared speech engine knows which voices to load. */
export default function TranslateEnhanced() {
  const [target, setTarget] = useStickyLanguage("listenup-target-enhanced", "ko");
  return (
    <SpeechProvider language={target}>
      <TranslateEnhancedInner target={target} setTarget={setTarget} />
    </SpeechProvider>
  );
}
