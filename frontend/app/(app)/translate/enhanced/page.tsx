import type { Metadata } from "next";
import TranslateEnhanced from "@/components/translate/TranslateEnhanced";

export const metadata: Metadata = { title: "Cultural Translation — ListenUp" };

export default function TranslateEnhancedPage() {
  return (
    <div className="mx-auto flex max-w-3xl flex-col">
      <TranslateEnhanced />
    </div>
  );
}
