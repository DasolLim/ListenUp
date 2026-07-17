import type { Metadata } from "next";

export const metadata: Metadata = { title: "About — ListenUp" };

export default function AboutPage() {
  return (
    <article className="prose-zinc mx-auto max-w-2xl">
      <h1 className="text-3xl font-bold">About ListenUp</h1>
      <p className="mt-4 text-zinc-600 dark:text-zinc-300">
        Existing captioning tools produce a wall of text — you can&apos;t tell who said what.
        Existing translators translate words, not meaning — they miss slang, tone, and culture.
      </p>
      <p className="mt-4 text-zinc-600 dark:text-zinc-300">
        ListenUp exists to fix both. We build live captions that name each speaker — including the
        people you talk to most — and translation that explains register, slang, and cultural
        nuance. Built first for deaf and hard-of-hearing users; useful to anyone navigating a
        conversation across languages or cultures.
      </p>
    </article>
  );
}
