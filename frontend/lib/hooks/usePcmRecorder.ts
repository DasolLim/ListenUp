"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { openCapture } from "@/lib/captureGraph";

/** Records mic audio as 16 kHz mono s16le PCM via the shared AudioWorklet.
 * Used by enrollment (20–30 s guided recording). */
export function usePcmRecorder(maxSeconds = 30) {
  const [recording, setRecording] = useState(false);
  const [seconds, setSeconds] = useState(0);
  const [error, setError] = useState<string | null>(null);
  /** What the microphone actually runs at — see lib/audioPcm.ts. */
  const [captureRate, setCaptureRate] = useState<number | null>(null);
  // Int16Array rather than its `.buffer`: a typed array is a valid BlobPart,
  // and keeping it typed means the element size is never in doubt at the seam.
  const chunksRef = useRef<Int16Array<ArrayBuffer>[]>([]);
  const audioRef = useRef<{ context: AudioContext; stream: MediaStream } | null>(null);

  const stop = useCallback(() => {
    audioRef.current?.stream.getTracks().forEach((t) => t.stop());
    audioRef.current?.context.close().catch(() => undefined);
    audioRef.current = null;
    setRecording(false);
  }, []);

  const start = useCallback(async () => {
    setError(null);
    chunksRef.current = [];
    setSeconds(0);
    let stream: MediaStream;
    try {
      stream = await navigator.mediaDevices.getUserMedia({
        audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true },
      });
    } catch (err) {
      setError(
        err instanceof DOMException && err.name === "NotAllowedError"
          ? "Microphone access was denied. Enrollment needs the mic — allow access and try again."
          : "Couldn't open the microphone."
      );
      return;
    }
    // The same graph live captions uses, so a device that refuses 16 kHz is
    // handled once rather than in each place that records. A wrong rate here
    // would enrol a voice profile from mislabelled audio, and a wrong profile
    // is worse than none — it goes on to name the wrong person.
    const capture = await openCapture(stream, (pcm) => {
      chunksRef.current.push(pcm);
      // each chunk is 200 ms; auto-stop at the cap (event context, not render)
      const elapsed = chunksRef.current.length * 0.2;
      setSeconds(elapsed);
      if (elapsed >= maxSeconds) stop();
    });
    setCaptureRate(capture.captureRate);
    audioRef.current = { context: capture.context, stream };
    setRecording(true);
  }, [maxSeconds, stop]);

  const getPcmBlob = useCallback(() => {
    return new Blob(chunksRef.current, { type: "application/octet-stream" });
  }, []);

  const reset = useCallback(() => {
    chunksRef.current = [];
    setSeconds(0);
    setError(null);
  }, []);

  useEffect(() => stop, [stop]);

  return { recording, seconds, error, captureRate, start, stop, reset, getPcmBlob };
}
