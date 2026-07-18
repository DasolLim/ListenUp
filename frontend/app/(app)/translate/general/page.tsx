import type { Metadata } from "next";
import TranslateGeneral from "@/components/translate/TranslateGeneral";

export const metadata: Metadata = { title: "Translate (General) — ListenUp" };

export default function TranslateGeneralPage() {
  return (
    <div className="mx-auto flex max-w-3xl flex-col">
      <TranslateGeneral />
    </div>
  );
}
