/**
 * The two translation lanes race, and either can land first.
 *
 * Run: `node scripts/verify-translation-merge.mjs` from /frontend.
 *
 * The merges live in `lib/translationMerge.ts` — no React import — so this
 * loads the real module rather than cutting the hook out of a hook's file with
 * a regex, which is what it used to do.
 *
 * This is worth pinning because the failure is silent and per-utterance: when
 * the cultural lane won the race its whole result was discarded, so one line
 * kept its slang explanation and the next one lost it permanently, with nothing
 * on screen to say so. A reader who cannot hear the original has no way to tell
 * an unexplained line from one with nothing to explain.
 */
import { harness, loadTs } from "./lib/harness.mjs";

const { mergeFastLane, mergeCulturalLane, newestSpeakableLine } = await loadTs(
  new URL("../lib/translationMerge.ts", import.meta.url)
);

const h = harness();
const check = h.check;

const NOTE = {
  phrase: "no cap",
  meaning: "no lie",
  cultural_context: "from hip-hop; 'cap' means a lie",
  equivalent: "de verdad",
  confidence: "high",
};
const FAST = { translation: "그 영화 최고였어", detectedSourceLang: "en" };
const CULTURAL = { translation: "그 영화 진짜 갓띵작", register: "slang-heavy", slangNotes: [NOTE] };

console.log("\nexpected order: fast, then cultural");
{
  const afterFast = mergeFastLane(undefined, FAST);
  check("fast lane alone shows the literal translation", afterFast.text, FAST.translation);
  check("fast lane records the source language", afterFast.sourceLang, "en");
  check("fast lane has no explanation yet", [afterFast.notes.length, afterFast.register], [0, null]);

  const afterCultural = mergeCulturalLane(afterFast, CULTURAL);
  check("cultural upgrade replaces the text", afterCultural.text, CULTURAL.translation);
  check("cultural upgrade adds the notes", afterCultural.notes, [NOTE]);
  check("cultural upgrade adds the register", afterCultural.register, "slang-heavy");
  check("source language survives the upgrade", afterCultural.sourceLang, "en");
}

console.log("\nreversed order: cultural first (a cached LLM answer beats Google)");
{
  const afterCultural = mergeCulturalLane(undefined, CULTURAL);
  check("cultural result stands alone", afterCultural.text, CULTURAL.translation);
  check("the explanation is kept, not dropped", afterCultural.notes, [NOTE]);
  check("the register is kept", afterCultural.register, "slang-heavy");

  const afterFast = mergeFastLane(afterCultural, FAST);
  check("the late fast lane does NOT overwrite the better text", afterFast.text, CULTURAL.translation);
  check("the late fast lane does NOT wipe the notes", afterFast.notes, [NOTE]);
  check("the late fast lane does NOT wipe the register", afterFast.register, "slang-heavy");
  check("the late fast lane still contributes the source language", afterFast.sourceLang, "en");
}

console.log("\npartial answers");
{
  // Notes but no adapted translation: keep the literal line, attach the notes.
  const afterFast = mergeFastLane(undefined, FAST);
  const notesOnly = mergeCulturalLane(afterFast, { slangNotes: [NOTE] });
  check("notes without a translation keep the literal text", notesOnly.text, FAST.translation);
  check("notes without a translation still attach", notesOnly.notes, [NOTE]);

  // An adapted translation with nothing to explain is normal, not a failure.
  const noNotes = mergeCulturalLane(afterFast, { translation: "번역", register: "casual" });
  check("a translation with no slang keeps an empty note list", noNotes.notes, []);
  check("register still lands with no notes", noNotes.register, "casual");
}

console.log("\nshape");
{
  const fromNothing = mergeCulturalLane(undefined, { slangNotes: [NOTE] });
  check(
    "every field is present even when built from nothing",
    Object.keys(fromNothing).sort(),
    ["notes", "register", "sourceLang", "text"]
  );
  check("text is a string, never undefined", typeof fromNothing.text, "string");
}


// ── What may be read aloud ───────────────────────────────────────────────────
// Reported as "read aloud says the wrong thing": the two lanes race, and
// speaking on first arrival read out the literal translation while the screen
// showed the culturally adapted one. Audible on the interpreter path, where the
// person opposite only ever hears this version.
console.log("\nspeakable line");
{
  const seg = (id, isFinal) => ({ id, isFinal, speaker: "A", speakerName: null, text: "x", start: 0, end: 1 });
  const segments = [seg("a", true), seg("b", true), seg("c", false)];
  const translated = { a: { text: "A" }, b: { text: "B" }, c: { text: "C" } };
  const all = () => true;
  const none = () => false;

  check("picks the newest settled final", newestSpeakableLine(segments, translated, all)?.id, "b");
  check("never an interim line", newestSpeakableLine([seg("c", false)], translated, all), undefined);
  check("nothing while unsettled", newestSpeakableLine(segments, translated, none), undefined);
  check(
    "skips back to the newest line that has settled",
    newestSpeakableLine(segments, translated, (id) => id === "a")?.id,
    "a"
  );
  check(
    "a line with no translation yet is not speakable",
    newestSpeakableLine(segments, { a: { text: "A" } }, all)?.id,
    "a"
  );
  check("nothing to say", newestSpeakableLine([], {}, all), undefined);
}

h.done();
