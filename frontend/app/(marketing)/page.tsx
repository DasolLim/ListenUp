import Link from "next/link";

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
    <div className="flex flex-col gap-12">
      <section className="pt-8 text-center">
        <h1 className="text-4xl font-bold tracking-tight">
          Captions that know who&apos;s talking.
        </h1>
        <p className="mx-auto mt-4 max-w-2xl text-lg text-zinc-600 dark:text-zinc-300">
          ListenUp makes spoken conversation accessible and culturally understandable — live
          speaker-named captions for deaf and hard-of-hearing users, and translation that carries
          meaning, tone, and slang, not just words.
        </p>
      </section>

      <section aria-labelledby="features-heading">
        <h2 id="features-heading" className="text-2xl font-semibold">
          Features
        </h2>
        <ul className="mt-4 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {features.map((feature) => (
            <li key={feature.href}>
              <Link
                href={feature.href}
                className="block h-full rounded-lg border border-zinc-200 p-4 hover:border-zinc-400 focus-visible:outline-2 focus-visible:outline-offset-2 dark:border-zinc-800 dark:hover:border-zinc-600"
              >
                <h3 className="font-semibold">{feature.title}</h3>
                <p className="mt-1 text-sm text-zinc-600 dark:text-zinc-400">
                  {feature.description}
                </p>
              </Link>
            </li>
          ))}
        </ul>
      </section>
    </div>
  );
}
