import Link from "next/link";
import { type ReactNode } from "react";

export type TileWash = "peach" | "sage" | "lilac" | "amber";

const washes: Record<TileWash, string> = {
  peach: "tile-wash-peach",
  sage: "tile-wash-sage",
  lilac: "tile-wash-lilac",
  amber: "tile-wash-amber",
};

/**
 * Meditation-style tile: soft blurred gradient wash, label bottom-left,
 * action bottom-right. A scrim keeps the label AA-legible on the imagery.
 */
export default function ImageTile({
  href,
  label,
  sublabel,
  wash,
  className = "",
  action,
}: {
  href: string;
  label: string;
  sublabel?: string;
  wash: TileWash;
  className?: string;
  action?: ReactNode;
}) {
  return (
    <Link
      href={href}
      className={`group relative block overflow-hidden rounded-(--radius-tile) border border-white/60 shadow-glass transition-transform hover:-translate-y-0.5 ${washes[wash]} ${className}`}
    >
      <span aria-hidden="true" className="tile-scrim absolute inset-x-0 bottom-0 h-2/3" />
      <span className="absolute bottom-4 left-5 right-14">
        <span className="block font-display text-[22px] font-semibold text-ink">{label}</span>
        {sublabel && <span className="mt-0.5 block text-[13px] text-ink-soft">{sublabel}</span>}
      </span>
      <span
        aria-hidden="true"
        className="absolute bottom-4 right-4 flex h-9 w-9 items-center justify-center rounded-full bg-white/85 text-ink shadow-glass transition-transform group-hover:translate-x-0.5"
      >
        {action ?? (
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
            <path d="M7 17 17 7M9 7h8v8" />
          </svg>
        )}
      </span>
    </Link>
  );
}
