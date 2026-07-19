import type { Metadata } from "next";
import Link from "next/link";
import { Eyebrow, Section, SectionHeading } from "@/components/marketing/Section";

export const metadata: Metadata = { title: "About — ListenUp" };

const audiences = [
  {
    title: "Deaf and hard-of-hearing people",
    body: "The primary users. Follow a group conversation and know who is speaking, without straining to lip-read or guessing from a wall of text.",
  },
  {
    title: "Travelers and immigrants",
    body: "Hear a room in your own language, with the slang and tone that word-for-word translation drops.",
  },
  {
    title: "Anyone in a mixed-language room",
    body: "Family dinners, classrooms, and meetings where more than one language is in the air at once.",
  },
];

export default function AboutPage() {
  return (
    <>
      <section className="mx-auto w-full max-w-6xl px-5 pt-12 sm:px-8 sm:pt-16">
        <div className="flex max-w-2xl flex-col gap-4">
          <Eyebrow>About</Eyebrow>
          <h1 className="font-display text-[34px] font-extrabold leading-tight tracking-tight sm:text-[44px]">
            Conversation should include everyone.
          </h1>
          <p className="text-lg leading-relaxed text-ink-soft">
            Existing captions tell you the words but not the speaker. Existing translators tell you
            the words but not the meaning. ListenUp was built to fix both, for the people who feel
            those gaps most.
          </p>
        </div>
      </section>

      <Section tone="tint" labelledBy="mission-heading">
        <SectionHeading
          id="mission-heading"
          eyebrow="Our mission"
          title="Keep the parts of a conversation that carry meaning"
          intro="Who said it, and what they actually meant. Those are the two things a flattened transcript loses, and the two things we protect."
        />
        <div className="mt-8 grid gap-5 md:grid-cols-2">
          <div className="glass-card flex flex-col gap-2 p-7">
            <p className="font-display text-[19px] font-semibold">Accessible by default</p>
            <p className="leading-relaxed text-ink-soft">
              Full keyboard control, screen-reader support, a high-contrast mode, and caption text
              that scales on its own. Accessibility is a build requirement here, not a setting we
              added later.
            </p>
          </div>
          <div className="glass-card flex flex-col gap-2 p-7">
            <p className="font-display text-[19px] font-semibold">Private with voices</p>
            <p className="leading-relaxed text-ink-soft">
              A voice profile is biometric data. We take consent from the enrolled person, store a
              math signature rather than audio, and let anyone delete or export their data at any
              time.
            </p>
          </div>
        </div>
      </Section>

      <Section labelledBy="who-heading">
        <SectionHeading id="who-heading" eyebrow="Who it's for" title="Built for real rooms" />
        <div className="mt-8 grid gap-5 md:grid-cols-3">
          {audiences.map((audience) => (
            <div key={audience.title} className="glass-card flex flex-col gap-2 p-7">
              <p className="font-display text-[18px] font-semibold">{audience.title}</p>
              <p className="text-sm leading-relaxed text-ink-soft">{audience.body}</p>
            </div>
          ))}
        </div>
      </Section>

      <Section tone="tint" labelledBy="about-cta">
        <div className="flex flex-col items-center gap-5 text-center">
          <h2 id="about-cta" className="font-display text-[26px] font-bold tracking-tight sm:text-[32px]">
            See it work for yourself
          </h2>
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
