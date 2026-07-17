"use client";

import { useCallback, useRef, useState } from "react";

export type CaptionSegment = {
  id: string;
  speaker: string;
  text: string;
  start: number;
  end: number;
  isFinal: boolean;
};

export type TranscriptionStatus = "idle" | "connecting" | "listening" | "stopped" | "error";

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

export function useTranscription() {
  const [status, setStatus] = useState<TranscriptionStatus>("idle");
  const [error, setError] = useState<string | null>(null);
  const [segments, setSegments] = useState<CaptionSegment[]>([]);
  const [latency, setLatency] = useState<LatencyStats>(null);

  const wsRef = useRef<WebSocket | null>(null);
  const audioRef = useRef<{ context: AudioContext; stream: MediaStream } | null>(null);
  const captureStartRef = useRef<number>(0);
  const latenciesRef = useRef<number[]>([]);
  const counterRef = useRef(0);
  const sessionIdRef = useRef<string>("");

  const cleanup = useCallback(() => {
    audioRef.current?.stream.getTracks().forEach((track) => track.stop());
    audioRef.current?.context.close().catch(() => undefined);
    audioRef.current = null;
    wsRef.current?.close();
    wsRef.current = null;
  }, []);

  const start = useCallback(async () => {
    setError(null);
    setSegments([]);
    latenciesRef.current = [];
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

    // 2) Audio pipeline at 16 kHz (browser resamples for us).
    const context = new AudioContext({ sampleRate: SAMPLE_RATE });
    await context.audioWorklet.addModule("/pcm-worklet.js");
    const source = context.createMediaStreamSource(stream);
    const chunker = new AudioWorkletNode(context, "pcm-chunker");
    source.connect(chunker);
    audioRef.current = { context, stream };

    // 3) WebSocket to the transcription gateway.
    const backend = process.env.NEXT_PUBLIC_BACKEND_URL ?? "http://localhost:8000";
    const ws = new WebSocket(backend.replace(/^http/, "ws") + "/ws/transcribe");
    wsRef.current = ws;

    ws.onopen = () => {
      ws.send(JSON.stringify({ sampleRate: SAMPLE_RATE, encoding: "pcm_s16le" }));
    };

    ws.onmessage = (event) => {
      const message = JSON.parse(event.data as string);
      if (message.type === "ready") {
        captureStartRef.current = performance.now();
        chunker.port.onmessage = (audioEvent) => {
          if (ws.readyState === WebSocket.OPEN) ws.send(audioEvent.data as ArrayBuffer);
        };
        setStatus("listening");
      } else if (message.type === "segment") {
        const segment: CaptionSegment = {
          id: `turn-${message.turnId ?? counterRef.current++}`,
          speaker: message.speaker,
          text: message.text,
          start: message.start,
          end: message.end,
          isFinal: message.isFinal,
        };
        if (segment.isFinal && captureStartRef.current) {
          // End-to-end: from when this audio moment was captured to render.
          const captured = captureStartRef.current + segment.end * 1000;
          latenciesRef.current.push(Math.max(0, performance.now() - captured));
          const sorted = [...latenciesRef.current].sort((a, b) => a - b);
          setLatency({
            count: sorted.length,
            p50: percentile(sorted, 50),
            p95: percentile(sorted, 95),
          });
        }
        setSegments((list) => smooth(mergeSegment(list, segment)));
      } else if (message.type === "done") {
        // Session over: anything still marked interim is as final as it gets.
        setSegments((list) => list.map((s) => (s.isFinal ? s : { ...s, isFinal: true })));
      } else if (message.type === "error") {
        setStatus("error");
        setError(message.message);
        cleanup();
      }
    };

    ws.onerror = () => {
      setStatus((current) => (current === "listening" || current === "connecting" ? "error" : current));
      setError((current) => current ?? "Lost the connection to the caption service.");
      cleanup();
    };
  }, [cleanup]);

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

  return { status, error, segments, latency, start, stop, sessionId: sessionIdRef };
}
