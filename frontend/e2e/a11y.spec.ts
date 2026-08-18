import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

import { gotoSettled } from "./support";

/**
 * WCAG 2.1 AA is build-breaking for this product (CLAUDE.md), and contrast is
 * a *computed* property — it depends on the glass opacity, the gradient behind
 * it, and the token that won the cascade. Nothing short of a rendered page
 * knows the answer, which is why this check lives here and not in a unit test.
 *
 * **The unit under test is a page in a contrast mode**, not a component. Axe on
 * a single mounted component re-tests what the primitive gallery already covers
 * and misses the only interesting case: a component on the background it is
 * actually used against.
 *
 * High contrast is seeded through `sessionStorage`, which is where `A11yBar`
 * reads it — driving the real code path rather than stamping the attribute the
 * CSS keys on. A test that sets `data-contrast` directly would keep passing if
 * the control stopped writing it.
 */

/**
 * Public routes.
 *
 * The five tool pages are auth-gated, so nothing they render reaches this loop
 * — a comment here used to claim they were "covered in `app.spec.ts`", which
 * does not exist. `/design` is the gallery that closes the worst of that gap:
 * the conversation pane, shared by live captions and Translate's voice mode, is
 * rendered there, and measuring it found two pieces of text that had been below
 * AA since they were written.
 */
const PAGES = ["/", "/about", "/product", "/design", "/login"];

// Reduced motion is set suite-wide in `playwright.config.ts`; see the note there.

for (const path of PAGES) {
  for (const contrast of [false, true]) {
    test(`${path} has no axe violations${contrast ? " in high contrast" : ""}`, async ({
      page,
    }) => {
      await gotoSettled(page, path, { contrast });

      const { violations } = await new AxeBuilder({ page })
        .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"])
        .analyze();

      // Named rather than counted: `expect(violations).toHaveLength(0)` prints
      // "expected 0, got 3", which starts the next debugging session from zero.
      expect(
        violations.map((v) => `${v.id}: ${v.nodes.length}x ${v.help}`),
        JSON.stringify(
          violations.map((v) => ({ id: v.id, nodes: v.nodes.map((n) => n.html) })),
          null,
          1
        )
      ).toEqual([]);
    });
  }
}
