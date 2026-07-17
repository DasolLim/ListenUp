// Batches mic audio into ~200 ms Int16 PCM chunks (INTRODUCTION §5: 100–250 ms).
// The AudioContext is created at 16 kHz, so `sampleRate` here is already 16000
// and the browser has done the resampling — this worklet only converts + batches.
const CHUNK_SAMPLES = 3200; // 200 ms @ 16 kHz

class PcmChunker extends AudioWorkletProcessor {
  constructor() {
    super();
    this.buffers = [];
    this.length = 0;
  }

  process(inputs) {
    const channel = inputs[0] && inputs[0][0];
    if (channel && channel.length) {
      this.buffers.push(new Float32Array(channel));
      this.length += channel.length;
      if (this.length >= CHUNK_SAMPLES) {
        const all = new Float32Array(this.length);
        let offset = 0;
        for (const buffer of this.buffers) {
          all.set(buffer, offset);
          offset += buffer.length;
        }
        const pcm = new Int16Array(all.length);
        for (let i = 0; i < all.length; i++) {
          const s = Math.max(-1, Math.min(1, all[i]));
          pcm[i] = s < 0 ? s * 0x8000 : s * 0x7fff;
        }
        this.port.postMessage(pcm.buffer, [pcm.buffer]);
        this.buffers = [];
        this.length = 0;
      }
    }
    return true;
  }
}

registerProcessor("pcm-chunker", PcmChunker);
