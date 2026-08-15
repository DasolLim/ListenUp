"use client";

import { useState } from "react";
import Button from "@/components/ui/Button";
import GlassCard from "@/components/ui/GlassCard";
import { networkError } from "@/lib/networkError";
import {
  CHARS_PER_HOUR,
  type PlanCatalogue,
  type PlanCatalogueEntry,
  type Tier,
} from "@/lib/plans";

/**
 * Choose Basic or Pro, then start the trial on it.
 *
 * The plan is chosen *before* the trial rather than after, because Stripe needs
 * to know what to charge when it converts. Nothing is lost by that: the card
 * isn't charged for seven days, the plan can be changed in the portal, and
 * cancelling during the trial costs nothing — all of which is stated on the
 * button rather than buried in terms.
 */

function describe(plan: PlanCatalogueEntry): string[] {
  const lines: string[] = [];
  const captions = (plan.limits.captions ?? 0) / 3600;
  lines.push(`${captions} hrs of captions a month`);

  const translated = plan.limits.translated ?? 0;
  lines.push(
    translated
      ? `${Math.round(translated / CHARS_PER_HOUR)} hrs of translated captions`
      : "Translation not included",
  );

  lines.push(
    plan.limits.explain === null
      ? "Unlimited term explanations"
      : `${plan.limits.explain} term explanations`,
  );

  lines.push(
    plan.profiles === 1 ? "Names one person" : `Names up to ${plan.profiles} people`,
  );

  if (plan.limits.cloud_tts) {
    lines.push(`${Math.round(plan.limits.cloud_tts / 60)} min of cloud read-aloud`);
  }
  if (plan.voiceCloning) lines.push("Record your own voice");
  return lines;
}

export default function PlanPicker({
  catalogue,
  currentTier,
  trialUsed,
  onChoose,
}: {
  catalogue: PlanCatalogue | null;
  currentTier: Tier;
  trialUsed: boolean;
  onChoose: (plan: Tier) => Promise<void>;
}) {
  const [busy, setBusy] = useState<Tier | null>(null);
  const [error, setError] = useState<string | null>(null);

  if (!catalogue) return null;
  const sellable = catalogue.plans.filter((plan) => plan.tier !== "free");
  const discount = catalogue.proFirstMonthDiscount;

  async function choose(plan: Tier) {
    setBusy(plan);
    setError(null);
    try {
      await onChoose(plan);
    } catch (err) {
      setError(networkError(err, "Couldn't open checkout."));
      setBusy(null);
    }
  }

  return (
    <div className="flex flex-col gap-3">
      <div className="grid gap-3 sm:grid-cols-2">
        {sellable.map((plan) => {
          const isPro = plan.tier === "pro";
          const discounted = isPro && discount > 0;
          const firstMonth = plan.priceUsd * (1 - discount / 100);
          return (
            <GlassCard
              key={plan.tier}
              strong={isPro}
              className="flex flex-col gap-3 p-5"
            >
              <div className="flex flex-wrap items-baseline justify-between gap-2">
                <p className="font-display text-[17px] font-semibold text-ink">{plan.name}</p>
                {discounted && (
                  <span className="rounded-full bg-white/70 px-2.5 py-0.5 text-[11px] font-semibold text-accent-strong">
                    {discount}% off first month
                  </span>
                )}
              </div>

              <p className="numeric text-sm text-ink-soft">
                {discounted ? (
                  <>
                    <span className="text-ink">${firstMonth.toFixed(2)}</span> first month,
                    then ${plan.priceUsd.toFixed(2)}/mo
                  </>
                ) : (
                  <>${plan.priceUsd.toFixed(2)} / month</>
                )}
              </p>

              <ul className="flex flex-col gap-1.5 text-[13px] text-ink-soft">
                {describe(plan).map((line) => (
                  <li key={line} className="flex items-start gap-2">
                    <span
                      aria-hidden="true"
                      className="mt-1.5 size-1.5 shrink-0 rounded-full bg-accent-strong"
                    />
                    {line}
                  </li>
                ))}
              </ul>

              {/* A button that cannot work is worse than no button: it invites
                  a click and answers with an error the user can do nothing
                  about. When a tier has no Stripe price on this deployment, say
                  so where the button would be. */}
              <Button
                variant={isPro ? "primary" : "ghost"}
                onClick={() => choose(plan.tier)}
                disabled={busy !== null || currentTier === plan.tier || !plan.purchasable}
                className="mt-auto"
              >
                {busy === plan.tier
                  ? "Opening…"
                  : !plan.purchasable
                    ? "Not available yet"
                    : trialUsed
                      ? `Choose ${plan.name}`
                      : `Start ${catalogue.trialDays}-day trial`}
              </Button>
            </GlassCard>
          );
        })}
      </div>

      <p className="text-[12px] leading-relaxed text-ink-faint">
        {!catalogue.checkoutReady
          ? "Paid plans aren't open for signup yet. Everything on your current plan keeps working."
          : trialUsed
            ? "Billing starts today. Cancel any time from Settings."
            : `Free for ${catalogue.trialDays} days. We ask for a card so your plan continues without interruption — you can cancel any time, including during the trial, and you won't be charged.`}
      </p>

      {error && (
        <p role="alert" className="text-[13px] text-error-strong">
          {error}
        </p>
      )}
    </div>
  );
}
