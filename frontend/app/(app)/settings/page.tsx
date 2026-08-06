import type { Metadata } from "next";
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
          Enrol the people you talk with, and choose how translations are read aloud.
        </p>
      </header>
      <VoiceProfiles />
      <VoiceStudio />
    </div>
  );
}
