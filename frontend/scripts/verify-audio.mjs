/**
 * The microphone PCM path: rate conversion and int16 encoding.
 *
 * Run: `node scripts/verify-audio.mjs` from /frontend.
 *
 * This is the highest-risk assumption in the mobile port. The capture path
 * *asks* for a 16 kHz `AudioContext` and then declares 16 kHz on the wire —
 * `useTranscription.ts` sent `sampleRate: SAMPLE_RATE` as a constant, and
 * nothing ever read `context.sampleRate` to find out what it actually got.
 * iOS Safari and WKWebView have a long history of ignoring the request and
 * handing back the hardware rate.
 *
 * The failure is silent and total: 48 kHz samples labelled 16 kHz arrive at the
 * recogniser three times too slow, so the transcript is nonsense and the
 * speaker embeddings are meaningless — and it reads like a model problem
 * rather than a sample-rate one.
 *
 * These rules live in a module rather than in `public/pcm-worklet.js` because a
 * worklet is loaded by URL into an audio thread and cannot be imported by a
 * test. The worklet now only batches; every decision worth pinning is here.
 */
import { harness, loadTs } from "./lib/harness.mjs";

const { resampleTo16k, toInt16, TARGET_RATE, chunkSamplesFor } = await loadTs(
  new URL("../lib/audioPcm.ts", import.meta.url)
);

const h = harness();
const check = h.check;

/** A sine at `hz`, `seconds` long, sampled at `rate`. */
const sine = (hz, rate, seconds) => {
  const out = new Float32Array(Math.round(rate * seconds));
  for (let i = 0; i < out.length; i++) out[i] = Math.sin((2 * Math.PI * hz * i) / rate);
  return out;
};

/** Zero crossings per second — a cheap frequency estimate that survives resampling. */
const pitch = (samples, rate) => {
  let crossings = 0;
  for (let i = 1; i < samples.length; i++) {
    if (samples[i - 1] < 0 && samples[i] >= 0) crossings++;
  }
  return (crossings * rate) / samples.length;
};

console.log("target rate");
check("16 kHz, the rate the whole pipeline assumes", TARGET_RATE, 16000);

console.log("\nchunk sizing — 200 ms of input whatever the rate");
check("at 16 kHz", chunkSamplesFor(16000), 3200);
check("at 48 kHz", chunkSamplesFor(48000), 9600);
check("at 44.1 kHz", chunkSamplesFor(44100), 8820);

console.log("\nresampling");
{
  const at48 = sine(440, 48000, 1);
  const out = resampleTo16k(at48, 48000);
  check("48 kHz second becomes 16000 samples", out.length, 16000);
  // The point of the whole exercise: the *sound* has to survive. A resampler
  // that returned the right number of wrong samples would pass a length check
  // and produce exactly the garbage transcript this is meant to prevent.
  check("440 Hz stays 440 Hz", Math.abs(pitch(out, 16000) - 440) < 5, true);
}
{
  const at44 = sine(440, 44100, 1);
  const out = resampleTo16k(at44, 44100);
  check("44.1 kHz second becomes 16000 samples", out.length, 16000);
  check("non-integer ratio keeps pitch", Math.abs(pitch(out, 16000) - 440) < 5, true);
}
{
  const at16 = sine(440, 16000, 0.5);
  const out = resampleTo16k(at16, 16000);
  check("already 16 kHz is untouched", out.length, at16.length);
  check("sample for sample", out[1234], at16[1234]);
}
check("empty input is empty output", resampleTo16k(new Float32Array(0), 48000).length, 0);

console.log("\nint16 encoding");
{
  const pcm = toInt16(new Float32Array([0, 1, -1, 0.5, -0.5]));
  check("silence", pcm[0], 0);
  check("full scale positive", pcm[1], 32767);
  check("full scale negative", pcm[2], -32768);
  check("half scale positive", pcm[3], 16383);
  check("output is Int16Array", pcm instanceof Int16Array, true);
}
{
  // Float32 from a microphone can exceed ±1 after gain; wrapping instead of
  // clamping turns a loud syllable into a burst of noise.
  const pcm = toInt16(new Float32Array([2, -2]));
  check("clamps above +1", pcm[0], 32767);
  check("clamps below -1", pcm[1], -32768);
}

h.done();
