import GlassCard from "@/components/ui/GlassCard";

// Page title comes from the app shell Topbar; this renders the body surface.
export default function ToolPagePlaceholder({
  title,
  description,
  phase,
}: {
  title: string;
  description: string;
  phase: string;
}) {
  return (
    <GlassCard strong className="max-w-2xl p-7">
      <h2 className="font-display text-[22px] font-semibold">{title}</h2>
      <p className="mt-3 text-ink-soft">{description}</p>
      <p
        role="status"
        className="mt-6 rounded-2xl border border-dashed border-ink-faint/40 p-4 text-sm text-ink-soft"
      >
        This tool is under construction — it ships in {phase}.
      </p>
    </GlassCard>
  );
}
