import Link from "next/link";
import Orb from "@/components/ui/Orb";

const features = [
  {
    href: "/voice-to-text/general",
    title: "Live Captions",
    description: "Real-time captions with multi-speaker separation — see who said what.",
  },
  {
    href: "/voice-to-text/enhanced",
    title: "Enhanced Captions",
    description: "Saved voice profiles label friends and family by name, not “Speaker 1”.",
  },
  {
    href: "/translate/general",
    title: "Translate",
    description: "Fast text and voice translation across a wide range of languages.",
  },
  {
    href: "/translate/enhanced",
    title: "Cultural Translation",
    description: "Translation plus register, slang, and cultural nuance — meaning, not just words.",
  },
  {
    href: "/translate/genz",
    title: "GenZ Slang",
    description: "Modern internet slang, memes, and abbreviations, explained.",
  },
];

export default function Home() {
  return (
    <div className="flex flex-col gap-14">
      <section className="flex flex-col items-center gap-6 pt-12 text-center">
        <Orb size="lg" />
        <h1 className="max-w-3xl font-display text-[38px] font-extrabold leading-tight tracking-tight sm:text-[44px]">
          Captions that know who&apos;s talking.
        </h1>
        <p className="max-w-2xl text-lg leading-relaxed text-ink-soft">
          ListenUp makes spoken conversation accessible and culturally understandable — live
          speaker-named captions for deaf and hard-of-hearing users, and translation that carries
          meaning, tone, and slang, not just words.
        </p>
        <Link
          href="/login"
          className="btn-primary rounded-full px-7 py-3 font-semibold text-on-accent transition-transform hover:-translate-y-0.5"
        >
          Get started
        </Link>
      </section>

      <section aria-labelledby="features-heading">
        <h2 id="features-heading" className="font-display text-[22px] font-semibold">
          Features
        </h2>
        <ul className="mt-5 grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
          {features.map((feature) => (
            <li key={feature.href}>
              <Link
                href={feature.href}
                className="glass-card block h-full p-6 transition-transform hover:-translate-y-0.5"
              >
                <h3 className="font-display text-[17px] font-semibold">{feature.title}</h3>
                <p className="mt-2 text-sm leading-relaxed text-ink-soft">{feature.description}</p>
              </Link>
            </li>
          ))}
        </ul>
      </section>
    </div>
  );
}
