"use client";

import { motion, useInView } from "framer-motion";
import { useRef } from "react";
import MoonPhase from "@/components/ui/MoonPhase";
import { useCountUp } from "@/hooks/useCountUp";
import { useReducedMotion } from "@/hooks/useReducedMotion";
import type { TonightSummary } from "@/lib/types";

/** One glass bar with four items: darkness, Moon, best constellation, brightest stars. */
export default function TonightStrip({ data }: { data: TonightSummary }) {
  const ref = useRef<HTMLDivElement>(null);
  const inView = useInView(ref, { once: true, amount: 0.4 });
  const reduced = useReducedMotion();

  const minutes =
    data.darkness.state === "dark"
      ? data.darkness.minutesUntilDawn
      : data.darkness.state === "light"
        ? data.darkness.minutesUntilDark
        : 0;
  const counted = useCountUp(minutes, inView);
  const moonPct = useCountUp(Math.round(data.moon.illumination * 100), inView);
  const altitude = useCountUp(data.best?.altitude ?? 0, inView);
  const h = Math.floor(counted / 60);
  const m = Math.floor(counted % 60);

  const darkness =
    data.darkness.state === "never-dark"
      ? { value: "Never fully dark", note: "Summer twilight all night" }
      : {
          value: `${h}h ${String(m).padStart(2, "0")}m`,
          note: data.darkness.state === "dark" ? "of darkness left until dawn" : "until it gets dark",
        };

  return (
    <motion.div
      ref={ref}
      initial={{ opacity: 0, y: reduced ? 0 : 24 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true, amount: 0.4 }}
      transition={{ duration: 0.9, ease: [0.22, 1, 0.36, 1] }}
      className="glass grid grid-cols-1 rounded-3xl sm:grid-cols-2 lg:grid-cols-4"
    >
      <Item label="Darkness">
        <p className="font-display text-3xl font-light tabular-nums text-ink">{darkness.value}</p>
        <p className="mt-1 text-sm text-muted">{darkness.note}</p>
      </Item>
      <Item label="Moon">
        <div className="flex items-center gap-4">
          <MoonPhase illumination={data.moon.illumination} waxing={data.moon.waxing} size={46} />
          <div>
            <p className="font-display text-3xl font-light tabular-nums text-ink">{Math.round(moonPct)}%</p>
            <p className="text-sm text-muted">{data.moon.phaseName}</p>
          </div>
        </div>
      </Item>
      <Item label="Look for">
        {data.best ? (
          <>
            <p className="font-display text-3xl font-light text-gold">{data.best.name}</p>
            <p className="mt-1 text-sm text-muted">
              <span className="tabular-nums text-ink">{Math.round(altitude)}°</span> up in the{" "}
              {data.best.direction}
            </p>
          </>
        ) : (
          <p className="text-sm text-muted">Nothing from our catalogue is up right now.</p>
        )}
      </Item>
      <Item label="Brightest stars up" last>
        <p className="text-[0.95rem] leading-relaxed text-ink">{data.brightestStars.join(" · ")}</p>
      </Item>
    </motion.div>
  );
}

function Item({ label, children, last = false }: { label: string; children: React.ReactNode; last?: boolean }) {
  return (
    <div
      className={`px-7 py-6 ${last ? "" : "border-b border-line sm:[&:nth-child(odd)]:border-r lg:border-b-0 lg:border-r"} sm:[&:nth-child(n+3)]:border-b-0`}
    >
      <p className="label-caps mb-3 !text-[0.62rem]">{label}</p>
      {children}
    </div>
  );
}
