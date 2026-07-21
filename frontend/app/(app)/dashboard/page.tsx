import type { Metadata } from "next";
import Link from "next/link";
import Reveal from "@/components/Reveal";
import { Eyebrow } from "@/components/marketing/Section";
import Orb from "@/components/ui/Orb";

export const metadata: Metadata = { title: "Dashboard — ListenUp" };

const tools = [
  {
    href: "/voice-to-text/enhanced",
    name: "Voice profiles",
    blurb: "Name the people you talk to most, so captions show “Mom”, not “Speaker 1”.",
    wash: "tile-wash-lilac",
  },
  {
    href: "/translate/general",
    name: "Translate",
    blurb: "Fast text and voice translation across a wide range of languages.",
    wash: "tile-wash-sage",
  },
  {
    href: "/translate/enhanced",
    name: "Cultural translation",
    blurb: "Meaning, register, and slang, with the closest local equivalent.",
    wash: "tile-wash-amber",
  },
  {
    href: "/translate/genz",
    name: "GenZ slang",
    blurb: "Modern internet slang and memes, decoded into plain language.",
    wash: "tile-wash-lilac",
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

export default function DashboardPage() {
  return (
    <div className="flex flex-col gap-8">
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
            Live captions that name who&apos;s speaking, and translation that keeps the meaning.
            Pick a tool to begin.
          </p>
        </div>
      </Reveal>

      {/* Featured: live captions is the core of the product */}
      <Reveal delay={60}>
        <Link
          href="/voice-to-text/general"
          className="group tile-wash-peach relative flex flex-col justify-end overflow-hidden rounded-card border border-white/60 p-7 shadow-glass transition-transform hover:-translate-y-0.5 sm:min-h-56"
        >
          <span className="flex items-center gap-2 self-start rounded-full bg-white/70 px-3 py-1 text-[12px] font-medium text-ink-soft">
            <span className="h-1.5 w-1.5 rounded-full bg-accent-strong" />
            Start here
          </span>
          <span className="mt-4 flex items-center gap-2 font-display text-[24px] font-bold tracking-tight sm:text-[28px]">
            Live captions
            <Arrow />
          </span>
          <span className="mt-1 max-w-md text-[15px] leading-relaxed text-ink-soft">
            Open the mic and see who said what in real time, each speaker in their own colored
            bubble.
          </span>
        </Link>
      </Reveal>

      <section aria-label="More tools" className="grid gap-5 sm:grid-cols-2 lg:grid-cols-4">
        {tools.map((tool, i) => (
          <Reveal key={tool.href} delay={100 + i * 70}>
            <Link
              href={tool.href}
              className="group glass-card flex h-full flex-col overflow-hidden transition-transform hover:-translate-y-0.5"
            >
              <span aria-hidden="true" className={`h-16 w-full ${tool.wash}`} />
              <span className="flex flex-1 flex-col gap-1.5 p-5">
                <span className="flex items-center gap-1.5 font-display text-[17px] font-semibold">
                  {tool.name}
                  <Arrow />
                </span>
                <span className="text-sm leading-relaxed text-ink-soft">{tool.blurb}</span>
              </span>
            </Link>
          </Reveal>
        ))}
      </section>
    </div>
  );
}
