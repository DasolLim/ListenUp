import { defineConfig, devices } from "@playwright/test";

/**
 * The browser feedback loop.
 *
 * Every bug this project has shipped and had reported back was invisible to the
 * type checker and to unit tests: a pane whose bottom edge sat below the fold,
 * an 18px touch target, read-aloud speaking a different sentence from the one
 * on screen, a toggle that hid a result while still paying for it. Those are
 * facts about a running page, so they need a running page.
 *
 * Both servers are started here so the loop is one command. `next dev` is not
 * an option: hydration never completes under it in this sandbox, so every
 * handler is dead and a working feature reads as broken (DEBUG_LOG). The build
 * is the slow part, and `reuseExistingServer` means it is paid once per
 * session rather than once per run.
 *
 * The backend runs on its **mocks**. Every external tool has a mock path by
 * constraint (INTRODUCTION §6), and an e2e suite that spent real AssemblyAI
 * sessions would be a suite nobody runs — this repo has already burned billed
 * sessions to a script that escaped `conftest.py`.
 */
const BACKEND_MOCKS = {
  TRANSCRIPTION_SERVICE: "mock",
  SPEAKER_ID_SERVICE: "mock",
  TRANSLATION_SERVICE: "mock",
  ENHANCED_TRANSLATION_SERVICE: "mock",
  GENZ_EXPLAINER_SERVICE: "mock",
  TEXT_EMBEDDER: "hashing",
  TTS_SERVICE: "browser",
};

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  workers: process.env.CI ? 2 : undefined,
  reporter: process.env.CI ? [["github"], ["list"]] : [["list"]],
  timeout: 30_000,
  use: {
    baseURL: "http://localhost:3000",
    trace: "retain-on-failure",
    // A failure that cannot be seen is a failure that gets re-debugged from
    // scratch next time.
    screenshot: "only-on-failure",
  },
  projects: [
    {
      name: "chromium",
      use: {
        ...devices["Desktop Chrome"],
        launchOptions: {
          args: [
            // A real microphone permission prompt would block every session
            // test; a fake device makes the capture path exercisable.
            "--use-fake-ui-for-media-stream",
            "--use-fake-device-for-media-stream",
          ],
        },
      },
    },
  ],
  webServer: [
    {
      // Prefer the local venv, fall back to whatever `python3` is on PATH so
      // CI needs no special casing.
      command:
        'sh -c \'PY=../backend/.venv/bin/python; [ -x "$PY" ] || PY=python3; ' +
        'cd ../backend && exec "$PY" -m uvicorn app.main:app --port 8000\'',
      url: "http://localhost:8000/health",
      reuseExistingServer: !process.env.CI,
      stdout: "pipe",
      stderr: "pipe",
      timeout: 120_000,
      env: BACKEND_MOCKS,
    },
    {
      command: "npm run build && npm run start",
      url: "http://localhost:3000",
      reuseExistingServer: !process.env.CI,
      timeout: 300_000,
    },
  ],
});
