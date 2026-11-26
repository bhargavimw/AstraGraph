"use client";

import { motion } from "framer-motion";
import type { ReactNode } from "react";
import { useReducedMotion } from "@/hooks/useReducedMotion";

const EASE = [0.22, 1, 0.36, 1] as const;

/**
 * Full-width scroll section: text on one side, a visual on the other,
 * alternating per section. Both halves reveal as they scroll into view.
 */
export default function StorySection({
  index,
  label,
  title,
  children,
  visual,
  flip = false,
  id,
}: {
  index: string;
  label: string;
  title: ReactNode;
  children: ReactNode;
  visual: ReactNode;
  flip?: boolean;
  id?: string;
}) {
  const reduced = useReducedMotion();
  const rise = (delay: number) => ({
    initial: { opacity: 0, y: reduced ? 0 : 28 },
    whileInView: { opacity: 1, y: 0 },
    viewport: { once: true, amount: 0.35 },
    transition: { duration: 0.9, ease: EASE, delay },
  });
  return (
    <section
      id={id}
      className="mx-auto grid min-h-[85vh] max-w-[100rem] items-center gap-12 px-6 py-24 sm:px-10 md:grid-cols-2 md:gap-16 lg:px-16"
    >
      <motion.div {...rise(0)} className={flip ? "md:order-2" : ""}>
        <p className="label-caps mb-5 flex items-center gap-4">
          <span className="font-display text-gold">{index}</span>
          <span className="h-px w-10 bg-line" aria-hidden="true" />
          {label}
        </p>
        <h2 className="font-display text-4xl font-light leading-[1.08] tracking-tight text-ink sm:text-5xl lg:text-6xl">
          {title}
        </h2>
        <div className="mt-6 max-w-xl space-y-4 text-base leading-relaxed text-muted sm:text-lg">{children}</div>
      </motion.div>
      <motion.div {...rise(0.15)} className={`relative ${flip ? "md:order-1" : ""}`}>
        {visual}
      </motion.div>
    </section>
  );
}
