/**
 * When a caption session started, how long it spent paused, and how far behind
 * each caption actually landed.
 *
 * All three used to be loose refs inside `useTranscription`, and the checks
 * that covered them re-expressed the rules "against fakes with the same shape"
 * — a copy. Mutation proved the copy worthless: setting `pausedRef.current =
 * false` inside `pause()`, so audio kept streaming while the interface said
 * Paused, left every check green.
 *
 * There is deliberately no separate `paused` flag in the hook now. The hook
 * asks this object, so "the mic gate and the billing clock disagree" is not a
 * state the code can be in.
 *
 * The arithmetic that earns this a module of its own: `segment.end` is a
 * position in the *audio* timeline, which stops advancing while paused, so
 * mapping an audio moment back to the wall clock has to add the pauses back on.
 * Without that the first caption after a pause reports a latency inflated by
 * the whole pause — a false cliff in exactly the series the latency work reads.
 */

import { summarise, type Summary } from "@/lib/stats";

export type LatencyStats = Summary;

export class SessionTimeline {
  private startedAt = 0;
  private started = false;
  private paused_ = false;
  private pausedAt: number | null = null;
  private pausedTotal = 0;
  private lags: number[] = [];

  /** `now` is injectable so the rules can be checked without a real clock. */
  constructor(private readonly now: () => number = () => performance.now()) {}

  /** Begin (or restart) a session. Everything the last one accumulated is dropped. */
  start(): void {
    this.startedAt = this.now();
    this.started = true;
    this.paused_ = false;
    this.pausedAt = null;
    this.pausedTotal = 0;
    this.lags = [];
  }

  get paused(): boolean {
    return this.paused_;
  }

  /** Whether an audio frame may be sent. The only gate the hook consults. */
  accepts(): boolean {
    return !this.paused_;
  }

  /** Returns whether this actually changed state, so callers stay idempotent. */
  pause(): boolean {
    if (this.paused_) return false;
    this.paused_ = true;
    this.pausedAt = this.now();
    return true;
  }

  resume(): boolean {
    if (!this.paused_) return false;
    if (this.pausedAt !== null) this.pausedTotal += this.now() - this.pausedAt;
    this.pausedAt = null;
    this.paused_ = false;
    return true;
  }

  /** Wall-clock milliseconds spent paused so far. */
  get pausedMs(): number {
    return this.pausedTotal;
  }

  /**
   * Record how late one finalised caption was, end to end: from the moment its
   * audio was captured to the moment it arrived.
   */
  observe(segmentEnd: number): void {
    // A session that never started has no capture moment to measure from —
    // and `startedAt` can legitimately be 0, so this is a flag rather than a
    // truthiness check on the timestamp.
    if (!this.started) return;
    const captured = this.startedAt + this.pausedTotal + segmentEnd * 1000;
    this.lags.push(Math.max(0, this.now() - captured));
  }

  get stats(): LatencyStats {
    return summarise(this.lags);
  }
}
