"use client";

import { AnimatePresence, motion } from "framer-motion";
import { useEffect, useState } from "react";
import ConstellationTrace from "@/components/sky/ConstellationTrace";
import { getConstellation } from "@/lib/data/catalog";
import { useReducedMotion } from "@/hooks/useReducedMotion";

const FEATURED = ["Orion", "Cassiopeia", "Ursa Major"] as const;
const CYCLE_MS = 9000;

/** A constellation traces itself while the first line of its myth fades in. */
export default function StoriesDemo() {
  const [index, setIndex] = useState(0);
  const reduced = useReducedMotion();
  useEffect(() => {
    if (reduced) return;
    const id = window.setInterval(() => setIndex((i) => (i + 1) % FEATURED.length), CYCLE_MS);
    return () => window.clearInterval(id);
  }, [reduced]);

  const name = FEATURED[index]!;
  const constellation = getConstellation(name);
  if (!constellation) return null;
  const firstSentence = constellation.mythology.split(/(?<=\.)\s/)[0] ?? "";

  return (
    <div className="relative">
      <div className="aspect-[4/3] w-full">
        <ConstellationTrace constellation={constellation} name={name} />
      </div>
      <div className="mt-4 min-h-[6.5rem] text-center">
        <AnimatePresence mode="wait">
          <motion.div
            key={name}
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0, transition: { duration: 0.6, delay: 0.15 } }}
            exit={{ opacity: 0, y: -8, transition: { duration: 0.3 } }}
          >
            <p className="label-caps mb-2 !text-gold">{name}</p>
            <p className="mx-auto max-w-md font-display text-lg font-light leading-snug text-ink/90 italic">
              &ldquo;{firstSentence}&rdquo;
            </p>
          </motion.div>
        </AnimatePresence>
      </div>
      <div className="mt-2 flex justify-center gap-2" role="tablist" aria-label="Featured constellations">
        {FEATURED.map((n, i) => (
          <button
            key={n}
            type="button"
            role="tab"
            aria-selected={i === index}
            aria-label={n}
            onClick={() => setIndex(i)}
            className="flex h-11 w-11 items-center justify-center rounded-full"
          >
            <span className={`block h-1.5 rounded-full transition-all duration-500 ${i === index ? "w-6 bg-gold" : "w-1.5 bg-ink/30"}`} />
          </button>
        ))}
      </div>
    </div>
  );
}
