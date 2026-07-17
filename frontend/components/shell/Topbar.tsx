"use client";

import { usePathname } from "next/navigation";
import { BellIcon, SearchIcon, UserIcon } from "@/components/shell/icons";
import IconButton from "@/components/ui/IconButton";

const titles: [string, string][] = [
  ["/dashboard", "Dashboard"],
  ["/voice-to-text/general", "Live Captions"],
  ["/voice-to-text/enhanced", "Enhanced Captions"],
  ["/voice-to-text", "Voice-to-Text"],
  ["/translate/general", "Translate"],
  ["/translate/enhanced", "Cultural Translation"],
  ["/translate/genz", "GenZ Slang"],
  ["/translate", "Translate"],
];

export default function Topbar() {
  const pathname = usePathname();
  const title = titles.find(([prefix]) => pathname.startsWith(prefix))?.[1] ?? "ListenUp";

  return (
    <header className="flex items-center justify-between gap-4 pl-14 lg:pl-0">
      <h1 className="font-display text-[28px] font-bold sm:text-[34px]">{title}</h1>
      <div className="flex items-center gap-2">
        <label htmlFor="app-search" className="sr-only">
          Search
        </label>
        <div className="btn-ghost hidden items-center gap-2 rounded-full px-4 py-2 text-ink-soft sm:flex">
          <SearchIcon />
          <input
            id="app-search"
            type="search"
            placeholder="Search…"
            className="w-36 bg-transparent text-sm text-ink outline-none placeholder:text-ink-faint"
          />
        </div>
        <IconButton label="Notifications">
          <BellIcon />
        </IconButton>
        <IconButton label="Account">
          <UserIcon />
        </IconButton>
      </div>
    </header>
  );
}
