import { expect, test } from "@playwright/test";

import { contrastFindings, gotoSettled } from "./support";

/**
 * AA contrast on the glass, measured from pixels.
 *
 * This exists because `a11y.spec.ts` cannot do it. Axe reports zero contrast
 * violations on `/` and 84 results marked *incomplete* — it cannot determine a
 * background over a gradient — and gradient-under-frosted-glass is the whole
 * design system. Proven by mutation: `--text-secondary` was set to a near-white
 * `#cfc9c2`, putting 36 elements of pale grey on pale peach, and axe stayed
 * green.
 *
 * High contrast is included because it is a separate palette, not a filter:
 * `[data-contrast="high"]` redefines the tokens, so it can regress on its own.
 */
const PAGES = ["/", "/about", "/product", "/design", "/login"];

for (const path of PAGES) {
  for (const contrast of [false, true]) {
    test(`${path} text meets AA against what is painted behind it${
      contrast ? " in high contrast" : ""
    }`, async ({ page }) => {
      await gotoSettled(page, path, { contrast });
      const findings = await contrastFindings(page);
      expect(
        findings.map((f) => `${f.ratio}:1 (needs ${f.required}) ${f.selector} — "${f.text}"`),
        JSON.stringify(findings, null, 1)
      ).toEqual([]);
    });
  }
}
