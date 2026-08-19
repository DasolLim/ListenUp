"use client";

import { useCallback, useEffect, useRef, useState } from "react";

/** Within this many pixels of the bottom still counts as "following along". */
const NEAR_BOTTOM_PX = 100;

/**
 * Bottom-anchored scrolling for a live, appending transcript.
 *
 * Extracted so the scroll rules can be reasoned about and tested on their own —
 * they are the fiddly part, and they were previously spread across three
 * effects and a scroll handler inside the caption component.
 *
 * Two things make this different from a normal chat feed:
 *
 *   1. **Captions grow after they render.** A translation lands a moment later
 *      and adds lines; a slang card is opened; the caption-size control steps
 *      up. None of that changes the item count, so following the newest line
 *      means watching *height*, not arrivals.
 *   2. **Interim text updates several times a second.** Only finalised captions
 *      may count as "new", or the unread badge climbs while one sentence is
 *      still being spoken.
 *
 * Deliberately not `flex-direction: column-reverse`: that lays children out
 * bottom-to-top, so keeping chronological DOM order would put the *oldest*
 * caption at the bottom, and reversing the array to compensate inverts reading
 * order for screen readers. The caller pins content with `mt-auto` instead,
 * which bottom-anchors without touching order at all.
 */
export function useChatScroll({ finalCount }: { finalCount: number }) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [pinned, setPinned] = useState(true);
  // Finalised-caption count at the moment the reader scrolled away; null while
  // they are following along.
  const [anchor, setAnchor] = useState<number | null>(null);

  const unread = anchor === null ? 0 : Math.max(0, finalCount - anchor);

  const scrollToBottom = useCallback((smooth: boolean) => {
    const container = containerRef.current;
    if (!container) return;
    // Interim text is retargeted many times a second, so only a deliberate jump
    // animates — smooth-scrolling every update reads as jitter.
    const reduced =
      typeof window !== "undefined" &&
      window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
    container.scrollTo({
      top: container.scrollHeight,
      behavior: smooth && !reduced ? "smooth" : "auto",
    });
  }, []);

  const onScroll = useCallback(() => {
    const container = containerRef.current;
    if (!container) return;
    const fromBottom = container.scrollHeight - container.scrollTop - container.clientHeight;
    const atBottom = fromBottom < NEAR_BOTTOM_PX;
    setPinned(atBottom);
    setAnchor((current) => (atBottom ? null : (current ?? finalCount)));
  }, [finalCount]);

  const jumpToLatest = useCallback(() => {
    setPinned(true);
    setAnchor(null);
    scrollToBottom(true);
  }, [scrollToBottom]);

  // Follow new captions.
  useEffect(() => {
    if (pinned) scrollToBottom(false);
  }, [finalCount, pinned, scrollToBottom]);

  // Read inside the observer below, which must see the current value without
  // being rebuilt every time the reader scrolls.
  const pinnedRef = useRef(true);
  useEffect(() => {
    pinnedRef.current = pinned;
  }, [pinned]);

  /**
   * Attach to the element that holds the transcript content.
   *
   * A callback ref rather than an effect, so it survives the content being
   * unmounted and remounted (the empty state) without extra bookkeeping.
   */
  const resizeRef = useRef<ResizeObserver | null>(null);
  const watchContent = useCallback((node: HTMLElement | null) => {
    resizeRef.current?.disconnect();
    resizeRef.current = null;
    if (!node || typeof ResizeObserver === "undefined") return;
    const observer = new ResizeObserver(() => {
      const container = containerRef.current;
      // Assigned rather than animated: growth arrives in steps, and a smooth
      // scroll restarting mid-flight reads as drift.
      if (container && pinnedRef.current) container.scrollTop = container.scrollHeight;
    });
    observer.observe(node);
    resizeRef.current = observer;
  }, []);

  useEffect(() => () => resizeRef.current?.disconnect(), []);

  return { containerRef, watchContent, pinned, unread, onScroll, jumpToLatest };
}
