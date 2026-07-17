import type { Metadata } from "next";
import ToolPagePlaceholder from "@/components/ToolPagePlaceholder";

export const metadata: Metadata = { title: "GenZ Slang — ListenUp" };

export default function TranslateGenzPage() {
  return (
    <ToolPagePlaceholder
      title="GenZ Slang Translator"
      description="Modern internet slang, memes, and abbreviations explained — with shareable translation cards."
      phase="Phase 5"
    />
  );
}
