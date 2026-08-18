/**
 * Latency summaries, defined once.
 *
 * The same `percentile` was written out three times — in `useTranscription`,
 * in `useLiveTranslation`, and again inside each check script's fake — and the
 * three had drifted in their index arithmetic, so "p50" did not mean the same
 * thing in the caption readout as in the translation readout.
 */

export type Summary = { count: number; p50: number; p95: number } | null;

export function percentile(sorted: number[], p: number): number {
  if (!sorted.length) return 0;
  const index = Math.min(sorted.length - 1, Math.ceil((p / 100) * sorted.length) - 1);
  return sorted[Math.max(0, index)];
}

/** Count, median and 95th percentile of a set of measurements. */
export function summarise(values: number[]): Summary {
  if (!values.length) return null;
  const sorted = [...values].sort((a, b) => a - b);
  return { count: sorted.length, p50: percentile(sorted, 50), p95: percentile(sorted, 95) };
}
