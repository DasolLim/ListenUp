"use client";

import { useEffect, useState } from "react";
import { createClient, isSupabaseConfigured } from "@/lib/supabase/client";
import { usePcmRecorder } from "@/lib/usePcmRecorder";
import { MicIcon } from "@/components/shell/icons";
import Button from "@/components/ui/Button";
import SpeakButton from "@/components/speech/SpeakButton";
import VoiceShaper from "@/components/speech/VoiceShaper";
import { SHAPE_LIMITS } from "@/lib/useSpeech";
import { SpeechProvider, useSharedSpeech } from "@/lib/SpeechProvider";
import { networkError } from "@/lib/networkError";

const BACKEND = process.env.NEXT_PUBLIC_BACKEND_URL ?? "http://localhost:8000";

const MIN_SECONDS = 30;
const MAX_SECONDS = 180;

const READING_SCRIPT =
  "Hi, this is my voice for ListenUp. I'm reading for about half a minute so the " +
  "app can learn how I sound. I'm speaking at my normal pace, the way I would in " +
  "a real conversation, about the weather, weekend plans, or what we're having " +
  "for dinner. Nothing unusual, just me talking the way I usually do.";

type CustomVoice = {
  id: string;
  display_name: string;
  provider_voice_id: string;
  language: string;
  created_at: string;
};

async function authHeader(): Promise<Record<string, string>> {
  if (!isSupabaseConfigured()) return {};
  const { data } = await createClient().auth.getSession();
  const token = data.session?.access_token;
  return token ? { Authorization: `Bearer ${token}` } : {};
}

/**
 * Voice studio: pick how the preset voices sound, and build a custom voice from
 * a recording.
 *
 * Recording someone's voice so the app can *speak as them* is a bigger step than
 * recognising them, so the consent gate is part of the form rather than a
 * footnote: you cannot reach Save without naming the person and confirming they
 * agreed.
 */
