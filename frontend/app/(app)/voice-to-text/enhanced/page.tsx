import type { Metadata } from "next";
import LiveCaptions from "@/components/captions/LiveCaptions";
import VoiceProfiles from "@/components/profiles/VoiceProfiles";

export const metadata: Metadata = { title: "Enhanced Captions — ListenUp" };

export default function VoiceToTextEnhancedPage() {
  return (
    <div className="mx-auto flex max-w-3xl flex-col gap-6">
      <LiveCaptions enhanced />
      <VoiceProfiles />
    </div>
  );
}
