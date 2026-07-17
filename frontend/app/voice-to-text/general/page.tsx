import type { Metadata } from "next";
import ToolPagePlaceholder from "@/components/ToolPagePlaceholder";
import WsEchoDebug from "@/components/WsEchoDebug";

export const metadata: Metadata = { title: "Live Captions — ListenUp" };

export default function VoiceToTextGeneralPage() {
  return (
    <div>
      <ToolPagePlaceholder
        title="Live Captions (General)"
        description="Real-time captions with multi-speaker separation and a color-coded chat-bubble view."
        phase="Phase 2"
      />
      <div className="mx-auto max-w-2xl">
        <WsEchoDebug />
      </div>
    </div>
  );
}
