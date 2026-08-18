import type { Page } from "@playwright/test";

/**
 * Shared setup for checks that measure *rendered* facts — contrast, geometry,
 * hit areas.
 *
 * Two sources of non-determinism have to go before any of those can be
 * asserted, and both were found the hard way by a suite that failed on three
 * pages and was right about none of them:
 *
 * 1. `Reveal` fades sections in on scroll, so the page really does contain
 *    semi-transparent text for a few hundred milliseconds. Axe measures what is
 *    painted and reported 47 violations on `/` — correct about the pixels,
 *    useless as a signal. Reduced motion (set per-file via `test.use`) stops
 *    `Reveal` arming at all, which is the documented no-JS/reduced-motion path.
 *
 * 2. `A11yBar` applies the stored preference in a `requestAnimationFrame` after
 *    hydration, and its own toggle carries `transition-colors` — so the button
 *    animates from off to on and axe caught it mid-transition. That one flipped
 *    between runs, which is worse than failing: a suite that is right four
 *    times out of five teaches people to re-run it.
 *
 * The fix is to kill transitions rather than to sleep until they finish. A
 * timing race resolved by waiting comes back on a slower machine, and contrast
 * is a property of the settled design — nobody is asked to read a frame that
 * exists for 80ms.
 */
const STILL = `*, *::before, *::after {
  transition-duration: 0s !important;
  animation-duration: 0s !important;
  animation-delay: 0s !important;
}`;

export async function gotoSettled(
  page: Page,
  path: string,
  { contrast = false }: { contrast?: boolean } = {}
): Promise<void> {
  await page.addInitScript(
    ({ still, high }) => {
      if (high) sessionStorage.setItem("a11y-contrast", "high");
      // Injected at document start so the very first paint is already still.
      document.addEventListener("DOMContentLoaded", () => {
        const style = document.createElement("style");
        style.textContent = still;
        document.head.append(style);
      });
    },
    { still: STILL, high: contrast }
  );
  // Not for speed: `Reveal` fades sections in on scroll, so the page genuinely
  // holds semi-transparent text for a few hundred milliseconds, and axe was
  // right to flag 47 of them on `/`. Reduced motion is the documented
  // no-JS/reduced-motion path — `Reveal` never arms, content renders at final
  // opacity immediately — and it is the rendering an a11y suite should assert
  // about anyway. Set here rather than in the config because `reducedMotion` is
  // documented but not declared in this version's test-options types.
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.goto(path);
  if (contrast) {
    // Seeded through sessionStorage, which is where `A11yBar` reads it, so the
    // real code path runs. Stamping `data-contrast` directly would keep passing
    // if the control ever stopped writing it.
    await page.waitForSelector('html[data-contrast="high"]');
  }
  await page.evaluate(() => document.fonts.ready);
  await assertStyled(page);
}

/**
 * Refuse to measure an unstyled page.
 *
 * Found by mutation: a contrast token was deliberately broken, the suite stayed
 * green, and the reason was that the server was serving HTML that referenced a
 * stylesheet chunk from a different build — the CSS 500'd, the page rendered as
 * black-on-white unstyled text, and every contrast check passed trivially.
 *
 * That is the worst failure a feedback loop can have: it is loudest exactly
 * when the design is most broken. Every rendered assertion in this suite is
 * meaningless without the design tokens, so the tokens are checked first.
 */
async function assertStyled(page: Page): Promise<void> {
  const probe = await page.evaluate(() => {
    const root = getComputedStyle(document.documentElement);
    return {
      secondary: root.getPropertyValue("--text-secondary").trim(),
      accent: root.getPropertyValue("--accent-strong").trim(),
      sheets: document.styleSheets.length,
    };
  });
  if (!probe.secondary || !probe.accent) {
    throw new Error(
      `Design tokens did not load (--text-secondary=${probe.secondary}, ` +
        `--accent-strong=${probe.accent}, ${probe.sheets} stylesheets). ` +
        "The page is unstyled, so every contrast and layout assertion here " +
        "would pass for the wrong reason. Rebuild the frontend (rm -rf .next " +
        "&& npm run build) rather than trusting this run."
    );
  }
}

/** One piece of text whose rendered contrast falls below its WCAG AA bar. */
export type ContrastFinding = {
  text: string;
  selector: string;
  color: string;
  background: string;
  ratio: number;
  required: number;
};

