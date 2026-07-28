"use client";

import { type ButtonHTMLAttributes } from "react";

type PillProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  active?: boolean;
};

/** Category / mode toggle pill. Active = solid white with dark text (per reference). */
export default function Pill({ active, className = "", ...props }: PillProps) {
  return (
    <button
      type="button"
      aria-pressed={active}
      className={`inline-flex min-h-11 items-center rounded-full px-4 text-sm font-medium transition-colors ${
        active
          ? "pill-active text-ink shadow-glass"
          : "pill-inactive text-ink-soft hover:text-ink"
      } ${className}`}
      {...props}
    />
  );
}
