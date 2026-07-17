"use client";

import { useEffect, useState } from "react";
import { createClient, isSupabaseConfigured } from "@/lib/supabase/client";
import SpeakerBubble, { type Caption } from "@/components/captions/SpeakerBubble";
import { MicIcon, PlayIcon, SendIcon } from "@/components/shell/icons";
import GlassCard from "@/components/ui/GlassCard";
import IconButton from "@/components/ui/IconButton";
import Orb from "@/components/ui/Orb";

// Placeholder conversation — Phase 2 streams real captions into the live region.
const sampleCaptions: Caption[] = [
  { id: "1", speaker: "Mom", speakerIndex: 0, text: "Are you coming over for dinner on Sunday?" },
  { id: "2", speaker: "You", speakerIndex: 1, text: "Yes! I'll bring dessert. What time works?" },
  { id: "3", speaker: "Dad", speakerIndex: 2, text: "Six-ish. Your grandmother's joining too." },
  { id: "4", speaker: "Mom", speakerIndex: 0, text: "Come earlier if you want to help cook." },
];

function timeGreeting(): string {
  const hour = new Date().getHours();
  if (hour < 12) return "Good morning";
  if (hour < 18) return "Good afternoon";
  return "Good evening";
}

export default function CaptionPanel() {
  const [name, setName] = useState<string | null>(null);

  useEffect(() => {
    if (!isSupabaseConfigured()) return;
    createClient()
      .auth.getClaims()
      .then(({ data }) => {
        const email = data?.claims?.email as string | undefined;
        if (email) setName(email.split("@")[0]);
      });
  }, []);

  return (
    <GlassCard className="flex h-full min-h-120 flex-col gap-4 p-6">
      <div className="flex flex-col items-center gap-3 pt-2 text-center">
        <Orb size="lg" />
        <h2 className="font-display text-[22px] font-semibold leading-snug">
          {timeGreeting()}
          {name ? `, ${name}` : ""}.
          <span className="block text-[15px] font-normal text-ink-soft">
            Ready when the conversation is.
          </span>
        </h2>
      </div>

      {/* Active-session pill */}
      <div className="glass-strong flex items-center gap-3 self-center rounded-full border border-white/60 py-1.5 pl-2 pr-4 shadow-glass">
        <span className="flex h-7 w-7 items-center justify-center rounded-full bg-(--accent) text-on-accent">
          <PlayIcon />
        </span>
        <span className="text-[13px] font-medium text-ink">Live Captioning</span>
        <span className="text-[13px] tabular-nums text-ink-faint">00:42</span>
      </div>

      {/* Caption stream — ARIA live region for Phase 2 */}
      <div
        role="log"
        aria-live="polite"
        aria-label="Live captions"
        className="flex min-h-0 flex-1 flex-col justify-end gap-2.5 overflow-y-auto"
      >
        {sampleCaptions.map((caption) => (
          <SpeakerBubble key={caption.id} caption={caption} />
        ))}
      </div>

      {/* Ask input */}
      <form
        className="glass-strong flex items-center gap-1 rounded-full border border-white/60 py-1.5 pl-4 pr-1.5 shadow-glass"
        onSubmit={(e) => e.preventDefault()}
      >
        <label htmlFor="ask-input" className="sr-only">
          Ask anything
        </label>
        <input
          id="ask-input"
          placeholder="Ask anything…"
          className="min-w-0 flex-1 bg-transparent text-sm text-ink outline-none placeholder:text-ink-faint"
        />
        <IconButton label="Start voice input" className="h-9 w-9">
          <MicIcon />
        </IconButton>
        <IconButton label="Send" accent className="h-9 w-9">
          <SendIcon />
        </IconButton>
      </form>
    </GlassCard>
  );
}
