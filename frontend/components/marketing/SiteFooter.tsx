import Link from "next/link";
import Orb from "@/components/ui/Orb";

const columns = [
  {
    heading: "Product",
    links: [
      { href: "/voice-to-text/general", label: "Live captions" },
      { href: "/voice-to-text/enhanced", label: "Voice profiles" },
      { href: "/translate/general", label: "Translate" },
      { href: "/translate/genz", label: "GenZ slang" },
    ],
  },
  {
    heading: "Company",
    links: [
      { href: "/about", label: "About" },
      { href: "/product", label: "Product overview" },
      { href: "/login", label: "Log in" },
    ],
  },
];

export default function SiteFooter() {
  return (
    <footer className="mt-8 border-t border-white/40 bg-white/25">
      <div className="mx-auto grid w-full max-w-6xl gap-10 px-5 py-14 sm:px-8 md:grid-cols-[1.4fr_1fr_1fr]">
        <div className="flex flex-col gap-3">
          <Link href="/" className="inline-flex min-h-11 items-center gap-2.5 font-display text-[17px] font-bold">
            <Orb size="sm" />
            ListenUp
          </Link>
          <p className="max-w-xs text-sm leading-relaxed text-ink-soft">
            Speaker-named live captions and cultural translation. Built for deaf and hard-of-hearing
            people first, useful to anyone across a language.
          </p>
          <p className="text-[13px] text-ink-faint">
            Voice profiles are biometric data: consent-gated, deletable, and exportable anytime.
          </p>
        </div>
        {columns.map((column) => (
          <nav key={column.heading} aria-label={column.heading} className="flex flex-col gap-3">
            <p className="text-[13px] font-semibold uppercase tracking-[0.14em] text-ink-faint">
              {column.heading}
            </p>
            {/* min-h-11 makes each link a real touch target (they rendered at
                17px tall); the negative margin keeps the footer's rhythm. */}
            <ul className="-my-1.5 flex flex-col">
              {column.links.map((link) => (
                <li key={link.href}>
                  <Link
                    href={link.href}
                    className="inline-flex min-h-11 items-center text-sm text-ink-soft transition-colors hover:text-ink"
                  >
                    {link.label}
                  </Link>
                </li>
              ))}
            </ul>
          </nav>
        ))}
      </div>
      <div className="border-t border-white/40">
        <p className="mx-auto w-full max-w-6xl px-5 py-5 text-[13px] text-ink-faint sm:px-8">
          © {new Date().getFullYear()} ListenUp. WCAG 2.1 AA throughout.
        </p>
      </div>
    </footer>
  );
}
