import type { Metadata } from "next";
import ToolPagePlaceholder from "@/components/ToolPagePlaceholder";

export const metadata: Metadata = { title: "Enhanced Captions — ListenUp" };

export default function VoiceToTextEnhancedPage() {
  return (
    <ToolPagePlaceholder
      title="Enhanced Captions"
      description="Saved voice profiles label the people you talk to most by name — with tap-to-correct and higher accuracy for up to 4–5 speakers."
      phase="Phase 3"
    />
  );
}
