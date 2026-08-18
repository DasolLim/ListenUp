import { expect, test } from "@playwright/test";

import { gotoSettled } from "./support";

/**
 * Geometry facts, which only a laid-out page knows.
 *
 * Both checks exist because this project shipped the bug they catch: a
 * conversation pane whose bottom edge sat 61px below the fold (measured, not
 * eyeballed — it recreated the original complaint in miniature), and an 18px
 * tap-to-correct target a phone user could not reliably hit.
 */
const PAGES = ["/", "/about", "/product", "/design", "/login"];
const VIEWPORTS = [
  { name: "phone", width: 390, height: 844 },
  { name: "tablet", width: 834, height: 1112 },
  { name: "desktop", width: 1440, height: 900 },
];

for (const { name, width, height } of VIEWPORTS) {
  for (const path of PAGES) {
    test(`${path} does not scroll sideways on ${name}`, async ({ page }) => {
      await page.setViewportSize({ width, height });
      await gotoSettled(page, path);
      const overflow = await page.evaluate(() => {
        const root = document.documentElement;
        if (root.scrollWidth <= root.clientWidth + 1) return null;
        // Name the widest offender. "scrollWidth 431 > 390" sends the next
        // reader hunting; a selector does not.
        const guilty = Array.from(document.querySelectorAll<HTMLElement>("*"))
          .map((el) => ({ el, right: el.getBoundingClientRect().right }))
          .filter((x) => x.right > root.clientWidth + 1)
          .sort((a, b) => b.right - a.right)[0];
        return {
          scrollWidth: root.scrollWidth,
          clientWidth: root.clientWidth,
          widest: guilty
            ? `${guilty.el.tagName.toLowerCase()}.${String(guilty.el.className)
                .split(" ")
                .slice(0, 3)
                .join(".")} @ ${Math.round(guilty.right)}px`
            : "unknown",
        };
      });
      expect(overflow, `horizontal overflow on ${name}`).toBeNull();
    });
  }
}

test.describe("touch targets", () => {
  const INTERACTIVE =
    'a, button, input:not([type="hidden"]), select, textarea, [role="button"], [role="switch"]';

  for (const path of PAGES) {
    test(`${path} interactive controls are reachable with a thumb`, async ({ page }) => {
      await page.setViewportSize({ width: 390, height: 844 });
      await gotoSettled(page, path);

      const small = await page.evaluate((selector) => {
        const MIN = 44;
        const bad: string[] = [];
        for (const el of Array.from(document.querySelectorAll<HTMLElement>(selector))) {
          const box = el.getBoundingClientRect();
          if (box.width === 0 || box.height === 0) continue;
          const cx = box.left + box.width / 2;
          const cy = box.top + box.height / 2;
          if (cx < 0 || cy < 0 || cx > innerWidth || cy > innerHeight) continue;

          // Precondition, and the reason an earlier version of this check
          // reported five failures for elements that were not on screen at
          // all: if the centre does not hit the control, it is covered,
          // clipped out of a scroll container, or behind an overlay — and its
          // *size* is not what is wrong with it.
          const centre = document.elementFromPoint(cx, cy);
          if (!centre || !(el.contains(centre) || centre.contains(el))) continue;

          // Hit-tested, never measured. `SpeakerName` expands an 18px label to
          // 44px with a `before:` pseudo-element, which a bounding box cannot
          // see — and `.bubble-glass` has a backdrop-filter, so it paints as
          // though positioned and covers that invisible band unless the label
          // is raised above it. Both facts are invisible to
          // `getBoundingClientRect`, which is why an earlier bounding-box
          // version of this check was wrong in both directions.
          const reach = (dx: number, dy: number) => {
            const hit = document.elementFromPoint(cx + dx, cy + dy);
            return !!hit && (el.contains(hit) || hit.contains(el) || hit === el);
          };
          // Two bars, because a control's width is not always its own choice.
          // An icon-only button picks both dimensions, so it owes 44x44 — that
          // is the control this rule exists for. A text link's width is its
          // label: demanding 44px of "About" means inventing padding to satisfy
          // a checker, and WCAG 2.5.8 asks 24px of a target sized by its text.
          // Height is the dimension a thumb misses on a phone, and both kinds
          // owe the full 44 there.
          const labelled = (el.textContent ?? "").trim().length > 0;
          const rx = (labelled ? 24 : MIN) / 2 - 1;
          const ry = MIN / 2 - 1;
          const wide = reach(-rx, 0) && reach(rx, 0);
          const tall = reach(0, -ry) && reach(0, ry);
          if (!wide || !tall) {
            bad.push(
              `${el.tagName.toLowerCase()}${el.id ? "#" + el.id : ""} ` +
                `"${(el.textContent ?? "").trim().slice(0, 24)}" ` +
                `${Math.round(box.width)}x${Math.round(box.height)}` +
                `${!wide ? " (too narrow)" : ""}${!tall ? " (too short)" : ""}`
            );
          }
        }
        return bad;
      }, INTERACTIVE);

      // The skip link is `sr-only` until focused, and correctly small.
      expect(small.filter((s) => !s.includes("Skip to"))).toEqual([]);
    });
  }
});
