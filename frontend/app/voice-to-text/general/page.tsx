import type { Metadata } from "next";
import ToolPagePlaceholder from "@/components/ToolPagePlaceholder";

export const metadata: Metadata = { title: "Live Captions — ListenUp" };

export default function VoiceToTextGeneralPage() {
  return (
    <ToolPagePlaceholder
      title="Live Captions (General)"
      description="Real-time captions with multi-speaker separation and a color-coded chat-bubble view."
      phase="Phase 2"
    />
  );
}
