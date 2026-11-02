"use client";

import { useEffect, useState } from "react";

const BACKEND = process.env.NEXT_PUBLIC_BACKEND_URL ?? "http://localhost:8000";

type Info = {
  languages: Record<string, string>;
  modes: Record<string, "streaming" | "batch">;
};

/** Which language the MIC is speaking (distinct from the translation target).
 * Languages with no streaming model are captioned in buffered batches, so we
 * say plainly that they arrive a few seconds behind rather than looking stuck. */
export default function SpokenLanguagePicker({
  value,
  onChange,
  disabled,
  id = "spoken-language",
}: {
  value: string;
  onChange: (code: string) => void;
  disabled?: boolean;
  id?: string;
}) {
  const [info, setInfo] = useState<Info>({ languages: { en: "English" }, modes: { en: "streaming" } });

  useEffect(() => {
    const controller = new AbortController();
    fetch(`${BACKEND}/transcribe/languages`, { signal: controller.signal })
      .then((r) => r.json())
      .then((body: Info) => {
        if (body?.languages) setInfo(body);
      })
      .catch(() => undefined);
    return () => controller.abort();
  }, []);

  const batched = info.modes?.[value] === "batch";

  return (
    <div className="flex flex-wrap items-center gap-2">
      <label htmlFor={id} className="text-sm font-medium text-ink">
        Spoken language
      </label>
      <select
        id={id}
        value={value}
        disabled={disabled}
        onChange={(e) => onChange(e.target.value)}
        className="glass-strong min-h-11 rounded-xl border border-white/60 px-3 text-sm text-ink shadow-glass outline-none disabled:opacity-50"
      >
        {Object.entries(info.languages).map(([code, name]) => (
          <option key={code} value={code}>
            {name}
          </option>
        ))}
      </select>
      {batched && (
        <span role="status" className="text-[12px] text-warning-strong">
          Korean has no live model yet — captions arrive a few seconds behind.
        </span>
      )}
    </div>
  );
}
