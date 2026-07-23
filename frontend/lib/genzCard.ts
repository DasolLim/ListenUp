// Renders a slang explanation to a branded, shareable card on a <canvas>.
// Original ListenUp design only (no external branding/IP). Colors mirror the
// DESIGN_SYSTEM tokens; hardcoded here because this is an exported static image,
// not live UI (canvas can't read CSS vars).

import type { Explanation } from "@/components/translate/TranslateGenz";

const SIZE = 1080;
const C = {
  bg1: "#F3E9E2",
  bg2: "#F0E6E9",
  bg3: "#E9DDF0",
  bg4: "#D9C9EC",
  panel: "rgba(255,255,255,0.74)",
  border: "rgba(255,255,255,0.75)",
  ink: "#2B2622",
  inkSoft: "#6B6259",
  inkFaint: "#9A9089",
  verified: "#2F6D4F",
  unverified: "#8A5A17",
};

/** Resolve the real (next/font-hashed) family list for a CSS variable. */
function resolveFont(cssVar: string): string {
  const probe = document.createElement("span");
  probe.style.fontFamily = `var(${cssVar})`;
  probe.style.position = "absolute";
  probe.style.visibility = "hidden";
  document.body.appendChild(probe);
  const family = getComputedStyle(probe).fontFamily || "sans-serif";
  probe.remove();
  return family;
}

function roundRect(
  ctx: CanvasRenderingContext2D,
  x: number,
  y: number,
  w: number,
  h: number,
  r: number
): void {
  ctx.beginPath();
  ctx.moveTo(x + r, y);
  ctx.arcTo(x + w, y, x + w, y + h, r);
  ctx.arcTo(x + w, y + h, x, y + h, r);
  ctx.arcTo(x, y + h, x, y, r);
  ctx.arcTo(x, y, x + w, y, r);
  ctx.closePath();
}

function wrap(ctx: CanvasRenderingContext2D, text: string, maxWidth: number, maxLines: number): string[] {
  const words = text.split(/\s+/).filter(Boolean);
  const lines: string[] = [];
  let line = "";
  for (const word of words) {
    const test = line ? `${line} ${word}` : word;
    if (ctx.measureText(test).width > maxWidth && line) {
      lines.push(line);
      line = word;
      if (lines.length === maxLines - 1) break;
    } else {
      line = test;
    }
  }
  if (line && lines.length < maxLines) lines.push(line);
  const used = lines.join(" ").split(/\s+/).filter(Boolean).length;
  if (used < words.length && lines.length) {
    lines[lines.length - 1] = lines[lines.length - 1].replace(/[.,;:]?$/, "…");
  }
  return lines;
}

