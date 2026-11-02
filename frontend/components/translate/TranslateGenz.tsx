"use client";

import { useRef, useState } from "react";
import Button from "@/components/ui/Button";
import SpeakButton from "@/components/speech/SpeakButton";
import { SpeechProvider, useSharedSpeech } from "@/lib/hooks/SpeechProvider";
import { postJson } from "@/lib/api";
import { networkError } from "@/lib/networkError";
import GlassCard from "@/components/ui/GlassCard";
import ShareCard from "@/components/translate/ShareCard";


export type Explanation = {
  term: string;
  plain_meaning: string;
  origin: string;
  first_seen: string;
  region: string;
  example: string;
  adult_friendly_explanation: string;
  confidence: "high" | "low";
  grounded_terms: string[];
};

const EXAMPLES = ["bussin", "rizz", "delulu", "no cap", "spill the tea", "갓생"];

function Meta({ label, value }: { label: string; value: string }) {
  if (!value) return null;
  return (
    <span className="rounded-full bg-white/70 px-3 py-1 text-[12px] text-ink-soft">
      <span className="font-semibold text-ink">{label}:</span> {value}
    </span>
  );
}

function ExplanationCard({ data }: { data: Explanation }) {
  const low = data.confidence === "low";
  const speech = useSharedSpeech();
  const [sharing, setSharing] = useState(false);
  return (
    <article className="rounded-2xl border border-white/60 bg-white/60 p-5">
      {low && (
        <p
          role="status"
          className="mb-3 rounded-xl border border-warning bg-white/70 px-3.5 py-2.5 text-sm text-warning-strong"
        >
          <span className="font-semibold">Best guess.</span> This term isn’t in our verified slang
          dictionary yet, so double-check before relying on it.
        </p>
      )}
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h3 className="font-display text-[26px] font-semibold text-ink">{data.term}</h3>
        <span
          className={`rounded-full px-2.5 py-0.5 text-[11px] font-medium ${
            low ? "bg-white/80 text-warning-strong" : "bg-white/80 text-success-strong"
          }`}
        >
          {low ? "unverified" : "verified"}
        </span>
      </div>

      <div className="mt-1.5 flex items-start justify-between gap-2">
        <p className="caption-text min-w-0 flex-1 text-ink">{data.plain_meaning}</p>
        <SpeakButton
          onSpeak={() => speech.speak(data.plain_meaning)}
          onStop={speech.stop}
          speaking={speech.speaking}
          label="the explanation"
        />
      </div>

      {(data.origin || data.first_seen || data.region) && (
        <div className="mt-3 flex flex-wrap gap-2">
          <Meta label="Origin" value={data.origin} />
          <Meta label="First seen" value={data.first_seen} />
          <Meta label="Where" value={data.region} />
        </div>
      )}

      {data.example && (
        <div className="mt-4 rounded-xl border border-white/60 bg-white/45 px-4 py-3">
          <p className="text-[12px] font-semibold uppercase tracking-wide text-ink-soft">Example</p>
          <p className="mt-0.5 text-ink">“{data.example}”</p>
        </div>
      )}

      {data.adult_friendly_explanation && (
        <div className="mt-4">
          <p className="text-[12px] font-semibold uppercase tracking-wide text-ink-soft">
            In plain terms
          </p>
          <p className="mt-0.5 text-ink-soft">{data.adult_friendly_explanation}</p>
        </div>
      )}

      <div className="mt-5 border-t border-white/50 pt-4">
        {sharing ? (
          <ShareCard data={data} />
        ) : (
          <Button type="button" variant="ghost" onClick={() => setSharing(true)}>
            Create share card
          </Button>
        )}
      </div>
    </article>
  );
}

function TranslateGenzInner() {
  const [input, setInput] = useState("");
  const [result, setResult] = useState<Explanation | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const seqRef = useRef(0);

  async function explain(text: string) {
    const trimmed = text.trim();
    if (!trimmed) return;
    const seq = ++seqRef.current;
    setBusy(true);
    setError(null);
    // Drop the previous explanation up front. Otherwise a failed lookup leaves
    // the last term's card on screen next to the error, so the UI appears to
    // have "not updated" — the symptom that reads as a caching bug.
    setResult(null);
    try {
      // postJson attaches the caller's token — /genz/explain is metered per
      // lookup, so an unauthenticated call is a 401 that reads as "broken".
      const body = await postJson<Explanation>("/genz/explain", { text: trimmed });
      if (seqRef.current === seq) setResult(body);
    } catch (err) {
      if (seqRef.current === seq) {
        setError(networkError(err, "Couldn’t explain that right now."));
      }
    } finally {
      if (seqRef.current === seq) setBusy(false);
    }
  }

  return (
    <GlassCard strong className="flex flex-col gap-5 p-6">
      <div>
        <h2 className="font-display text-[22px] font-semibold text-ink">Slang, explained</h2>
        <p className="mt-1 text-sm text-ink-soft">
          Type any internet slang, meme, or abbreviation — get a clear, grown-up-friendly
          explanation with its meaning, origin, and an example.
        </p>
      </div>

      <form
        className="flex flex-col gap-3"
        onSubmit={(e) => {
          e.preventDefault();
          explain(input);
        }}
      >
        <div className="flex flex-col gap-1">
          <label htmlFor="genz-term" className="text-sm font-medium text-ink">
            Word or phrase
          </label>
          <input
            id="genz-term"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            maxLength={200}
            placeholder="e.g. bussin, no cap, delulu, 갓생"
            className="glass-strong rounded-xl border border-white/60 px-3.5 py-2.5 text-ink shadow-glass outline-none placeholder:text-ink-faint"
          />
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Button type="submit" disabled={busy || !input.trim()}>
            {busy ? "Explaining…" : "Explain"}
          </Button>
          <span className="text-[12px] text-ink-soft">or try:</span>
          {EXAMPLES.map((word) => (
            <button
              key={word}
              type="button"
              onClick={() => {
                setInput(word);
                explain(word);
              }}
              className="rounded-full border border-white/60 bg-white/50 px-3 py-1 text-[13px] text-ink-soft transition-colors hover:text-ink"
            >
              {word}
            </button>
          ))}
        </div>
      </form>

      {error && (
        <p
          role="alert"
          className="rounded-xl border border-error bg-white/70 px-4 py-3 text-sm text-error-strong"
        >
          {error}
        </p>
      )}

      <div aria-live="polite">
        {result ? (
          <ExplanationCard data={result} />
        ) : (
          !busy && (
            <p className="rounded-2xl border border-dashed border-ink-faint/40 p-5 text-sm text-ink-soft">
              Your explanation will appear here. Slang ages fast — if we don’t know a term yet,
              we’ll give our best guess and flag it as unverified.
            </p>
          )
        )}
      </div>
    </GlassCard>
  );
}

/** Slang explanations are written in English, so the voice language is fixed. */
export default function TranslateGenz() {
  return (
    <SpeechProvider language="en">
      <TranslateGenzInner />
    </SpeechProvider>
  );
}
