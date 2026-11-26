"use client";

import { AnimatePresence, motion } from "framer-motion";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import ConstellationChart from "@/components/learn/ConstellationChart";
import ConstellationPicker from "@/components/learn/ConstellationPicker";
import { BestMonthRing, NowPosition, TonightTimeline } from "@/components/learn/LearnFacts";
import { ApiErrorNotice, ConstellationSkeleton, WakingTelescope } from "@/components/ui/LoadingStates";
import { useApiResource } from "@/hooks/useApiResource";
import { formatLocation, useLocation } from "@/hooks/useLocation";
import { api, type ApiError, type RequestOptions } from "@/lib/api";

const DEFAULT = "Orion";

const errorText = (error: ApiError | null) =>
  error?.status === null || !error
    ? "We couldn't reach the AstraGraph server. Check your connection, or try again in a moment."
    : error.message;

/** A thin shimmering placeholder line while facts load. */
function Shimmer({ className = "" }: { className?: string }) {
  return (
    <span className={`relative block overflow-hidden rounded-full bg-ink/[0.06] ${className}`} aria-hidden="true">
      <span className="absolute inset-y-0 w-1/3 animate-[shimmer_1.6s_ease-in-out_infinite] bg-gradient-to-r from-transparent via-ink/10 to-transparent" />
    </span>
  );
}

