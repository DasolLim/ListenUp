"use client";

import { TARGET_RATE, chunkSamplesFor, resampleTo16k, toInt16 } from "@/lib/audioPcm";

/**
 * One microphone capture graph, used by every path that records audio.
 *
 * Extracted because the alternative was three near-identical copies of the same
 * four calls — live captions, voice enrolment, and the diagnostic panel — and
 * the browser check that measures the pipeline was measuring the *diagnostic's*
 * copy. Deleting the resampling from live captions left that check green, which
 * is the "a test that describes the code rather than importing it" failure this
 * repo keeps finding. There is now one implementation to break.
 *
 * The rate is read back rather than assumed. `new AudioContext({ sampleRate })`
 * is a request, and iOS Safari and WKWebView are known to refuse it and hand
 * over the hardware rate; the old code declared 16 kHz on the wire either way,
 * which puts 48 kHz audio in front of the recogniser three times too slow.
 */
export type Capture = {
  context: AudioContext;
  /** What the microphone is really running at, which may not be TARGET_RATE. */
  captureRate: number;
  /** The mic node, so a caller can branch a level meter off the same graph. */
  source: MediaStreamAudioSourceNode;
  close: () => void;
};

export async function openCapture(
  stream: MediaStream,
  /** Called with 200 ms of 16 kHz mono PCM, whatever the microphone runs at. */
  onChunk: (pcm: Int16Array<ArrayBuffer>) => void
): Promise<Capture> {
  const context = new AudioContext({ sampleRate: TARGET_RATE });
  const captureRate = context.sampleRate;
  if (captureRate !== TARGET_RATE) {
    console.info(
      `[listenup] microphone runs at ${captureRate} Hz, not the requested ` +
        `${TARGET_RATE}; resampling on the client.`
    );
  }
  await context.audioWorklet.addModule("/pcm-worklet.js");
  const source = context.createMediaStreamSource(stream);
  const chunker = new AudioWorkletNode(context, "pcm-chunker", {
    // 200 ms of *input*, so the chunk is 200 ms of sound rather than 200 ms
    // worth of samples at a rate we guessed.
    processorOptions: { chunkSamples: chunkSamplesFor(captureRate) },
  });
  source.connect(chunker);
  chunker.port.onmessage = (event) => {
    onChunk(toInt16(resampleTo16k(event.data as Float32Array, captureRate)));
  };

  return {
    context,
    captureRate,
    source,
    close: () => {
      stream.getTracks().forEach((track) => track.stop());
      context.close().catch(() => undefined);
    },
  };
}
