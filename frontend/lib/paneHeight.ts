/**
 * How tall the transcript pane is, in the two states that matter.
 *
 * Shared so the real page and the `/design` sample that measures it cannot
 * drift — a measurement of a copy is a measurement of nothing.
 *
 * **Idle**: generous. There is chrome above it, nothing is streaming, and the
 * user is choosing languages rather than reading.
 *
 * **Live**: sized from what is left of the viewport, because the guarantee the
 * pane exists to provide — the newest line never moves — only holds if the
 * pane is on screen. A fixed `18rem` floor cannot survive a phone in landscape:
 * 390px of height minus a navbar, page padding and the header leaves less than
 * 288px, so the bottom edge fell below the fold and the reader had to scroll to
 * follow their own conversation.
 *
 * `dvh` rather than `vh`: mobile browser chrome grows and shrinks as you
 * scroll, and `vh` freezes at the largest size, which is exactly the case that
 * pushes content out of view.
 *
 * The `18rem` is the chrome this pane sits inside — navbar (66), page padding
 * (64), card padding (48) and the compact header (96) — **measured at 274px in
 * a browser**, on every phone viewport, and rounded up for headroom. A first
 * guess of `20rem` was wrong in the other direction and the fold check caught
 * it: the surface ran 47px past the fold in portrait and 81px in landscape.
 *
 * The `6rem` floor is not a design preference either. A 375px-tall landscape
 * phone has 101px left after the chrome, so anything larger cannot fit — the
 * transcript is genuinely small there, and that is the honest consequence of
 * captioning on a phone held sideways rather than something to hide.
 *
 * If the chrome changes, `e2e/layout.spec.ts` fails and this is the number to
 * change.
 */
export const PANE_HEIGHT_IDLE = "h-[clamp(18rem,55vh,34rem)]";
export const PANE_HEIGHT_LIVE = "h-[clamp(6rem,calc(100dvh-18rem),34rem)]";
