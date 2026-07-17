const sizes = {
  sm: "h-8 w-8",
  md: "h-12 w-12",
  lg: "h-20 w-20",
} as const;

/** The coral orb — brand mark + assistant avatar. Ambient shimmer honors reduced-motion. */
export default function Orb({
  size = "md",
  className = "",
}: {
  size?: keyof typeof sizes;
  className?: string;
}) {
  return (
    <span
      aria-hidden="true"
      className={`orb inline-block shrink-0 ${sizes[size]} ${className}`}
    />
  );
}