/** Draw the card. Returns the canvas (sized SIZE×SIZE). */
export async function drawCard(canvas: HTMLCanvasElement, data: Explanation): Promise<void> {
  await document.fonts.ready;
  const display = resolveFont("--font-display");
  const body = resolveFont("--font-body");
  canvas.width = SIZE;
  canvas.height = SIZE;
  const ctx = canvas.getContext("2d");
  if (!ctx) return;

  // Background gradient (peach → lilac).
  const g = ctx.createLinearGradient(0, 0, SIZE, SIZE);
  g.addColorStop(0, C.bg1);
  g.addColorStop(0.45, C.bg2);
  g.addColorStop(0.75, C.bg3);
  g.addColorStop(1, C.bg4);
  ctx.fillStyle = g;
  ctx.fillRect(0, 0, SIZE, SIZE);

  // Glass panel.
  const M = 72;
  ctx.save();
  ctx.shadowColor = "rgba(60,45,80,0.14)";
  ctx.shadowBlur = 40;
  ctx.shadowOffsetY = 16;
  ctx.fillStyle = C.panel;
  roundRect(ctx, M, M, SIZE - M * 2, SIZE - M * 2, 44);
  ctx.fill();
  ctx.restore();
  ctx.strokeStyle = C.border;
  ctx.lineWidth = 1.5;
  roundRect(ctx, M, M, SIZE - M * 2, SIZE - M * 2, 44);
  ctx.stroke();

  const padX = M + 56;
  const maxW = SIZE - padX * 2;
  let y = M + 96;

  // Brand: coral orb + wordmark.
  const orb = ctx.createRadialGradient(padX + 12, y - 14, 4, padX + 20, y - 6, 30);
  orb.addColorStop(0, "#FBC9A8");
  orb.addColorStop(0.55, "#E8804F");
  orb.addColorStop(1, "#C9522B");
  ctx.fillStyle = orb;
  ctx.beginPath();
  ctx.arc(padX + 18, y - 8, 22, 0, Math.PI * 2);
  ctx.fill();
  ctx.fillStyle = C.ink;
  ctx.font = `600 34px ${display}`;
  ctx.textBaseline = "alphabetic";
  ctx.fillText("ListenUp", padX + 54, y);

  // Eyebrow.
  y += 74;
  ctx.fillStyle = C.inkFaint;
  ctx.font = `600 24px ${body}`;
  ctx.fillText("SLANG, EXPLAINED", padX, y);

  // Term (big display, up to 2 lines).
  y += 26;
  ctx.fillStyle = C.ink;
  ctx.font = `700 92px ${display}`;
  const termLines = wrap(ctx, data.term, maxW, 2);
  for (const l of termLines) {
    y += 92;
    ctx.fillText(l, padX, y);
  }

  // Confidence tag.
  y += 40;
  const low = data.confidence === "low";
  ctx.font = `600 26px ${body}`;
  const tag = low ? "UNVERIFIED — BEST GUESS" : "VERIFIED";
  const tw = ctx.measureText(tag).width;
  ctx.fillStyle = "rgba(255,255,255,0.85)";
  roundRect(ctx, padX, y - 30, tw + 40, 46, 23);
  ctx.fill();
  ctx.fillStyle = low ? C.unverified : C.verified;
  ctx.fillText(tag, padX + 20, y);

  // Meaning.
  y += 66;
  ctx.fillStyle = C.ink;
  ctx.font = `500 40px ${body}`;
  for (const l of wrap(ctx, data.plain_meaning, maxW, 3)) {
    y += 50;
    ctx.fillText(l, padX, y);
  }

  // Meta (origin • first seen • where).
  const meta = [data.origin, data.first_seen, data.region].filter(Boolean).join("   •   ");
  if (meta) {
    y += 52;
    ctx.fillStyle = C.inkSoft;
    ctx.font = `400 26px ${body}`;
    for (const l of wrap(ctx, meta, maxW, 2)) {
      y += 32;
      ctx.fillText(l, padX, y);
    }
  }

  // Example (quiet sub-panel).
  if (data.example) {
    y += 44;
    ctx.font = `italic 400 30px ${body}`;
    const exLines = wrap(ctx, `“${data.example}”`, maxW - 56, 3);
    const boxH = 40 + exLines.length * 42;
    ctx.fillStyle = "rgba(255,255,255,0.5)";
    roundRect(ctx, padX, y, maxW, boxH, 22);
    ctx.fill();
    ctx.fillStyle = C.inkSoft;
    let ey = y + 34;
    for (const l of exLines) {
      ctx.fillText(l, padX + 28, ey);
      ey += 42;
    }
    y += boxH;
  }

  // Footer brand line pinned to the panel bottom.
  ctx.fillStyle = C.inkFaint;
  ctx.font = `500 24px ${body}`;
  ctx.fillText("listenup.app  ·  understand every conversation", padX, SIZE - M - 44);
}

export function cardToBlob(canvas: HTMLCanvasElement): Promise<Blob | null> {
  return new Promise((resolve) => canvas.toBlob((b) => resolve(b), "image/png"));
}
