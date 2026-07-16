import Link from "next/link";

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
            <Link
              href="/login"
              aria-label="Log in or register"
              className="flex items-center gap-1.5 rounded-full border border-zinc-300 px-3 py-1.5 hover:bg-zinc-100 focus-visible:outline-2 focus-visible:outline-offset-2 dark:border-zinc-700 dark:hover:bg-zinc-900"
            >
              <svg aria-hidden="true" width="16" height="16" viewBox="0 0 24 24" fill="currentColor">
                <path d="M12 12a5 5 0 1 0-5-5 5 5 0 0 0 5 5Zm0 2c-3.34 0-10 1.67-10 5v3h20v-3c0-3.33-6.66-5-10-5Z" />
              </svg>
              <span>Log in</span>
            </Link>
          </li>
        </ul>
      </nav>
    </header>
  );
}
