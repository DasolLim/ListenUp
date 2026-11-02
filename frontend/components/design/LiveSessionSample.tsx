"use client";

import { useState } from "react";
import ConversationPane from "@/components/captions/ConversationPane";
import SessionHeader from "@/components/captions/SessionHeader";
import Button from "@/components/ui/Button";
import { PANE_HEIGHT_LIVE } from "@/lib/paneHeight";
import { SpeechProvider } from "@/lib/hooks/SpeechProvider";
import { SEGMENTS, TRANSLATIONS } from "./ConversationPaneSample";

/**
 * Live captions **mid-session**, at the real heights, in the real shell.
 *
 * This exists to be measured. The gate for Task 1.1 is a rendered fact — "the
 * transcript's bottom edge is above the fold on a phone" — and `/captions` is
 * auth-gated, so the browser loop cannot reach it. Rather than describe the
 * layout in a test that could drift from it, this composes the **same**
 * `SessionHeader` and `ConversationPane` the real page does, with the same
 * height class, inside the same shell spacing.
 *
 * The wrapper reproduces `app/(app)/layout.tsx` exactly — `max-w-6xl px-4 py-8
 * sm:px-6`, then the page's own `max-w-3xl` — and this sample is rendered
 * **first** on `/design` so it sits directly under the same `<Navbar />`. That
 * makes the measured offset the real one rather than an approximation.
 *
 * If the real page's shell or height class changes and this is not updated,
 * the measurement stops describing the product — so keep them together.
 */
export default function LiveSessionSample() {
  const [correcting, setCorrecting] = useState(false);
  return (
    <div className="mx-auto w-full max-w-6xl px-4 py-8 sm:px-6">
      <div className="mx-auto max-w-3xl" data-testid="live-session-sample">
        <SpeechProvider language="ko">
          <div className="glass-strong flex flex-col gap-4 rounded-3xl p-6 shadow-glass">
            <SessionHeader
              title="Live captions"
              status="Listening — captions appear as people speak."
              compact
              orb={<div className="size-16 shrink-0 rounded-full bg-white/40" aria-hidden="true" />}
              setup={
                <>
                  <select
                    aria-label="Spoken language"
                    className="glass-strong min-h-11 rounded-xl border border-white/60 px-3 text-sm text-ink shadow-glass outline-none"
                    defaultValue="en"
                  >
                    <option value="en">English</option>
                    <option value="ko">Korean</option>
                  </select>
                  <label className="flex items-center gap-2 text-sm text-ink">
                    <input
                      type="checkbox"
                      defaultChecked
                      className="h-4 w-4 accent-accent-strong"
                    />
                    Translate to
                  </label>
                  <select
                    aria-label="Target language"
                    className="glass-strong min-h-11 rounded-xl border border-white/60 px-3 text-sm text-ink shadow-glass outline-none"
                    defaultValue="ko"
                  >
                    <option value="ko">Korean</option>
                    <option value="en">English</option>
                  </select>
                </>
              }
              actions={
                <>
                  <Button variant="ghost">Pause</Button>
                  <Button variant="ghost">Stop</Button>
                </>
              }
            />
            <ConversationPane
              segments={SEGMENTS}
              translations={TRANSLATIONS}
              languages={{ en: "English", ko: "Korean" }}
              label="Live captions"
              height={PANE_HEIGHT_LIVE}
              noun="caption"
              active
              correcting={correcting}
              onCorrect={() => setCorrecting(true)}
              empty={<p className="m-auto text-sm text-ink-soft">Nothing spoken yet.</p>}
            />
          </div>
        </SpeechProvider>
      </div>
    </div>
  );
}
