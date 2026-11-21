"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import SkyDome from "@/components/sky/SkyDome";
import { useLocation } from "@/hooks/useLocation";
import { sceneFromCatalog } from "@/lib/scene";

/** A mini sky dome playing 24 hours of sky in ~24 s, for the saved location. */
const SECONDS_PER_DAY = 24;

export default function SkyMotionDemo() {
  const { location } = useLocation();
  const [base] = useState(() => {
    const d = new Date();
    d.setMinutes(0, 0, 0);
    return d.getTime();
  });
  const sceneAt = useCallback(
    (seconds: number) => {
      const hours = (seconds % SECONDS_PER_DAY) * (24 / SECONDS_PER_DAY);
      return sceneFromCatalog(new Date(base + hours * 3600000), location.lat, location.lon, 3.2);
    },
    [base, location.lat, location.lon],
  );

  // Clock readout, updated a few times a second (not every frame).
  const [clock, setClock] = useState("");
  const formatter = useMemo(
    () => new Intl.DateTimeFormat("en-GB", { hour: "2-digit", minute: "2-digit", timeZone: location.tz }),
    [location.tz],
  );
  useEffect(() => {
    const t0 = performance.now();
    const update = () => {
      const seconds = (performance.now() - t0) / 1000;
      const hours = (seconds % SECONDS_PER_DAY) * (24 / SECONDS_PER_DAY);
      setClock(formatter.format(new Date(base + hours * 3600000)));
    };
    update();
    const id = window.setInterval(update, 250);
    return () => window.clearInterval(id);
  }, [base, formatter]);

  return (
    <div className="relative mx-auto w-full max-w-[34rem]">
      <SkyDome sceneAt={sceneAt} highlight="Orion" ariaLabel="Animated sky chart showing 24 hours of sky" />
      <p className="mt-2 text-center font-display text-sm tracking-[0.3em] text-muted tabular-nums" aria-live="off">
        {clock} <span className="text-[0.65rem]">LOCAL</span>
      </p>
    </div>
  );
}
