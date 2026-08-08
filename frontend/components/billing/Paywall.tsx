"use client";

import { useState } from "react";
import Button from "@/components/ui/Button";
import GlassCard from "@/components/ui/GlassCard";
import { networkError } from "@/lib/networkError";
import { METRIC_NOUN, type Metric, type Tier, formatDate } from "@/lib/plans";
import { useSubscription } from "@/lib/useSubscription";

/**
 * Wraps a paid feature.
 *
 * While entitlement is unknown it renders the feature rather than a spinner:
 * flashing a paywall at a paying subscriber on every page load is worse than a
 * moment of optimism, and the backend refuses the request anyway if we get it
 * wrong. The lock is server-side; this is the explanation.
 */
export default function Paywall({
  feature,
  metric,
  children,
}: {
  /** What is behind the wall, named as the user would name it. */
  feature: string;
  /** The allowance this feature spends, if it meters one. */
  metric?: Metric;
  children: React.ReactNode;
}) {
  const { subscription, catalogue, loading, startCheckout, trialDaysLeft } = useSubscription();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const usage = metric && subscription ? subscription.usage[metric] : undefined;
  const included = usage ? usage.included : (subscription?.paid ?? true);
  const exhausted = usage?.exhausted ?? false;

  if (loading || (included && !exhausted)) {
    return (
      <>
        {trialDaysLeft !== null && trialDaysLeft <= 3 && subscription && (
          <p
            role="status"
            className="mb-4 rounded-2xl border border-warning bg-white/70 px-4 py-2.5 text-[13px] leading-relaxed text-ink"
          >
            {trialDaysLeft === 0
              ? `Your free trial ends today. Your card will be charged $${subscription.priceUsd.toFixed(2)} unless you cancel.`
              : `${trialDaysLeft} day${trialDaysLeft === 1 ? "" : "s"} left in your free trial. Cancel any time in Settings.`}
          </p>
        )}
        {usage?.warning && (
          <p
            role="status"
            className="mb-4 rounded-2xl border border-warning bg-white/70 px-4 py-2.5 text-[13px] leading-relaxed text-ink"
          >
            You&rsquo;ve used most of your {metric ? METRIC_NOUN[metric] : feature.toLowerCase()}{" "}
            this month.
            {subscription?.periodEnd && ` They reset ${formatDate(subscription.periodEnd)}.`}
          </p>
        )}
        {children}
      </>
    );
  }

  // Which plan fixes this. Free upgrades to Basic for most things; Pro is only
  // proposed when Basic genuinely wouldn't help.
  const upgradeTo: Tier =
    metric === "cloud_tts" || subscription?.tier === "basic" ? "pro" : "basic";
  // "term explanations", not "Explain a term" — the label is a heading, this
  // goes in a sentence.
  const noun = metric ? METRIC_NOUN[metric] : feature.toLowerCase();
  const target = catalogue?.plans.find((plan) => plan.tier === upgradeTo);
  const discount = upgradeTo === "pro" ? (catalogue?.proFirstMonthDiscount ?? 0) : 0;
  const firstTime = !subscription?.trialUsed;
  const resets = formatDate(subscription?.periodEnd ?? null);

  async function begin() {
    setBusy(true);
    setError(null);
    try {
      await startCheckout(upgradeTo);
    } catch (err) {
      setError(networkError(err, "Couldn't open checkout."));
      setBusy(false);
    }
  }

  return (
    <GlassCard strong className="mx-auto flex max-w-lg flex-col items-center gap-5 p-8 text-center">
      <span aria-hidden="true" className="orb size-16" />

      <div className="flex flex-col gap-2">
        <h2 className="font-display text-[22px] font-semibold text-ink">
          {exhausted
            ? `You've used all your ${noun} this month`
            : `${feature} is part of ${target?.name ?? "ListenUp Paid"}`}
        </h2>
        {/* The three things a limit must say: what ran out, when it comes back,
            and what upgrading changes. Only the first two apply to a plain
            upgrade prompt, so the copy branches rather than padding. */}
        <p className="text-sm leading-relaxed text-ink-soft">
          {exhausted ? (
            <>
              {resets ? `It resets ${resets}.` : "It resets when your billing period does."}{" "}
              {upgradeTo === "pro" && target
                ? `Pro raises the limit and adds cloud voices.`
                : `${target?.name ?? "Upgrading"} raises the limit.`}
            </>
          ) : firstTime ? (
            `Try everything free for ${catalogue?.trialDays ?? 7} days. We ask for a card so it can continue without interruption, and you can cancel any time — including during the trial.`
          ) : (
            `${target?.name ?? "A paid plan"} unlocks this.`
          )}
        </p>
      </div>

      {/* One button, not a funnel. Someone who has hit a wall wants past it, not
          a pricing tour — the full table stays in Settings. */}
      <div className="flex flex-col items-center gap-2">
        <Button onClick={begin} disabled={busy}>
          {busy
            ? "Opening checkout…"
            : firstTime
              ? `Start ${catalogue?.trialDays ?? 7}-day free trial`
              : `Upgrade to ${target?.name ?? "Paid"}`}
        </Button>
        {target && (
          <p className="text-[12px] text-ink-faint">
            {discount > 0
              ? `$${(target.priceUsd * (1 - discount / 100)).toFixed(2)} first month, then $${target.priceUsd.toFixed(2)}/month · Cancel any time`
              : `$${target.priceUsd.toFixed(2)}/month · Cancel any time`}
          </p>
        )}
      </div>

      {error && (
        <p role="alert" className="text-[13px] text-error-strong">
          {error}
        </p>
      )}

      <p className="text-[12px] leading-relaxed text-ink-faint">
        Live captions stay on every plan, including speaker separation.
      </p>
    </GlassCard>
  );
}
