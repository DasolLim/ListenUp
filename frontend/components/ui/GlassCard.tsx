import { type HTMLAttributes } from "react";

type GlassCardProps = HTMLAttributes<HTMLDivElement> & {
  /** Use the stronger (more opaque) glass, e.g. behind body text. */
  strong?: boolean;
};

export default function GlassCard({ strong, className = "", ...props }: GlassCardProps) {
  return (
    <div className={`glass-card ${strong ? "glass-strong" : ""} ${className}`} {...props} />
  );
}
