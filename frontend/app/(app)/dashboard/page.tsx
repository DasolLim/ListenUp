import type { Metadata } from "next";
import Link from "next/link";
import ImageTile from "@/components/ui/ImageTile";

export const metadata: Metadata = { title: "Dashboard — ListenUp" };

const modes = [
  { label: "Live", href: "/voice-to-text/general" },
  { label: "Enhanced", href: "/voice-to-text/enhanced" },
  { label: "Cultural", href: "/translate/enhanced" },
  { label: "GenZ", href: "/translate/genz" },
];

export default function DashboardPage() {
  return (
    <div className="grid gap-6 xl:grid-cols-[1fr_360px]">
      {/* Center: feature tiles */}
      <div className="flex min-w-0 flex-col gap-6">
        <section aria-label="Your tools" className="grid grid-cols-2 gap-5">
          <ImageTile
            href="/voice-to-text/general"
            label="Voice-to-Text"
            sublabel="Live captions that name the speaker"
            wash="peach"
            className="col-span-2 h-64 sm:col-span-1 sm:row-span-2 sm:h-auto sm:min-h-105"
          />
          <ImageTile
            href="/translate/general"
            label="Translate"
            sublabel="90+ languages, meaning included"
            wash="sage"
            className="h-50"
          />
          <ImageTile
            href="/translate/genz"
            label="GenZ"
            sublabel="Slang, decoded"
            wash="lilac"
            className="h-50"
          />
        </section>

        <section aria-labelledby="recommended-heading" className="flex flex-col gap-4">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <h2 id="recommended-heading" className="font-display text-[18px] font-semibold">
              Recommended
            </h2>
            <ul aria-label="Caption and translation modes" className="flex flex-wrap gap-2">
              {modes.map((mode, i) => (
                <li key={mode.label}>
                  <Link
                    href={mode.href}
                    className={`inline-block rounded-full px-4 py-1.5 text-sm font-medium transition-colors ${
                      i === 0
                        ? "pill-active text-ink shadow-glass"
                        : "pill-inactive text-ink-soft hover:text-ink"
                    }`}
                  >
                    {mode.label}
                  </Link>
                </li>
              ))}
            </ul>
          </div>
          <div className="grid grid-cols-1 gap-5 sm:grid-cols-2">
            <ImageTile
              href="/voice-to-text/enhanced"
              label="My Sessions"
              sublabel="Saved transcripts and voice profiles"
              wash="amber"
              className="h-44"
            />
            <ImageTile
              href="/translate/enhanced"
              label="Cultural Translation"
              sublabel="Register, idioms, and context"
              wash="lilac"
              className="h-44"
            />
          </div>
        </section>
      </div>

      {/* Right rail: caption/assistant panel lands in Step 1.5.5 */}
      <aside aria-label="Assistant" className="hidden xl:block" />
    </div>
  );
}
