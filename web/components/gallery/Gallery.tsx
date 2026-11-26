"use client";

import { AnimatePresence, motion } from "framer-motion";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useCallback, useEffect, useMemo, useState } from "react";
import Lightbox from "@/components/gallery/Lightbox";
import { DownloadIcon } from "@/components/ui/icons-extra";
import { ApiErrorNotice, ConstellationSkeleton } from "@/components/ui/LoadingStates";
import {
  capitalise,
  citiesOf,
  cityId,
  isManifest,
  STYLES,
  styleRank,
  type GalleryManifest,
  type Wallpaper,
} from "@/lib/wallpaper";

/**
 * Wallpaper gallery: 36 pre-rendered phone wallpapers from public/manifest.json.
 * Featured 20 by default, "Show all" for every one, filters by city and style,
 * and a lightbox with the full PNG and a download button. Filters live in the
 * address (?city=bengaluru&style=classic&all=1&w=<id>) so any view can be shared.
 */
export default function Gallery() {
  const router = useRouter();
  const pathname = usePathname();
  const params = useSearchParams();
  const [manifest, setManifest] = useState<GalleryManifest | null>(null);
  const [failed, setFailed] = useState(false);
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    setFailed(false);
    fetch("/manifest.json", { signal: controller.signal })
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(String(r.status)))))
      .then((data: unknown) => {
        if (!isManifest(data)) throw new Error("Bad manifest");
        setManifest(data);
      })
      .catch(() => !controller.signal.aborted && setFailed(true));
    return () => controller.abort();
  }, [attempt]);

  const wallpapers = useMemo(() => manifest?.wallpapers ?? [], [manifest]);
  const cities = useMemo(() => citiesOf(wallpapers), [wallpapers]);

  // ---- filters from the address
  const cityParam = params.get("city")?.toLowerCase() ?? "";
  const styleParam = params.get("style")?.toLowerCase() ?? "";
  const city = cities.some((c) => c.id === cityParam) ? cityParam : "";
  const style = (STYLES as readonly string[]).includes(styleParam) ? styleParam : "";
  const wantAll = params.get("all") === "1";
  const openId = params.get("w");

  const setParams = useCallback(
    (changes: Record<string, string | null>) => {
      const next = new URLSearchParams(params.toString());
      for (const [k, v] of Object.entries(changes)) {
        if (v) next.set(k, v);
        else next.delete(k);
      }
      const q = next.toString();
      router.replace(q ? `${pathname}?${q}` : pathname, { scroll: false });
    },
    [params, router, pathname],
  );

  // Featured only, unless "Show all" is on — or the chosen filters have no featured wallpapers.
  const matching = wallpapers.filter((w) => (!city || cityId(w) === city) && (!style || w.style === style));
  const featuredMatching = matching.filter((w) => w.featured);
  const showingAll = wantAll || featuredMatching.length === 0;
  const visible = (showingAll ? matching : featuredMatching);

  // Group by city: Indian cities first, then the rest.
  const groups = cities
    .map((c) => ({
      city: c,
      items: visible.filter((w) => cityId(w) === c.id).sort((a, b) => styleRank(a.style) - styleRank(b.style)),
    }))
    .filter((g) => g.items.length > 0);
  const ordered = groups.flatMap((g) => g.items);

  const openIndex = openId ? ordered.findIndex((w) => w.id === openId) : -1;
  const open = openIndex >= 0 ? ordered[openIndex]! : openId ? wallpapers.find((w) => w.id === openId) ?? null : null;
  const step = (d: 1 | -1) => {
    if (ordered.length === 0) return;
    const i = openIndex >= 0 ? openIndex : 0;
    setParams({ w: ordered[(i + d + ordered.length) % ordered.length]!.id });
  };

  const india = cities.filter((c) => c.country === "India");
  const world = cities.filter((c) => c.country !== "India");

  return (
    <section className="relative pt-[var(--nav-height)]">
      <div className="mx-auto max-w-[100rem] px-5 pt-10 sm:px-10 lg:px-16">
        <p className="label-caps">Wallpaper gallery</p>
        <h1 className="mt-4 max-w-4xl font-display text-5xl font-light leading-[1.05] tracking-tight text-ink sm:text-7xl">
          Tonight&apos;s sky, <span className="bg-gradient-to-r from-gold to-cyan bg-clip-text text-transparent">for your phone.</span>
        </h1>
        <p className="mt-5 max-w-2xl text-base leading-relaxed text-muted sm:text-lg">
          The real night sky over nine cities, drawn star by star from the HYG catalogue and placed with
          Skyfield — in four styles. Tap one to see it full size and download it.
        </p>

        {/* Controls */}
        <div className="mt-10 flex flex-wrap items-center gap-3">
          <div role="group" aria-label="Which wallpapers" className="glass flex rounded-full p-1">
            {([["Featured", false], ["Show all", true]] as const).map(([label, all]) => {
              const on = showingAll === all;
              return (
                <button key={label} type="button" aria-pressed={on}
                  onClick={() => setParams({ all: all ? "1" : null })}
                  className={`min-h-10 rounded-full px-4 text-sm transition-colors ${on ? "bg-gold text-void" : "text-ink/80 hover:text-ink"}`}>
                  {label}
                  {manifest && (
                    <span className={`ml-1.5 tabular-nums ${on ? "text-void/70" : "text-muted"}`}>
                      {all ? matching.length : featuredMatching.length}
                    </span>
                  )}
                </button>
              );
            })}
          </div>

          <label className="glass flex min-h-12 items-center gap-2 rounded-full pl-4 pr-2 text-sm text-muted">
            City
            <select value={city} onChange={(e) => setParams({ city: e.target.value || null, w: null })}
              className="min-h-10 rounded-full bg-transparent px-2 text-ink outline-none [&_option]:bg-deep">
              <option value="">All cities</option>
              <optgroup label="India">
                {india.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
              </optgroup>
              <optgroup label="Around the world">
                {world.map((c) => <option key={c.id} value={c.id}>{c.name}, {c.country}</option>)}
              </optgroup>
            </select>
          </label>

          <div role="group" aria-label="Style" className="flex flex-wrap gap-2">
            {(["", ...STYLES] as const).map((s) => {
              const on = style === s;
              return (
                <button key={s || "any"} type="button" aria-pressed={on}
                  onClick={() => setParams({ style: s || null, w: null })}
                  className={`min-h-11 rounded-full border px-4 text-sm transition-colors ${
                    on ? "border-gold/60 bg-gold/10 text-gold" : "border-line text-ink/80 hover:border-ink/30 hover:text-ink"}`}>
                  {s ? capitalise(s) : "All styles"}
                </button>
              );
            })}
          </div>
        </div>
        {manifest && !wantAll && featuredMatching.length === 0 && matching.length > 0 && (
          <p className="mt-4 text-sm text-muted" role="status">None of these are in the featured set, so all of them are shown.</p>
        )}

        {/* Grid */}
        <div className="mt-12 min-h-[24rem]">
          {failed ? (
            <ApiErrorNotice className="py-20" message="The gallery couldn't be loaded. Check your connection and try again."
              onRetry={() => setAttempt((n) => n + 1)} />
          ) : !manifest ? (
            <ConstellationSkeleton className="py-24" label="Loading the gallery" />
          ) : groups.length === 0 ? (
            <p className="py-20 text-center text-muted">No wallpapers match these filters.</p>
          ) : (
            <div className="space-y-14">
              {groups.map(({ city: c, items }) => (
                <section key={c.id} aria-labelledby={`city-${c.id}`}>
                  <h2 id={`city-${c.id}`} className="mb-5 flex items-baseline gap-3">
                    <span className="font-display text-2xl font-light text-ink">{c.name}</span>
                    <span className="label-caps">{c.country}</span>
                  </h2>
                  <ul className="grid grid-cols-2 gap-4 sm:grid-cols-3 sm:gap-5 lg:grid-cols-4 2xl:grid-cols-5">
                    <AnimatePresence initial={false}>
                      {items.map((w) => (
                        <motion.li key={w.id} layout initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }}
                          exit={{ opacity: 0 }} transition={{ duration: 0.35, ease: [0.22, 1, 0.36, 1] }}>
                          <Card wallpaper={w} onOpen={() => setParams({ w: w.id })} />
                        </motion.li>
                      ))}
                    </AnimatePresence>
                  </ul>
                </section>
              ))}
            </div>
          )}
        </div>
      </div>

      <AnimatePresence>
        {open && (
          <Lightbox
            key="lightbox"
            wallpaper={open}
            position={openIndex >= 0 ? `${openIndex + 1} of ${ordered.length}` : capitalise(open.style)}
            onClose={() => setParams({ w: null })}
            onPrev={() => step(-1)}
            onNext={() => step(1)}
          />
        )}
      </AnimatePresence>
    </section>
  );
}

