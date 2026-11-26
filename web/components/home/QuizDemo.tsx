"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
import { ArrowRightIcon, ResetIcon } from "@/components/ui/icons-extra";
import { ciToRgb, magnitudeToRadius, rgba } from "@/lib/color";
import { getConstellation } from "@/lib/data/catalog";
import { chartProject, fitToBox } from "@/lib/sky-math";

/** Mini connect-the-dots: draw Cassiopeia's "W" by clicking stars in pairs. */
const NAME = "Cassiopeia";
const W = 420;
const H = 300;

const round2 = (v: number) => Math.round(v * 100) / 100;

const key = (a: string, b: string) => (a < b ? `${a}|${b}` : `${b}|${a}`);

export default function QuizDemo() {
  const cas = getConstellation(NAME);
  const [pending, setPending] = useState<string | null>(null);
  const [lines, setLines] = useState<string[]>([]);
  const [wrong, setWrong] = useState<string | null>(null);

  const layout = useMemo(() => {
    if (!cas) return new Map<string, { x: number; y: number }>();
    const pts = fitToBox(chartProject(cas.stars), W, H, 48);
    // Round to 0.01 px: the server (Node) and the browser compute trigonometry
    // with slightly different libraries, so unrounded values can differ in the
    // 14th decimal place and trigger a React hydration mismatch.
    return new Map(cas.stars.map((s, i) => [s.name, { x: round2(pts[i]!.x), y: round2(pts[i]!.y) }]));
  }, [cas]);
  const correct = useMemo(() => new Set(cas?.lines.map(([a, b]) => key(a, b)) ?? []), [cas]);
  if (!cas) return null;

  const done = lines.length === correct.size;

  const pick = (name: string) => {
    if (done) return;
    if (!pending) return setPending(name);
    if (pending === name) return setPending(null);
    const k = key(pending, name);
    setPending(null);
    if (correct.has(k)) {
      if (!lines.includes(k)) setLines((l) => [...l, k]);
    } else {
      setWrong(k);
      window.setTimeout(() => setWrong((w) => (w === k ? null : w)), 900);
    }
  };

  const reset = () => {
    setLines([]);
    setPending(null);
    setWrong(null);
  };

  const segment = (k: string) => {
    const [a, b] = k.split("|") as [string, string];
    return { A: layout.get(a)!, B: layout.get(b)! };
  };

  return (
    <div className="mx-auto w-full max-w-[30rem]">
      <svg
        viewBox={`0 0 ${W} ${H}`}
        className="w-full touch-manipulation select-none"
        role="group"
        aria-label={`Connect the stars of ${NAME}`}
      >
        {lines.map((k) => {
          const { A, B } = segment(k);
          return (
            <line key={k} x1={A.x} y1={A.y} x2={B.x} y2={B.y} stroke="#f5c451" strokeWidth={1.8}
              strokeLinecap="round" className="animate-[draw_0.5s_ease-out]"
              style={{ filter: "drop-shadow(0 0 4px rgb(245 196 81 / 0.7))" }} />
          );
        })}
        {wrong && (() => {
          const { A, B } = segment(wrong);
          return <line x1={A.x} y1={A.y} x2={B.x} y2={B.y} stroke="#ff6b6b" strokeWidth={1.6}
            strokeDasharray="4 4" className="animate-[fadeout_0.9s_ease-out_forwards]" />;
        })()}
        {cas.stars.map((s) => {
          const p = layout.get(s.name)!;
          const r = round2(magnitudeToRadius(s.magnitude, 2.2));
          const isPending = pending === s.name;
          return (
            <g key={s.name}>
              <circle cx={p.x} cy={p.y} r={round2(r * 3)} fill={rgba(ciToRgb(s.ci), 0.15)} />
              <circle cx={p.x} cy={p.y} r={r} fill={rgba(ciToRgb(s.ci), 1)} />
              {isPending && (
                <circle cx={p.x} cy={p.y} r={16} fill="none" stroke="#5ce1e6" strokeWidth={1.5}
                  className="animate-pulse" />
              )}
              {/* 44px+ invisible hit target */}
              <circle
                cx={p.x} cy={p.y} r={24} fill="transparent" className="cursor-pointer outline-none"
                role="button" tabIndex={0} aria-label={`${s.name}${isPending ? " (selected)" : ""}`}
                onClick={() => pick(s.name)}
                onKeyDown={(e) => (e.key === "Enter" || e.key === " ") && (e.preventDefault(), pick(s.name))}
                style={{ outline: "none" }}
              />
              <text x={p.x} y={p.y + 30} textAnchor="middle" className="fill-muted text-[11px]">
                {s.name.replace(" Cassiopeiae", "")}
              </text>
            </g>
          );
        })}
      </svg>
      <div className="mt-4 flex items-center justify-between gap-4">
        <p className="text-sm text-muted" aria-live="polite">
          {done ? (
            <span className="text-gold">Perfect — that&apos;s Cassiopeia&apos;s W.</span>
          ) : wrong ? (
            "Not quite — that pair isn't joined in the sky."
          ) : (
            <>Lines found: <span className="tabular-nums text-ink">{lines.length}</span> / {correct.size}</>
          )}
        </p>
        <button type="button" onClick={reset}
          className="flex min-h-11 items-center gap-2 rounded-full px-4 text-sm text-muted transition-colors hover:text-ink">
          <ResetIcon size={16} /> Reset
        </button>
      </div>
      {done && (
        <Link href="/learn?c=Cassiopeia" className="mt-2 inline-flex items-center gap-2 text-sm text-cyan hover:underline">
          Meet Cassiopeia <ArrowRightIcon size={16} />
        </Link>
      )}
    </div>
  );
}
