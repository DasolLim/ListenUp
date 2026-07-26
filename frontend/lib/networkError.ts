/**
 * Turns a thrown fetch error into copy a person can act on.
 *
 * A failed `fetch()` rejects with the browser's own string — "Failed to fetch",
 * "NetworkError when attempting to fetch resource", "Load failed" — which is
 * meaningless to a user. Server-sent messages are already written for humans,
 * so those pass through unchanged.
 */
export function networkError(err: unknown, fallback: string): string {
  const raw = err instanceof Error ? err.message : "";
  const lower = raw.toLowerCase();
  const isTransport =
    lower.includes("failed to fetch") ||
    lower.includes("networkerror") ||
    lower.includes("load failed") ||
    lower.includes("fetch failed") ||
    lower.includes("network request failed");

  if (isTransport) {
    return "Can't reach the ListenUp server. It may still be starting up — wait a moment and try again.";
  }
  return raw || fallback;
}
