import type { Metadata } from "next";
import Paywall from "@/components/billing/Paywall";
import TranslateEnhanced from "@/components/translate/TranslateEnhanced";

export const metadata: Metadata = { title: "Translate — ListenUp" };

/**
 * One translate surface.
 *
 * The General/Enhanced pair contradicted the architecture behind it: the
 * backend already fires fast Google translation and the LLM cultural upgrade
 * together, showing the quick answer immediately and enriching it when the
 * model returns. That is one tool with two speeds, so the UI no longer asks
 * people to choose a lane the system doesn't actually have.
 */
export default function TranslatePage() {
  return (
    <Paywall feature="Translate" metric="translated">
      <TranslateEnhanced />
    </Paywall>
  );
}