function VoiceStudioInner({ language = "en" }: { language?: string }) {
  const speech = useSharedSpeech();
  const recorder = usePcmRecorder(MAX_SECONDS);

  const [voices, setVoices] = useState<CustomVoice[]>([]);
  const [creating, setCreating] = useState(false);
  const [name, setName] = useState("");
  const [consentGiven, setConsentGiven] = useState(false);
  const [consentedBy, setConsentedBy] = useState("");
  const [consentText, setConsentText] = useState("");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<{ kind: "error" | "ok"; text: string } | null>(null);
  const [confirmDelete, setConfirmDelete] = useState<string | null>(null);
  /**
   * Whether a cloning provider is configured. Recording is pointless without
   * one: the backend refuses at the end of the flow, so a user could read a
   * 30-second script and fill in a consent form before learning it can't work.
   * `null` while we're still asking.
   */
  const [cloningReady, setCloningReady] = useState<boolean | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    fetch(`${BACKEND}/tts/voices`, { signal: controller.signal })
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error("voices"))))
      .then((body: { consent_text: string; voices: { provider: string }[] }) => {
        setConsentText(body.consent_text);
        // Only the cloud provider can build a voice from a recording.
        setCloningReady(body.voices.some((v) => v.provider !== "browser"));
      })
      .catch(() => setCloningReady(false));
    return () => controller.abort();
  }, []);

  async function refresh() {
    const headers = await authHeader();
    if (!headers.Authorization) return;
    const response = await fetch(`${BACKEND}/tts/custom-voices`, { headers });
    if (response.ok) setVoices(await response.json());
  }

  useEffect(() => {
    const raf = requestAnimationFrame(() => void refresh());
    return () => cancelAnimationFrame(raf);
  }, []);

  async function save() {
    setMessage(null);
    if (!name.trim()) {
      setMessage({ kind: "error", text: "Give the voice a name so you can find it later." });
      return;
    }
    if (!consentGiven || !consentedBy.trim()) {
      setMessage({
        kind: "error",
        text:
          "Consent is required: enter the name of the person speaking and confirm they agreed. " +
          "A cloned voice can say things they never said, so we never build one without it.",
      });
      return;
    }
    if (recorder.seconds < MIN_SECONDS) {
      setMessage({
        kind: "error",
        text: `The recording is ${Math.floor(recorder.seconds)}s. At least ${MIN_SECONDS}s is needed for a voice that actually sounds like them.`,
      });
      return;
    }

    setBusy(true);
    try {
      const form = new FormData();
      form.append("display_name", name.trim());
      form.append("consent_given", "true");
      form.append("consented_by", consentedBy.trim());
      form.append("language", language);
      form.append("sample", recorder.getPcmBlob(), "voice.pcm");
      const response = await fetch(`${BACKEND}/tts/custom-voices`, {
        method: "POST",
        headers: await authHeader(),
        body: form,
      });
      const body = await response.json().catch(() => ({}));
      if (!response.ok) {
        // Return BEFORE recorder.reset(): a failed save must keep the audio so
        // the user can retry without re-reading the script. Do not move the
        // reset above this line.
        setMessage({
          kind: "error",
          text: `${body.detail ?? "Could not build that voice."} Your recording is still here, so you can try again.`,
        });
        return;
      }
      setMessage({
        kind: "ok",
        text: `${body.display_name} is ready. Pick them under "Read aloud" anywhere in the app.`,
      });
      setCreating(false);
      setName("");
      setConsentGiven(false);
      setConsentedBy("");
      recorder.reset();
      await refresh();
    } catch (err) {
      setMessage({
        kind: "error",
        text: `${networkError(err, "Could not build that voice.")} Your recording is still here, so you can try again.`,
      });
    } finally {
      setBusy(false);
    }
  }

  async function remove(voice: CustomVoice) {
    setConfirmDelete(null);
    setBusy(true);
    try {
      const response = await fetch(`${BACKEND}/tts/custom-voices/${voice.id}`, {
        method: "DELETE",
        headers: await authHeader(),
      });
      if (response.status === 204) {
        setMessage({ kind: "ok", text: `${voice.display_name}'s voice was deleted.` });
        await refresh();
      } else {
        const body = await response.json().catch(() => ({}));
        setMessage({
          kind: "error",
          text: body.detail ?? `Could not delete that voice (${response.status}). Nothing changed.`,
        });
      }
    } catch (err) {
      setMessage({ kind: "error", text: networkError(err, "Could not delete that voice.") });
    } finally {
      setBusy(false);
    }
  }

  const enough = recorder.seconds >= MIN_SECONDS;

  return (
    <div className="flex flex-col gap-5">
      {message && (
        <p
          role={message.kind === "error" ? "alert" : "status"}
          className={`rounded-xl border bg-white/70 px-4 py-3 text-sm ${
            message.kind === "error" ? "border-error text-error-strong" : "border-success text-ink"
          }`}
        >
          {message.text}
        </p>
      )}

      {/* Two tiles matching the dashboard's tool-tile vocabulary: a coloured
          wash header, a 17px card title, quiet body copy, coral spent only on
          the one action. The section heading above already says "Read aloud",
          so these name what they each do instead of repeating it. */}
      <div className="grid gap-5 lg:grid-cols-2">
        {/* ── Tile 1: shape the preset voices (free, no key needed) ── */}
        <section
          aria-labelledby="shape-heading"
          className="glass-card flex flex-col overflow-hidden"
        >
          <span aria-hidden="true" className="tile-wash-teal h-16 w-full" />
          <div className="flex flex-1 flex-col gap-3 p-5">
            <div>
              <h3
                id="shape-heading"
                className="font-display text-[17px] font-semibold text-ink"
              >
                How it sounds
              </h3>
              <p className="mt-1 text-sm leading-relaxed text-ink-soft">
                Lower the pitch for a deeper voice, raise it for a lighter one. Saved per voice.
              </p>
            </div>

        <div className="flex flex-wrap items-center gap-2">
          <label htmlFor="studio-voice" className="text-sm text-ink">
            Voice
          </label>
          <select
            id="studio-voice"
            value={speech.voiceId}
            onChange={(event) => speech.chooseVoice(event.target.value)}
            className="glass-strong min-h-11 rounded-xl border border-white/60 px-3 text-sm text-ink shadow-glass outline-none"
          >
            {speech.voices.map((voice) => (
              <option key={voice.id} value={voice.id}>
                {voice.label}
              </option>
            ))}
          </select>
          <SpeakButton
            onSpeak={() =>
              speech.speak(
                language === "ko"
                  ? "일요일에 저녁 먹으러 올 거예요?"
                  : "Are you coming over for dinner on Sunday?",
              )
            }
            onStop={speech.stop}
            speaking={speech.speaking}
            label="a preview of this voice"
          />
        </div>

            <VoiceShaper
              shape={speech.shape}
              limits={SHAPE_LIMITS}
              onChange={speech.adjustShape}
              onReset={speech.resetShape}
            />
          </div>
        </section>

        {/* ── Tile 2: recorded voices ── */}
        <section
          aria-labelledby="custom-heading"
          className="glass-card flex flex-col overflow-hidden"
        >
          <span aria-hidden="true" className="tile-wash-teal h-16 w-full opacity-70" />
          <div className="flex flex-1 flex-col gap-3 p-5">
            <div>
              <h3
                id="custom-heading"
                className="font-display text-[17px] font-semibold text-ink"
              >
                Recorded voices
              </h3>
              <p className="mt-1 text-sm leading-relaxed text-ink-soft">
                Record someone you talk with often, with their consent, and translations can read
                in their voice.
              </p>
            </div>

            {/* Say upfront that recording isn't available yet. Without this a
                user reads a 30-second script and fills in a consent form before
                the backend refuses at the very end. */}
            {cloningReady === false && !creating && (
              <p
                role="status"
                className="rounded-xl border border-warning bg-white/70 px-4 py-3 text-[13px] leading-relaxed text-ink"
              >
                <span className="font-semibold">Recording a voice isn&apos;t available yet.</span>{" "}
                It needs a cloud voice provider, which isn&apos;t switched on for this account. Aria,
                Miles and the system voice work everywhere in the meantime, and you can change how
                they sound on the left.
              </p>
            )}

            {cloningReady !== false && voices.length === 0 && !creating && (
              <p className="rounded-xl border border-dashed border-ink-faint/40 px-4 py-3 text-[13px] leading-relaxed text-ink-soft">
                No recorded voices yet. Aria, Miles and the system voice are always available.
              </p>
            )}

            <ul className="flex flex-col gap-2.5">
            {voices.map((voice) => (
              <li
                key={voice.id}
                className="flex flex-col gap-3 rounded-2xl border border-white/60 bg-white/50 px-4 py-3"
              >
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div>
                    <p className="font-medium text-ink">{voice.display_name}</p>
                    <p className="text-[13px] text-ink-soft">
                      {voice.language === "ko" ? "Korean" : "English"} · recorded with consent
                    </p>
                  </div>
                  <div className="flex gap-2">
                    <SpeakButton
                      onSpeak={() =>
                        speech.speak("This is how I sound.", voice.provider_voice_id)
                      }
                      onStop={speech.stop}
                      speaking={speech.speaking}
                      label={`${voice.display_name}'s voice`}
                    />
                    <button
                      type="button"
                      onClick={() => setConfirmDelete(voice.id)}
                      aria-expanded={confirmDelete === voice.id}
                      className="inline-flex min-h-11 items-center rounded-full border border-error bg-white/60 px-3.5 text-sm text-error-strong"
                    >
                      Delete
                    </button>
                  </div>
                </div>

                {confirmDelete === voice.id && (
                  <div className="rounded-xl border border-error bg-white/80 p-3.5">
                    <p className="text-sm font-medium text-ink">
                      Delete {voice.display_name}&apos;s voice?
                    </p>
                    <p className="mt-1 text-[13px] leading-relaxed text-ink-soft">
                      This removes the voice and their consent record permanently, here and at the
                      voice provider. It cannot be undone.
                    </p>
                    <div className="mt-3 flex flex-wrap gap-2">
                      <button
                        type="button"
                        onClick={() => remove(voice)}
                        disabled={busy}
                        className="inline-flex min-h-11 items-center rounded-full border border-error bg-white/70 px-4 text-sm font-medium text-error-strong disabled:opacity-50"
                      >
                        {busy ? "Deleting…" : "Delete permanently"}
                      </button>
                      <button
                        type="button"
                        onClick={() => setConfirmDelete(null)}
                        className="inline-flex min-h-11 items-center rounded-full px-4 text-sm text-ink-soft hover:text-ink"
                      >
                        Keep it
                      </button>
                    </div>
                  </div>
                )}
              </li>
            ))}
            </ul>

            {/* Hidden rather than disabled while cloning is unavailable: a
                disabled button invites clicking and explains nothing, and the
                status message above already says why. */}
            {!creating && cloningReady && (
              <div className="pt-1">
                {/* Ghost, not coral: dashboard tiles spend coral only on the
                    small arrow, so a filled primary here would out-shout every
                    tool card beside it. */}
                <Button variant="ghost" onClick={() => setCreating(true)}>
                  Record a voice
                </Button>
              </div>
            )}
          </div>
        </section>
      </div>

      {/* ── Record a new voice: full width, since it is a focused task ── */}
      {creating && (
        <section
          aria-labelledby="record-heading"
          className="glass-card flex flex-col gap-4 p-5"
        >
          <div>
            <h3 id="record-heading" className="font-display text-[17px] font-semibold text-ink">
              Record a voice
            </h3>
            <p className="mt-1 text-[13px] leading-relaxed text-ink-soft">
              The person speaking must be present and agree. Their voice is biometric data: it is
              consent-gated, deletable, and exportable at any time.
            </p>
          </div>

          <div className="flex flex-col gap-1">
            <label htmlFor="voice-name" className="text-sm font-medium text-ink">
              Name this voice
            </label>
            <input
              id="voice-name"
              value={name}
              onChange={(event) => setName(event.target.value)}
              maxLength={60}
              placeholder="Mom"
              className="glass-strong max-w-xs rounded-xl border border-white/60 px-3.5 py-2.5 text-ink shadow-glass outline-none placeholder:text-ink-faint"
            />
          </div>

          <div className="rounded-xl border border-white/60 bg-white/60 p-4">
            <p className="text-[12px] font-semibold uppercase tracking-wide text-ink-soft">
              Read this aloud
            </p>
            <p className="mt-1 text-sm leading-relaxed text-ink">{READING_SCRIPT}</p>
          </div>

          <div className="flex flex-wrap items-center gap-3">
            {recorder.recording ? (
              <Button variant="ghost" onClick={recorder.stop}>
                Stop recording
              </Button>
            ) : (
              <Button onClick={recorder.start} className="flex items-center gap-2">
                <MicIcon />
                {recorder.seconds > 0 ? "Record again" : "Start recording"}
              </Button>
            )}
            <p role="status" className="numeric text-sm text-ink-soft">
              {Math.floor(recorder.seconds)}s recorded
              {enough ? " ✓" : ` — need ${MIN_SECONDS}s`}
            </p>
          </div>

          {recorder.error && (
            <p role="alert" className="text-sm text-error-strong">
              {recorder.error}
            </p>
          )}

          {/* Consent gate: last, so it reads as the deliberate final step. */}
          <div className="flex flex-col gap-2 rounded-xl border border-white/60 bg-white/60 p-4">
            <label className="flex items-start gap-2 text-sm text-ink">
              <input
                type="checkbox"
                checked={consentGiven}
                onChange={(event) => setConsentGiven(event.target.checked)}
                className="mt-0.5 h-4 w-4 accent-accent-strong"
              />
              <span>{consentText || "Loading the consent statement…"}</span>
            </label>
            <div className="flex flex-col gap-1">
              <label htmlFor="consented-by" className="text-sm font-medium text-ink">
                Name of the person speaking
              </label>
              <input
                id="consented-by"
                value={consentedBy}
                onChange={(event) => setConsentedBy(event.target.value)}
                maxLength={60}
                placeholder="Their full name"
                className="glass-strong max-w-xs rounded-xl border border-white/60 px-3.5 py-2.5 text-ink shadow-glass outline-none placeholder:text-ink-faint"
              />
            </div>
          </div>

          <div className="flex flex-wrap gap-2">
            {/* Save stays enabled so a blocked attempt explains itself, rather
                than leaving the user guessing which requirement is missing. */}
            <Button onClick={save} disabled={busy || recorder.recording}>
              {busy ? "Building the voice…" : "Save voice"}
            </Button>
            <Button
              variant="ghost"
              onClick={() => {
                setCreating(false);
                recorder.reset();
                setMessage(null);
              }}
            >
              Cancel
            </Button>
          </div>
        </section>
      )}
    </div>
  );
}

/** Wraps the studio in its own speech engine so previews use the chosen voice. */
export default function VoiceStudio({ language = "en" }: { language?: string }) {
  return (
    <SpeechProvider language={language}>
      <VoiceStudioInner language={language} />
    </SpeechProvider>
  );
}
