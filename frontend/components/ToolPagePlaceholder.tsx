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
    <div className="mx-auto max-w-2xl">
      <h1 className="text-3xl font-bold">{title}</h1>
      <p className="mt-4 text-zinc-600 dark:text-zinc-300">{description}</p>
      <p
        role="status"
        className="mt-8 rounded-lg border border-dashed border-zinc-300 p-4 text-sm text-zinc-500 dark:border-zinc-700 dark:text-zinc-400"
      >
        This tool is under construction — it ships in {phase}.
      </p>
    </div>
  );
}
