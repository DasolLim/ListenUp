import type { Metadata } from "next";
import TranslateGenz from "@/components/translate/TranslateGenz";

export const metadata: Metadata = { title: "GenZ Slang — ListenUp" };

export default function TranslateGenzPage() {
  return (
    <div className="mx-auto flex max-w-3xl flex-col">
      <TranslateGenz />
    </div>
  );
}
