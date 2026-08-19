import type { ReactNode } from "react";

/**
 * Shared shell for the privacy policy and terms.
 *
 * Legal text is long-form reading, so it gets a narrower measure than the
 * marketing pages (~68 characters) and more line height. Headings stay in the
 * display face so the pages still read as part of the product rather than as a
 * PDF someone pasted in.
 */
export default function LegalPage({
  title,
  updated,
  summary,
  children,
}: {
  title: string;
  /** ISO date. Rendered plainly — a policy with no date is not a policy. */
  updated: string;
  summary: ReactNode;
  children: ReactNode;
}) {
  return (
    <section className="mx-auto w-full max-w-3xl px-5 py-12 sm:px-8 sm:py-16">
      <h1 className="font-display text-[32px] font-extrabold leading-tight tracking-tight text-ink sm:text-[40px]">
        {title}
      </h1>
      <p className="mt-3 text-sm text-ink-soft">
        Last updated <time dateTime={updated}>{updated}</time>
      </p>
      <div className="glass mt-8 rounded-2xl p-5 sm:p-6">
        <p className="text-[15px] leading-relaxed text-ink">{summary}</p>
      </div>
      <div className="mt-10 flex flex-col gap-8 text-[15px] leading-relaxed text-ink-soft">
        {children}
      </div>
    </section>
  );
}

export function LegalSection({ heading, children }: { heading: string; children: ReactNode }) {
  return (
    <section className="flex flex-col gap-3">
      <h2 className="font-display text-[20px] font-semibold text-ink">{heading}</h2>
      {children}
    </section>
  );
}
