"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import Button from "@/components/ui/Button";
import { TARGET_RATE } from "@/lib/audioPcm";
import { openCapture } from "@/lib/captureGraph";

/**
 * What this device's microphone actually does.
 *
 * The single highest-risk unknown in the mobile port is whether iOS honours
 * `new AudioContext({ sampleRate: 16000 })`. Safari and WKWebView are known to
 * ignore it and hand back the hardware rate, and the resulting failure is
 * silent: 48 kHz samples labelled 16 kHz reach the recogniser three times too
 * slow, so the transcript is nonsense and it reads like a bad model.
 *
 * The client now resamples whatever it is given, so the failure should not
 * occur — but "should not" is not a measurement, and this panel is how the
 * number gets read off a real handset.
 *
 * Deliberately on `/design`, which needs no sign-in, and deliberately opening
 * **no socket**: reading this costs nothing at any provider and nothing off an
 * allowance, so it can be run on any phone that happens to be nearby.
 */
export default function MicDiagnostic() {
  const [state, setState] = useState<"idle" | "running" | "denied">("idle");
  const [granted, setGranted] = useState<number | null>(null);
  const [chunks, setChunks] = useState(0);
  /** Computed in the chunk handler, not during render: `performance.now()` is
   *  impure and a ref is not readable while rendering. */
  const [bytesPerSecond, setBytesPerSecond] = useState<number | null>(null);
  /** Bytes in the most recent chunk. Bytes/second cannot see chunk *sizing* —
   *  a chunk a third the size arriving three times as often gives the same
   *  rate — and chunk duration is its own constraint (INTRODUCTION §5 asks for
   *  100–250 ms) as well as the message frequency on a cellular link. */
  const [chunkBytes, setChunkBytes] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const startedAt = useRef(0);
  const audio = useRef<{ context: AudioContext; stream: MediaStream } | null>(null);

  const stop = useCallback(() => {
    audio.current?.stream.getTracks().forEach((t) => t.stop());
    audio.current?.context.close().catch(() => undefined);
    audio.current = null;
    setState("idle");
  }, []);

  const start = useCallback(async () => {
    setError(null);
    setChunks(0);
    setBytesPerSecond(null);
    setChunkBytes(null);
    let stream: MediaStream;
    try {
      stream = await navigator.mediaDevices.getUserMedia({ audio: { channelCount: 1 } });
    } catch {
      setState("denied");
      setError("Microphone access was refused, so there is nothing to measure.");
      return;
    }
    // The same graph live captions uses. That is the whole point of this
    // panel: measuring a parallel copy would report on code nobody ships.
    startedAt.current = performance.now();
    let total = 0;
    const capture = await openCapture(stream, (pcm) => {
      total += pcm.byteLength;
      const elapsed = (performance.now() - startedAt.current) / 1000;
      setChunks((n) => n + 1);
      setChunkBytes(pcm.byteLength);
      if (elapsed > 0.5) setBytesPerSecond(Math.round(total / elapsed));
    });
    setGranted(capture.captureRate);
    audio.current = { context: capture.context, stream };
    setState("running");
  }, []);

  useEffect(() => stop, [stop]);

  const resampling = granted !== null && granted !== TARGET_RATE;

  return (
    <div className="glass flex flex-col gap-3 rounded-2xl p-5" data-testid="mic-diagnostic">
      <p className="text-sm leading-relaxed text-ink-soft">
        Open this page on a phone and tap Measure. It reports what the microphone actually runs at —
        nothing is sent anywhere, and no session is started.
      </p>
      <div className="flex flex-wrap items-center gap-2">
        {state === "running" ? (
          <Button variant="ghost" onClick={stop}>
            Stop
          </Button>
        ) : (
          <Button onClick={start}>Measure the microphone</Button>
        )}
      </div>
      {error && (
        <p role="alert" className="text-sm text-error-strong">
          {error}
        </p>
      )}
      <dl className="grid grid-cols-2 gap-x-4 gap-y-1 text-sm">
        <dt className="text-ink-soft">Requested</dt>
        <dd className="numeric text-ink">{TARGET_RATE} Hz</dd>
        <dt className="text-ink-soft">Granted</dt>
        <dd className="numeric text-ink" data-testid="granted-rate">
          {granted === null ? "—" : `${granted} Hz`}
        </dd>
        <dt className="text-ink-soft">Resampling</dt>
        <dd className="text-ink" data-testid="resampling">
          {granted === null ? "—" : resampling ? `yes, ${granted} → ${TARGET_RATE}` : "not needed"}
        </dd>
        <dt className="text-ink-soft">Chunks sent</dt>
        <dd className="numeric text-ink">{chunks}</dd>
        <dt className="text-ink-soft">Chunk size</dt>
        <dd className="numeric text-ink" data-testid="chunk-bytes">
          {chunkBytes === null ? "—" : `${chunkBytes.toLocaleString()} B`}
        </dd>
        <dt className="text-ink-soft">Bytes / second</dt>
        <dd className="numeric text-ink" data-testid="bytes-per-second">
          {bytesPerSecond === null ? "—" : bytesPerSecond.toLocaleString()}
        </dd>
      </dl>
      <p className="text-[13px] leading-relaxed text-ink-soft">
        Healthy output is <strong className="text-ink">6,400 B</strong> per chunk and{" "}
        <strong className="text-ink">32,000 bytes/second</strong> — 16,000 samples at two bytes each
        — whatever the granted rate says. A different number means the conversion is wrong, not the
        microphone.
      </p>
    </div>
  );
}
