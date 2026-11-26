"use client";

import { motion } from "framer-motion";
import Link from "next/link";
import type { TonightSummary } from "@/lib/types";

/** Constellation chips with compass direction; each opens its Learn page. */
export default function UpTonight({ items }: { items: TonightSummary["upTonight"] }) {
  if (items.length === 0) return null;
  return (
    <div>
      <p className="label-caps mb-5">Up tonight</p>
      <motion.ul
        className="flex flex-wrap gap-3"
        initial="hidden"
        whileInView="show"
        viewport={{ once: true, amount: 0.5 }}
        variants={{ show: { transition: { staggerChildren: 0.06 } } }}
      >
        {items.map((item) => (
          <motion.li
            key={item.name}
            variants={{ hidden: { opacity: 0, y: 10 }, show: { opacity: 1, y: 0, transition: { duration: 0.5 } } }}
          >
            <Link
              href={`/learn?c=${encodeURIComponent(item.name)}`}
              className="group flex min-h-11 items-center gap-3 rounded-full border border-line px-5 py-2 text-sm text-ink transition-[border-color,box-shadow,color] duration-300 hover:border-gold/60 hover:text-gold hover:shadow-[0_0_20px_rgb(245_196_81/0.18)]"
            >
              {item.name}
              <span className="font-display text-[0.7rem] tracking-[0.2em] text-muted transition-colors group-hover:text-gold/80">
                {item.direction}
              </span>
            </Link>
          </motion.li>
        ))}
      </motion.ul>
    </div>
  );
}
