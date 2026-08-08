import type { Metadata } from "next";
import Paywall from "@/components/billing/Paywall";
import TranslateGenz from "@/components/translate/TranslateGenz";

export const metadata: Metadata = { title: "Explain a term — ListenUp" };

/**
 * Not a third translator — a dictionary.
 *
 * Translate answers "what does this mean in Korean?"; this answers "what does
 * 'fanum tax' mean?". Different input, different output, different moment. It
 * was previously named after its audience (GenZ), which told you who it was for
 * but not what it did, and left it competing with cultural translation for the
 * same job.
 */
export default function ExplainPage() {
  return (
    <Paywall feature="Explain a term" metric="explain">
      <TranslateGenz />
    </Paywall>
  );
}
