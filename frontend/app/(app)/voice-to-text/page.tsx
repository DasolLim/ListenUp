import type { Metadata } from "next";
import Link from "next/link";
import GlassCard from "@/components/ui/GlassCard";

export const metadata: Metadata = { title: "Voice-to-Text — ListenUp" };

export default function VoiceToTextPage() {
  return (
    <GlassCard strong className="max-w-2xl p-7">
      <h2 className="font-display text-[22px] font-semibold">Live captions, readable</h2>
      <p className="mt-3 text-ink-soft">
        Captions that separate speakers, so conversation is readable — not a wall of text.
      </p>
      <ul className="mt-6 flex flex-col gap-3">
        <li>
          <Link
            href="/voice-to-text/general"
            className="text-ink underline underline-offset-4 hover:text-accent-strong"
          >
            General — live captions with speaker separation
          </Link>
        </li>
        <li>
          <Link
            href="/voice-to-text/enhanced"
            className="text-ink underline underline-offset-4 hover:text-accent-strong"
          >
            Enhanced — saved voice profiles, people labeled by name
          </Link>
        </li>
      </ul>
    </GlassCard>
  );
}
