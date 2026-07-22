"use client";

import { useEffect, useRef, useState } from "react";
import Button from "@/components/ui/Button";
import GlassCard from "@/components/ui/GlassCard";

const BACKEND = process.env.NEXT_PUBLIC_BACKEND_URL ?? "http://localhost:8000";

type SlangNote = {
  phrase: string;
  meaning: string;
  cultural_context: string;
  equivalent: string;
};

type EnhancedState = {
  fast: string | null; // Google, instant
  fastSource: string | null;
  upgraded: string | null; // LLM, arrives later
  register: string | null;
  notes: SlangNote[];
  llmFailed: boolean;
};

const EMPTY: EnhancedState = {
  fast: null,
  fastSource: null,
  upgraded: null,
  register: null,
  notes: [],
  llmFailed: false,
};

export default function TranslateEnhanced() {
  const [languages, setLanguages] = useState<Record<string, string>>({});
  const [target, setTarget] = useState("en");
  const [input, setInput] = useState("");
  const [state, setState] = useState<EnhancedState>(EMPTY);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const requestSeq = useRef(0);

  useEffect(() => {
    const controller = new AbortController();
    fetch(`${BACKEND}/translate/languages`, { signal: controller.signal })
      .then((r) => r.json())
      .then(setLanguages)
      .catch(() => undefined);
    return () => controller.abort();
  }, []);

  async function run() {
    const text = input.trim();
    if (!text) return;
    const seq = ++requestSeq.current;
    setError(null);
    setState(EMPTY);
    setBusy(true);

    // Fast lane: Google, render the moment it lands.
    fetch(`${BACKEND}/translate`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text, target_lang: target }),
    })
      .then(async (r) => {
        const body = await r.json();
        if (!r.ok) throw new Error(body.detail);
        if (requestSeq.current === seq) {
          setState((s) => ({ ...s, fast: body.translation, fastSource: body.detectedSourceLang }));
        }
      })
      .catch((err) => {
        if (requestSeq.current === seq) {
          setError(err instanceof Error ? err.message : "Translation failed.");
        }
      })
      .finally(() => {
        if (requestSeq.current === seq) setBusy(false);
      });

    // Slow lane: LLM cultural upgrade — NEVER blocks the fast result.
    fetch(`${BACKEND}/translate/enhanced`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text, target_lang: target }),
    })
      .then(async (r) => {
        if (!r.ok) throw new Error("llm unavailable");
        const body = await r.json();
        if (requestSeq.current === seq) {
          setState((s) => ({
            ...s,
            upgraded: body.translation,
            register: body.register,
            notes: body.slangNotes,
          }));
        }
      })
      .catch(() => {
        if (requestSeq.current === seq) setState((s) => ({ ...s, llmFailed: true }));
      });
  }

  const shown = state.upgraded ?? state.fast;

  return (
    <GlassCard strong className="flex flex-col gap-5 p-6">
      <form
        className="flex flex-col gap-4"
        onSubmit={(e) => {
          e.preventDefault();
          run();
        }}
      >
        <div className="flex flex-wrap items-end justify-between gap-3">
          <div className="flex min-w-0 flex-1 flex-col gap-1">
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
          <div className="flex items-center gap-2">
            <label htmlFor="enhanced-target" className="text-sm font-medium">
              To
            </label>
            <select
              id="enhanced-target"
              value={target}
              onChange={(e) => setTarget(e.target.value)}
              className="glass-strong rounded-xl border border-white/60 px-3 py-2 text-sm text-ink shadow-glass outline-none"
            >
              {Object.entries(languages).map(([code, name]) => (
                <option key={code} value={code}>
                  {name}
                </option>
              ))}
            </select>
            <Button type="submit" disabled={busy || !input.trim()}>
              Translate
            </Button>
          </div>
        </div>
      </form>

      {error && (
        <p role="alert" className="rounded-xl border border-error bg-white/70 px-4 py-3 text-sm text-error-strong">
          {error}
        </p>
      )}

      <div aria-live="polite" className="flex flex-col gap-3">
        {shown && (
          <div className="rounded-2xl border border-white/60 bg-white/60 p-4">
            <div className="flex flex-wrap items-center gap-2">
              <p className="text-[12px] font-semibold uppercase tracking-wide text-ink-soft">
                {languages[target] ?? target}
                {state.fastSource ? ` · from ${languages[state.fastSource] ?? state.fastSource}` : ""}
              </p>
              {state.register && (
                <span className="rounded-full bg-white/80 px-2.5 py-0.5 text-[11px] font-medium text-ink-soft">
                  register: {state.register}
                </span>
              )}
              {!state.register && !state.llmFailed && state.fast && (
                <span role="status" className="text-[11px] text-ink-soft">
                  checking for slang…
                </span>
              )}
            </div>
            <p data-testid="translation-output" className="caption-text mt-1.5 text-ink">
              {shown}
            </p>
          </div>
        )}

        {state.notes.length > 0 && (
          <section aria-label="Slang and culture notes" className="flex flex-col gap-2">
            {state.notes.map((note) => (
              <details
                key={note.phrase}
                className="rounded-2xl border border-white/60 bg-white/50 px-4 py-3"
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
          </section>
        )}
      </div>
    </GlassCard>
  );
}
