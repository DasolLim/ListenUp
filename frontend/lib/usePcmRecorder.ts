"use client";

import { useCallback, useEffect, useRef, useState } from "react";

/** Records mic audio as 16 kHz mono s16le PCM via the shared AudioWorklet.
 * Used by enrollment (20–30 s guided recording). */
export function usePcmRecorder(maxSeconds = 30) {
  const [recording, setRecording] = useState(false);
  const [seconds, setSeconds] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const chunksRef = useRef<ArrayBuffer[]>([]);
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
    const context = new AudioContext({ sampleRate: 16000 });
    await context.audioWorklet.addModule("/pcm-worklet.js");
    const source = context.createMediaStreamSource(stream);
    const chunker = new AudioWorkletNode(context, "pcm-chunker");
    source.connect(chunker);
    chunker.port.onmessage = (event) => {
      chunksRef.current.push(event.data as ArrayBuffer);
      // each chunk is 200 ms; auto-stop at the cap (event context, not render)
      const elapsed = chunksRef.current.length * 0.2;
      setSeconds(elapsed);
      if (elapsed >= maxSeconds) stop();
    };
    audioRef.current = { context, stream };
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

  return { recording, seconds, error, start, stop, reset, getPcmBlob };
}
