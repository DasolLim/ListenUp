import type { Metadata } from "next";
import Link from "next/link";

export const metadata: Metadata = { title: "Translate — ListenUp" };

export default function TranslatePage() {
  return (
    <div className="mx-auto max-w-2xl">
      <h1 className="text-3xl font-bold">Translate</h1>
      <p className="mt-4 text-zinc-600 dark:text-zinc-300">
        Translation that carries meaning — register, slang, and cultural nuance included.
      </p>
      <ul className="mt-6 flex flex-col gap-3">
        <li>
          <Link href="/translate/general" className="underline focus-visible:outline-2 focus-visible:outline-offset-2">
            General — fast translation, wide language coverage
          </Link>
        </li>
        <li>
          <Link href="/translate/enhanced" className="underline focus-visible:outline-2 focus-visible:outline-offset-2">
            Enhanced — cultural translation with register and slang notes
          </Link>
        </li>
        <li>
          <Link href="/translate/genz" className="underline focus-visible:outline-2 focus-visible:outline-offset-2">
            GenZ — internet slang and memes, explained
          </Link>
        </li>
      </ul>
    </div>
  );
}
