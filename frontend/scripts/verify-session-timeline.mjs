/**
 * The client half of pause/resume: what may be sent, and what a caption's
 * latency is once a pause has moved the wall clock without moving the audio.
 *
 * Run: `node scripts/verify-session-timeline.mjs` from /frontend.
 *
 * This replaces a suite that re-expressed the hook's rules "against fakes with
 * the same shape" — that is, against a copy. It was proved worthless by
 * mutation: setting `pausedRef.current = false` inside `pause()`, so audio kept
 * streaming while the interface said Paused, left all 69 checks green. The
 * logic now lives in `lib/sessionTimeline.ts` and this imports the real thing,
 * so the same mutation is no longer expressible in the hook at all.
 */
import { harness, loadTs } from "./lib/harness.mjs";

const { SessionTimeline } = await loadTs(new URL("../lib/sessionTimeline.ts", import.meta.url));

const h = harness();

/** A timeline on a clock the test drives, in milliseconds. */
function at(ms) {
  let now = ms;
  const timeline = new SessionTimeline(() => now);
  return { timeline, set: (t) => (now = t) };
}

h.section("nothing is captured while paused");
{
  const { timeline, set } = at(0);
  timeline.start();
  h.check("audio flows before a pause", timeline.accepts(), true);
  set(1000);
  timeline.pause();
  h.check("paused", timeline.paused, true);
  h.check("audio is refused while paused", timeline.accepts(), false);
  set(4000);
  timeline.resume();
  h.check("audio flows again after resume", timeline.accepts(), true);
  h.check("the pause is remembered", timeline.pausedMs, 3000);
}

h.section("the transitions are idempotent");
{
  const { timeline, set } = at(0);
  timeline.start();
  set(1000);
  h.check("pausing changes state once", timeline.pause(), true);
  h.check("pausing again changes nothing", timeline.pause(), false);
  set(2000);
  h.check("resuming changes state once", timeline.resume(), true);
  h.check("resuming again changes nothing", timeline.resume(), false);
  h.check("a double pause is not counted twice", timeline.pausedMs, 1000);
  h.check("resuming while running cannot rewind the clock", timeline.pausedMs, 1000);
}

h.section("a pause is not reported as latency");
{
  // A caption for audio at t=2s, delivered at wall-clock 7s, having been paused
  // for 4s in between: the true lag is 1s, not 5s.
  const { timeline, set } = at(0);
  timeline.start();
  set(1000);
  timeline.pause();
  set(5000);
  timeline.resume();
  set(7000);
  timeline.observe(2.0);
  h.check("lag excludes the pause", timeline.stats.p50, 1000);
  h.check("one measurement", timeline.stats.count, 1);
}

h.section("without compensation the same pause reads as latency");
{
  // The bug this guards, stated as the arithmetic rather than as prose: drop
  // pausedMs and a five-second pause is reported as five seconds of lag.
  const { timeline, set } = at(0);
  timeline.start();
  set(7000);
  timeline.observe(2.0);
  h.check("an uncompensated session reports the whole wall clock", timeline.stats.p50, 5000);
}

h.section("latency never goes negative");
{
  const { timeline, set } = at(0);
  timeline.start();
  set(500);
  timeline.observe(2.0); // a caption ahead of the wall clock (fixtures replay fast)
  h.check("clamped at zero", timeline.stats.p50, 0);
}

h.section("percentiles");
{
  const { timeline, set } = at(0);
  timeline.start();
  for (const ms of [100, 200, 300, 400, 1000]) {
    set(ms);
    timeline.observe(0);
  }
  h.check("count", timeline.stats.count, 5);
  h.check("p50", timeline.stats.p50, 300);
  h.check("p95", timeline.stats.p95, 1000);
  h.check("no measurements yet is null", at(0).timeline.stats, null);
}

h.section("a fresh session starts clean");
{
  const { timeline, set } = at(0);
  timeline.start();
  set(1000);
  timeline.pause();
  set(3000);
  timeline.resume();
  timeline.observe(0);
  set(5000);
  timeline.start(); // the user stopped and started again
  h.check("the previous session's pause is gone", timeline.pausedMs, 0);
  h.check("the previous session's measurements are gone", timeline.stats, null);
  h.check("a restarted session is not paused", timeline.paused, false);
}

h.done();