/**
 * Measure text contrast from the **rendered pixels**.
 *
 * Axe cannot do this here. Asked about `/`, it reports zero violations and 84
 * results marked *incomplete* — "background color could not be determined due
 * to a background gradient" — and this product is a peach→lilac gradient under
 * frosted glass from edge to edge. So axe's contrast rule is blind on almost
 * every surface the design system defines, and the repeated "0 axe violations"
 * in the decisions log was a weaker claim than it read.
 *
 * That was not a suspicion: `--text-secondary` was set to a near-white
 * `#cfc9c2`, which put 36 elements of pale grey on pale peach, and the axe
 * suite stayed green.
 *
 * The method sidesteps the whole problem of *deriving* a background: take one
 * screenshot, hand it back to the page as an image, and read the actual pixels
 * behind each run of text. A gradient, a backdrop-filter and an image tile are
 * all just pixels by then. The background is the most common colour in the
 * element's box after discarding anything close to the text colour — glyphs
 * cover a minority of a line box, so the mode is the ground they sit on.
 */
export async function contrastFindings(page: Page): Promise<ContrastFinding[]> {
  const shot = (await page.screenshot({ scale: "css" })).toString("base64");
  return page.evaluate(async (png) => {
    const image = new Image();
    image.src = `data:image/png;base64,${png}`;
    await image.decode();
    const canvas = document.createElement("canvas");
    canvas.width = image.width;
    canvas.height = image.height;
    const ctx = canvas.getContext("2d")!;
    ctx.drawImage(image, 0, 0);

    const parse = (value: string): [number, number, number] => {
      const [r, g, b] = value.match(/[\d.]+/g)!.map(Number);
      return [r, g, b];
    };
    const luminance = ([r, g, b]: [number, number, number]) => {
      const f = (c: number) => {
        const s = c / 255;
        return s <= 0.03928 ? s / 12.92 : ((s + 0.055) / 1.055) ** 2.4;
      };
      return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b);
    };
    const ratio = (a: [number, number, number], b: [number, number, number]) => {
      const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x);
      return (hi + 0.05) / (lo + 0.05);
    };
    const distance = (a: [number, number, number], b: [number, number, number]) =>
      Math.abs(a[0] - b[0]) + Math.abs(a[1] - b[1]) + Math.abs(a[2] - b[2]);

    const findings = [];
    for (const el of Array.from(document.querySelectorAll<HTMLElement>("*"))) {
      // Leaf text only. A wrapper's box spans its children, so its "background"
      // would be whatever its biggest child happens to be painted in.
      const text = Array.from(el.childNodes)
        .filter((n) => n.nodeType === Node.TEXT_NODE)
        .map((n) => n.textContent ?? "")
        .join("")
        .trim();
      if (!text) continue;

      const style = getComputedStyle(el);
      if (style.visibility === "hidden" || style.display === "none") continue;
      if (Number(style.opacity) < 0.99) continue;
      const box = el.getBoundingClientRect();
      // Off-screen, clipped to nothing, or `sr-only`: not read by a sighted
      // user, and the pixels under it are somebody else's.
      if (box.width < 4 || box.height < 4) continue;
      if (box.top < 0 || box.left < 0 || box.bottom > innerHeight || box.right > innerWidth)
        continue;

      const fg = parse(style.color);
      const size = parseFloat(style.fontSize);
      const bold = Number(style.fontWeight) >= 700;
      // WCAG 1.4.3: large text (>=24px, or >=18.66px bold) needs only 3:1.
      const required = size >= 24 || (bold && size >= 18.66) ? 3 : 4.5;

      const { data } = ctx.getImageData(
        Math.round(box.left),
        Math.round(box.top),
        Math.round(box.width),
        Math.round(box.height)
      );
      const counts = new Map<string, number>();
      for (let i = 0; i < data.length; i += 4) {
        const px: [number, number, number] = [data[i], data[i + 1], data[i + 2]];
        if (distance(px, fg) < 90) continue; // a glyph or its antialiasing
        const key = `${px[0]},${px[1]},${px[2]}`;
        counts.set(key, (counts.get(key) ?? 0) + 1);
      }
      if (!counts.size) continue;
      const [modal] = [...counts.entries()].sort((a, b) => b[1] - a[1])[0];
      const bg = parse(modal);

      const measured = ratio(fg, bg);
      if (measured < required) {
        findings.push({
          text: text.slice(0, 40),
          selector: `${el.tagName.toLowerCase()}.${el.className.toString().split(" ")[0]}`,
          color: style.color,
          background: `rgb(${modal})`,
          ratio: Math.round(measured * 100) / 100,
          required,
        });
      }
    }
    return findings;
  }, shot);
}
