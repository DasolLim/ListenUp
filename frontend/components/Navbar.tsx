"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { CloseIcon, MenuIcon } from "@/components/shell/icons";
import Orb from "@/components/ui/Orb";
import { createClient, isSupabaseConfigured } from "@/lib/supabase/client";

const links = [
  { href: "/", label: "Home" },
  { href: "/product", label: "Product" },
  { href: "/about", label: "About" },
];

export default function Navbar() {
  const pathname = usePathname();
  const router = useRouter();
  const [signedIn, setSignedIn] = useState(false);
  const [open, setOpen] = useState(false);

  useEffect(() => {
    if (!isSupabaseConfigured()) return;
    const supabase = createClient();
    supabase.auth.getClaims().then(({ data }) => setSignedIn(Boolean(data?.claims)));
    const {
      data: { subscription },
    } = supabase.auth.onAuthStateChange((_e, session) => setSignedIn(Boolean(session)));
    return () => subscription.unsubscribe();
  }, []);

  // Close the mobile drawer whenever the route changes (deferred per lint rule).
  useEffect(() => {
    const raf = requestAnimationFrame(() => setOpen(false));
    return () => cancelAnimationFrame(raf);
  }, [pathname]);

  async function logOut() {
    if (isSupabaseConfigured()) await createClient().auth.signOut();
    router.push("/");
    router.refresh();
  }

  const isActive = (href: string) => (href === "/" ? pathname === "/" : pathname.startsWith(href));

  const cta = signedIn ? (
    <Link
      href="/dashboard"
      className="btn-primary rounded-full px-5 py-2 text-[15px] font-semibold text-on-accent transition-transform hover:-translate-y-0.5"
    >
      Open app
    </Link>
  ) : (
    <Link
      href="/login"
      className="btn-primary rounded-full px-5 py-2 text-[15px] font-semibold text-on-accent transition-transform hover:-translate-y-0.5"
    >
      Get started
    </Link>
  );

  return (
    <header className="sticky top-0 z-40 px-4 pt-4">
      <nav
        aria-label="Main"
        className="glass-card glass-strong mx-auto flex max-w-6xl items-center justify-between gap-4 rounded-full py-2.5 pl-5 pr-3"
      >
        <Link
          href="/"
          className="flex items-center gap-2.5 font-display text-[17px] font-bold tracking-tight"
        >
          <Orb size="sm" />
          ListenUp
        </Link>

        {/* Desktop / tablet: inline links + auth + CTA */}
        <div className="hidden items-center gap-1 md:flex">
          <ul className="flex items-center gap-1">
            {links.map((link) => (
              <li key={link.href}>
                <Link
                  href={link.href}
                  aria-current={isActive(link.href) ? "page" : undefined}
                  className={`rounded-full px-3.5 py-1.5 text-[15px] font-medium transition-colors ${
                    isActive(link.href)
                      ? "nav-active text-ink"
                      : "text-ink-soft hover:bg-white/50 hover:text-ink"
                  }`}
                >
                  {link.label}
                </Link>
              </li>
            ))}
          </ul>
          <span className="mx-1 h-5 w-px bg-white/60" aria-hidden="true" />
          {signedIn ? (
            <button
              type="button"
              onClick={logOut}
              className="rounded-full px-3.5 py-1.5 text-[15px] font-medium text-ink-soft transition-colors hover:bg-white/50 hover:text-ink"
            >
              Log out
            </button>
          ) : (
            <Link
              href="/login"
              className="rounded-full px-3.5 py-1.5 text-[15px] font-medium text-ink-soft transition-colors hover:bg-white/50 hover:text-ink"
            >
              Log in
            </Link>
          )}
          {cta}
        </div>

        {/* Mobile: hamburger */}
        <button
          type="button"
          onClick={() => setOpen(true)}
          aria-expanded={open}
          aria-label="Open menu"
          className="btn-ghost flex h-10 w-10 items-center justify-center rounded-full text-ink md:hidden"
        >
          <MenuIcon />
        </button>
      </nav>

      {/* Mobile drawer */}
      {open && (
        <div className="fixed inset-0 z-50 md:hidden">
          <div
            aria-hidden="true"
            onClick={() => setOpen(false)}
            className="absolute inset-0 bg-black/25"
          />
          <div className="glass-card glass-strong absolute inset-x-4 top-4 flex flex-col gap-2 p-5">
            <div className="flex items-center justify-between">
              <span className="flex items-center gap-2.5 font-display text-[17px] font-bold">
                <Orb size="sm" />
                ListenUp
              </span>
              <button
                type="button"
                onClick={() => setOpen(false)}
                aria-label="Close menu"
                className="flex h-10 w-10 items-center justify-center rounded-full text-ink-soft hover:text-ink"
              >
                <CloseIcon />
              </button>
            </div>
            <ul className="mt-2 flex flex-col gap-1">
              {links.map((link) => (
                <li key={link.href}>
                  <Link
                    href={link.href}
                    aria-current={isActive(link.href) ? "page" : undefined}
                    className={`block rounded-2xl px-4 py-3 text-[17px] font-medium transition-colors ${
                      isActive(link.href) ? "nav-active text-ink" : "text-ink hover:bg-white/50"
                    }`}
                  >
                    {link.label}
                  </Link>
                </li>
              ))}
            </ul>
            <div className="mt-2 flex flex-col gap-2">
              {cta}
              {signedIn ? (
                <button
                  type="button"
                  onClick={logOut}
                  className="btn-ghost rounded-full px-5 py-2.5 text-[15px] font-medium text-ink"
                >
                  Log out
                </button>
              ) : (
                <Link
                  href="/login"
                  className="btn-ghost rounded-full px-5 py-2.5 text-center text-[15px] font-medium text-ink"
                >
                  Log in
                </Link>
              )}
            </div>
          </div>
        </div>
      )}
    </header>
  );
}
