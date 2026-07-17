import { type ButtonHTMLAttributes } from "react";

type IconButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  /** Accessible name — icon-only buttons must always have one. */
  label: string;
  accent?: boolean;
};

export default function IconButton({ label, accent, className = "", ...props }: IconButtonProps) {
  return (
    <button
      type="button"
      aria-label={label}
      title={label}
      className={`flex h-10 w-10 items-center justify-center rounded-full transition-colors ${
        accent ? "btn-primary text-on-accent" : "btn-ghost text-ink-soft hover:text-ink"
      } ${className}`}
      {...props}
    />
  );
}
