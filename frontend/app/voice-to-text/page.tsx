import type { Metadata } from "next";
import Link from "next/link";

export const metadata: Metadata = { title: "Voice-to-Text — ListenUp" };

export default function VoiceToTextPage() {
  return (
    <div className="mx-auto max-w-2xl">
      <h1 className="text-3xl font-bold">Voice-to-Text</h1>
      <p className="mt-4 text-zinc-600 dark:text-zinc-300">
        Live captions that separate speakers, so conversation is readable — not a wall of text.
      </p>
      <ul className="mt-6 flex flex-col gap-3">
        <li>
          <Link href="/voice-to-text/general" className="underline focus-visible:outline-2 focus-visible:outline-offset-2">
            General — live captions with speaker separation
          </Link>
        </li>
        <li>
          <Link href="/voice-to-text/enhanced" className="underline focus-visible:outline-2 focus-visible:outline-offset-2">
            Enhanced — saved voice profiles, people labeled by name
          </Link>
        </li>
      </ul>
    </div>
  );
}
