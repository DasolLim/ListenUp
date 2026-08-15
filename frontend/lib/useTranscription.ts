"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { getAccessToken } from "@/lib/auth/token";

export type CaptionSegment = {
  id: string;
  speaker: string;
  speakerName: string | null;
  text: string;
  start: number;
  end: number;
  isFinal: boolean;
};

export type TranscriptionStatus =
  | "idle"
  | "connecting"
  | "listening"
  | "paused"
  | "stopped"
  | "error";

export type LatencyStats = { count: number; p50: number; p95: number } | null;

const SAMPLE_RATE = 16000;
// Diarization smoothing: a final segment shorter than this that flips to a new
// speaker and flips back is treated as noise and merged into the neighbor.
const SMOOTHING_WINDOW_S = 1.0;

function percentile(sorted: number[], p: number): number {
  if (!sorted.length) return 0;
  const index = Math.min(sorted.length - 1, Math.ceil((p / 100) * sorted.length) - 1);
  return sorted[Math.max(0, index)];
}

/** Merge an incoming segment into the list, keyed on the provider's stable
 * turn id. Interim and final versions of one utterance share the id even when
 * diarization revises the speaker label or timestamps mid-turn — matching on
 * anything else (speaker/start) orphans interims as duplicate bubbles. */
function mergeSegment(list: CaptionSegment[], incoming: CaptionSegment): CaptionSegment[] {
  const index = list.findIndex((s) => s.id === incoming.id);
  if (index >= 0) {
    const next = [...list];
    // Never let a late interim overwrite an already-final turn.
    next[index] = list[index].isFinal && !incoming.isFinal ? list[index] : incoming;
    return next;
  }
  return [...list, incoming];
}

/** Merge speaker flips shorter than ~1s between same-speaker neighbors. */
function smooth(list: CaptionSegment[]): CaptionSegment[] {
  const finals = list.filter((s) => s.isFinal);
  if (finals.length < 3) return list;
  const flip = finals[finals.length - 2];
  const before = finals[finals.length - 3];
  const after = finals[finals.length - 1];
  if (
    flip.end - flip.start < SMOOTHING_WINDOW_S &&
    flip.speaker !== before.speaker &&
    before.speaker === after.speaker
  ) {
    return list.map((s) => (s.id === flip.id ? { ...s, speaker: before.speaker } : s));
  }
  return list;
}

/** Caption hours are gone for this billing period. */
export type CaptionLimit = {
  resetsAt: string | null;
  upgradeTo: "basic" | "pro" | null;
  message: string;
};

/** Past 80% — shown once, at the start of a session. */
export type CaptionWarning = {
  used: number;
  limit: number;
  remaining: number;
  resetsAt: string | null;
};

