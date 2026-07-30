"use client";

import {
  DEFAULT_SHAPE,
  SHAPE_LIMITS,
  supportsDimension,
  type VoiceShape,
} from "@/lib/useSpeech";

type Limits = typeof SHAPE_LIMITS;

/**
 * Named starting points, so nobody meets four raw sliders first. Each is a real
 * combination of values, not a label on nothing.
 *
 * "Deeper" and "Lighter" are how a gender dial actually works in browser TTS:
 * there is no morph parameter, but pitch genuinely moves a voice along that
 * range. The rest exist because they solve stated problems — following speech
 * you can't lip-read, being heard in a loud room, or reading to someone who
 * needs time between sentences.
 */
const PRESETS: { label: string; hint: string; shape: VoiceShape }[] = [
  { label: "Default", hint: "Natural pace", shape: { ...DEFAULT_SHAPE } },
  {
    label: "Deeper",
    hint: "Lower register",
    shape: { ...DEFAULT_SHAPE, pitch: 0.7, rate: 0.95, volume: 1, pauses: 0 },
  },
  {
    label: "Lighter",
    hint: "Higher register",
    shape: { ...DEFAULT_SHAPE, pitch: 1.45, rate: 1, volume: 1, pauses: 0 },
  },
  {
    label: "Slower, clearer",
    hint: "Easier to follow",
    shape: { ...DEFAULT_SHAPE, pitch: 1, rate: 0.75, volume: 1, pauses: 250 },
  },
  {
    label: "Patient",
    hint: "Long gaps to catch up",
    shape: { ...DEFAULT_SHAPE, pitch: 1, rate: 0.7, volume: 1, pauses: 700 },
  },
  {
    label: "Loud room",
    hint: "Carries over noise",
    shape: { ...DEFAULT_SHAPE, pitch: 0.95, rate: 0.9, volume: 1, pauses: 150 },
  },
];

type Dimension = {
  key: keyof VoiceShape;
  label: string;
  help: string;
  step: number;
  format: (value: number) => string;
};

/** Delivery: what the Web Speech API gives us directly, plus derived pauses. */
const DELIVERY: Dimension[] = [
  {
    key: "pitch",
    label: "Pitch",
    help: "Lower is deeper, higher is lighter.",
    step: 0.05,
    format: (v) => `${v.toFixed(2)}×`,
  },
  {
    key: "rate",
    label: "Speed",
    help: "Slower is easier to follow.",
    step: 0.05,
    format: (v) => `${v.toFixed(2)}×`,
  },
  {
    key: "volume",
    label: "Volume",
    help: "Turn up when the room is noisy.",
    step: 0.05,
    format: (v) => `${Math.round(v * 100)}%`,
  },
  {
    key: "pauses",
    label: "Pause between sentences",
    help: "Adds silence so the listener can catch up.",
    step: 50,
    format: (v) => (v === 0 ? "None" : `${(v / 1000).toFixed(2)}s`),
  },
];

/**
 * Tone: the actual *sound* of the voice, not its delivery.
 *
 * These need audio we can route through a filter graph, which rules out browser
 * voices entirely — `speechSynthesis` plays straight to the sound card and
 * exposes no output node. They are shown to everyone (so the capability is
 * discoverable) but disabled with a reason on the free tier.
 */
const TONE: Dimension[] = [
  {
    key: "bass",
    label: "Warmth",
    help: "Adds low-end body to a thin voice.",
    step: 0.5,
    format: (v) => (v === 0 ? "Neutral" : `${v > 0 ? "+" : ""}${v.toFixed(1)} dB`),
  },
  {
    key: "treble",
    label: "Brightness",
    help: "Sharpens consonants so words cut through.",
    step: 0.5,
    format: (v) => (v === 0 ? "Neutral" : `${v > 0 ? "+" : ""}${v.toFixed(1)} dB`),
  },
  {
    key: "clarity",
    label: "Evenness",
    help: "Levels out loud and quiet parts.",
    step: 0.05,
    format: (v) => (v === 0 ? "Off" : `${Math.round(v * 100)}%`),
  },
  {
    key: "expressiveness",
    label: "Expressiveness",
    help: "How much the delivery varies, versus staying flat.",
    step: 0.05,
    format: (v) => `${Math.round(v * 100)}%`,
  },
];

