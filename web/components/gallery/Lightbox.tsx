"use client";

import { motion } from "framer-motion";
import { useEffect, useRef, useState } from "react";
import { CloseIcon } from "@/components/ui/icons";
import { ChevronLeftIcon, ChevronRightIcon, DownloadIcon } from "@/components/ui/icons-extra";
import { capitalise, type Wallpaper } from "@/lib/wallpaper";

/**
 * Full-size view of one wallpaper (the 1080×2340 PNG from `wallpaper.path`),
 * with its details and a download button. Esc closes; ← → step through the
 * current selection. Focus moves into the dialog and back out when it closes.
 */
export default function Lightbox({
  wallpaper,
  onClose,
  onPrev,
  onNext,
  position,
}: {
  wallpaper: Wallpaper;
  onClose: () => void;
  onPrev: () => void;
  onNext: () => void;
  position: string;
}) {
  const closeButton = useRef<HTMLButtonElement | null>(null);
  const [loaded, setLoaded] = useState<string | null>(null);

  useEffect(() => {
    const opener = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    closeButton.current?.focus();
    const overflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = overflow;
      opener?.focus();
    };
  }, []);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
      else if (e.key === "ArrowLeft") onPrev();
      else if (e.key === "ArrowRight") onNext();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose, onPrev, onNext]);

  const time = new Intl.DateTimeFormat("en-GB", {
    dateStyle: "medium", timeStyle: "short", timeZone: wallpaper.timezone,
  }).format(new Date(wallpaper.datetime_utc));
  const sizeMb = (wallpaper.bytes / 1_000_000).toFixed(2);
  const ready = loaded === wallpaper.path;

  return (
    <motion.div
      role="dialog"
      aria-modal="true"
      aria-label={wallpaper.title}
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      transition={{ duration: 0.25 }}
      className="fixed inset-0 z-[70] overflow-y-auto bg-[rgb(3_5_12/0.92)] backdrop-blur-xl"
      onClick={(e) => e.target === e.currentTarget && onClose()}
    >
      <div className="flex min-h-full flex-col items-center gap-6 px-4 py-16 lg:flex-row lg:justify-center lg:gap-12 lg:py-8"
        onClick={(e) => e.target === e.currentTarget && onClose()}>
        {/* Image with prev/next */}
        <div className="relative flex items-center gap-2 sm:gap-4">
          <button type="button" onClick={onPrev} aria-label="Previous wallpaper"
            className="glass flex h-11 w-11 shrink-0 items-center justify-center rounded-full text-ink transition-colors hover:text-gold">
            <ChevronLeftIcon size={20} />
          </button>
          <div className="relative overflow-hidden rounded-[1.6rem] border border-ink/10 shadow-[0_30px_100px_rgb(0_0_0/0.7)]"
            style={{ aspectRatio: `${wallpaper.width} / ${wallpaper.height}`, height: "min(84svh, calc((100vw - 8rem) * 2.1667))" }}>
            {/* Thumbnail first, sharpened by the full PNG once it arrives. */}
            {/* eslint-disable-next-line @next/next/no-img-element -- static files from public/ */}
            <img src={wallpaper.thumbnail} alt="" aria-hidden="true" className="absolute inset-0 h-full w-full object-cover blur-[2px]" />
            {/* eslint-disable-next-line @next/next/no-img-element -- full-size static PNG */}
            <img
              key={wallpaper.path}
              src={wallpaper.path}
              alt={`${wallpaper.title}: ${wallpaper.caption}`}
              width={wallpaper.width}
              height={wallpaper.height}
              onLoad={() => setLoaded(wallpaper.path)}
              className={`absolute inset-0 h-full w-full object-cover transition-opacity duration-500 ${ready ? "opacity-100" : "opacity-0"}`}
            />
          </div>
          <button type="button" onClick={onNext} aria-label="Next wallpaper"
            className="glass flex h-11 w-11 shrink-0 items-center justify-center rounded-full text-ink transition-colors hover:text-gold">
            <ChevronRightIcon size={20} />
          </button>
        </div>

        {/* Details */}
        <div className="w-full max-w-sm">
          <p className="label-caps">{position}</p>
          <h2 className="mt-3 font-display text-3xl font-light text-ink">{wallpaper.title}</h2>
          <p className="mt-2 text-sm text-muted">{wallpaper.caption}</p>

          <dl className="mt-6 grid grid-cols-[auto_1fr] gap-x-5 gap-y-2 text-sm">
            <dt className="text-muted">Place</dt>
            <dd className="text-ink">{wallpaper.city}, {wallpaper.country}</dd>
            <dt className="text-muted">Sky at</dt>
            <dd className="text-ink">{time}</dd>
            <dt className="text-muted">Style</dt>
            <dd className="text-ink">{capitalise(wallpaper.style)}</dd>
            <dt className="text-muted">Moon</dt>
            <dd className="text-ink">{capitalise(wallpaper.moon_phase)}</dd>
            <dt className="text-muted">Size</dt>
            <dd className="tabular-nums text-ink">{wallpaper.width} × {wallpaper.height} · {sizeMb} MB</dd>
          </dl>

          {wallpaper.visible_constellations.length > 0 && (
            <>
              <p className="label-caps mb-3 mt-6">In this sky</p>
              <ul className="flex flex-wrap gap-2">
                {wallpaper.visible_constellations.map((c) => (
                  <li key={c} className="rounded-full border border-line px-3 py-1 text-xs text-ink/85">{c}</li>
                ))}
              </ul>
            </>
          )}

          <a
            href={wallpaper.path}
            download={wallpaper.filename}
            className="mt-8 inline-flex min-h-11 items-center gap-2 rounded-full bg-gold px-6 text-sm font-medium text-void shadow-[0_0_24px_rgb(245_196_81/0.35)] transition-shadow hover:shadow-[0_0_36px_rgb(245_196_81/0.6)]"
          >
            <DownloadIcon size={18} /> Download wallpaper
          </a>
        </div>
      </div>

      <button
        ref={closeButton}
        type="button"
        onClick={onClose}
        aria-label="Close"
        className="glass fixed right-4 top-4 flex h-11 w-11 items-center justify-center rounded-full text-ink transition-colors hover:text-gold sm:right-6 sm:top-6"
      >
        <CloseIcon size={20} />
      </button>
    </motion.div>
  );
}
