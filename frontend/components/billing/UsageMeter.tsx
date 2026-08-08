"use client";

import {
  METRIC_LABEL,
  type Metric,
  type MetricUsage,
  formatValue,
  meterState,
  metricUnit,
} from "@/lib/plans";

/**
 * One allowance, as a bar plus its numbers.
 *
 * The bar exists because proportion is read faster than arithmetic — "how much
 * is left" is a glance, not a subtraction. The numbers stay because a bar alone
 * can't answer "how much exactly", and because colour must never be the only
 * signal: everything the fill colour says is also said in text.
 */
export default function UsageMeter({
  metric,
  usage,
}: {
  metric: Metric;
  usage: MetricUsage;
}) {
  const state = meterState(usage);
  const unit = metricUnit(metric);
  const label = METRIC_LABEL[metric];
  const percent = Math.round(Math.min(1, Math.max(0, usage.ratio)) * 100);

  // What goes to the right of the bar, and what a screen reader hears instead
  // of "78 percent" — which on its own says nothing about what ran out.
  let figure: string;
  let spoken: string;
  if (!usage.included) {
    figure = "Not on your plan";
    spoken = `${label}: not included on your plan`;
  } else if (usage.unlimited) {
    figure = "Unlimited";
    spoken = `${label}: unlimited`;
  } else {
    const used = formatValue(metric, usage.used);
    const limit = formatValue(metric, usage.limit ?? 0);
    figure = unit ? `${used} / ${limit} ${unit}` : `${used} / ${limit}`;
    spoken = `${label}: ${figure} used, ${percent}%`;
  }

  return (
    <div className="flex flex-col gap-1.5">
      <div className="flex items-baseline justify-between gap-3">
        <span className="text-[13px] font-medium text-ink">{label}</span>
        <span
          className={`numeric text-[13px] ${
            state === "limit"
              ? "text-error-strong"
              : state === "warning"
                ? "text-warning-strong"
                : "text-ink-soft"
          }`}
        >
          {figure}
        </span>
      </div>

      <div
        className="meter-track"
        data-state={state === "excluded" ? "excluded" : undefined}
        role="progressbar"
        aria-valuemin={0}
        aria-valuemax={100}
        // An excluded or unlimited meter has no meaningful position, so the
        // value is omitted rather than faked as 0 or 100.
        aria-valuenow={usage.included && !usage.unlimited ? percent : undefined}
        aria-valuetext={spoken}
        aria-label={label}
      >
        {usage.included && !usage.unlimited && (
          <div
            className="meter-fill"
            data-state={state === "ok" ? undefined : state}
            style={{ width: `${percent}%` }}
          />
        )}
      </div>
    </div>
  );
}
