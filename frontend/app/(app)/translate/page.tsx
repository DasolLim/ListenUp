import type { Metadata } from "next";
import Link from "next/link";
import GlassCard from "@/components/ui/GlassCard";

export const metadata: Metadata = { title: "Translate — ListenUp" };

export default function TranslatePage() {
  return (
    <GlassCard strong className="max-w-2xl p-7">
      <h2 className="font-display text-[22px] font-semibold">Meaning, not just words</h2>
      <p className="mt-3 text-ink-soft">
        Translation that carries register, slang, and cultural nuance.
      </p>
      <ul className="mt-6 flex flex-col gap-3">
        <li>
          <Link
            href="/translate/general"
            className="text-ink underline underline-offset-4 hover:text-accent-strong"
          >
            General — fast translation, wide language coverage
          </Link>
        </li>
        <li>
          <Link
            href="/translate/enhanced"
            className="text-ink underline underline-offset-4 hover:text-accent-strong"
          >
            Enhanced — cultural translation with register and slang notes
          </Link>
        </li>
        <li>
          <Link
            href="/translate/genz"
            className="text-ink underline underline-offset-4 hover:text-accent-strong"
          >
            GenZ — internet slang and memes, explained
          </Link>
        </li>
      </ul>
    </GlassCard>
  );
}