/**
 * A preset is "active" only when every dimension it sets still matches.
 *
 * Checked across all eight rather than the original four: a preset that left
 * Warmth at +6 dB while claiming to be "Default" would misreport what you are
 * hearing.
 */
function isActive(shape: VoiceShape, preset: VoiceShape) {
  const near = (a: number, b: number, tolerance: number) => Math.abs(a - b) < tolerance;
  return (
    near(shape.pitch, preset.pitch, 0.02) &&
    near(shape.rate, preset.rate, 0.02) &&
    near(shape.volume, preset.volume, 0.02) &&
    near(shape.pauses, preset.pauses, 25) &&
    near(shape.bass, preset.bass, 0.3) &&
    near(shape.treble, preset.treble, 0.3) &&
    near(shape.clarity, preset.clarity, 0.02) &&
    near(shape.expressiveness, preset.expressiveness, 0.02)
  );
}

function Slider({
  dimension,
  shape,
  limits,
  onChange,
  disabled,
}: {
  dimension: Dimension;
  shape: VoiceShape;
  limits: Limits;
  onChange: (next: Partial<VoiceShape>) => void;
  disabled: boolean;
}) {
  const value = shape[dimension.key];
  const range = limits[dimension.key];
  return (
    <div className="flex flex-col gap-1">
      <label
        htmlFor={`shape-${dimension.key}`}
        className={`flex justify-between text-[13px] ${disabled ? "text-ink-faint" : "text-ink"}`}
      >
        <span>{dimension.label}</span>
        {/* The numeric value is shown because a slider alone gives a
            screen-reader user nothing to compare against. */}
        <span className="numeric text-ink-soft">{dimension.format(value)}</span>
      </label>
      <input
        id={`shape-${dimension.key}`}
        type="range"
        min={range.min}
        max={range.max}
        step={dimension.step}
        value={value}
        disabled={disabled}
        // Range inputs announce the raw number, which is meaningless for volume
        // (0.85) and pauses (700). Override with the formatted text.
        aria-valuetext={dimension.format(value)}
        onChange={(event) =>
          onChange({ [dimension.key]: Number(event.target.value) } as Partial<VoiceShape>)
        }
        className="accent-accent-strong disabled:opacity-40"
      />
      <p className="text-[12px] text-ink-faint">{dimension.help}</p>
    </div>
  );
}

export default function VoiceShaper({
  shape,
  limits,
  onChange,
  onReset,
  provider = "browser",
}: {
  shape: VoiceShape;
  limits: Limits;
  onChange: (next: Partial<VoiceShape>) => void;
  onReset: () => void;
  /** Which tier the selected voice belongs to; decides what can be shaped. */
  provider?: string;
}) {
  const toneAvailable = supportsDimension("bass", provider);
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
              // The hint is the accessible name's tail so a screen-reader user
              // hears what the preset does, not just its invented name.
              aria-label={`${preset.label} — ${preset.hint}`}
              title={preset.hint}
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
        {DELIVERY.map((dimension) => (
          <Slider
            key={dimension.key}
            dimension={dimension}
            shape={shape}
            limits={limits}
            onChange={onChange}
            disabled={!supportsDimension(dimension.key, provider)}
          />
        ))}
      </div>

      <fieldset
        disabled={!toneAvailable}
        className="flex flex-col gap-3 border-t border-white/60 pt-4"
      >
        <legend className="sr-only">Tone</legend>
        <div>
          <h4 className="text-[13px] font-semibold text-ink">Tone</h4>
          {/* Say plainly why these are off, rather than greying them out with no
              explanation. The limit is the browser's, not a paywall we invented:
              speechSynthesis has no audio output to filter. */}
          <p className="mt-0.5 text-[12px] leading-relaxed text-ink-faint">
            {toneAvailable
              ? "Shapes the sound itself, not just the delivery."
              : "Built-in voices play straight to your speakers, so their sound can’t be " +
                "filtered. These need a cloud voice."}
          </p>
        </div>
        <div className="grid gap-4 sm:grid-cols-2">
          {TONE.map((dimension) => (
            <Slider
              key={dimension.key}
              dimension={dimension}
              shape={shape}
              limits={limits}
              onChange={onChange}
              disabled={!supportsDimension(dimension.key, provider)}
            />
          ))}
        </div>
      </fieldset>

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
