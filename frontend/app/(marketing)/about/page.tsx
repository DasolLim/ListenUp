import type { Metadata } from "next";
import GlassCard from "@/components/ui/GlassCard";

export const metadata: Metadata = { title: "About — ListenUp" };

export default function AboutPage() {
  return (
    <article className="mx-auto max-w-2xl pt-8">
      <h1 className="font-display text-[34px] font-bold">About ListenUp</h1>
      <GlassCard strong className="mt-6 flex flex-col gap-4 p-7 leading-relaxed text-ink-soft">
        <p>
          Existing captioning tools produce a wall of text — you can&apos;t tell who said what.
          Existing translators translate words, not meaning — they miss slang, tone, and culture.
        </p>
        <p>
          ListenUp exists to fix both. We build live captions that name each speaker — including
          the people you talk to most — and translation that explains register, slang, and
          cultural nuance. Built first for deaf and hard-of-hearing users; useful to anyone
          navigating a conversation across languages or cultures.
        </p>
      </GlassCard>
    </article>
  );
}