function Card({ wallpaper: w, onOpen }: { wallpaper: Wallpaper; onOpen: () => void }) {
  return (
    <div className="group relative">
      <button type="button" onClick={onOpen} aria-label={`Open ${w.title} full size`}
        className="block w-full overflow-hidden rounded-2xl border border-ink/10 bg-deep transition-[border-color,box-shadow,transform] duration-500 ease-[cubic-bezier(0.22,1,0.36,1)] hover:-translate-y-1 hover:border-gold/40 hover:shadow-[0_20px_60px_rgb(0_0_0/0.5),0_0_30px_rgb(245_196_81/0.12)]">
        {/* eslint-disable-next-line @next/next/no-img-element -- pre-sized WebP thumbnails from public/ */}
        <img src={w.thumbnail} alt={`${w.title} — ${w.caption}`} width={400} height={866} loading="lazy" decoding="async"
          className="block aspect-[1080/2340] h-auto w-full object-cover" />
      </button>
      <div className="mt-3 flex items-start justify-between gap-2">
        <div className="min-w-0">
          <p className="truncate text-sm text-ink">{capitalise(w.style)}</p>
          <p className="truncate text-xs text-muted">{w.visible_constellations.slice(0, 3).join(" · ")}</p>
        </div>
        <a href={w.path} download={w.filename} aria-label={`Download ${w.title}`}
          className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full border border-line text-muted transition-colors hover:border-gold/50 hover:text-gold">
          <DownloadIcon size={17} />
        </a>
      </div>
    </div>
  );
}
