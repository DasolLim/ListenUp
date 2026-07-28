import { type ButtonHTMLAttributes } from "react";

type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: "primary" | "ghost";
};

/** Primary = coral gradient (spend boldness sparingly). Ghost = quiet glass. */
export default function Button({ variant = "primary", className = "", ...props }: ButtonProps) {
  const styles =
    variant === "primary"
      ? "btn-primary text-on-accent font-semibold"
      : "btn-ghost text-ink font-medium";
  return (
    <button
      className={`inline-flex min-h-11 items-center justify-center rounded-full px-5 text-sm transition-transform hover:-translate-y-0.5 disabled:opacity-50 disabled:hover:translate-y-0 ${styles} ${className}`}
      {...props}
    />
  );
}
