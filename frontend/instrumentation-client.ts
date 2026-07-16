import * as Sentry from "@sentry/nextjs";
import posthog from "posthog-js";

// Client-side observability. Both SDKs are no-ops without their env vars.
const sentryDsn = process.env.NEXT_PUBLIC_SENTRY_DSN;
const posthogKey = process.env.NEXT_PUBLIC_POSTHOG_KEY;

if (sentryDsn) {
  Sentry.init({
    dsn: sentryDsn,
    tracesSampleRate: 0.1,
    sendDefaultPii: false,
  });
}

if (posthogKey) {
  posthog.init(posthogKey, {
    api_host: process.env.NEXT_PUBLIC_POSTHOG_HOST ?? "https://us.i.posthog.com",
    capture_pageview: true,
    // Privacy default (INTRODUCTION §6): no session recordings until explicitly enabled.
    disable_session_recording: true,
  });
}

export const onRouterTransitionStart: typeof Sentry.captureRouterTransitionStart = (...args) => {
  if (!sentryDsn) return;
  return Sentry.captureRouterTransitionStart(...args);
};
