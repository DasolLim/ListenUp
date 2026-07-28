import type { Metadata } from "next";
import Link from "next/link";
import Reveal from "@/components/Reveal";
import { Eyebrow } from "@/components/marketing/Section";
import { CaptionsIcon, TranslateIcon } from "@/components/shell/icons";
import Orb from "@/components/ui/Orb";
import VoiceStudio from "@/components/speech/VoiceStudio";

export const metadata: Metadata = { title: "Dashboard — ListenUp" };

type Tool = {
  href: string;
  name: string;
  tier?: string;
  blurb: string;
  wash: string;
  badge?: string;
};

// Grouped by product family so it's obvious which tool belongs where,
// mirroring the Product page (Voice-to-Text vs Translation).
const families: {
  key: string;
  label: string;
  intro: string;
  icon: React.ReactNode;
  tools: Tool[];
}[] = [
  {
    key: "voice-to-text",
    label: "Voice-to-Text",
    intro: "Live captions that name who is speaking.",
    icon: <CaptionsIcon />,
    tools: [
      {
        href: "/voice-to-text/general",
        name: "Live captions",
        tier: "General",
        blurb: "See who said what in real time, each speaker in their own colored bubble.",
        wash: "tile-wash-peach",
        badge: "Start here",
      },
      {
        href: "/voice-to-text/enhanced",
        name: "Voice profiles",
        tier: "Enhanced",
        blurb: "Name the people you talk to most, so captions show “Mom”, not “Speaker 1”.",
        wash: "tile-wash-lilac",
      },
    ],
  },
  {
    key: "translation",
    label: "Translation",
    intro: "Translation that keeps the meaning, not just the words.",
    icon: <TranslateIcon />,
    tools: [
      {
        href: "/translate/general",
        name: "Translate",
        tier: "General",
        blurb: "Translate between English and Korean, by text or voice.",
        wash: "tile-wash-sage",
      },
      {
        href: "/translate/enhanced",
        name: "Cultural translation",
        tier: "Enhanced",
        blurb: "Meaning, register, and slang, with the closest local equivalent.",
        wash: "tile-wash-amber",
      },
      {
        href: "/translate/genz",
        name: "GenZ slang",
        blurb: "Modern internet slang and memes, decoded into plain language.",
        wash: "tile-wash-lilac",
      },
    ],
  },
];

function Arrow() {
  return (
    <svg
      className="text-accent-strong transition-transform group-hover:translate-x-0.5"
      width="18"
      height="18"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d="M5 12h14M13 6l6 6-6 6" />
    </svg>
  );
}

function ToolTile({ tool }: { tool: Tool }) {
  return (
    <Link
      href={tool.href}
      className="group glass-card flex h-full flex-col overflow-hidden transition-transform hover:-translate-y-0.5"
    >
      <span aria-hidden="true" className={`relative h-16 w-full ${tool.wash}`}>
        {tool.badge && (
          <span className="absolute left-3 top-3 flex items-center gap-1.5 rounded-full bg-white/75 px-2.5 py-1 text-[12px] font-medium text-ink-soft">
            <span className="h-1.5 w-1.5 rounded-full bg-accent-strong" />
            {tool.badge}
          </span>
        )}
      </span>
      <span className="flex flex-1 flex-col gap-1.5 p-5">
        <span className="flex items-center gap-2">
          <span className="font-display text-[17px] font-semibold">{tool.name}</span>
          {tool.tier && (
            <span className="rounded-full bg-white/60 px-2 py-0.5 text-[11px] font-medium text-ink-soft">
              {tool.tier}
            </span>
          )}
          <Arrow />
        </span>
        <span className="text-sm leading-relaxed text-ink-soft">{tool.blurb}</span>
      </span>
    </Link>
  );
}

export default function DashboardPage() {
  return (
    <div className="flex flex-col gap-12">
      <Reveal>
        <div className="flex flex-col gap-3">
          <div className="flex items-center gap-3">
            <Orb size="md" />
            <Eyebrow>Your tools</Eyebrow>
          </div>
          <h1 className="font-display text-[30px] font-extrabold leading-tight tracking-tight sm:text-[38px]">
            What do you want to caption?
          </h1>
          <p className="max-w-xl text-[15px] leading-relaxed text-ink-soft sm:text-base">
            Two products, one conversation. Voice-to-Text names who is speaking; Translation
            carries what they mean. Pick a tool to begin.
          </p>
        </div>
      </Reveal>

      {families.map((family) => (
        <section key={family.key} aria-labelledby={family.key} className="flex flex-col gap-5">
          <Reveal>
            <div className="flex flex-col gap-1.5 border-b border-white/40 pb-4">
              <div className="flex items-center gap-2.5">
                <span className="flex h-9 w-9 items-center justify-center rounded-full bg-white/60 text-accent-strong">
                  {family.icon}
                </span>
                <h2 id={family.key} className="font-display text-[22px] font-bold tracking-tight">
                  {family.label}
                </h2>
              </div>
              <p className="text-[15px] text-ink-soft">{family.intro}</p>
            </div>
          </Reveal>
          <div
            className={`grid gap-5 sm:grid-cols-2 ${
              family.tools.length > 2 ? "lg:grid-cols-3" : ""
            }`}
          >
            {family.tools.map((tool, i) => (
              <Reveal key={tool.href} delay={i * 70}>
                <ToolTile tool={tool} />
              </Reveal>
            ))}
          </div>
        </section>
      ))}

      {/* Read-aloud settings live on the dashboard rather than buried in a tool:
          the voice applies everywhere, so configuring it is an account-level
          job, not a per-translation one. */}
      <section aria-labelledby="voice-studio" className="flex flex-col gap-5">
        <Reveal>
          <div className="flex flex-col gap-1.5 border-b border-white/40 pb-4">
            <div className="flex items-center gap-2.5">
              <span className="flex h-9 w-9 items-center justify-center rounded-full bg-white/60 text-accent-strong">
                <SpeakerIcon />
              </span>
              <h2 id="voice-studio" className="font-display text-[22px] font-bold tracking-tight">
                Read aloud
              </h2>
            </div>
            <p className="text-[15px] text-ink-soft">
              The voice that speaks translations, anywhere in the app.
            </p>
          </div>
        </Reveal>
        <Reveal>
          <VoiceStudio />
        </Reveal>
      </section>
    </div>
  );
}

function SpeakerIcon() {
  return (
    <svg
      width="18"
      height="18"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d="M11 5 6 9H3v6h3l5 4V5Z" />
      <path d="M15.5 8.5a5 5 0 0 1 0 7" />
      <path d="M18.5 5.5a9 9 0 0 1 0 13" />
    </svg>
  );
}
