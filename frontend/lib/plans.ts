/**
 * Plan shapes and the formatting rules for allowances.
 *
 * Deliberately holds **no limits**. Every number displayed comes from
 * `/billing/subscription`, because the backend is what enforces them — a "3 hrs"
 * hard-coded here is a support ticket the day the cap changes on the server.
 * What lives here is how to *render* those numbers.
 */

export type Tier = "free" | "basic" | "pro";
export type Metric = "captions" | "translated" | "explain" | "cloud_tts";

export type MetricUsage = {
  used: number;
  limit: number | null;
  included: boolean;
  unlimited: boolean;
  remaining: number | null;
  ratio: number;
  warning: boolean;
  exhausted: boolean;
};

export type Subscription = {
  paid: boolean;
  tier: Tier;
  planName: string;
  priceUsd: number;
  status: string;
  trialEndsAt: string | null;
  currentPeriodEnd: string | null;
  trialUsed: boolean;
  trialDays: number;
  profiles: number;
  voiceCloning: boolean;
  periodStart: string | null;
  periodEnd: string | null;
  usage: Record<Metric, MetricUsage>;
};

export type PlanCatalogueEntry = {
  tier: Tier;
  name: string;
  priceUsd: number;
  limits: Record<Metric, number | null>;
  profiles: number;
  voiceCloning: boolean;
};

export type PlanCatalogue = {
  plans: PlanCatalogueEntry[];
  trialDays: number;
  proFirstMonthDiscount: number;
};

/** Characters of speech in an hour — mirrors CHARS_PER_HOUR in app/plans.py. */
export const CHARS_PER_HOUR = 52_200;

export const METRIC_LABEL: Record<Metric, string> = {
  captions: "Captions",
  translated: "Translated",
  explain: "Explain a term",
  cloud_tts: "Cloud read-aloud",
};

/**
 * What the allowance is *of*, as a plural noun.
 *
 * Separate from the label because the label is a column heading and the noun
 * goes in a sentence — "you've used all your Explain a term this month" is what
 * you get when one string tries to do both jobs.
 */
export const METRIC_NOUN: Record<Metric, string> = {
  captions: "caption hours",
  translated: "translated captions",
  explain: "term explanations",
  cloud_tts: "cloud read-aloud minutes",
};

/**
 * How each metric is counted on the wire, and how to say it to a person.
 *
 * Translation is stored in characters because that is what providers bill, but
 * nobody thinks in characters — so it is shown in hours. Keeping the conversion
 * in one place stops the bar and the caption disagreeing.
 */
export function formatAmount(metric: Metric, value: number): string {
  switch (metric) {
    case "captions":
      return formatHours(value / 3600);
    case "translated":
      return formatHours(value / CHARS_PER_HOUR);
    case "cloud_tts":
      return `${Math.round(value / 60)} min`;
    case "explain":
      return `${value}`;
  }
}

/** The unit shown once, after the pair — "9.4 / 15 hrs", not "9.4 hrs / 15 hrs". */
export function metricUnit(metric: Metric): string {
  switch (metric) {
    case "captions":
    case "translated":
      return "hrs";
    case "cloud_tts":
      return "min";
    case "explain":
      return "";
  }
}

function formatHours(hours: number): string {
  // One decimal below ten so small usage is still visible — "0.4" reads as
  // progress where "0" reads as broken.
  return hours < 10 ? hours.toFixed(1) : Math.round(hours).toString();
}

/** Bare number for the pair, with the unit appended once by the caller. */
export function formatValue(metric: Metric, value: number): string {
  switch (metric) {
    case "captions":
      return formatHours(value / 3600);
    case "translated":
      return formatHours(value / CHARS_PER_HOUR);
    case "cloud_tts":
      return Math.round(value / 60).toString();
    case "explain":
      return value.toString();
  }
}

export type MeterState = "ok" | "warning" | "limit" | "excluded";

export function meterState(usage: MetricUsage): MeterState {
  if (!usage.included) return "excluded";
  if (usage.exhausted) return "limit";
  if (usage.warning) return "warning";
  return "ok";
}

/**
 * "12 September" — the reset date, which is the most-asked support question.
 *
 * Rendered in **UTC**, deliberately. A billing period boundary often lands near
 * midnight UTC, and formatting that in local time shows the *previous day* to
 * anyone west of Greenwich: the API says it resets on the 12th, the invoice says
 * the 12th, and the panel would say the 11th. Being consistently right with the
 * rest of the system beats being locally precise about an instant nobody is
 * watching the clock for.
 */
export function formatDate(value: string | null): string {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  return date.toLocaleDateString(undefined, {
    day: "numeric",
    month: "long",
    timeZone: "UTC",
  });
}

export function formatFullDate(value: string | null): string {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  return date.toLocaleDateString(undefined, {
    day: "numeric",
    month: "long",
    year: "numeric",
    timeZone: "UTC",
  });
}

/**
 * The structured body a 402 carries. The backend distinguishes "your plan
 * doesn't include this" from "you've used it up" because they need different
 * copy and a different button; parsing English here would throw that away.
 */
export type PaywallDetail = {
  reason: "not_included" | "limit_reached";
  metric?: Metric;
  plan?: Tier;
  used?: number;
  limit?: number | null;
  resetsAt?: string | null;
  upgradeTo?: Tier | null;
  message?: string;
};

export function paywallDetail(body: unknown): PaywallDetail | null {
  if (!body || typeof body !== "object") return null;
  const detail = (body as { detail?: unknown }).detail;
  if (!detail || typeof detail !== "object") return null;
  const reason = (detail as PaywallDetail).reason;
  if (reason !== "not_included" && reason !== "limit_reached") return null;
  return detail as PaywallDetail;
}
