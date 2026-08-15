/**
 * The two translation lanes race, and either can land first.
 *
 * Run: `node scripts/verify-translation-merge.mjs` from /frontend.
 *
 * This is worth pinning because the failure is silent and per-utterance: when
 * the cultural lane won the race its whole result was discarded, so one line
 * kept its slang explanation and the next one lost it permanently, with nothing
 * on screen to say so. A reader who cannot hear the original has no way to tell
 * an unexplained line from one with nothing to explain.
 */
import { readFileSync, writeFileSync, mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import ts from "typescript";

const source = readFileSync(new URL("../lib/useLiveTranslation.ts", import.meta.url), "utf8")
  // Strip the React hook and its imports; only the pure merges are under test.
  .replace(/^import .*$/gm, "")
  .replace(/^export function useLiveTranslation[\s\S]*$/m, "");

const js = ts.transpileModule(source, {
  compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ESNext },
}).outputText;

const file = join(mkdtempSync(join(tmpdir(), "merge-")), "merge.mjs");
writeFileSync(file, js);
const { mergeFastLane, mergeCulturalLane } = await import(file);

let pass = 0;
let fail = 0;
function check(name, actual, expected) {
  if (JSON.stringify(actual) === JSON.stringify(expected)) {
    pass += 1;
    console.log(`  ok   ${name}`);
  } else {
    fail += 1;
    console.log(
      `  FAIL ${name}\n    expected ${JSON.stringify(expected)}\n    actual   ${JSON.stringify(actual)}`
    );
  }
}

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

console.log(`\n${pass}/${pass + fail} checks passed`);
process.exit(fail === 0 ? 0 : 1);
