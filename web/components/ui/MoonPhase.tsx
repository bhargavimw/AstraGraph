/**
 * The Moon drawn with its real illuminated fraction. The terminator is an
 * ellipse whose width follows the phase; waxing Moons are lit on the right
 * (as seen from the Northern Hemisphere), waning Moons on the left.
 */
export default function MoonPhase({
  illumination,
  waxing,
  size = 40,
  title,
}: {
  illumination: number;
  waxing: boolean;
  size?: number;
  title?: string;
}) {
  const k = Math.max(0, Math.min(1, illumination));
  const c = 20;
  const r = 15;
  const rx = Math.abs(1 - 2 * k) * r;
  const limbSweep = waxing ? 1 : 0; // trace the lit limb on the right (waxing) or left
  const termSweep = (k > 0.5) === waxing ? 1 : 0;
  const lit =
    k <= 0.001
      ? ""
      : k >= 0.999
        ? `M ${c} ${c - r} A ${r} ${r} 0 1 1 ${c} ${c + r} A ${r} ${r} 0 1 1 ${c} ${c - r} Z`
        : `M ${c} ${c - r} A ${r} ${r} 0 0 ${limbSweep} ${c} ${c + r} A ${rx} ${r} 0 0 ${termSweep} ${c} ${c - r} Z`;
  return (
    <svg width={size} height={size} viewBox="0 0 40 40" role="img" aria-label={title ?? `Moon ${Math.round(k * 100)}% lit`}>
      <defs>
        <radialGradient id="moon-lit" cx="40%" cy="35%" r="70%">
          <stop offset="0%" stopColor="#fdf6e3" />
          <stop offset="100%" stopColor="#d9cfb4" />
        </radialGradient>
      </defs>
      <circle cx={c} cy={c} r={r} fill="#1a2140" stroke="rgba(232,236,246,0.18)" strokeWidth="1" />
      {lit && <path d={lit} fill="url(#moon-lit)" />}
      <circle cx={c} cy={c} r={r + 3} fill="none" stroke="rgba(253,246,227,0.08)" strokeWidth="2" />
    </svg>
  );
}
