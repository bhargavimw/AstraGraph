"use client";

import { motion } from "framer-motion";
import { useReducedMotion } from "@/hooks/useReducedMotion";

/** A faint constellation whose stars pulse in turn, used while data loads. */
export function ConstellationSkeleton({ className = "", label = "Loading" }: { className?: string; label?: string }) {
  const reduced = useReducedMotion();
  const stars = [
    [18, 70], [34, 38], [52, 52], [66, 28], [82, 46], [70, 74], [44, 82],
  ] as const;
  const lines = [[0, 1], [1, 2], [2, 3], [3, 4], [2, 5], [5, 6], [6, 0]] as const;
  return (
    <div role="status" aria-label={label} className={`flex items-center justify-center ${className}`}>
      <svg viewBox="0 0 100 100" className="h-24 w-24 opacity-70" aria-hidden="true">
        {lines.map(([a, b], i) => (
          <line key={i} x1={stars[a][0]} y1={stars[a][1]} x2={stars[b][0]} y2={stars[b][1]}
            stroke="rgb(232 236 246 / 0.12)" strokeWidth={0.8} />
        ))}
        {stars.map(([x, y], i) => (
          <motion.circle
            key={i} cx={x} cy={y} r={1.8} fill="#e8ecf6"
            animate={reduced ? undefined : { opacity: [0.25, 1, 0.25] }}
            transition={{ duration: 1.8, repeat: Infinity, delay: i * 0.18, ease: "easeInOut" }}
            opacity={reduced ? 0.6 : undefined}
          />
        ))}
      </svg>
      <span className="sr-only">{label}</span>
    </div>
  );
}

/** Shown while a sleeping free-tier server is being woken up (retried). */
export function WakingTelescope({ className = "" }: { className?: string }) {
  return (
    <div role="status" aria-live="polite" className={`flex flex-col items-center gap-4 text-center ${className}`}>
      <p className="font-display text-xl font-light text-ink">Waking the telescope…</p>
      <p className="max-w-sm text-sm text-muted">
        The AstraGraph server naps when nobody is using it. It takes up to a minute to wake.
      </p>
      <div className="relative h-px w-48 overflow-hidden bg-line">
        <span className="absolute inset-y-0 w-1/3 animate-[shimmer_1.6s_ease-in-out_infinite] bg-gradient-to-r from-transparent via-gold to-transparent" />
      </div>
    </div>
  );
}

/** Friendly error with a retry action. */
export function ApiErrorNotice({ message, onRetry, className = "" }: { message: string; onRetry: () => void; className?: string }) {
  return (
    <div role="alert" className={`flex flex-col items-center gap-4 text-center ${className}`}>
      <p className="font-display text-lg font-light text-ink">The sky is out of reach right now.</p>
      <p className="max-w-md text-sm text-muted">{message}</p>
      <button type="button" onClick={onRetry}
        className="min-h-11 rounded-full border border-gold/50 px-6 text-sm text-gold transition-colors hover:bg-gold/10">
        Try again
      </button>
    </div>
  );
}
