import { expect, test } from "@playwright/test";

import { gotoSettled } from "./support";

/**
 * The capture pipeline when the browser refuses the rate we asked for.
 *
 * This is the highest-risk assumption in the mobile port. The code asks for a
 * 16 kHz `AudioContext` and the whole backend contract assumes it — the
 * transcription request declares it, `audio_seconds()` divides by it, and
 * `embedder.embed(pcm, 16000)` trusts it. iOS Safari and WKWebView are known to
 * ignore the request and hand back the hardware rate, and until this task
 * nothing read the rate back: 48 kHz samples went out **labelled** 16 kHz,
 * which reaches the recogniser three times too slow and reads like a bad model
 * rather than a bad number.
 *
 * `scripts/verify-audio.mjs` pins the arithmetic. This pins what only a browser
 * knows: that the real `AudioWorklet`, in a context running at a rate nobody
 * asked for, still puts exactly 16 kHz of PCM on the wire.
 *
 * iOS is simulated by patching `AudioContext` to ignore its `sampleRate`
 * option, which is precisely what the real failure is. That is better than
 * waiting for a handset, because it runs on every commit — the handset check in
 * this task's gate remains, for the things a simulation cannot speak to.
 */

/** 16,000 samples a second at two bytes each, whatever the microphone runs at. */
const HEALTHY_BYTES_PER_SECOND = 32000;
/** 200 ms of that — the chunk size INTRODUCTION §5 asks for. Checked separately
 *  because the byte *rate* cannot see chunk sizing: a chunk a third the size
 *  arriving three times as often looks identical by that measure. */
const HEALTHY_CHUNK_BYTES = 6400;

async function measure(page: import("@playwright/test").Page) {
  await page.getByRole("button", { name: "Measure the microphone" }).click();
  const rate = page.getByTestId("granted-rate");
  await expect(rate).not.toHaveText("—", { timeout: 10_000 });
  // Only appears after half a second of audio, so wait for the placeholder to
  // go rather than for the element to exist — the first version of this matched
  // the chunk counter instead and measured the wrong number entirely.
  const bytes = page.getByTestId("bytes-per-second");
  await expect(bytes).not.toHaveText("—", { timeout: 15_000 });
  return {
    granted: await rate.textContent(),
    chunkBytes: Number(
      (await page.getByTestId("chunk-bytes").textContent())!.replace(/[^\d]/g, "")
    ),
    resampling: await page.getByTestId("resampling").textContent(),
    bytesPerSecond: Number((await bytes.textContent())!.replace(/,/g, "")),
  };
}

test("a browser that honours 16 kHz needs no conversion", async ({ page }) => {
  await gotoSettled(page, "/design");
  const result = await measure(page);

  expect(result.granted).toBe("16000 Hz");
  expect(result.resampling).toBe("not needed");
  expect(result.chunkBytes).toBe(HEALTHY_CHUNK_BYTES);
  expect(result.bytesPerSecond).toBeGreaterThan(HEALTHY_BYTES_PER_SECOND * 0.85);
  expect(result.bytesPerSecond).toBeLessThan(HEALTHY_BYTES_PER_SECOND * 1.15);
});

test("a browser that refuses 16 kHz still sends 16 kHz", async ({ page }) => {
  // Exactly what iOS does: accept the option and ignore it.
  await page.addInitScript(() => {
    const Original = window.AudioContext;
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    (window as any).AudioContext = class extends Original {
      constructor(options?: AudioContextOptions) {
        super({ ...options, sampleRate: 48000 });
      }
    };
  });
  await gotoSettled(page, "/design");
  const result = await measure(page);

  // The simulation has to have worked, or the rest of this proves nothing.
  expect(result.granted, "the patched context did not take effect").toBe("48000 Hz");
  expect(result.resampling).toContain("48000 → 16000");
  // 200 ms of 16 kHz audio, even though the worklet batched 9,600 input samples.
  expect(result.chunkBytes, "chunk duration drifted from 200 ms").toBe(HEALTHY_CHUNK_BYTES);

  // The claim: the wire format is unchanged even though the microphone is not.
  expect(
    result.bytesPerSecond,
    `expected ~${HEALTHY_BYTES_PER_SECOND} B/s on the wire regardless of capture rate`
  ).toBeGreaterThan(HEALTHY_BYTES_PER_SECOND * 0.85);
  expect(result.bytesPerSecond).toBeLessThan(HEALTHY_BYTES_PER_SECOND * 1.15);
});
