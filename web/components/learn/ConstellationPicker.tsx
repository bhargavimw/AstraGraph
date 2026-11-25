"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { ArrowRightIcon } from "@/components/ui/icons-extra";
import { chartProject, fitToBox } from "@/lib/sky-math";
import type { ApiConstellationSummary } from "@/lib/types";

/** Two decimals, so server and browser render identical SVG attributes. */
const round2 = (v: number) => Math.round(v * 100) / 100;

/** Line-art drawing of a constellation, drawn from its star data. */
function Thumb({ constellation, active }: { constellation: ApiConstellationSummary; active: boolean }) {
  const { points, lines } = useMemo(() => {
    const projected = fitToBox(chartProject(constellation.stars), 100, 70, 10);
    const pos = new Map(constellation.stars.map((s, i) => [s.name, projected[i]!]));
    return {
      points: constellation.stars.map((s) => ({ ...pos.get(s.name)!, magnitude: s.magnitude, name: s.name })),
      lines: constellation.lines.flatMap(([a, b]) => {
        const A = pos.get(a);
        const B = pos.get(b);
        return A && B ? [{ key: `${a}-${b}`, A, B }] : [];
      }),
    };
  }, [constellation]);

  return (
    <svg viewBox="0 0 100 70" className="h-14 w-20" aria-hidden="true">
      {lines.map(({ key, A, B }) => (
        <line
          key={key}
          x1={round2(A.x)} y1={round2(A.y)} x2={round2(B.x)} y2={round2(B.y)}
          stroke={active ? "#f5c451" : "rgb(232 236 246 / 0.45)"}
          strokeWidth={1.5}
          strokeLinecap="round"
          className="transition-[stroke] duration-300"
        />
      ))}
      {points.map((p) => (
        <circle
          key={p.name}
          cx={round2(p.x)} cy={round2(p.y)}
          r={round2(Math.max(1.4, 3.4 - p.magnitude * 0.55))}
          fill={active ? "#fff3cf" : "#e8ecf6"}
        />
      ))}
    </svg>
  );
}

/** Horizontal scroller of constellation thumbnails. */
export default function ConstellationPicker({
  items,
  selected,
  onSelect,
}: {
  items: ApiConstellationSummary[];
  selected: string;
  onSelect: (name: string) => void;
}) {
  const scroller = useRef<HTMLDivElement | null>(null);

  // Keep the selected thumbnail in view (e.g. when arriving via ?c=Lyra).
  useEffect(() => {
    const el = scroller.current?.querySelector<HTMLElement>(`[data-name="${CSS.escape(selected)}"]`);
    el?.scrollIntoView({ block: "nearest", inline: "center", behavior: "smooth" });
  }, [selected, items.length]);

  // Arrows appear only when there is more to scroll in that direction.
  const [edges, setEdges] = useState({ left: false, right: false });
  useEffect(() => {
    const el = scroller.current;
    if (!el) return;
    const update = () =>
      setEdges({ left: el.scrollLeft > 4, right: el.scrollLeft + el.clientWidth < el.scrollWidth - 4 });
    update();
    el.addEventListener("scroll", update, { passive: true });
    const observer = new ResizeObserver(update);
    observer.observe(el);
    return () => {
      el.removeEventListener("scroll", update);
      observer.disconnect();
    };
  }, [items.length]);

  const scrollBy = (dir: 1 | -1) =>
    scroller.current?.scrollBy({ left: dir * scroller.current.clientWidth * 0.7, behavior: "smooth" });

  return (
    <div className="relative">
      <div
        ref={scroller}
        role="toolbar"
        aria-label="Choose a constellation"
        className="flex snap-x gap-2 overflow-x-auto scroll-px-6 px-1 pb-3 [scrollbar-width:thin] [mask-image:linear-gradient(90deg,transparent,#000_1.5rem,#000_calc(100%-1.5rem),transparent)]"
      >
        {items.map((c) => {
          const active = c.name === selected;
          return (
            <button
              key={c.name}
              type="button"
              data-name={c.name}
              aria-pressed={active}
              onClick={() => onSelect(c.name)}
              className={`group flex shrink-0 snap-start flex-col items-center gap-1.5 rounded-2xl border px-4 pb-2.5 pt-3 transition-[border-color,background-color,box-shadow] duration-300 first:ml-5 last:mr-5 ${
                active
                  ? "border-gold/50 bg-gold/[0.07] shadow-[0_0_28px_rgb(245_196_81/0.15)]"
                  : "border-transparent hover:border-line hover:bg-ink/[0.03]"
              }`}
            >
              <Thumb constellation={c} active={active} />
              <span className={`text-xs tracking-wide transition-colors ${active ? "text-gold" : "text-muted group-hover:text-ink"}`}>
                {c.name}
              </span>
            </button>
          );
        })}
      </div>
      <div className="pointer-events-none absolute inset-y-0 -left-2 -right-2 hidden items-center justify-between md:flex">
        <button
          type="button"
          tabIndex={-1}
          style={{ visibility: edges.left ? "visible" : "hidden" }}
          onClick={() => scrollBy(-1)}
          aria-label="Scroll constellations left"
          className="pointer-events-auto flex h-9 w-9 -translate-y-1.5 items-center justify-center rounded-full border border-line bg-void/70 text-muted backdrop-blur transition-colors hover:text-gold"
        >
          <ArrowRightIcon size={16} className="rotate-180" />
        </button>
        <button
          type="button"
          tabIndex={-1}
          style={{ visibility: edges.right ? "visible" : "hidden" }}
          onClick={() => scrollBy(1)}
          aria-label="Scroll constellations right"
          className="pointer-events-auto flex h-9 w-9 -translate-y-1.5 items-center justify-center rounded-full border border-line bg-void/70 text-muted backdrop-blur transition-colors hover:text-gold"
        >
          <ArrowRightIcon size={16} />
        </button>
      </div>
    </div>
  );
}
