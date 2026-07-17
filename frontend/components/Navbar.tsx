import Link from "next/link";
import AuthButton from "@/components/AuthButton";
import Orb from "@/components/ui/Orb";

const navLinks = [
  { href: "/", label: "Home" },
  { href: "/about", label: "About" },
  { href: "/product", label: "Product" },
];

export default function Navbar() {
  return (
    <header className="sticky top-0 z-30 px-4 pt-4">
      <nav
        aria-label="Main navigation"
        className="glass-card glass-strong mx-auto flex max-w-5xl items-center justify-between gap-4 rounded-full px-5 py-2.5"
      >
        <Link href="/" className="flex items-center gap-2.5 font-display text-[17px] font-bold">
          <Orb size="sm" />
          ListenUp
        </Link>
        <ul className="flex items-center gap-1 sm:gap-2">
          {navLinks.map((link) => (
            <li key={link.href}>
              <Link
                href={link.href}
                className="rounded-full px-3 py-1.5 text-[15px] font-medium text-ink-soft transition-colors hover:bg-white/50 hover:text-ink"
              >
                {link.label}
              </Link>
            </li>
          ))}
          <li>
            <AuthButton />
          </li>
        </ul>
      </nav>
    </header>
  );
}
