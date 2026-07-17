import type { Metadata } from "next";
import Link from "next/link";

export const metadata: Metadata = { title: "Product — ListenUp" };

const products = [
  {
    heading: "Voice-to-Text",
    items: [
      {
        href: "/voice-to-text/general",
        name: "General",
        blurb: "Real-time live captions with multi-speaker separation and a color-coded chat-bubble view.",
      },
      {
        href: "/voice-to-text/enhanced",
        name: "Enhanced",
        blurb: "Higher accuracy in busy settings (up to 4–5 speakers), saved voice profiles that label people by name, and tap-to-correct.",
      },
    ],
  },
  {
    heading: "Translation",
    items: [
      {
        href: "/translate/general",
        name: "General",
        blurb: "Fast text→text and voice→text translation with wide language coverage.",
      },
      {
        href: "/translate/enhanced",
        name: "Enhanced (Cultural)",
        blurb: "Translation plus formality register and slang/idiom notes — meaning, context, and closest equivalent.",
      },
      {
        href: "/translate/genz",
        name: "GenZ Slang",
        blurb: "Modern internet slang, memes, and abbreviations explained, with shareable translation cards.",
      },
    ],
  },
];

export default function ProductPage() {
  return (
    <div className="mx-auto max-w-3xl">
      <h1 className="text-3xl font-bold">Product</h1>
      {products.map((group) => (
        <section key={group.heading} aria-labelledby={group.heading} className="mt-8">
          <h2 id={group.heading} className="text-2xl font-semibold">
            {group.heading}
          </h2>
          <ul className="mt-3 flex flex-col gap-3">
            {group.items.map((item) => (
              <li key={item.href}>
                <Link
                  href={item.href}
                  className="block rounded-lg border border-zinc-200 p-4 hover:border-zinc-400 focus-visible:outline-2 focus-visible:outline-offset-2 dark:border-zinc-800 dark:hover:border-zinc-600"
                >
                  <h3 className="font-semibold">{item.name}</h3>
                  <p className="mt-1 text-sm text-zinc-600 dark:text-zinc-400">{item.blurb}</p>
                </Link>
              </li>
            ))}
          </ul>
        </section>
      ))}
    </div>
  );
}
