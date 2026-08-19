import type { Metadata } from "next";
import Link from "next/link";
import SubscriptionPanel from "@/components/billing/SubscriptionPanel";
import VoiceProfiles from "@/components/profiles/VoiceProfiles";
import VoiceStudio from "@/components/speech/VoiceStudio";

export const metadata: Metadata = { title: "Settings — ListenUp" };

/**
 * Setup, gathered in one place.
 *
 * Enrolling someone's voice and choosing a read-aloud voice are things you do
 * once, at home — not mid-conversation. They previously sat in the tool rack as
 * peers of Captions, which made the product look wider than it is and buried
 * the two things people actually open it for.
 */
export default function SettingsPage() {
  return (
    <div className="mx-auto flex max-w-3xl flex-col gap-8">
      <header>
        <h1 className="font-display text-[26px] font-semibold text-ink">Settings</h1>
        <p className="mt-1 text-sm leading-relaxed text-ink-soft">
          Your plan, the people you talk with, and how translations are read aloud.
        </p>
      </header>
      <SubscriptionPanel />
      <VoiceProfiles />
      <VoiceStudio />
      {/* Reachable from inside the product, not only from the marketing footer.
          Someone looking for how to withdraw a consent they gave for a voice
          profile is already signed in and already on this page — sending them
          to the public site to find it would be the wrong way round. */}
      <footer className="border-t border-white/40 pt-6 text-sm text-ink-soft">
        How we handle your data, including voice profiles, is in the{" "}
        <Link href="/privacy" className="text-accent-strong underline underline-offset-2">
          privacy policy
        </Link>
        . Using ListenUp is subject to the{" "}
        <Link href="/terms" className="text-accent-strong underline underline-offset-2">
          terms of use
        </Link>
        .
      </footer>
    </div>
  );
}
