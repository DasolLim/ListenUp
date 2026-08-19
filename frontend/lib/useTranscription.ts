"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { TARGET_RATE } from "@/lib/audioPcm";
import { openCapture } from "@/lib/captureGraph";
import { getAccessToken } from "@/lib/auth/token";
import { applyCaptionMessage } from "@/lib/captionStream";
import type { CaptionSegment } from "@/lib/captionStream";
import { SessionTimeline } from "@/lib/sessionTimeline";
import type { LatencyStats } from "@/lib/sessionTimeline";

export type { CaptionSegment } from "@/lib/captionStream";
export type { LatencyStats } from "@/lib/sessionTimeline";

export type TranscriptionStatus =
  "idle" | "connecting" | "listening" | "paused" | "stopped" | "error";

// The rate the whole pipeline is written around; see lib/audioPcm.ts. Kept as
// a local alias because the analyser fallbacks below read it too.
const SAMPLE_RATE = TARGET_RATE;

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
  /** What the microphone actually runs at, once a session has opened. Exposed
   *  because "my captions are gibberish" and "this device refused 16 kHz" are
   *  the same report, and only one of them is answerable without it. */
  const [captureRate, setCaptureRate] = useState<number | null>(null);
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
  const counterRef = useRef(0);
  const sessionIdRef = useRef<string>("");

  // When the session started, how long it has been paused, and how late each
  // caption was. One object rather than four refs, and deliberately the *only*
  // record of whether we are paused: the audio callback, the billing clock and
  // the latency arithmetic all read it, so "the mic gate and the billing clock
  // disagree" is not a state this code can be in.
  const timelineRef = useRef<SessionTimeline>(null as unknown as SessionTimeline);
  if (timelineRef.current === null) timelineRef.current = new SessionTimeline();
  const timeline = timelineRef.current;

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
    setLatency(null);
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

    // 2) One shared capture graph — see lib/captureGraph.ts. It reads back the
    // rate the context actually granted and resamples anything that is not
    // 16 kHz, because `new AudioContext({ sampleRate })` is a request that iOS
    // is known to refuse.
    const capture = await openCapture(stream, (pcm) => {
      // Paused means the audio never leaves the device. The track is muted as
      // well, so this is the second of two locks rather than the only one —
      // but it is the one that guarantees nothing is transmitted.
      if (!timeline.accepts()) return;
      if (wsRef.current?.readyState === WebSocket.OPEN) wsRef.current.send(pcm.buffer);
    });
    const context = capture.context;
    setCaptureRate(capture.captureRate);

    // Loudness tap for the voice orb. Branched off the STT stream on purpose:
    // opening a second getUserMedia for visuals would capture the same device
    // twice with different constraints (STT wants echo cancellation and noise
    // suppression, a visualiser wants neither), which wastes a pipeline and on
    // some devices fails outright. One microphone, one graph.
    const analyser = context.createAnalyser();
    analyser.fftSize = 512;
    analyser.smoothingTimeConstant = 0.3; // responsive, but not jittery
    capture.source.connect(analyser);
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
          // Now true rather than assumed: anything else was resampled above.
          sampleRate: TARGET_RATE,
          encoding: "pcm_s16le",
          token,
          language,
        })
      );
    };

    ws.onmessage = (event) => {
      const message = JSON.parse(event.data as string);
      // A number for a provider that sends no turn id, taken *outside* the
      // state updater: an updater must be pure, and React may call it twice —
      // which would hand the two calls different ids for one utterance and draw
      // it as two bubbles.
      const fallbackIndex =
        message.type === "segment" && message.turnId === undefined
          ? counterRef.current++
          : counterRef.current;
      // Every message goes through one reducer, which returns the transcript
      // untouched for the ones that say nothing about it. Deciding here which
      // messages matter would put that decision in the transport, where it was
      // reachable only by opening a socket in a browser.
      setSegments((list) =>
        applyCaptionMessage(list, message, sessionIdRef.current, fallbackIndex)
      );
      if (message.type === "ready") {
        if (message.mode === "batch" || message.mode === "streaming") setMode(message.mode);
        timeline.start();
        setStatus("listening");
      } else if (message.type === "segment") {
        if (message.isFinal) {
          // End to end: from when this audio moment was captured to render.
          timeline.observe(message.end);
          setLatency(timeline.stats);
        }
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
  }, [cleanup, language, timeline]);

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
    if (!timeline.pause()) return;
    audioRef.current?.stream.getTracks().forEach((track) => (track.enabled = false));
    const ws = wsRef.current;
    // The server stops the billing clock on this. Skipping it would charge the
    // user for the pause, which would make the button worse than useless.
    if (ws && ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify({ type: "pause" }));
    setStatus("paused");
  }, [timeline]);

  const resume = useCallback(() => {
    if (statusRef.current !== "paused") return;
    if (!timeline.resume()) return;
    audioRef.current?.stream.getTracks().forEach((track) => (track.enabled = true));
    const ws = wsRef.current;
    if (ws && ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify({ type: "resume" }));
    setStatus("listening");
  }, [timeline]);

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
    captureRate,
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
