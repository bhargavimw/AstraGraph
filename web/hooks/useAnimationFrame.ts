"use client";

import { useEffect, useRef } from "react";

/**
 * Run `callback(time, delta)` on every animation frame while `active`.
 * Pauses automatically while the tab is hidden and cleans up on unmount.
 */
export function useAnimationFrame(
  callback: (timeMs: number, deltaMs: number) => void,
  active = true,
): void {
  const saved = useRef(callback);
  saved.current = callback;

  useEffect(() => {
    if (!active) return;
    let frame = 0;
    let last = performance.now();

    const loop = (now: number) => {
      const delta = Math.min(now - last, 100); // avoid jumps after a stall
      last = now;
      saved.current(now, delta);
      frame = requestAnimationFrame(loop);
    };
    const start = () => {
      cancelAnimationFrame(frame);
      last = performance.now();
      frame = requestAnimationFrame(loop);
    };
    const onVisibility = () => {
      if (document.hidden) cancelAnimationFrame(frame);
      else start();
    };

    start();
    document.addEventListener("visibilitychange", onVisibility);
    return () => {
      cancelAnimationFrame(frame);
      document.removeEventListener("visibilitychange", onVisibility);
    };
  }, [active]);
}
