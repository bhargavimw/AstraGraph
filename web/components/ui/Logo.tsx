import Link from "next/link";

/** Planet-and-orbit mark plus the ASTRAGRAPH wordmark. */
export default function Logo() {
  return (
    <Link href="/" className="group flex items-center gap-3 rounded-md" aria-label="AstraGraph home">
      <svg width="30" height="30" viewBox="0 0 32 32" aria-hidden="true" className="shrink-0">
        <defs>
          <radialGradient id="logo-planet" cx="35%" cy="30%" r="75%">
            <stop offset="0%" stopColor="#fff6d8" />
            <stop offset="45%" stopColor="#f5c451" />
            <stop offset="100%" stopColor="#8a5a0c" />
          </radialGradient>
        </defs>
        <ellipse
          cx="16" cy="16" rx="14" ry="5.2"
          fill="none" stroke="#5ce1e6" strokeOpacity="0.7" strokeWidth="1.2"
          transform="rotate(-20 16 16)"
          className="origin-center transition-transform duration-700 ease-[var(--ease-cosmic)] group-hover:rotate-[10deg]"
        />
        <circle cx="16" cy="16" r="7" fill="url(#logo-planet)" />
        <circle cx="27.4" cy="11.6" r="1.4" fill="#5ce1e6" />
      </svg>
      <span className="font-display text-[0.95rem] font-medium tracking-[0.34em] text-ink">
        ASTRAGRAPH
      </span>
    </Link>
  );
}
