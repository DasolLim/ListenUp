"use client";

import SpeakButton from "@/components/speech/SpeakButton";
import { type Voice } from "@/lib/useSpeech";

const PREVIEW: Record<string, string> = {
  en: "Are you coming over for dinner on Sunday?",
  ko: "일요일에 저녁 먹으러 올 거예요?",
};

/**
 * Choose the voice that reads translations aloud, with a preview and an
 * auto-speak toggle.
 *
 * Preview matters: a voice name means nothing until you hear it, and picking
 * the wrong one mid-conversation is exactly when you can't afford to fiddle.
 */
export default function VoicePicker({
  voices,
  voiceId,
  onChoose,
  onPreview,
  onStop,
  speaking,
  autoSpeak,
  onToggleAutoSpeak,
  language,
  id = "voice-picker",
}: {
  voices: Voice[];
  voiceId: string;
  onChoose: (id: string) => void;
  onPreview: (text: string, voiceId: string) => void;
  onStop: () => void;
  speaking: boolean;
  autoSpeak: boolean;
  onToggleAutoSpeak: () => void;
  language: string;
  id?: string;
}) {
  if (voices.length === 0) return null;

  return (
    <div className="flex flex-wrap items-center gap-2">
      <label htmlFor={id} className="text-sm text-ink">
        Read aloud
      </label>
      <select
        id={id}
        value={voiceId}
        onChange={(event) => onChoose(event.target.value)}
        className="glass-strong rounded-xl border border-white/60 px-3 py-2 text-sm text-ink shadow-glass outline-none"
      >
        {voices.map((voice) => (
          <option key={voice.id} value={voice.id}>
            {voice.label}
          </option>
        ))}
      </select>

      <SpeakButton
        onSpeak={() => onPreview(PREVIEW[language] ?? PREVIEW.en, voiceId)}
        onStop={onStop}
        speaking={speaking}
        label="a preview of this voice"
      />

      {/* Stated in words as well as pressed-state, never colour alone. */}
      <button
        type="button"
        aria-pressed={autoSpeak}
        onClick={onToggleAutoSpeak}
        className={`inline-flex min-h-11 items-center rounded-full px-3.5 text-[13px] font-medium transition-colors ${
          autoSpeak
            ? "bg-accent-strong text-on-accent"
            : "pill-inactive text-ink-soft hover:text-ink"
        }`}
      >
        Auto-speak {autoSpeak ? "on" : "off"}
      </button>
    </div>
  );
}
