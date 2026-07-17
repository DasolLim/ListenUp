"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useState, type ReactNode } from "react";
import { createClient, isSupabaseConfigured } from "@/lib/supabase/client";
import Orb from "@/components/ui/Orb";
import {
  CaptionsIcon,
  CloseIcon,
  CommunityIcon,
  DashboardIcon,
  HistoryIcon,
  LogoutIcon,
  MenuIcon,
  PremiumIcon,
  SavedIcon,
  SharedIcon,
  TranslateIcon,
} from "@/components/shell/icons";

type NavItem = {
  label: string;
  icon: ReactNode;
  href?: string; // absent = not built yet, rendered disabled
};

const general: NavItem[] = [
  { label: "Dashboard", icon: <DashboardIcon />, href: "/dashboard" },
  { label: "Voice-to-Text", icon: <CaptionsIcon />, href: "/voice-to-text" },
  { label: "Translate", icon: <TranslateIcon />, href: "/translate" },
  { label: "Community", icon: <CommunityIcon /> },
  { label: "History", icon: <HistoryIcon /> },
];

const others: NavItem[] = [
  { label: "Premium Access", icon: <PremiumIcon /> },
  { label: "Saved Phrases", icon: <SavedIcon /> },
  { label: "Shared Sessions", icon: <SharedIcon /> },
];

function NavLink({ item, active }: { item: NavItem; active: boolean }) {
  const base = "flex w-full items-center gap-3 rounded-full px-4 py-2.5 text-[15px]";
  if (!item.href) {
    return (
      <span aria-disabled="true" className={`${base} cursor-default text-ink-faint`}>
        {item.icon}
        <span>{item.label}</span>
        <span className="ml-auto rounded-full bg-white/50 px-2 py-0.5 text-[11px] text-ink-faint">
          soon
        </span>
      </span>
    );
  }
  return (
    <Link
      href={item.href}
      aria-current={active ? "page" : undefined}
      className={`${base} font-medium transition-colors ${
        active
          ? "nav-active text-ink shadow-glass"
          : "text-ink-soft hover:bg-white/40 hover:text-ink"
      }`}
    >
      {/* accent-strong: the icon must clear the 3:1 non-text minimum on the white pill */}
      <span className={active ? "text-accent-strong" : ""}>{item.icon}</span>
      <span>{item.label}</span>
    </Link>
  );
}

export default function Sidebar() {
  const pathname = usePathname();
  const router = useRouter();
  const [open, setOpen] = useState(false);

  const isActive = (href: string) =>
    href === "/dashboard" ? pathname === href : pathname.startsWith(href);

  async function handleLogout() {
    if (isSupabaseConfigured()) {
      await createClient().auth.signOut();
    }
    router.push("/");
    router.refresh();
  }

  const nav = (
    <nav aria-label="App navigation" className="flex h-full flex-col gap-6">
      <Link
        href="/"
        className="flex items-center gap-3 px-2 font-display text-[20px] font-bold"
      >
        <Orb size="sm" />
        ListenUp
      </Link>

      <div>
        <p className="px-4 pb-2 text-[11px] font-semibold tracking-[0.12em] text-ink-faint">
          GENERAL
        </p>
        <ul className="flex flex-col gap-1">
          {general.map((item) => (
            <li key={item.label}>
              <NavLink item={item} active={item.href ? isActive(item.href) : false} />
            </li>
          ))}
        </ul>
      </div>

      <div>
        <p className="px-4 pb-2 text-[11px] font-semibold tracking-[0.12em] text-ink-faint">
          OTHERS
        </p>
        <ul className="flex flex-col gap-1">
          {others.map((item) => (
            <li key={item.label}>
              <NavLink item={item} active={false} />
            </li>
          ))}
          <li>
            <button
              type="button"
              onClick={handleLogout}
              className="flex w-full items-center gap-3 rounded-full px-4 py-2.5 text-[15px] font-medium text-ink-soft transition-colors hover:bg-white/40 hover:text-ink"
            >
              <LogoutIcon />
              Log out
            </button>
          </li>
        </ul>
      </div>
    </nav>
  );

  return (
    <>
      {/* Mobile: hamburger + drawer */}
      <button
        type="button"
        onClick={() => setOpen(true)}
        aria-expanded={open}
        aria-label="Open navigation"
        className="btn-ghost fixed left-4 top-4 z-40 flex h-11 w-11 items-center justify-center rounded-full text-ink lg:hidden"
      >
        <MenuIcon />
      </button>
      {open && (
        <div className="fixed inset-0 z-50 lg:hidden">
          <div
            aria-hidden="true"
            onClick={() => setOpen(false)}
            className="absolute inset-0 bg-black/25"
          />
          <div className="glass-card glass-strong absolute bottom-4 left-4 top-4 w-72 overflow-y-auto p-6">
            <button
              type="button"
              onClick={() => setOpen(false)}
              aria-label="Close navigation"
              className="absolute right-4 top-4 flex h-9 w-9 items-center justify-center rounded-full text-ink-soft hover:text-ink"
            >
              <CloseIcon />
            </button>
            {nav}
          </div>
        </div>
      )}

      {/* Desktop: fixed glass panel */}
      <aside className="glass-card sticky top-6 hidden h-[calc(100vh-3rem)] w-64 shrink-0 overflow-y-auto p-6 lg:block">
        {nav}
      </aside>
    </>
  );
}
