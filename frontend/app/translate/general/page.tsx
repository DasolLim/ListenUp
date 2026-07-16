import type { Metadata } from "next";
import ToolPagePlaceholder from "@/components/ToolPagePlaceholder";

export const metadata: Metadata = { title: "Translate (General) — ListenUp" };

export default function TranslateGeneralPage() {
  return (
    <ToolPagePlaceholder
      title="Translate (General)"
      description="Fast text→text and voice→text translation across a wide range of languages."
      phase="Phase 4"
    />
  );
}
