"use client";

import Link from "next/link";
import { ArrowDownIcon, CameraIcon } from "@/components/ui/icons-extra";

/**
 * The entrance animations are plain CSS (`.rise` in globals.css), so the text
 * is painted straight from the server HTML without waiting for JavaScript.
 */
const enter = (delay: number) => ({ style: { animationDelay: `${delay}s` } });

export default function Hero() {
  return (
    <section className="relative flex min-h-[100svh] flex-col items-center px-6 pt-[var(--nav-height)] text-center">
      {/* Content centred in the space above the scroll cue; the cue is in the
          normal flow so it can never overlap the buttons on short screens. */}
      <div className="flex w-full flex-1 flex-col items-center justify-center py-10">
      <p style={enter(0.05).style} className="rise label-caps mb-8">
        A planetarium in your browser
      </p>
      <h1 className="font-display text-[clamp(2.9rem,8.5vw,8.5rem)] font-light leading-[0.98] tracking-[-0.02em] text-ink">
        <span style={enter(0.15).style} className="rise block">
          Your window to
        </span>
        <span
          style={enter(0.3).style}
          className="rise block bg-gradient-to-r from-gold via-[#f9dfa0] to-cyan bg-clip-text pb-2 text-transparent"
        >
          the night sky
        </span>
      </h1>
      <p style={enter(0.45).style} className="rise mt-8 max-w-xl text-base leading-relaxed text-muted sm:text-lg">
        Point your camera at the stars, travel through tonight&apos;s sky, and learn the stories written
        in them.
      </p>
      <div style={enter(0.6).style} className="rise mt-12 flex flex-col items-center gap-4 sm:flex-row">
        <Link
          href="/live"
          className="group flex items-center gap-2.5 rounded-full bg-gold px-7 py-3.5 text-sm font-medium tracking-wide text-void transition-shadow duration-500 hover:shadow-[0_0_40px_rgb(245_196_81/0.55)]"
        >
          <CameraIcon size={18} />
          Open Live Camera
        </Link>
        <a
          href="#tonight"
          className="rounded-full border border-ink/20 px-7 py-3.5 text-sm tracking-wide text-ink transition-colors duration-500 hover:border-cyan/60 hover:text-cyan"
        >
          Explore tonight&apos;s sky
        </a>
      </div>

      </div>

      <a
        href="#tonight"
        aria-label="Scroll to tonight's sky"
        style={{ animationDelay: "1.4s" }}
        className="fade-in mb-8 flex flex-col items-center gap-3 text-muted"
      >
        <span className="text-[0.65rem] tracking-[0.4em] uppercase">Scroll</span>
        <span className="relative block h-10 w-px overflow-hidden bg-line">
          <span className="absolute inset-x-0 top-0 h-4 animate-[scrollcue_2.2s_ease-in-out_infinite] bg-gold" />
        </span>
        <ArrowDownIcon size={14} className="sr-only" />
      </a>
    </section>
  );
}
