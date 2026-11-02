"use client";

import { useEffect, useState } from "react";
import PlanPicker from "@/components/billing/PlanPicker";
import UsageMeter from "@/components/billing/UsageMeter";
import GlassCard from "@/components/ui/GlassCard";
import { networkError } from "@/lib/networkError";
import { type Metric, formatDate, formatFullDate } from "@/lib/plans";
import { useSubscription } from "@/lib/hooks/useSubscription";

// Order matters: captions first because it is the headline number people
// understand, translated second because it is the real constraint.
const METRICS: Metric[] = ["captions", "translated", "explain", "cloud_tts"];

/**
 * Plan, what's left of it, and the way out.
 *
 * Two rules shape this panel. The reset date is always visible — "when does this
 * come back" is the most common question a cap produces, and making someone ask
 * it is a support ticket we wrote ourselves. And cancellation goes to Stripe's
 * hosted portal rather than a flow of ours: the cancel path should be as short
 * as the subscribe path, and burying it is what makes subscriptions feel
 * predatory.
 */
export default function SubscriptionPanel() {
  const { subscription, catalogue, loading, refresh, startCheckout, openPortal, trialDaysLeft } =
    useSubscription();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Stripe sends the user back here after checkout, but the webhook that grants
  // access may land a moment later. Re-read once so the panel doesn't sit on a
  // stale "Free" immediately after a successful payment.
  useEffect(() => {
    if (typeof window === "undefined") return;
    if (!new URLSearchParams(window.location.search).has("checkout")) return;
    const timer = setTimeout(() => void refresh(), 1500);
    return () => clearTimeout(timer);
  }, [refresh]);

  async function portal() {
    setBusy(true);
    setError(null);
    try {
      await openPortal();
    } catch (err) {
      setError(networkError(err, "Something went wrong. Try again."));
      setBusy(false);
    }
  }

  const tier = subscription?.tier ?? "free";
  const status = subscription?.status ?? "none";
  const resets = formatDate(subscription?.periodEnd ?? null);

  return (
    <section aria-labelledby="subscription-heading" className="flex flex-col gap-4">
      <div>
        <h2 id="subscription-heading" className="font-display text-[22px] font-semibold text-ink">
          Subscription
        </h2>
        <p className="mt-1 text-sm leading-relaxed text-ink-soft">
          Captions are on every plan. Translation, speaker names, term explanations, and
          recorded voices scale with it.
        </p>
      </div>

      <GlassCard className="flex flex-col gap-5 p-5">
        {loading ? (
          <p className="text-sm text-ink-soft">Checking your plan…</p>
        ) : (
          <>
            {/* ── ListenUp Basic · $7.99/month · renews 12 September ── */}
            <div className="flex flex-wrap items-baseline gap-x-2 gap-y-1">
              <p className="font-display text-[17px] font-semibold text-ink">
                {subscription ? `ListenUp ${subscription.planName}` : "Free"}
              </p>
              <span aria-hidden="true" className="text-ink-faint">
                ·
              </span>
              <p className="numeric text-sm text-ink-soft">
                {subscription?.priceUsd ? `$${subscription.priceUsd.toFixed(2)}/month` : "$0"}
              </p>
              {resets && (
                <>
                  <span aria-hidden="true" className="text-ink-faint">
                    ·
                  </span>
                  <p className="text-sm text-ink-soft">
                    {status === "canceled" ? "ends" : "renews"} {resets}
                  </p>
                </>
              )}
            </div>

            {status === "trialing" && trialDaysLeft !== null && (
              <p role="status" className="text-sm leading-relaxed text-ink-soft">
                Free trial — {trialDaysLeft} day{trialDaysLeft === 1 ? "" : "s"} left. Your card
                will be charged ${subscription?.priceUsd.toFixed(2)} on{" "}
                {formatFullDate(subscription?.trialEndsAt ?? null)} unless you cancel.
              </p>
            )}
            {(status === "past_due" || status === "unpaid") && (
              <p role="alert" className="text-sm leading-relaxed text-error-strong">
                We couldn&rsquo;t take the last payment. Update your card to keep your plan.
              </p>
            )}

            {/* ── The meters ── */}
            {subscription && (
              <div className="flex flex-col gap-3.5">
                {METRICS.map((metric) => (
                  <UsageMeter key={metric} metric={metric} usage={subscription.usage[metric]} />
                ))}
              </div>
            )}

            {/* ── Resets 12 September · Manage billing ── */}
            <div className="flex flex-wrap items-center justify-between gap-3 border-t border-[var(--glass-border)] pt-4">
              <p className="text-[13px] text-ink-soft">
                {resets ? `Resets ${resets}` : "Usage resets monthly"}
              </p>
              {subscription && status !== "none" && (
                <button
                  type="button"
                  onClick={portal}
                  disabled={busy}
                  className="btn-ghost inline-flex min-h-11 items-center rounded-full px-5 text-[15px] font-medium text-ink"
                >
                  {busy ? "Opening…" : "Manage billing"}
                </button>
              )}
            </div>

            {error && (
              <p role="alert" className="text-[13px] text-error-strong">
                {error}
              </p>
            )}
          </>
        )}
      </GlassCard>

      {/* Upgrade options sit below the current plan rather than inside it, so
          the panel reads as "here's where you are" before "here's what else
          exists". Hidden on Pro — there is nothing to sell someone who already
          has everything. */}
      {!loading && tier !== "pro" && (
        <div className="flex flex-col gap-3">
          <h3 className="font-display text-[15px] font-semibold text-ink">
            {tier === "free" ? "Plans" : "Upgrade"}
          </h3>
          <PlanPicker
            catalogue={catalogue}
            currentTier={tier}
            trialUsed={subscription?.trialUsed ?? false}
            onChoose={startCheckout}
          />
        </div>
      )}

      <p className="text-[12px] leading-relaxed text-ink-faint">
        Billing, invoices, plan changes, and cancellation are handled by Stripe. We never see
        your card details.
      </p>
    </section>
  );
}
