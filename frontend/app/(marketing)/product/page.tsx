import type { Metadata } from "next";
import Link from "next/link";
import { Eyebrow, Section, SectionHeading } from "@/components/marketing/Section";

export const metadata: Metadata = { title: "Product — ListenUp" };

type Feature = {
  href: string;
  name: string;
  blurb: string;
  wash: string;
};

const families: { key: string; heading: string; intro: string; features: Feature[] }[] = [
  {
    key: "conversation",
    heading: "In conversation",
    intro: "The two things ListenUp does while people are talking.",
    features: [
      {
        href: "/captions",
        name: "Captions",
        blurb:
          "Real-time captions that separate speakers into colour-coded bubbles. Enrol the people you talk with and they appear by name instead of “Speaker 1”.",
        wash: "tile-wash-peach",
      },
      {
        href: "/translate",
        name: "Translate",
        blurb:
          "English ↔ Korean by text or voice. The fast translation lands immediately; register and slang notes follow a moment later.",
        wash: "tile-wash-sage",
      },
    ],
  },
  {
    key: "look-up",
    heading: "Look something up",
    intro: "For a phrase you heard and didn’t recognise.",
    features: [
      {
        href: "/explain",
        name: "Explain a term",
        blurb:
          "Internet slang, memes, and abbreviations decoded into plain language, with shareable cards.",
        wash: "tile-wash-lilac",
      },
    ],
  },
];

export default function ProductPage() {
  return (
    <>
      <section className="mx-auto w-full max-w-6xl px-5 pt-12 sm:px-8 sm:pt-16">
        <div className="flex max-w-2xl flex-col gap-4">
          <Eyebrow>Product</Eyebrow>
          <h1 className="font-display text-[34px] font-extrabold leading-tight tracking-tight sm:text-[44px]">
            Two products, one conversation.
          </h1>
          <p className="text-lg leading-relaxed text-ink-soft">
            Voice-to-Text names who is speaking. Translation carries what they mean. Use either on
            its own, or together for speaker-named captions in your language.
          </p>
        </div>
      </section>

      {families.map((family, index) => (
        <Section key={family.key} tone={index % 2 === 1 ? "tint" : "plain"} labelledBy={family.key}>
          <SectionHeading id={family.key} title={family.heading} intro={family.intro} />
          <div className="mt-8 grid gap-5 sm:grid-cols-2">
            {family.features.map((feature) => (
              <Link
                key={feature.href}
                href={feature.href}
                className="group glass-card flex flex-col overflow-hidden transition-transform hover:-translate-y-0.5"
              >
                <span aria-hidden="true" className={`h-24 w-full ${feature.wash}`} />
                <span className="flex flex-1 flex-col gap-2 p-6">
                  <span className="flex items-center gap-2 font-display text-[19px] font-semibold">
                    {feature.name}
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
                  </span>
                  <span className="text-sm leading-relaxed text-ink-soft">{feature.blurb}</span>
                </span>
              </Link>
            ))}
          </div>
        </Section>
      ))}

      <Section labelledBy="product-cta">
        <div className="glass-card glass-strong flex flex-col items-center gap-5 px-6 py-12 text-center">
          <h2
            id="product-cta"
            className="font-display text-[26px] font-bold tracking-tight sm:text-[32px]"
          >
            Start with live captions
          </h2>
          <p className="max-w-md leading-relaxed text-ink-soft">
            Everything runs in your browser. Add voice profiles and translation whenever you need
            them.
          </p>
          <Link
            href="/login"
            className="btn-primary rounded-full px-8 py-3 font-semibold text-on-accent transition-transform hover:-translate-y-0.5"
          >
            Get started
          </Link>
        </div>
      </Section>
    </>
  );
}
