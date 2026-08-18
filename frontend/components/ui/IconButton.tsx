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
      // 44x44, not 40: the project's touch-target floor, the same one
      // A11yBar's controls were grown to (32x34 -> 44x44). Expanding the hit
      // area with a pseudo-element instead was tried and reverted — an
      // absolutely positioned box still counts toward scroll width, so it put
      // 2px of horizontal overflow on a 390px phone. `shrink-0` matters:
      // inside a flex row the button was squeezed to 42px wide.
      className={`flex h-11 w-11 shrink-0 items-center justify-center rounded-full transition-colors ${
        accent ? "btn-primary text-on-accent" : "btn-ghost text-ink-soft hover:text-ink"
      } ${className}`}
      {...props}
    />
  );
}
