import type { Metadata } from "next";
import { Suspense } from "react";
import LiveCaptions from "@/components/captions/LiveCaptions";

export const metadata: Metadata = { title: "Captions — ListenUp" };

/**
 * One captions surface.
 *
 * This replaces the old General/Enhanced pair. That split exposed a backend
 * tier as a product choice, and it was never a real choice: "Enhanced" was a
 * strict superset, so nobody would knowingly pick the version that calls their
 * mother "Speaker 1". Whether names appear is a *condition* — have you enrolled
 * anyone — not a fork in the product, so captions now always try to name people
 * and fall back to generic labels when they can't.
 */
export default function CaptionsPage() {
  return (
    <div className="mx-auto flex max-w-3xl flex-col gap-6">
      {/* Reading `?start=1` makes this subtree client-rendered, so it needs a
          Suspense boundary to keep the rest of the route prerenderable. The
          fallback is a plain height reservation rather than a spinner: the
          window before hydration is a frame or two, and a flash of loading
          chrome would be more noticeable than the wait it describes. */}
      <Suspense fallback={<div className="min-h-112" aria-hidden="true" />}>
        <LiveCaptions />
      </Suspense>
    </div>
  );
}
