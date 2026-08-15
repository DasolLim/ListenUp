"use client";

import { authHeader } from "@/lib/auth/token";
import { type PaywallDetail, paywallDetail } from "@/lib/plans";

const BACKEND = process.env.NEXT_PUBLIC_BACKEND_URL ?? "http://localhost:8000";

/**
 * A failed call to the backend, with the paywall body already parsed.
 *
 * `paywall` is non-null only for a 402, and distinguishes "your plan doesn't
 * include this" from "you've used it up" — the client needs to say different
 * things and offer different buttons.
 */
export class ApiError extends Error {
  readonly status: number;
  readonly paywall: PaywallDetail | null;

  constructor(status: number, message: string, paywall: PaywallDetail | null = null) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.paywall = paywall;
  }

  /** Signed out, or the token expired mid-session. */
  get isAuth(): boolean {
    return this.status === 401;
  }
}

/**
 * POST JSON to the backend **as the signed-in user**.
 *
 * Every metered endpoint — translation, the cultural pass, term explanations —
 * is gated on plan and allowance, so all of them need the caller's token. This
 * exists because they were each built before that was true: five call sites
 * hand-rolled the same fetch, the gate was added to the backend, and every one
 * of them started returning 401 into a `.catch(() => undefined)`. The features
 * went silent with nothing in the UI to say why.
 *
 * Routing them through one function means a new endpoint cannot be added to the
 * paywall and forgotten here, and that a refusal arrives as a typed error
 * instead of an empty result.
 */
export async function postJson<T>(path: string, body: unknown): Promise<T> {
  const headers = await authHeader();
  const response = await fetch(`${BACKEND}${path}`, {
    method: "POST",
    headers: { ...headers, "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });

  const payload = await response.json().catch(() => null);
  if (response.ok) return payload as T;

  const detail = (payload as { detail?: unknown } | null)?.detail;
  throw new ApiError(
    response.status,
    typeof detail === "string" ? detail : messageFor(response.status, payload),
    paywallDetail(payload),
  );
}

function messageFor(status: number, payload: unknown): string {
  const paywall = paywallDetail(payload);
  if (paywall?.message) return paywall.message;
  if (status === 401) return "Sign in to use this.";
  if (status === 402) return "This isn't included in your plan.";
  if (status === 503) return "That service is unavailable right now.";
  return "Something went wrong.";
}
