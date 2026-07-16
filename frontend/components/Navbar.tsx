import Link from "next/link";
import AuthButton from "@/components/AuthButton";

const navLinks = [
  { href: "/", label: "Home" },
  { href: "/about", label: "About" },
  { href: "/product", label: "Product" },
];

export default function Navbar() {
  return (
    <header className="border-b border-zinc-200 dark:border-zinc-800">
      <nav
        aria-label="Main navigation"
        className="mx-auto flex max-w-5xl items-center justify-between gap-4 px-4 py-3"
      >
        <Link href="/" className="text-lg font-bold focus-visible:outline-2 focus-visible:outline-offset-2">
          ListenUp
        </Link>
        <ul className="flex items-center gap-6">
          {navLinks.map((link) => (
            <li key={link.href}>
              <Link
                href={link.href}
                className="rounded px-1 py-0.5 hover:underline focus-visible:outline-2 focus-visible:outline-offset-2"
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