export default function Learn() {
  const router = useRouter();
  const pathname = usePathname();
  const params = useSearchParams();
  const { location, ready } = useLocation();

  const list = useApiResource("constellations", useCallback((opts: RequestOptions) => api.constellations(opts), []));

  // The selected constellation lives in the address (?c=Lyra), so links from
  // the home page work and a view can be shared.
  const requested = params.get("c") ?? DEFAULT;
  const match = list.data?.find((c) => c.name.toLowerCase() === requested.toLowerCase());
  const name = match?.name ?? (list.data ? DEFAULT : requested);

  const select = useCallback(
    (next: string) => router.replace(`${pathname}?c=${encodeURIComponent(next)}`, { scroll: false }),
    [router, pathname],
  );
  // An unknown ?c= falls back to Orion; tidy the address to match.
  useEffect(() => {
    if (list.data && !match && params.get("c")) select(DEFAULT);
  }, [list.data, match, params, select]);

  const detailKey = ready ? `${name}|${location.lat},${location.lon},${location.tz}` : null;
  const detail = useApiResource(
    detailKey,
    useCallback((opts: RequestOptions) => api.constellation(name, location, opts), [name, location]),
  );

  const [activeStar, setActiveStar] = useState<string | null>(null);
  useEffect(() => setActiveStar(null), [name]);

  // Draw straight away from the list; the detail adds the facts.
  const chartData = (detail.data?.name === name ? detail.data : null) ?? list.data?.find((c) => c.name === name) ?? null;
  const info = detail.data?.name === name ? detail.data : null;
  const brightestFirst = chartData ? [...chartData.stars].sort((a, b) => a.magnitude - b.magnitude) : [];

  return (
    <section className="relative min-h-[100svh] pt-[var(--nav-height)]">
      <div className="mx-auto max-w-[110rem] px-0 pb-24 pt-6 sm:px-4 lg:px-8">
        {/* Picker */}
        <div className="mb-6 flex items-baseline justify-between px-5 sm:px-4">
          <p className="label-caps">Learn the sky</p>
          <p className="text-xs tabular-nums text-muted">{formatLocation(location)}</p>
        </div>
        {list.data ? (
          <ConstellationPicker items={list.data} selected={name} onSelect={select} />
        ) : (
          <div className="flex h-[6.5rem] items-center justify-center">
            {list.status === "waking" ? (
              <p className="text-sm text-muted">Waking the telescope…</p>
            ) : list.status === "error" ? (
              <ApiErrorNotice message={errorText(list.error)} onRetry={list.retry} />
            ) : (
              <div className="flex gap-3 px-5" aria-hidden="true">
                {Array.from({ length: 6 }, (_, i) => <Shimmer key={i} className="h-20 w-24 !rounded-2xl" />)}
              </div>
            )}
          </div>
        )}

        <div className="mt-6 grid gap-10 px-5 sm:px-4 lg:grid-cols-[minmax(0,1fr)_26rem] lg:gap-14">
          {/* Chart column */}
          <div className="min-w-0">
            <AnimatePresence mode="wait">
              <motion.header
                key={name}
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -6 }}
                transition={{ duration: 0.35, ease: [0.22, 1, 0.36, 1] }}
              >
                <h1 className="font-display text-5xl font-light leading-none tracking-tight text-ink sm:text-6xl">{name}</h1>
                <p className="mt-3 flex flex-wrap items-center gap-x-3 gap-y-1 text-sm text-muted">
                  {chartData && <span className="font-display tracking-[0.2em] text-ink/80">{chartData.abbreviation.toUpperCase()}</span>}
                  {info && (
                    <>
                      <span className="h-3 w-px bg-line" aria-hidden="true" />
                      <span>Best season: <span className="text-ink/90">{info.best_season}</span></span>
                    </>
                  )}
                  {chartData && (
                    <>
                      <span className="h-3 w-px bg-line" aria-hidden="true" />
                      <span>{chartData.stars.length} stars · {chartData.lines.length} lines</span>
                    </>
                  )}
                </p>
              </motion.header>
            </AnimatePresence>

            {/* Sized so the whole chart is on screen under the picker on laptops. */}
            <div className="relative mt-2 aspect-square w-full sm:aspect-[4/3] lg:aspect-auto lg:h-[max(22rem,calc(100svh-24.5rem))]">
              {chartData ? (
                <ConstellationChart constellation={chartData} activeStar={activeStar} onActiveStarChange={setActiveStar} />
              ) : list.status === "error" ? null : (
                <ConstellationSkeleton className="h-full" label="Loading the chart" />
              )}
            </div>

            {/* The story */}
            <div className="mt-6 max-w-3xl">
              {info ? (
                <motion.p key={info.name} initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ duration: 0.6 }}
                  className="text-base leading-relaxed text-ink/75">
                  {info.mythology}
                </motion.p>
              ) : detail.status !== "error" ? (
                <div className="space-y-2.5 pt-1.5">
                  <Shimmer className="h-3 w-full" />
                  <Shimmer className="h-3 w-11/12" />
                  <Shimmer className="h-3 w-2/3" />
                </div>
              ) : null}
            </div>

            {/* Star list: hover or focus a star to see it on the chart. */}
            {chartData && (
              <div className="mt-8">
                <p className="label-caps mb-3">Stars</p>
                <ul className="flex flex-wrap gap-2">
                  {brightestFirst.map((s) => {
                    const on = s.name === activeStar;
                    return (
                      <li key={s.name}>
                        <button
                          type="button"
                          aria-pressed={on}
                          onMouseEnter={() => setActiveStar(s.name)}
                          onMouseLeave={() => setActiveStar(null)}
                          onFocus={() => setActiveStar(s.name)}
                          onBlur={() => setActiveStar(null)}
                          onClick={() => setActiveStar(on ? null : s.name)}
                          className={`flex min-h-11 items-center gap-2 rounded-full border px-4 text-sm transition-colors ${
                            on ? "border-cyan/60 text-cyan" : "border-line text-ink hover:border-ink/30"
                          }`}
                        >
                          {s.name}
                          <span className="text-xs tabular-nums text-muted">{s.magnitude.toFixed(1)}</span>
                        </button>
                      </li>
                    );
                  })}
                </ul>
              </div>
            )}
          </div>

          {/* Facts column */}
          <aside className="lg:sticky lg:top-[calc(var(--nav-height)+1.5rem)] lg:self-start" aria-label={`${name} facts`}>
            {info ? (
              <motion.div
                key={info.name + detailKey}
                initial={{ opacity: 0, y: 12 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.45, ease: [0.22, 1, 0.36, 1] }}
                className="divide-y divide-line"
              >
                <div className="pb-8">
                  <p className="label-caps mb-4">Best month</p>
                  <BestMonthRing best={info.best_month} />
                </div>
                <div className="py-8">
                  <p className="label-caps mb-4">Right now</p>
                  <NowPosition now={info.now} />
                </div>
                <div className="pt-8">
                  <p className="label-caps mb-1">Tonight</p>
                  <TonightTimeline tonight={info.tonight} tz={location.tz} />
                </div>
              </motion.div>
            ) : detail.status === "waking" ? (
              <WakingTelescope className="py-16" />
            ) : detail.status === "error" ? (
              <ApiErrorNotice className="py-16" message={errorText(detail.error)} onRetry={detail.retry} />
            ) : (
              <div className="space-y-10" role="status" aria-label="Loading facts">
                {[0, 1, 2].map((i) => (
                  <div key={i} className="space-y-4">
                    <Shimmer className="h-2.5 w-24" />
                    <div className="flex items-center gap-5">
                      <Shimmer className="h-28 w-28 !rounded-full" />
                      <div className="flex-1 space-y-2.5">
                        <Shimmer className="h-3 w-full" />
                        <Shimmer className="h-3 w-3/4" />
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </aside>
        </div>
      </div>
    </section>
  );
}
