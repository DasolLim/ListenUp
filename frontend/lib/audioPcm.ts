/**
 * Turning whatever the microphone gives us into what the backend expects.
 *
 * **16 kHz is a contract, not a preference.** The transcription request
 * declares it, `audio_seconds()` divides by it, and `embedder.embed(pcm, 16000)`
 * assumes it — so the number cannot simply be changed on the wire without
 * rippling into speaker identity. The capture side has to meet it.
 *
 * Until now it was *assumed* to be met: the code asked for a 16 kHz
 * `AudioContext` and then declared 16 kHz to the server without ever reading
 * back what it was given. iOS Safari and WKWebView are known to ignore the
 * request and hand over the hardware rate, and the resulting failure is silent
 * and total — 48 kHz samples labelled 16 kHz reach the recogniser three times
 * too slow, so the transcript is nonsense and the embeddings are meaningless.
 * It reads like a bad model rather than a bad number.
 *
 * These functions live here, not in `public/pcm-worklet.js`, because a worklet
 * is loaded by URL into an audio thread and cannot be imported by a test. The
 * worklet batches; every decision worth pinning is in this file.
 */

/** The rate the entire pipeline is written around. */
export const TARGET_RATE = 16000;

/** 200 ms, the chunk size INTRODUCTION §5 asks for (100–250 ms). */
const CHUNK_SECONDS = 0.2;

/**
 * How many input samples make 200 ms at this rate.
 *
 * The old worklet batched a fixed 3200 samples, which is 200 ms only at 16 kHz.
 * At 48 kHz the same count is 66 ms, so a device that refused the requested
 * rate would also have started sending chunks three times as often.
 */
export function chunkSamplesFor(rate: number): number {
  return Math.round(rate * CHUNK_SECONDS);
}

/**
 * Resample mono float audio to 16 kHz by linear interpolation.
 *
 * Linear is enough here and a filter bank is not worth its weight: speech
 * content sits far below the 8 kHz Nyquist limit of the target rate, and the
 * recogniser is trained on telephone-grade audio. `docs/plans/PLAN_MOBILE_APP.md` says
 * this explicitly — do not add a DSP library for this.
 *
 * Already at the target rate, the input is returned untouched rather than
 * round-tripped through the interpolator, so the common desktop case costs
 * nothing and cannot be degraded by this code at all.
 */
export function resampleTo16k(input: Float32Array, fromRate: number): Float32Array {
  if (fromRate === TARGET_RATE || input.length === 0) return input;

  const ratio = fromRate / TARGET_RATE;
  const outLength = Math.round(input.length / ratio);
  const out = new Float32Array(outLength);
  for (let i = 0; i < outLength; i++) {
    const at = i * ratio;
    const low = Math.floor(at);
    const high = Math.min(low + 1, input.length - 1);
    const fraction = at - low;
    out[i] = input[low] * (1 - fraction) + input[high] * fraction;
  }
  return out;
}

/**
 * Float samples to signed 16-bit PCM.
 *
 * Clamped, not wrapped. Microphone float can exceed ±1 once gain is applied,
 * and letting it wrap turns a loud syllable into a burst of noise — audible as
 * a transcription error rather than as distortion.
 */
// The return type names its backing store: recent TypeScript distinguishes
// `ArrayBuffer` from `SharedArrayBuffer`, and a `Blob` will only take the former.
export function toInt16(samples: Float32Array): Int16Array<ArrayBuffer> {
  const pcm = new Int16Array(samples.length);
  for (let i = 0; i < samples.length; i++) {
    const s = Math.max(-1, Math.min(1, samples[i]));
    pcm[i] = s < 0 ? s * 0x8000 : s * 0x7fff;
  }
  return pcm;
}
