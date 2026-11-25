"use client";

import { AnimatePresence, motion } from "framer-motion";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import LocationPopover from "@/components/ui/LocationPopover";
import Logo from "@/components/ui/Logo";
import { CloseIcon, MenuIcon } from "@/components/ui/icons";
import { useReducedMotion } from "@/hooks/useReducedMotion";

export const NAV_LINKS = [
  { href: "/live", label: "Live" },
  { href: "/time-travel", label: "Time Travel" },
  { href: "/learn", label: "Learn" },
] as const;

const EASE = [0.22, 1, 0.36, 1] as const;

function isActive(pathname: string, href: string): boolean {
  return pathname === href || pathname.startsWith(`${href}/`);
}

export default function TopNav() {
  const pathname = usePathname();
  const reduced = useReducedMotion();
  const [scrolled, setScrolled] = useState(false);
  const [menuOpen, setMenuOpen] = useState(false);

  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 12);
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  // Close the mobile menu on navigation; lock page scroll while it is open.
  useEffect(() => setMenuOpen(false), [pathname]);
  useEffect(() => {
    document.body.style.overflow = menuOpen ? "hidden" : "";
    if (!menuOpen) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setMenuOpen(false);
    document.addEventListener("keydown", onKey);
    return () => {
      document.body.style.overflow = "";
      document.removeEventListener("keydown", onKey);
    };
  }, [menuOpen]);

  return (
    <>
      <header
        className={`fixed inset-x-0 top-0 z-40 transition-[background-color,border-color,backdrop-filter] duration-500 ${
          scrolled
            ? "border-b border-line bg-void/55 backdrop-blur-xl"
            : "border-b border-transparent bg-transparent"
        }`}
      >
        <nav
          aria-label="Main"
          className="mx-auto flex h-[var(--nav-height)] max-w-[110rem] items-center justify-between px-5 sm:px-8 lg:px-12"
        >
          <Logo />

          <div className="hidden items-center gap-10 md:flex">
            <ul className="flex items-center gap-8">
              {NAV_LINKS.map((link) => {
                const active = isActive(pathname, link.href);
                return (
                  <li key={link.href} className="relative">
                    <Link
                      href={link.href}
                      aria-current={active ? "page" : undefined}
                      className={`block rounded-sm py-2 text-[0.82rem] tracking-[0.14em] uppercase transition-colors duration-300 ${
                        active ? "text-ink" : "text-muted hover:text-ink"
                      }`}
                    >
                      {link.label}
                    </Link>
                    {active && (
                      <motion.span
                        layoutId="nav-underline"
                        className="absolute inset-x-0 -bottom-0.5 h-px bg-gold shadow-[0_0_10px_rgb(245_196_81/0.8)]"
                        transition={reduced ? { duration: 0 } : { duration: 0.45, ease: EASE }}
                      />
                    )}
                  </li>
                );
              })}
            </ul>
            <LocationPopover />
          </div>

          <button
            type="button"
            className="-mr-2 rounded-full p-2 text-ink md:hidden"
            onClick={() => setMenuOpen(true)}
            aria-label="Open menu"
            aria-expanded={menuOpen}
            aria-controls="mobile-menu"
          >
            <MenuIcon size={24} />
          </button>
        </nav>
      </header>

      <AnimatePresence>
        {menuOpen && (
          <motion.div
            id="mobile-menu"
            role="dialog"
            aria-modal="true"
            aria-label="Menu"
            className="fixed inset-0 z-50 flex flex-col bg-void/92 backdrop-blur-2xl md:hidden"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.3 }}
          >
            <div className="flex h-[var(--nav-height)] items-center justify-between px-5">
              <Logo />
              <button
                type="button"
                className="-mr-2 rounded-full p-2 text-ink"
                onClick={() => setMenuOpen(false)}
                aria-label="Close menu"
                autoFocus
              >
                <CloseIcon size={24} />
              </button>
            </div>

            <motion.ul
              className="flex flex-1 flex-col justify-center gap-2 px-8"
              initial="hidden"
              animate="show"
              variants={{ show: { transition: { staggerChildren: reduced ? 0 : 0.07, delayChildren: 0.08 } } }}
            >
              {[{ href: "/", label: "Home" }, ...NAV_LINKS].map((link) => {
                const active = link.href === "/" ? pathname === "/" : isActive(pathname, link.href);
                return (
                  <motion.li
                    key={link.href}
                    variants={{
                      hidden: { opacity: 0, y: reduced ? 0 : 18 },
                      show: { opacity: 1, y: 0, transition: { duration: 0.45, ease: EASE } },
                    }}
                  >
                    <Link
                      href={link.href}
                      aria-current={active ? "page" : undefined}
                      className={`flex items-center gap-4 rounded-md py-3 font-display text-4xl font-light tracking-tight ${
                        active ? "text-gold" : "text-ink"
                      }`}
                    >
                      <span
                        className={`h-px w-6 transition-colors ${active ? "bg-gold" : "bg-line"}`}
                        aria-hidden="true"
                      />
                      {link.label}
                    </Link>
                  </motion.li>
                );
              })}
            </motion.ul>

            <div className="px-8 pb-10">
              <p className="label-caps mb-3">Observing from</p>
              <LocationPopover align="left" side="up" />
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </>
  );
}
