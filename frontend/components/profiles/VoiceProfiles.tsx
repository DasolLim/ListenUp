"use client";

import { useCallback, useEffect, useState } from "react";
import { authHeader, isAuthConfigured } from "@/lib/auth/token";
import { usePcmRecorder } from "@/lib/usePcmRecorder";
import { MicIcon } from "@/components/shell/icons";
import Button from "@/components/ui/Button";
import GlassCard from "@/components/ui/GlassCard";

const BACKEND = process.env.NEXT_PUBLIC_BACKEND_URL ?? "http://localhost:8000";
const MIN_SECONDS = 20;
const MAX_SECONDS = 30;

const ENROLL_SCRIPT =
  "Hi, this is my voice for ListenUp. I'm recording about half a minute of natural " +
  "speech so captions can recognize me by name. I talk at my normal pace, the way I " +
  "would in a real conversation — about the weather, weekend plans, or what we're " +
  "having for dinner. Nothing fancy, just me, speaking the way I usually do.";

type Profile = {
  id: string;
  display_name: string;
  created_at: string;
  embedding_count: number;
};

export default function VoiceProfiles({ onChanged }: { onChanged?: () => void }) {
  const [profiles, setProfiles] = useState<Profile[]>([]);
  const [enrolling, setEnrolling] = useState(false);
  const [name, setName] = useState("");
  const [consentGiven, setConsentGiven] = useState(false);
  const [consentedBy, setConsentedBy] = useState("");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<{ kind: "error" | "ok"; text: string } | null>(null);
  const recorder = usePcmRecorder(MAX_SECONDS);

  const refresh = useCallback(async () => {
    if (!isAuthConfigured()) return;
    const response = await fetch(`${BACKEND}/profiles`, { headers: await authHeader() });
    if (response.ok) setProfiles(await response.json());
  }, []);

  useEffect(() => {
    // deferred initial load — state updates land outside the effect body
    const raf = requestAnimationFrame(() => void refresh());
    return () => cancelAnimationFrame(raf);
  }, [refresh]);

  async function save() {
    setMessage(null);
    if (!consentGiven || !consentedBy.trim()) {
      setMessage({
        kind: "error",
        text: "Consent is required: check the consent box and enter the enrolled person's name. Voice profiles are biometric data — we never save one without their agreement.",
      });
      return;
    }
    if (recorder.seconds < MIN_SECONDS) {
      setMessage({
        kind: "error",
        text: `The recording is ${Math.floor(recorder.seconds)}s — at least ${MIN_SECONDS}s is needed. Ask ${name || "the person"} to read the script at a natural pace.`,
      });
      return;
    }
    setBusy(true);
    try {
      const form = new FormData();
      form.append("display_name", name.trim());
      form.append("consent_given", "true");
      form.append("consented_by", consentedBy.trim());
      form.append("audio", recorder.getPcmBlob(), "enrollment.pcm");
      const response = await fetch(`${BACKEND}/profiles`, {
        method: "POST",
        headers: await authHeader(),
        body: form,
      });
      const body = await response.json().catch(() => ({}));
      if (!response.ok) {
        setMessage({ kind: "error", text: body.detail ?? "Enrollment failed. Try again." });
        return;
      }
      setMessage({ kind: "ok", text: `${body.display_name} can now be recognized in captions.` });
      setEnrolling(false);
      setName("");
      setConsentGiven(false);
      setConsentedBy("");
      recorder.reset();
      await refresh();
      onChanged?.();
    } finally {
      setBusy(false);
    }
  }

  async function remove(profile: Profile) {
    if (!confirm(`Delete ${profile.display_name}'s voice profile? This removes their voice data and consent record permanently.`)) return;
    const response = await fetch(`${BACKEND}/profiles/${profile.id}`, {
      method: "DELETE",
      headers: await authHeader(),
    });
    if (response.ok) {
      setMessage({ kind: "ok", text: `${profile.display_name}'s voice data was deleted.` });
      await refresh();
      onChanged?.();
    }
  }

  async function exportProfile(profile: Profile) {
    const response = await fetch(`${BACKEND}/profiles/${profile.id}/export`, {
      headers: await authHeader(),
    });
    if (!response.ok) return;
    const blob = new Blob([JSON.stringify(await response.json(), null, 2)], {
      type: "application/json",
    });
    const link = document.createElement("a");
    link.href = URL.createObjectURL(blob);
    link.download = `listenup-voice-profile-${profile.display_name}.json`;
    link.click();
    URL.revokeObjectURL(link.href);
  }

  // Save stays clickable so blocked attempts explain themselves (consent gate
  // and minimum-length messages) — only disabled mid-recording or mid-save.
  const canSave = !recorder.recording && !busy;

  return (
    <GlassCard strong className="flex flex-col gap-4 p-6">
      <div className="flex items-center justify-between gap-3">
        <h2 className="font-display text-[22px] font-semibold">Voice profiles</h2>
        {!enrolling && (
          <Button onClick={() => setEnrolling(true)}>Enroll someone</Button>
        )}
      </div>
      <p className="text-sm text-ink-soft">
        Enroll the people you talk to most (up to 4) and captions will use their names instead
        of “Speaker 1”. Each person must agree — their voice print is biometric data, stored
        encrypted, deletable and exportable anytime.
      </p>

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

      {profiles.length > 0 && (
        <ul className="flex flex-col gap-2.5">
          {profiles.map((profile) => (
            <li
              key={profile.id}
              className="flex flex-wrap items-center justify-between gap-2 rounded-2xl border border-white/60 bg-white/50 px-4 py-3"
            >
              <div>
                <p className="font-medium text-ink">{profile.display_name}</p>
                <p className="text-[13px] text-ink-soft">
                  {profile.embedding_count} voice sample{profile.embedding_count === 1 ? "" : "s"}
                </p>
              </div>
              <div className="flex gap-2">
                <button
                  type="button"
                  onClick={() => exportProfile(profile)}
                  className="btn-ghost rounded-full px-3.5 py-1.5 text-sm text-ink"
                >
                  Export data
                </button>
                <button
                  type="button"
                  onClick={() => remove(profile)}
                  className="rounded-full border border-error bg-white/60 px-3.5 py-1.5 text-sm text-error-strong"
                >
                  Delete
                </button>
              </div>
            </li>
          ))}
        </ul>
      )}
      {profiles.length === 0 && !enrolling && (
        <p className="text-sm text-ink-faint">No one enrolled yet.</p>
      )}

      {enrolling && (
        <form
          className="flex flex-col gap-4 rounded-2xl border border-white/60 bg-white/50 p-5"
          onSubmit={(e) => {
            e.preventDefault();
            save();
          }}
        >
          <div className="flex flex-col gap-1">
            <label htmlFor="profile-name" className="text-sm font-medium">
              Person&apos;s name (shown in captions)
            </label>
            <input
              id="profile-name"
              value={name}
              onChange={(e) => setName(e.target.value)}
              required
              maxLength={60}
              placeholder="Mom"
              className="glass-strong max-w-xs rounded-xl border border-white/60 px-3.5 py-2.5 text-ink shadow-glass outline-none placeholder:text-ink-faint"
            />
          </div>

          <div className="rounded-xl border border-white/60 bg-white/60 p-4">
            <p className="text-sm font-medium text-ink">
              Have {name || "them"} read this aloud ({MIN_SECONDS}–{MAX_SECONDS} seconds):
            </p>
            <p className="mt-2 text-sm italic leading-relaxed text-ink-soft">“{ENROLL_SCRIPT}”</p>
          </div>

          <div className="flex items-center gap-3">
            {recorder.recording ? (
              <Button variant="ghost" type="button" onClick={recorder.stop}>
                Stop recording
              </Button>
            ) : (
              <Button type="button" onClick={recorder.start} className="flex items-center gap-2">
                <MicIcon />
                {recorder.seconds > 0 ? "Re-record" : "Record"}
              </Button>
            )}
            <p role="status" className="text-sm tabular-nums text-ink-soft">
              {recorder.recording
                ? `Recording… ${recorder.seconds.toFixed(0)}s`
                : recorder.seconds > 0
                  ? `${recorder.seconds.toFixed(0)}s recorded${recorder.seconds < MIN_SECONDS ? ` — need ${MIN_SECONDS}s minimum` : " ✓"}`
                  : "Not recorded yet"}
            </p>
          </div>
          {recorder.error && (
            <p role="alert" className="text-sm text-error-strong">{recorder.error}</p>
          )}

          <div className="flex flex-col gap-2 rounded-xl border border-white/60 bg-white/60 p-4">
            <label className="flex items-start gap-2.5 text-sm text-ink">
              <input
                type="checkbox"
                checked={consentGiven}
                onChange={(e) => setConsentGiven(e.target.checked)}
                className="mt-0.5 h-4 w-4 accent-accent-strong"
              />
              <span>
                <strong>{name || "This person"} agrees</strong> to ListenUp storing a
                mathematical voice print (not a recording) so captions can label them by name.
                They can have it deleted or exported at any time.
              </span>
            </label>
            <div className="flex flex-col gap-1">
              <label htmlFor="consented-by" className="text-sm font-medium">
                Consenting person&apos;s full name
              </label>
              <input
                id="consented-by"
                value={consentedBy}
                onChange={(e) => setConsentedBy(e.target.value)}
                maxLength={120}
                className="glass-strong max-w-xs rounded-xl border border-white/60 px-3.5 py-2.5 text-ink shadow-glass outline-none"
              />
            </div>
          </div>

          <div className="flex gap-2">
            <Button type="submit" disabled={!canSave}>
              {busy ? "Saving…" : "Save profile"}
            </Button>
            <Button
              type="button"
              variant="ghost"
              onClick={() => {
                setEnrolling(false);
                recorder.stop();
                recorder.reset();
              }}
            >
              Cancel
            </Button>
          </div>
        </form>
      )}
    </GlassCard>
  );
}
