# DEBUG_LOG

Unexpected errors and their resolutions, per INTRODUCTION §8.6. Newest entries first.

| Date | Step | Error | Root cause | Fix |
|---|---|---|---|---|
| 2026-07-16 | 1.5.1 | Gate script reported FAIL though UI was correct | Chrome serializes CSS custom-property colors as shorthand (`#fff`) while the assertion compared `rgb(255, 255, 255)` | Normalized accepted color formats in the gate script; CSS unchanged |
| 2026-07-17 | 2.5 | axe: white 13px text on flat coral `--accent` = 2.75:1 (active caption-size button); same ratio invalidated white-on-coral-gradient buttons and the coral active-nav icon (<3:1 graphics) | Light Sense coral was never AA-safe as an interactive background/foreground | Split accent tokens: ambient coral unchanged; interactive coral deepened (`--accent-strong #B84A22`, gradient `#C4502A→#A63F19`, focus rings, accent icons). Documented in DESIGN_SYSTEM §2 note |
| 2026-07-16 | 2.2 | Abrupt-disconnect test couldn't observe the server's teardown log | Starlette TestClient cancels the app task tree when the websocket context exits, so `finally`-block awaits are cancelled before logging — a test-harness artifact, not production behavior (live uvicorn logs `transcribe_end` cleanly, verified) | Unit test asserts the disconnect log only; full teardown asserted in the live gate |
| 2026-07-16 | 1.5.3 | `tsc` failed with TS2307 on `.next/dev/types/validator.ts` after moving routes into route groups | Stale generated route types referenced the old paths | `rm -rf .next` and re-run; do this after any route restructure |
| 2026-07-16 | 1.5.2 | Glass blur not applied (`backdrop-filter` computed `none`) | Lightning CSS (Tailwind v4) merges a hand-written `backdrop-filter` + `-webkit-backdrop-filter` pair into one logical property and emitted only the `-webkit-` form, which Chrome's computed style didn't honor via var() | Write only the standard `backdrop-filter`; let the compiler add prefixes. Never hand-write `-webkit-backdrop-filter` in this codebase |
