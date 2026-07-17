import type { Metadata } from "next";
import LiveCaptions from "@/components/captions/LiveCaptions";

export const metadata: Metadata = { title: "Live Captions — ListenUp" };

export default function VoiceToTextGeneralPage() {
  return (
    <div className="mx-auto flex h-full max-w-3xl flex-col">
      <LiveCaptions />
    </div>
  );
}
