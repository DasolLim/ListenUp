"use client";

import { useCallback, useEffect, useState } from "react";
import { authHeader } from "@/lib/auth/token";
import type { PlanCatalogue, Subscription, Tier } from "@/lib/plans";

const BACKEND = process.env.NEXT_PUBLIC_BACKEND_URL ?? "http://localhost:8000";

export type { Subscription } from "@/lib/plans";

/**
 * The caller's plan, allowances, and usage, read from the server.
 *
 * This decides what the UI *shows*. It deliberately does not decide what anyone
 * may *do* — the backend re-checks entitlement and allowance on every gated
 * endpoint, because a value held in the browser is a suggestion. Losing this
 * fetch should cost you a nice panel, not the lock itself.
 */
export function useSubscription() {
  const [subscription, setSubscription] = useState<Subscription | null>(null);
  const [catalogue, setCatalogue] = useState<PlanCatalogue | null>(null);
  const [loading, setLoading] = useState(true);
  // Computed when the data arrives rather than during render: reading the clock
  // in a render body is impure, differs between server and client, and would
  // make the count drift between hydration passes.
  const [trialDaysLeft, setTrialDaysLeft] = useState<number | null>(null);

  const refresh = useCallback(async () => {
    try {
      const headers = await authHeader();
      if (!headers.Authorization) {
        setSubscription(null);
        return;
      }
      const response = await fetch(`${BACKEND}/billing/subscription`, { headers });
      const body: Subscription | null = response.ok ? await response.json() : null;
      setSubscription(body);
      setTrialDaysLeft(
        body?.status === "trialing" && body.trialEndsAt
          ? Math.max(
              0,
              Math.ceil((new Date(body.trialEndsAt).getTime() - Date.now()) / 86_400_000),
            )
          : null,
      );
    } catch {
      setSubscription(null);
    } finally {
      setLoading(false);
    }
  }, []);

  // The tier table is public and identical for everyone, so it is fetched
  // without auth and never blocks the entitlement read.
  const loadCatalogue = useCallback(async () => {
    try {
      const response = await fetch(`${BACKEND}/billing/plans`);
      if (response.ok) setCatalogue(await response.json());
    } catch {
      setCatalogue(null);
    }
  }, []);

  useEffect(() => {
    const raf = requestAnimationFrame(() => {
      void refresh();
      void loadCatalogue();
    });
    return () => cancelAnimationFrame(raf);
  }, [refresh, loadCatalogue]);

  /** Send the user to Stripe Checkout on a chosen plan. */
  const startCheckout = useCallback(async (plan: Tier) => {
    const headers = await authHeader();
    const response = await fetch(`${BACKEND}/billing/checkout`, {
      method: "POST",
      headers: { ...headers, "Content-Type": "application/json" },
      body: JSON.stringify({ plan }),
    });
    const body = await response.json().catch(() => ({}));
    if (!response.ok) {
      throw new Error(
        typeof body.detail === "string" ? body.detail : "Couldn't open checkout.",
      );
    }
    window.location.href = body.url;
  }, []);

  /** Stripe's hosted portal: payment method, plan changes, invoices, cancellation. */
  const openPortal = useCallback(async () => {
    const headers = await authHeader();
    const response = await fetch(`${BACKEND}/billing/portal`, { method: "POST", headers });
    const body = await response.json().catch(() => ({}));
    if (!response.ok) {
      throw new Error(
        typeof body.detail === "string" ? body.detail : "Couldn't open billing.",
      );
    }
    window.location.href = body.url;
  }, []);

  return {
    subscription,
    catalogue,
    loading,
    refresh,
    startCheckout,
    openPortal,
    trialDaysLeft,
  };
}
