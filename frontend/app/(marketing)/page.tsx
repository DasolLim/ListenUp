import Link from "next/link";
import HeroDemo from "@/components/marketing/HeroDemo";
import { Eyebrow, Section, SectionHeading } from "@/components/marketing/Section";
import Orb from "@/components/ui/Orb";

// ── Small on-brand visuals for the walkthrough rows (real product output) ──

function Bubble({
  name,
  tint,
  children,
  tag,
}: {
  name: string;
  tint: string;
  children: React.ReactNode;
  tag?: string;
}) {
  return (
    <div className="bubble-glass rounded-2xl px-4 py-2.5" style={{ backgroundColor: tint }}>
      <p className="text-[11px] font-semibold uppercase tracking-wide text-ink-soft">
        {name}
        {tag && <span className="ml-1 text-ink-faint">{tag}</span>}
      </p>
      <p className="mt-0.5 text-[15px] leading-snug text-ink">{children}</p>
    </div>
  );
}

function NamedVisual() {
  return (
    <div className="glass-card glass-strong flex w-full flex-col gap-2.5 p-5">
      <Bubble name="Mom" tint="var(--speaker-1)">
        Come earlier if you want to help cook.
      </Bubble>
      <Bubble name="Dad" tint="var(--speaker-2)">
        I&apos;ll be there by five.
      </Bubble>
    </div>
  );
}

function TranslatedVisual() {
  return (
    <div className="glass-card glass-strong flex w-full flex-col gap-2.5 p-5">
      <Bubble name="Léa" tag="(FR)" tint="var(--speaker-3)">
        C&apos;est pas ouf, franchement.
      </Bubble>
      <p className="px-1 text-[13px] text-ink-soft">
        <span className="font-medium text-ink">Honestly, it&apos;s nothing special.</span>{" "}
        <span className="rounded-full bg-white/60 px-2 py-0.5 text-[12px] text-ink-soft">
          slang: “ouf” = amazing (verlan)
        </span>
      </p>
    </div>
  );
}

function ComboVisual() {
  return (
    <div className="glass-card glass-strong flex w-full flex-col gap-2.5 p-5">
      <Bubble name="Min-jun" tag="(KO)" tint="var(--speaker-4)">
        저녁 준비는 제가 할게요. → I&apos;ll get dinner ready.
      </Bubble>
      <Bubble name="Sarah" tag="(EN)" tint="var(--speaker-1)">
        Thanks, that&apos;s so kind of you.
      </Bubble>
    </div>
  );
}

const pillars = [
  {
    eyebrow: "Speaker-named captions",
    title: "Everyone gets their own name",
    body: "Enroll the people you talk with most. Their names sit on every line they say, in their own color. No more guessing who “Speaker 1” was.",
    href: "/voice-to-text/enhanced",
    cta: "Set up voice profiles",
    visual: <NamedVisual />,
  },
  {
    eyebrow: "Cultural translation",
    title: "Meaning, not word-for-word",
    body: "Translation that carries register and slang. Each line comes with the plain meaning, the cultural context, and the closest equivalent in your language.",
    href: "/translate/enhanced",
    cta: "Try cultural translation",
    visual: <TranslatedVisual />,
  },
  {
    eyebrow: "The combination",
    title: "Named, translated, live",
    body: "The part no other tool does: multi-speaker, multi-language captions in real time. A deaf Korean speaker sees each English voice translated to Korean, labeled by person, as it happens.",
    href: "/voice-to-text/enhanced",
    cta: "See it live",
    visual: <ComboVisual />,
  },
];

const steps = [
  {
    title: "Enroll a voice",
    body: "Record about 20 seconds of someone speaking, with their consent. ListenUp learns to recognize them and never stores the audio.",
  },
  {
    title: "Start captioning",
    body: "Open the mic. Every speaker gets their own colored bubble in real time, up to four people plus everyone else.",
  },
  {
    title: "Read names and meaning",
    body: "Enrolled people show up by name. Turn on translation and each line also arrives in the language you chose.",
  },
];

