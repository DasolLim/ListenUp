import type { Metadata } from "next";
import ConversationPaneSample from "@/components/design/ConversationPaneSample";
import LiveSessionSample from "@/components/design/LiveSessionSample";
import MicDiagnostic from "@/components/design/MicDiagnostic";
import Button from "@/components/ui/Button";
import GlassCard from "@/components/ui/GlassCard";
import IconButton from "@/components/ui/IconButton";
import ImageTile from "@/components/ui/ImageTile";
import Orb from "@/components/ui/Orb";
import Pill from "@/components/ui/Pill";

export const metadata: Metadata = { title: "Design reference — ListenUp" };

// Internal style reference: every primitive on the gradient, used for design QA.
export default function DesignPage() {
  return (
    <div className="flex flex-col gap-8 pb-16">
      {/* First on the page deliberately: it sits directly under the same
          <Navbar /> the app shell uses, so the fold measurement in
          e2e/layout.spec.ts is the real offset rather than an approximation. */}
      <section aria-label="Live session layout">
        <LiveSessionSample />
      </section>

      <h1 className="font-display text-[34px] font-bold">Design reference</h1>

      <section aria-label="Glass cards" className="flex flex-wrap gap-6">
        <GlassCard className="w-72 p-7">
          <h2 className="font-display text-[18px] font-semibold">Glass card</h2>
          <p className="mt-2 text-sm text-ink-soft">
            The workhorse surface. Blur 24px, radius 28px, soft warm shadow.
          </p>
        </GlassCard>
        <GlassCard strong className="w-72 p-7">
          <h2 className="font-display text-[18px] font-semibold">Strong glass</h2>
          <p className="mt-2 text-sm text-ink-soft">
            More opaque — use behind dense body text to protect contrast.
          </p>
        </GlassCard>
      </section>

      {/* Public on purpose: the number this reports has to be read off a real
          handset, and requiring a sign-in on a borrowed phone is how a
          measurement does not get taken. */}
      <section aria-label="Microphone diagnostic" className="max-w-2xl">
        <h2 className="mb-3 font-display text-[18px] font-semibold">Microphone diagnostic</h2>
        <MicDiagnostic />
      </section>

      {/* The transcript pane, shared by live captions and Translate's voice
          mode. Both of those pages are auth-gated, so this gallery is where the
          browser loop can measure the pane's contrast, geometry and hit areas
          at all. */}
      <section aria-label="Conversation pane" className="max-w-2xl">
        <h2 className="mb-3 font-display text-[18px] font-semibold">Conversation pane</h2>
        <ConversationPaneSample />
      </section>

      <section aria-label="Orbs" className="flex items-end gap-6">
        <Orb size="lg" />
        <Orb size="md" />
        <Orb size="sm" />
      </section>

      <section aria-label="Pills" className="flex gap-3">
        <Pill active>Live</Pill>
        <Pill>Beta</Pill>
        <Pill>GenZ</Pill>
      </section>

      <section aria-label="Buttons" className="flex items-center gap-4">
        <Button>Start captioning</Button>
        <Button variant="ghost">Learn more</Button>
        <IconButton label="Search">
          <svg
            width="16"
            height="16"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
          >
            <circle cx="11" cy="11" r="7" />
            <path d="m20 20-3.5-3.5" />
          </svg>
        </IconButton>
        <IconButton label="Send" accent>
          <svg
            width="16"
            height="16"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
          >
            <path d="m22 2-7 20-4-9-9-4Z" />
          </svg>
        </IconButton>
      </section>

      <section aria-label="Image tiles" className="grid max-w-3xl grid-cols-2 gap-5">
        <ImageTile
          href="/captions"
          label="Voice-to-Text"
          sublabel="Live captions"
          wash="peach"
          className="h-56"
        />
        <ImageTile
          href="/translate"
          label="Translate"
          sublabel="English ↔ Korean"
          wash="sage"
          className="h-56"
        />
        <ImageTile
          href="/explain"
          label="GenZ"
          sublabel="Slang, decoded"
          wash="lilac"
          className="h-56"
        />
        <ImageTile
          href="/captions"
          label="My Sessions"
          sublabel="Saved transcripts"
          wash="amber"
          className="h-56"
        />
      </section>
    </div>
  );
}
