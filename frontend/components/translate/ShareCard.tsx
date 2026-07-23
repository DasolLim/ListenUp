"use client";

import { useEffect, useRef, useState } from "react";
import Button from "@/components/ui/Button";
import { cardToBlob, drawCard } from "@/lib/genzCard";
import type { Explanation } from "./TranslateGenz";

export default function ShareCard({ data }: { data: Explanation }) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [status, setStatus] = useState<string | null>(null);
  const canCopy =
    typeof navigator !== "undefined" &&
    !!navigator.clipboard &&
    typeof ClipboardItem !== "undefined";

  useEffect(() => {
    const canvas = canvasRef.current;
    if (canvas) void drawCard(canvas, data);
  }, [data]);

  async function download() {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const blob = await cardToBlob(canvas);
    if (!blob) return;
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `listenup-${data.term.replace(/\s+/g, "-").slice(0, 40) || "slang"}.png`;
    a.click();
    URL.revokeObjectURL(url);
    setStatus("Downloaded.");
  }

  async function copy() {
    const canvas = canvasRef.current;
    if (!canvas) return;
    try {
      const blob = await cardToBlob(canvas);
      if (!blob) throw new Error("no blob");
      await navigator.clipboard.write([new ClipboardItem({ "image/png": blob })]);
      setStatus("Card copied to clipboard.");
    } catch {
      setStatus("Couldn’t copy the image — use Download instead.");
    }
  }

  return (
    <div className="flex flex-col gap-3">
      <canvas
        ref={canvasRef}
        role="img"
        aria-label={`Shareable card explaining ${data.term}`}
        className="w-full max-w-xs rounded-2xl border border-white/60 shadow-glass"
      />
      <div className="flex flex-wrap items-center gap-2">
        <Button type="button" onClick={download}>
          Download PNG
        </Button>
        {canCopy && (
          <Button type="button" variant="ghost" onClick={copy}>
            Copy image
          </Button>
        )}
        {status && (
          <span role="status" className="text-[12px] text-ink-soft">
            {status}
          </span>
        )}
      </div>
    </div>
  );
}