export function useTranscription(options?: { language?: string }) {
  const language = options?.language ?? "en";
  const [status, setStatus] = useState<TranscriptionStatus>("idle");
  const [error, setError] = useState<string | null>(null);
  const [segments, setSegments] = useState<CaptionSegment[]>([]);
  const [latency, setLatency] = useState<LatencyStats>(null);
  // "batch" languages (no streaming model exists) lag a few seconds — the UI
  // says so instead of looking broken.
  const [mode, setMode] = useState<"streaming" | "batch">("streaming");
  // Running out of caption hours is not a fault, so it is kept apart from
  // `error`: a red "something went wrong" for a plan limit reads as a broken
  // product and tells the user nothing they can act on.
  const [limit, setLimit] = useState<CaptionLimit | null>(null);
  const [allowanceWarning, setAllowanceWarning] = useState<CaptionWarning | null>(null);

  const wsRef = useRef<WebSocket | null>(null);
  const audioRef = useRef<{ context: AudioContext; stream: MediaStream } | null>(null);
  const analyserRef = useRef<AnalyserNode | null>(null);
  const levelBufferRef = useRef<Uint8Array | null>(null);
  const captureStartRef = useRef<number>(0);
  const latenciesRef = useRef<number[]>([]);
  const counterRef = useRef(0);
  const sessionIdRef = useRef<string>("");

  // Read inside the audio callback, which is installed once per session and
  // must see the current value without being rebuilt.
  const pausedRef = useRef(false);
  // Wall-clock time spent paused. `segment.end` is a position in the *audio*
  // timeline, which stops advancing while paused, so mapping an audio moment
  // back to the wall clock has to add the pauses back on. Without this the
  // first caption after a pause reports a latency inflated by its whole length.
  const pausedMsRef = useRef(0);
  const pausedAtRef = useRef<number | null>(null);

  // Lets the pause/resume callbacks read the live status without depending on
  // it, so they stay stable and don't re-create the audio wiring around them.
  const statusRef = useRef<TranscriptionStatus>("idle");
  useEffect(() => {
    statusRef.current = status;
  }, [status]);

  /**
   * Current speaking loudness, 0–1.
   *
   * Deliberately a function rather than state: the orb samples this every frame,
   * and putting it in state would re-render the whole caption list 60 times a
   * second. Returns 0 whenever the mic is not running, so callers need no
   * separate "is listening" check.
   */
  const getAudioLevel = useCallback((): number => {
    const analyser = analyserRef.current;
    if (!analyser) return 0;
    if (!levelBufferRef.current || levelBufferRef.current.length !== analyser.frequencyBinCount) {
      levelBufferRef.current = new Uint8Array(analyser.frequencyBinCount);
    }
    const bins = levelBufferRef.current;
    analyser.getByteFrequencyData(bins as Uint8Array<ArrayBuffer>);

    // Measure only the band voices actually occupy. At a 16 kHz sample rate with
    // fftSize 512 each bin spans ~31 Hz, so the array reaches 8 kHz — and better
    // than half of it sits above where speech has meaningful energy. Averaging
    // across all of it divides real speech by a long tail of near-silent bins,
    // which is why a loud voice reads as a mild one. Bins ~3–128 cover roughly
    // 100 Hz to 4 kHz: fundamentals through the consonant range.
    const nyquistPerBin = (audioRef.current?.context.sampleRate ?? SAMPLE_RATE) / analyser.fftSize;
    const first = Math.max(1, Math.floor(100 / nyquistPerBin));
    const last = Math.min(bins.length - 1, Math.ceil(4000 / nyquistPerBin));

    // RMS rather than peak: peak jumps on every consonant, while RMS tracks how
    // loud someone actually is, which is what the orb should follow.
    let sum = 0;
    for (let i = first; i <= last; i += 1) {
      const value = bins[i] / 255;
      sum += value * value;
    }
    const rms = Math.sqrt(sum / (last - first + 1));
    // Gain of 2 on a speech-band reading lands normal conversation around the
    // middle of the range, leaving headroom so shouting still looks different
    // from talking — a level pinned at 1.0 is as uninformative as one stuck at 0.
    return Math.min(1, rms * 2);
  }, []);

  /**
   * Loudness *and* timbre, for a visualiser that tracks a voice rather than a
   * volume meter.
   *
   * `brightness` is the spectral centroid across the speech band, normalised:
   * low when someone is speaking in a dark, chesty register, high on sibilants
   * and brighter voices. It gives the orb a second, independent axis, so two
   * people at the same volume don't drive identical motion.
   */
  const getVoiceSignal = useCallback((): { level: number; brightness: number } => {
    const analyser = analyserRef.current;
    if (!analyser) return { level: 0, brightness: 0 };
    const level = getAudioLevel();
    const bins = levelBufferRef.current;
    if (!bins) return { level, brightness: 0 };

    const perBin = (audioRef.current?.context.sampleRate ?? SAMPLE_RATE) / analyser.fftSize;
    const first = Math.max(1, Math.floor(100 / perBin));
    const last = Math.min(bins.length - 1, Math.ceil(4000 / perBin));

    let weighted = 0;
    let total = 0;
    for (let i = first; i <= last; i += 1) {
      const magnitude = bins[i] / 255;
      weighted += magnitude * i;
      total += magnitude;
    }
    // Silence has no meaningful centroid; report neutral rather than a number
    // derived from noise, which would make the orb twitch when nobody is
    // speaking — the opposite of what a "is my mic working" signal should do.
    if (total < 0.001) return { level, brightness: 0 };
    const centroid = weighted / total;
    return { level, brightness: Math.min(1, Math.max(0, (centroid - first) / (last - first))) };
  }, [getAudioLevel]);

  const cleanup = useCallback(() => {
    audioRef.current?.stream.getTracks().forEach((track) => track.stop());
    audioRef.current?.context.close().catch(() => undefined);
    audioRef.current = null;
    // Drop the analyser with the context that owns it, so getAudioLevel goes
    // back to 0 the moment captions stop.
    analyserRef.current = null;
    levelBufferRef.current = null;
    wsRef.current?.close();
    wsRef.current = null;
  }, []);

  const start = useCallback(async () => {
    setError(null);
    setLimit(null);
    setAllowanceWarning(null);
    setSegments([]);
    latenciesRef.current = [];
    setLatency(null);
    pausedRef.current = false;
    pausedMsRef.current = 0;
    pausedAtRef.current = null;
    sessionIdRef.current = crypto.randomUUID();
    setStatus("connecting");

    // 1) Mic first — permission is the likeliest failure, surface it clearly.
    let stream: MediaStream;
    try {
      stream = await navigator.mediaDevices.getUserMedia({
        audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true },
      });
    } catch (err) {
      setStatus("error");
      setError(
        err instanceof DOMException && err.name === "NotAllowedError"
          ? "Microphone access was denied. Captions need the mic — allow access in your browser's site settings, then try again."
          : "Couldn't open the microphone. Check that one is connected and not in use by another app."
      );
      return;
    }

    // 2) Audio pipeline at 16 kHz (browser resamples for us).
    const context = new AudioContext({ sampleRate: SAMPLE_RATE });
    await context.audioWorklet.addModule("/pcm-worklet.js");
    const source = context.createMediaStreamSource(stream);
    const chunker = new AudioWorkletNode(context, "pcm-chunker");
    source.connect(chunker);

    // Loudness tap for the voice orb. Branched off the STT stream on purpose:
    // opening a second getUserMedia for visuals would capture the same device
    // twice with different constraints (STT wants echo cancellation and noise
    // suppression, a visualiser wants neither), which wastes a pipeline and on
    // some devices fails outright. One microphone, one graph.
    const analyser = context.createAnalyser();
    analyser.fftSize = 512;
    analyser.smoothingTimeConstant = 0.3; // responsive, but not jittery
    source.connect(analyser);
    analyserRef.current = analyser;
    audioRef.current = { context, stream };

    // 3) WebSocket to the transcription gateway.
    const backend = process.env.NEXT_PUBLIC_BACKEND_URL ?? "http://localhost:8000";
    const ws = new WebSocket(backend.replace(/^http/, "ws") + "/ws/transcribe");
    wsRef.current = ws;

    ws.onopen = async () => {
      // Sent on every session. The token does two jobs: it identifies whose
      // caption hours to meter, and it lets the backend load this user's voice
      // profiles so speakers can be named. A signed-out user still gets
      // captions — unmetered and unnamed, because there is nobody to attribute
      // them to.
      const token = (await getAccessToken()) ?? undefined;
      ws.send(
        JSON.stringify({
          sampleRate: SAMPLE_RATE,
          encoding: "pcm_s16le",
          token,
          language,
        })
      );
    };

    ws.onmessage = (event) => {
      const message = JSON.parse(event.data as string);
      if (message.type === "ready") {
        if (message.mode === "batch" || message.mode === "streaming") setMode(message.mode);
        captureStartRef.current = performance.now();
        chunker.port.onmessage = (audioEvent) => {
          // Paused means the audio never leaves the device. The track is muted
          // as well, so this is the second of two locks rather than the only
          // one — but it is the one that guarantees nothing is transmitted.
          if (pausedRef.current) return;
          if (ws.readyState === WebSocket.OPEN) ws.send(audioEvent.data as ArrayBuffer);
        };
        setStatus("listening");
      } else if (message.type === "segment") {
        const segment: CaptionSegment = {
          // Scoped to the session, because the provider's turn ids restart at
          // zero every time one begins. Consumers cache per-segment work
          // against this id — translations, "already spoken" — and those caches
          // outlive a session, so a bare turn id meant the first line of a new
          // conversation silently inherited the first line of the previous
          // one's translation and was never re-requested.
          id: `turn-${sessionIdRef.current}-${message.turnId ?? counterRef.current++}`,
          speaker: message.speaker,
          speakerName: message.speakerName ?? null,
          text: message.text,
          start: message.start,
          end: message.end,
          isFinal: message.isFinal,
        };
        if (segment.isFinal && captureStartRef.current) {
          // End-to-end: from when this audio moment was captured to render.
          // Paused time is added back because it advanced the wall clock
          // without advancing the audio timeline `segment.end` counts in.
          const captured = captureStartRef.current + pausedMsRef.current + segment.end * 1000;
          latenciesRef.current.push(Math.max(0, performance.now() - captured));
          const sorted = [...latenciesRef.current].sort((a, b) => a - b);
          setLatency({
            count: sorted.length,
            p50: percentile(sorted, 50),
            p95: percentile(sorted, 95),
          });
        }
        setSegments((list) => smooth(mergeSegment(list, segment)));
      } else if (message.type === "speakerUpdate") {
        // A speaker was identified (or corrected) — relabel their past bubbles.
        //
        // `fillOnly` marks an automatic identification, which may only name
        // bubbles that are still unnamed: one diarization label can carry
        // different people across a session, so overwriting every bubble would
        // rewrite the earlier speaker's lines with the current speaker's name.
        // A manual correction arrives without the flag and overwrites, because
        // the user is explicitly fixing that label.
        setSegments((list) =>
          list.map((s) =>
            s.speaker === message.speaker && !(message.fillOnly && s.speakerName)
              ? { ...s, speakerName: message.speakerName }
              : s
          )
        );
      } else if (message.type === "done") {
        // Session over: anything still marked interim is as final as it gets.
        setSegments((list) => list.map((s) => (s.isFinal ? s : { ...s, isFinal: true })));
      } else if (message.type === "usage") {
        // The 80% notice. Advisory only — the session is starting regardless,
        // which is the whole point of warning early rather than at the wall.
        setAllowanceWarning({
          used: message.used,
          limit: message.limit,
          remaining: message.remaining,
          resetsAt: message.resetsAt ?? null,
        });
      } else if (message.type === "error") {
        if (message.reason === "limit_reached") {
          // Not a failure: the plan ran out. Surfaced separately so the UI can
          // offer the way forward instead of an error banner.
          setLimit({
            resetsAt: message.resetsAt ?? null,
            upgradeTo: message.upgradeTo ?? null,
            message: message.message,
          });
          setStatus("stopped");
        } else {
          setStatus("error");
          setError(message.message);
        }
        cleanup();
      }
    };

    ws.onerror = () => {
      setStatus((current) =>
        current === "listening" || current === "connecting" ? "error" : current
      );
      setError((current) => current ?? "Lost the connection to the caption service.");
      cleanup();
    };
  }, [cleanup, language]);

  /**
   * Hold the session open without capturing anything.
   *
   * Distinct from `stop()` in the one way that matters: the transcript survives.
   * Stopping and starting again clears it, so someone who steps out of a
   * conversation for a minute would come back to an empty pane and lose the
   * part they were still reading.
   *
   * The microphone track is disabled rather than merely ignored. Both locks
   * matter, and for different reasons: muting the track means the browser
   * captures silence, which drops the level meter to zero so the interface
   * cannot claim to be listening while it isn't; gating the send means nothing
   * reaches the network even if a frame was already in flight.
   */
  const pause = useCallback(() => {
    // Guarded on a ref rather than inside a `setStatus` updater: an updater
    // must be pure, and React may call it twice. Muting a microphone twice is
    // harmless, but a side effect in an updater is a bug waiting for the next
    // person to add one that isn't.
    if (statusRef.current !== "listening") return;
    pausedRef.current = true;
    pausedAtRef.current = performance.now();
    audioRef.current?.stream.getTracks().forEach((track) => (track.enabled = false));
    const ws = wsRef.current;
    // The server stops the billing clock on this. Skipping it would charge the
    // user for the pause, which would make the button worse than useless.
    if (ws && ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify({ type: "pause" }));
    setStatus("paused");
  }, []);

  const resume = useCallback(() => {
    if (statusRef.current !== "paused") return;
    if (pausedAtRef.current !== null) {
      pausedMsRef.current += performance.now() - pausedAtRef.current;
      pausedAtRef.current = null;
    }
    pausedRef.current = false;
    audioRef.current?.stream.getTracks().forEach((track) => (track.enabled = true));
    const ws = wsRef.current;
    if (ws && ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify({ type: "resume" }));
    setStatus("listening");
  }, []);

  const correct = useCallback((speakerLabel: string, profileId: string | null) => {
    const ws = wsRef.current;
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({ type: "correct", speaker: speakerLabel, profileId }));
    }
  }, []);

  const stop = useCallback(() => {
    const ws = wsRef.current;
    audioRef.current?.stream.getTracks().forEach((track) => track.stop());
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({ type: "stop" }));
      // let "done" and trailing segments arrive, then close
      const close = () => ws.close();
      const previous = ws.onmessage?.bind(ws);
      ws.onmessage = (event) => {
        previous?.(event);
        if (JSON.parse(event.data as string).type === "done") close();
      };
    } else {
      cleanup();
    }
    setStatus("stopped");
  }, [cleanup]);

  return {
    status,
    error,
    limit,
    allowanceWarning,
    segments,
    latency,
    mode,
    start,
    stop,
    pause,
    resume,
    correct,
    getAudioLevel,
    getVoiceSignal,
    sessionId: sessionIdRef,
  };
}
