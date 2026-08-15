/**
 * The client half of pause/resume: state machine, mic gate, wire frames, and
 * the latency compensation.
 *
 * Run: `node scripts/verify-pause.mjs` from /frontend.
 *
 * `useTranscription` cannot be imported here (React + Web Audio + WebSocket), so
 * the rules under test are re-expressed against fakes with the same shape. The
 * value is in the transitions, which are what a wrong pause button gets wrong:
 * capturing while paused, billing a pause, or reporting a pause as latency.
 */

let pass = 0;
let fail = 0;
function check(name, actual, expected) {
  if (JSON.stringify(actual) === JSON.stringify(expected)) {
    pass += 1;
    console.log(`  ok   ${name}`);
  } else {
    fail += 1;
    console.log(
      `  FAIL ${name}\n    expected ${JSON.stringify(expected)}\n    actual   ${JSON.stringify(actual)}`
    );
  }
}

/** Mirrors the hook's pause/resume/latency logic exactly. */
function makeSession() {
  let now = 0;
  const sent = [];
  const tracks = [{ enabled: true }, { enabled: true }];
  const state = {
    status: "idle",
    paused: false,
    pausedMs: 0,
    pausedAt: null,
    captureStart: 0,
    latencies: [],
  };

  return {
    advance: (ms) => (now += ms),
    sent,
    tracks,
    state,
    start() {
      state.status = "listening";
      state.paused = false;
      state.pausedMs = 0;
      state.pausedAt = null;
      state.captureStart = now;
      state.latencies = [];
      tracks.forEach((t) => (t.enabled = true));
    },
    pause() {
      if (state.status !== "listening") return;
      state.paused = true;
      state.pausedAt = now;
      tracks.forEach((t) => (t.enabled = false));
      sent.push({ type: "pause" });
      state.status = "paused";
    },
    resume() {
      if (state.status !== "paused") return;
      if (state.pausedAt !== null) {
        state.pausedMs += now - state.pausedAt;
        state.pausedAt = null;
      }
      state.paused = false;
      tracks.forEach((t) => (t.enabled = true));
      sent.push({ type: "resume" });
      state.status = "listening";
    },
    stop() {
      sent.push({ type: "stop" });
      state.status = "stopped";
    },
    /** One 200 ms audio frame from the worklet. */
    emitAudio() {
      if (state.paused) return;
      sent.push({ type: "audio" });
    },
    /** A finalised segment whose audio ended at `endSeconds` on the audio timeline. */
    receiveFinal(endSeconds) {
      const captured = state.captureStart + state.pausedMs + endSeconds * 1000;
      state.latencies.push(Math.max(0, now - captured));
    },
  };
}

console.log("\nstate machine");

{
  const s = makeSession();
  s.start();
  s.pause();
  check("pause from listening -> paused", s.state.status, "paused");
  s.resume();
  check("resume from paused -> listening", s.state.status, "listening");
}

{
  const s = makeSession();
  s.pause();
  check("pause while idle is refused", [s.state.status, s.sent.length], ["idle", 0]);
}

{
  const s = makeSession();
  s.start();
  s.resume();
  check("resume while listening is refused", [s.state.status, s.sent.length], ["listening", 0]);
}

{
  const s = makeSession();
  s.start();
  s.pause();
  s.pause();
  s.pause();
  check("repeated pause sends one frame", s.sent.filter((m) => m.type === "pause").length, 1);
}

{
  const s = makeSession();
  s.start();
  s.pause();
  s.stop();
  check("stop works while paused", s.state.status, "stopped");
}

console.log("\nthe microphone actually stops");

{
  const s = makeSession();
  s.start();
  check("tracks live while listening", s.tracks.map((t) => t.enabled), [true, true]);
  s.pause();
  check("tracks muted on pause", s.tracks.map((t) => t.enabled), [false, false]);
  s.resume();
  check("tracks live again on resume", s.tracks.map((t) => t.enabled), [true, true]);
}

{
  const s = makeSession();
  s.start();
  for (let i = 0; i < 5; i += 1) s.emitAudio();
  s.pause();
  for (let i = 0; i < 50; i += 1) s.emitAudio(); // frames still arriving from the worklet
  s.resume();
  for (let i = 0; i < 3; i += 1) s.emitAudio();
  check("no audio frame is sent while paused", s.sent.filter((m) => m.type === "audio").length, 8);
}

console.log("\nframe order on the wire");

{
  const s = makeSession();
  s.start();
  s.emitAudio();
  s.pause();
  s.emitAudio();
  s.resume();
  s.emitAudio();
  s.stop();
  check(
    "wire sees audio, pause, resume, audio, stop",
    s.sent.map((m) => m.type),
    ["audio", "pause", "resume", "audio", "stop"]
  );
}

console.log("\nlatency excludes the pause");

{
  // Speak for 2 s, pause 5 min, resume, speak 1 s more. The caption for the
  // second sentence ends at 3 s on the AUDIO timeline but arrives 302 s into
  // the session by the wall clock.
  const s = makeSession();
  s.start();
  s.advance(2000);
  s.receiveFinal(2); // caption for the first 2 s, on time
  s.pause();
  s.advance(300_000);
  s.resume();
  s.advance(1000);
  s.receiveFinal(3); // caption for the second stretch, also on time
  check("both captions read as on time", s.state.latencies, [0, 0]);
}

{
  // The same session measured WITHOUT compensation, to show what it would say.
  const s = makeSession();
  s.start();
  s.advance(2000);
  s.receiveFinal(2);
  s.pause();
  s.advance(300_000);
  s.resume();
  s.state.pausedMs = 0; // the bug: forget the pause
  s.advance(1000);
  s.receiveFinal(3);
  check("uncompensated, the pause reads as 5 min of latency", s.state.latencies, [0, 300_000]);
}

{
  // Real lag must still be reported after a pause.
  const s = makeSession();
  s.start();
  s.pause();
  s.advance(60_000);
  s.resume();
  s.advance(5000);
  s.receiveFinal(4); // 4 s of audio, arriving at 5 s -> 1 s late
  check("genuine lag after a pause is still measured", s.state.latencies, [1000]);
}

{
  const s = makeSession();
  s.start();
  s.pause();
  s.advance(1000);
  s.resume();
  s.pause();
  s.advance(2000);
  s.resume();
  check("repeated pauses accumulate", s.state.pausedMs, 3000);
}

{
  const s = makeSession();
  s.start();
  s.advance(5000);
  s.pause();
  s.advance(9000);
  s.resume();
  s.start(); // a fresh session
  check("start clears pause bookkeeping", [s.state.pausedMs, s.state.pausedAt], [0, null]);
}

console.log(`\n${pass}/${pass + fail} checks passed`);
process.exit(fail === 0 ? 0 : 1);
