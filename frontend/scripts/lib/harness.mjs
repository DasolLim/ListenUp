/**
 * Load a TypeScript module for the node checks, and count assertions.
 *
 * Every check script used to carry its own copy of the transpile dance, and two
 * of them stripped imports with a regex first — `verify-translation-merge.mjs`
 * cut the React hook out of `useLiveTranslation.ts` by matching
 * `^export function useLiveTranslation[\s\S]*$`, which worked only because the
 * pure functions happened to sit above the hook. Nothing enforced that
 * ordering, so the day someone moved one the check would have silently stopped
 * covering it.
 *
 * The real fix was upstream: pure logic now lives in modules with no React
 * import, so they load as they are. This follows the `@/lib/…` imports between
 * them, which is what lets those modules depend on each other instead of each
 * carrying its own copy of, say, a percentile.
 */
import { mkdtempSync, readFileSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import ts from "typescript";

const LIB = join(dirname(fileURLToPath(import.meta.url)), "..", "..", "lib");

function transpile(source) {
  return ts.transpileModule(source, {
    compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ESNext },
  }).outputText;
}

/**
 * Transpile a module under `lib/` and everything it imports from `@/lib/`,
 * then import it. Type-only imports are dropped; `@/lib/x` becomes `./x.mjs`.
 */
export async function loadTs(url) {
  const dir = mkdtempSync(join(tmpdir(), "listenup-"));
  const written = new Set();

  const emit = (name) => {
    if (written.has(name)) return;
    written.add(name);
    const source = readFileSync(join(LIB, `${name}.ts`), "utf8").replace(
      /^import type .*$/gm,
      ""
    );
    for (const [, dep] of source.matchAll(/from "@\/lib\/([\w-]+)"/g)) emit(dep);
    writeFileSync(
      join(dir, `${name}.mjs`),
      transpile(source).replace(/from ["']@\/lib\/([\w-]+)["']/g, 'from "./$1.mjs"')
    );
  };

  const entry = fileURLToPath(url).replace(/\.ts$/, "").split("/").pop();
  emit(entry);
  return import(join(dir, `${entry}.mjs`));
}

/** A tiny assertion counter, shared so every script reports the same way. */
export function harness() {
  let pass = 0;
  let fail = 0;
  return {
    check(name, actual, expected) {
      if (JSON.stringify(actual) === JSON.stringify(expected)) {
        pass += 1;
        console.log(`  ok   ${name}`);
      } else {
        fail += 1;
        console.log(
          `  FAIL ${name}\n    expected ${JSON.stringify(expected)}\n    actual   ${JSON.stringify(actual)}`
        );
      }
    },
    section(title) {
      console.log(`\n${title}`);
    },
    done() {
      console.log(`\n${pass}/${pass + fail} checks passed`);
      if (fail) process.exit(1);
    },
  };
}
