// Batches mic audio into fixed-duration blocks and hands them to the main
// thread as Float32.
//
// It used to batch a fixed 3200 samples and convert to Int16 here, on the
// assumption that `AudioContext` had granted the 16 kHz it was asked for. That
// assumption is exactly what breaks on iOS: at 48 kHz, 3200 samples is 66 ms
// rather than 200, and the samples were 48 kHz audio being labelled 16 kHz all
// the way to the recogniser.
//
// So the batch size now comes from the main thread, which knows the rate the
// context actually granted, and conversion moved to `lib/audioPcm.ts` — a
// worklet is loaded by URL into an audio thread and cannot be imported by a
// test, and this is the part of the pipeline least able to afford being
// untestable.
class PcmChunker extends AudioWorkletProcessor {
  constructor(options) {
    super();
    // 200 ms at whatever rate this context is running at. Falls back to the
    // 16 kHz count so an older caller still behaves as it did.
    this.chunkSamples = options?.processorOptions?.chunkSamples ?? 3200;
    this.buffers = [];
    this.length = 0;
  }

  process(inputs) {
    const channel = inputs[0] && inputs[0][0];
    if (channel && channel.length) {
      this.buffers.push(new Float32Array(channel));
      this.length += channel.length;
      if (this.length >= this.chunkSamples) {
        const all = new Float32Array(this.length);
        let offset = 0;
        for (const buffer of this.buffers) {
          all.set(buffer, offset);
          offset += buffer.length;
        }
        this.port.postMessage(all, [all.buffer]);
        this.buffers = [];
        this.length = 0;
      }
    }
    return true;
  }
}

registerProcessor("pcm-chunker", PcmChunker);
