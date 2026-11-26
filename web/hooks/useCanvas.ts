"use client";

import { useEffect, useRef, useState, type RefObject } from "react";

export interface CanvasSize {
  width: number; // CSS px
  height: number;
  dpr: number;
}

/**
 * Keep a canvas's backing store matched to its CSS size × devicePixelRatio,
 * and report whether it is on screen (so animations can pause off-screen).
 */
export function useCanvas(): {
  ref: RefObject<HTMLCanvasElement | null>;
  size: CanvasSize;
  visible: boolean;
} {
  const ref = useRef<HTMLCanvasElement | null>(null);
  const [size, setSize] = useState<CanvasSize>({ width: 0, height: 0, dpr: 1 });
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    const canvas = ref.current;
    if (!canvas) return;
    const apply = () => {
      const rect = canvas.getBoundingClientRect();
      const dpr = Math.min(window.devicePixelRatio || 1, 2.5);
      const width = Math.max(1, Math.round(rect.width));
      const height = Math.max(1, Math.round(rect.height));
      canvas.width = Math.round(width * dpr);
      canvas.height = Math.round(height * dpr);
      setSize((prev) =>
        prev.width === width && prev.height === height && prev.dpr === dpr ? prev : { width, height, dpr },
      );
    };
    const resizeObserver = new ResizeObserver(apply);
    resizeObserver.observe(canvas);
    const intersectionObserver = new IntersectionObserver(
      ([entry]) => setVisible(Boolean(entry?.isIntersecting)),
      { rootMargin: "120px" },
    );
    intersectionObserver.observe(canvas);
    apply();
    return () => {
      resizeObserver.disconnect();
      intersectionObserver.disconnect();
    };
  }, []);

  return { ref, size, visible };
}

/** 2D context scaled so drawing uses CSS pixels. */
export function prepareContext(canvas: HTMLCanvasElement, size: CanvasSize): CanvasRenderingContext2D | null {
  const ctx = canvas.getContext("2d");
  if (!ctx) return null;
  ctx.setTransform(size.dpr, 0, 0, size.dpr, 0, 0);
  ctx.clearRect(0, 0, size.width, size.height);
  return ctx;
}
