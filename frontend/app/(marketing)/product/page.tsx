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
        blurb:
          "Real-time live captions with multi-speaker separation and a color-coded chat-bubble view.",
      },
      {
        href: "/voice-to-text/enhanced",
        name: "Enhanced",
        blurb:
          "Higher accuracy in busy settings (up to 4–5 speakers), saved voice profiles that label people by name, and tap-to-correct.",
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
        blurb:
          "Translation plus formality register and slang/idiom notes — meaning, context, and closest equivalent.",
      },
      {
        href: "/translate/genz",
        name: "GenZ Slang",
        blurb:
          "Modern internet slang, memes, and abbreviations explained, with shareable translation cards.",
      },
    ],
  },
];

export default function ProductPage() {
  return (
    <div className="mx-auto max-w-3xl pt-8">
      <h1 className="font-display text-[34px] font-bold">Product</h1>
      {products.map((group) => (
        <section key={group.heading} aria-labelledby={group.heading} className="mt-8">
          <h2 id={group.heading} className="font-display text-[22px] font-semibold">
            {group.heading}
          </h2>
          <ul className="mt-4 flex flex-col gap-4">
            {group.items.map((item) => (
              <li key={item.href}>
                <Link
                  href={item.href}
                  className="glass-card block p-6 transition-transform hover:-translate-y-0.5"
                >
                  <h3 className="font-display text-[17px] font-semibold">{item.name}</h3>
                  <p className="mt-1.5 text-sm leading-relaxed text-ink-soft">{item.blurb}</p>
                </Link>
              </li>
            ))}
          </ul>
        </section>
      ))}
    </div>
  );
}
