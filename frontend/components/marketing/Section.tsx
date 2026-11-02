import { type ReactNode } from "react";
import Reveal from "@/components/shell/Reveal";

/**
 * Marketing section wrapper: one consistent max width (1120px) and vertical
 * rhythm across the whole website, so every page reads as one system.
 * `tone="tint"` drops a soft glass band behind a section for contrast between
 * otherwise-open sections on the gradient. Content fades up on scroll unless
 * `reveal={false}` (used when a tall section reveals its own rows).
 */
export function Section({
  children,
  className = "",
  labelledBy,
  tone = "plain",
  reveal = true,
}: {
  children: ReactNode;
  className?: string;
  labelledBy?: string;
  tone?: "plain" | "tint";
  reveal?: boolean;
}) {
  const container = `mx-auto w-full max-w-6xl px-5 sm:px-8 ${className}`;
  return (
    <section
      aria-labelledby={labelledBy}
      className={
        tone === "tint"
          ? "border-y border-white/40 bg-white/25 py-16 sm:py-20 lg:py-24"
          : "py-16 sm:py-20 lg:py-24"
      }
    >
      {reveal ? (
        <Reveal className={container}>{children}</Reveal>
      ) : (
        <div className={container}>{children}</div>
      )}
    </section>
  );
}

/** Small eyebrow label above a section heading (encodes what the section is). */
export function Eyebrow({ children }: { children: ReactNode }) {
  return (
    <p className="text-[13px] font-semibold uppercase tracking-[0.18em] text-accent-strong">
      {children}
    </p>
  );
}

/** Section heading with optional eyebrow + supporting line, consistent scale. */
export function SectionHeading({
  eyebrow,
  title,
  intro,
  id,
  align = "left",
}: {
  eyebrow?: string;
  title: ReactNode;
  intro?: ReactNode;
  id?: string;
  align?: "left" | "center";
}) {
  return (
    <div className={`flex flex-col gap-3 ${align === "center" ? "items-center text-center" : ""}`}>
      {eyebrow && <Eyebrow>{eyebrow}</Eyebrow>}
      <h2
        id={id}
        className="max-w-2xl font-display text-[26px] font-bold leading-tight tracking-tight sm:text-[32px]"
      >
        {title}
      </h2>
      {intro && (
        <p className="max-w-2xl text-[15px] leading-relaxed text-ink-soft sm:text-base">{intro}</p>
      )}
    </div>
  );
}
