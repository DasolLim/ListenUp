# DEBUG_LOG

Unexpected errors and their resolutions, per INTRODUCTION §8.6. Newest entries first.

| Date | Step | Error | Root cause | Fix |
|---|---|---|---|---|
| 2026-07-16 | 1.5.1 | Gate script reported FAIL though UI was correct | Chrome serializes CSS custom-property colors as shorthand (`#fff`) while the assertion compared `rgb(255, 255, 255)` | Normalized accepted color formats in the gate script; CSS unchanged |
| 2026-07-16 | 1.5.3 | `tsc` failed with TS2307 on `.next/dev/types/validator.ts` after moving routes into route groups | Stale generated route types referenced the old paths | `rm -rf .next` and re-run; do this after any route restructure |
| 2026-07-16 | 1.5.2 | Glass blur not applied (`backdrop-filter` computed `none`) | Lightning CSS (Tailwind v4) merges a hand-written `backdrop-filter` + `-webkit-backdrop-filter` pair into one logical property and emitted only the `-webkit-` form, which Chrome's computed style didn't honor via var() | Write only the standard `backdrop-filter`; let the compiler add prefixes. Never hand-write `-webkit-backdrop-filter` in this codebase |