export default function Home() {
  return (
    <>
      {/* Hero: copy + a live demo of the actual product output */}
      <section className="mx-auto grid w-full max-w-6xl items-center gap-10 px-5 pb-8 pt-12 sm:px-8 sm:pt-16 lg:grid-cols-[1.05fr_0.95fr] lg:gap-12 lg:pb-16 lg:pt-20">
        <div className="flex flex-col gap-6">
          <Eyebrow>Accessible conversation</Eyebrow>
          <h1 className="font-display text-[38px] font-extrabold leading-[1.05] tracking-tight sm:text-[52px]">
            Captions that know who&apos;s talking.
          </h1>
          <p className="max-w-xl text-lg leading-relaxed text-ink-soft">
            ListenUp gives deaf and hard-of-hearing people live captions labeled by person, and
            translation that keeps slang and tone. See who said what, and what they really meant.
          </p>
          <div className="flex flex-wrap items-center gap-3">
            <Link
              href="/login"
              className="btn-primary rounded-full px-7 py-3 font-semibold text-on-accent transition-transform hover:-translate-y-0.5"
            >
              Get started
            </Link>
            <Link
              href="/product"
              className="btn-ghost rounded-full px-7 py-3 font-medium text-ink transition-transform hover:-translate-y-0.5"
            >
              See the product
            </Link>
          </div>
          <p className="text-[13px] text-ink-faint">
            No audio stored by default. Voice profiles need the enrolled person&apos;s consent.
          </p>
        </div>
        <div className="flex justify-center lg:justify-end">
          <HeroDemo />
        </div>
      </section>

      {/* The problem: a deliberate two-panel contrast, not a card grid */}
      <Section tone="tint" labelledBy="problem-heading">
        <SectionHeading
          id="problem-heading"
          eyebrow="The problem"
          title="Two things every other tool gets wrong"
          intro="Captioning and translation both flatten a conversation. ListenUp keeps the parts that carry meaning."
        />
        <div className="mt-10 grid gap-5 md:grid-cols-2">
          <div className="glass-card flex flex-col gap-2 p-7">
            <p className="font-display text-[19px] font-semibold">A wall of text</p>
            <p className="leading-relaxed text-ink-soft">
              Ordinary captions dump every voice into one column. In a group, you lose track of who
              said what within seconds.
            </p>
          </div>
          <div className="glass-card flex flex-col gap-2 p-7">
            <p className="font-display text-[19px] font-semibold">Words, not meaning</p>
            <p className="leading-relaxed text-ink-soft">
              Ordinary translators swap words one for one. Slang, register, and culture fall
              straight through the gaps.
            </p>
          </div>
        </div>
      </Section>

      {/* The moat: alternating walkthrough rows (avoids identical cards) */}
      <Section labelledBy="why-heading">
        <SectionHeading
          id="why-heading"
          eyebrow="Why ListenUp"
          title="Built around who is speaking"
          intro="Three things that only work when captions understand people, not just audio."
        />
        <div className="mt-12 flex flex-col gap-14 lg:gap-20">
          {pillars.map((pillar, i) => (
            <div
              key={pillar.title}
              className="grid items-center gap-6 lg:grid-cols-2 lg:gap-12"
            >
              <div className={`flex flex-col gap-3 ${i % 2 === 1 ? "lg:order-2" : ""}`}>
                <Eyebrow>{pillar.eyebrow}</Eyebrow>
                <h3 className="font-display text-[24px] font-bold tracking-tight sm:text-[28px]">
                  {pillar.title}
                </h3>
                <p className="max-w-md leading-relaxed text-ink-soft">{pillar.body}</p>
                <Link
                  href={pillar.href}
                  className="mt-1 inline-flex w-fit items-center gap-1.5 font-medium text-accent-strong hover:underline"
                >
                  {pillar.cta}
                  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                    <path d="M5 12h14M13 6l6 6-6 6" />
                  </svg>
                </Link>
              </div>
              <div className={i % 2 === 1 ? "lg:order-1" : ""}>{pillar.visual}</div>
            </div>
          ))}
        </div>
      </Section>

      {/* How it works: a genuine ordered sequence, so numbers earn their place */}
      <Section tone="tint" labelledBy="how-heading">
        <SectionHeading
          id="how-heading"
          eyebrow="How it works"
          title="Three steps to named captions"
        />
        <ol className="mt-10 grid gap-5 md:grid-cols-3">
          {steps.map((step, i) => (
            <li key={step.title} className="glass-card flex flex-col gap-3 p-7">
              <span className="flex h-10 w-10 items-center justify-center rounded-full bg-accent-strong font-display text-[17px] font-bold text-on-accent">
                {i + 1}
              </span>
              <p className="font-display text-[19px] font-semibold">{step.title}</p>
              <p className="leading-relaxed text-ink-soft">{step.body}</p>
            </li>
          ))}
        </ol>
      </Section>

      {/* Closing CTA */}
      <Section labelledBy="cta-heading">
        <div className="glass-card glass-strong flex flex-col items-center gap-6 px-6 py-14 text-center">
          <Orb size="lg" />
          <h2
            id="cta-heading"
            className="max-w-xl font-display text-[28px] font-bold tracking-tight sm:text-[34px]"
          >
            Ready to see who&apos;s talking?
          </h2>
          <p className="max-w-md leading-relaxed text-ink-soft">
            Start with live captions in your browser. Add voice profiles and translation whenever
            you want them.
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
