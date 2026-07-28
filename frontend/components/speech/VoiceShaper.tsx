"use client";

import { type VoiceShape } from "@/lib/useSpeech";

type Limits = { pitch: { min: number; max: number }; rate: { min: number; max: number } };

/**
 * Named starting points, so nobody meets two raw sliders first. Each is a real
 * pitch/rate pair, not a label on nothing.
 *
 * "Deeper" and "Lighter" are how a gender dial actually works in browser TTS:
 * there is no morph parameter, but pitch genuinely moves a voice along that
 * range. "Slower and clearer" exists because rate is an accessibility control
 * in its own right.
 */
const PRESETS: { label: string; shape: VoiceShape }[] = [
  { label: "Default", shape: { pitch: 1, rate: 1 } },
  { label: "Deeper", shape: { pitch: 0.7, rate: 0.95 } },
  { label: "Lighter", shape: { pitch: 1.45, rate: 1 } },
  { label: "Slower, clearer", shape: { pitch: 1, rate: 0.75 } },
];

function isActive(shape: VoiceShape, preset: VoiceShape) {
  return (
    Math.abs(shape.pitch - preset.pitch) < 0.02 && Math.abs(shape.rate - preset.rate) < 0.02
  );
}

export default function VoiceShaper({
  shape,
  limits,
  onChange,
  onReset,
}: {
  shape: VoiceShape;
  limits: Limits;
  onChange: (next: Partial<VoiceShape>) => void;
  onReset: () => void;
}) {
  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap gap-2" role="group" aria-label="Voice presets">
        {PRESETS.map((preset) => {
          const active = isActive(shape, preset.shape);
          return (
            <button
              key={preset.label}
              type="button"
              aria-pressed={active}
              onClick={() => onChange(preset.shape)}
              className={`inline-flex min-h-11 items-center rounded-full px-3.5 text-[13px] font-medium transition-colors ${
                active
                  ? "bg-accent-strong text-on-accent"
                  : "pill-inactive text-ink-soft hover:text-ink"
              }`}
            >
              {preset.label}
            </button>
          );
        })}
      </div>

      <div className="grid gap-4 sm:grid-cols-2">
        <div className="flex flex-col gap-1">
          <label htmlFor="shape-pitch" className="flex justify-between text-[13px] text-ink">
            <span>Pitch</span>
            {/* The numeric value is shown because a slider alone gives a
                screen-reader user nothing to compare against. */}
            <span className="numeric text-ink-soft">{shape.pitch.toFixed(2)}×</span>
          </label>
          <input
            id="shape-pitch"
            type="range"
            min={limits.pitch.min}
            max={limits.pitch.max}
            step={0.05}
            value={shape.pitch}
            onChange={(event) => onChange({ pitch: Number(event.target.value) })}
            className="accent-accent-strong"
          />
          <p className="text-[12px] text-ink-faint">Lower is deeper, higher is lighter.</p>
        </div>

        <div className="flex flex-col gap-1">
          <label htmlFor="shape-rate" className="flex justify-between text-[13px] text-ink">
            <span>Speed</span>
            <span className="numeric text-ink-soft">{shape.rate.toFixed(2)}×</span>
          </label>
          <input
            id="shape-rate"
            type="range"
            min={limits.rate.min}
            max={limits.rate.max}
            step={0.05}
            value={shape.rate}
            onChange={(event) => onChange({ rate: Number(event.target.value) })}
            className="accent-accent-strong"
          />
          <p className="text-[12px] text-ink-faint">Slower is easier to follow.</p>
        </div>
      </div>

      <button
        type="button"
        onClick={onReset}
        className="inline-flex min-h-11 w-fit items-center text-[13px] text-ink-soft underline underline-offset-2 hover:text-ink"
      >
        Reset to default
      </button>
    </div>
  );
}
