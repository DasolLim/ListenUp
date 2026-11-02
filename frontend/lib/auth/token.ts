"use client";

import { createClient, isSupabaseConfigured } from "@/lib/supabase/client";

/**
 * The caller's access token, whichever provider issued it.
 *
 * Every backend request that touches voice profiles needs a token, and before
 * this each call site reached for Supabase directly. Routing them through one
 * function means the Clerk cutover (docs/plans/MIGRATION_PLAN.md §2) is a change here
 * rather than in four components — and, more importantly, that no call site can
 * be forgotten and silently keep sending a Supabase token to a backend that has
 * moved on.
 *
 * Provider is chosen by which one is configured, so a deployment without Clerk
 * keys behaves exactly as it does today.
 */

/** Clerk attaches itself to `window` once its script has loaded. */
type ClerkWindow = Window & {
  Clerk?: { session?: { getToken: () => Promise<string | null> } };
};

export function isClerkConfigured(): boolean {
  return Boolean(process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY);
}

/** Whether *some* auth provider is set up, for guards that skip signed-in work. */
export function isAuthConfigured(): boolean {
  return isClerkConfigured() || isSupabaseConfigured();
}

export async function getAccessToken(): Promise<string | null> {
  if (isClerkConfigured() && typeof window !== "undefined") {
    const session = (window as ClerkWindow).Clerk?.session;
    // No session means signed out — the same answer Supabase gives, so callers
    // need no provider-specific branch.
    if (!session) return null;
    try {
      return await session.getToken();
    } catch {
      return null;
    }
  }

  if (!isSupabaseConfigured()) return null;
  const { data } = await createClient().auth.getSession();
  return data.session?.access_token ?? null;
}

/**
 * Authorization header, or `{}` when signed out.
 *
 * Returning an empty object rather than throwing keeps the callers' existing
 * shape: a request without the header gets a 401 from the backend, which is the
 * correct outcome and already handled.
 */
export async function authHeader(): Promise<Record<string, string>> {
  const token = await getAccessToken();
  return token ? { Authorization: `Bearer ${token}` } : {};
}
