"use client";

import { useEffect, useMemo, useState } from "react";
import type { ApiConstellationDetail } from "@/lib/types";

/** Two decimals, so SVG attributes are short and stable. */
const r2 = (v: number) => Math.round(v * 100) / 100;
const DEG = Math.PI / 180;
/** "−31°" with a true minus sign. */
const deg = (v: number) => `${Math.round(v) < 0 ? "−" : ""}${Math.abs(Math.round(v))}°`;

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
const MONTH_NAMES = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"];

/** Point on a circle, angle in degrees clockwise from the top. */
function polar(cx: number, cy: number, radius: number, angle: number) {
  return { x: r2(cx + radius * Math.sin(angle * DEG)), y: r2(cy - radius * Math.cos(angle * DEG)) };
}

function arcPath(cx: number, cy: number, outer: number, inner: number, start: number, end: number): string {
  const a = polar(cx, cy, outer, start);
  const b = polar(cx, cy, outer, end);
  const c = polar(cx, cy, inner, end);
  const d = polar(cx, cy, inner, start);
  const large = end - start > 180 ? 1 : 0;
  return `M${a.x} ${a.y}A${outer} ${outer} 0 ${large} 1 ${b.x} ${b.y}L${c.x} ${c.y}A${inner} ${inner} 0 ${large} 0 ${d.x} ${d.y}Z`;
}

// ------------------------------------------------------------- best month
/** 12-month ring with the best month (highest at 9 pm) lit. */
export function BestMonthRing({ best }: { best: ApiConstellationDetail["best_month"] }) {
  const month = best?.month ?? null;
  const size = 168;
  const c = size / 2;
  return (
    <div className="flex items-center gap-6">
      <svg viewBox={`0 0 ${size} ${size}`} className="h-40 w-40 shrink-0" role="img"
        aria-label={month ? `Best month: ${MONTH_NAMES[month - 1]}` : "No good month from this location"}>
        <defs>
          <filter id="month-glow" x="-50%" y="-50%" width="200%" height="200%">
            <feGaussianBlur stdDeviation="3" />
          </filter>
        </defs>
        {MONTHS.map((label, i) => {
          const start = i * 30 + 2;
          const end = (i + 1) * 30 - 2;
          const m = i + 1;
          const isBest = m === month;
          const near = month !== null && !isBest && (Math.abs(m - month) === 1 || Math.abs(m - month) === 11);
          const fill = isBest ? "#f5c451" : near ? "rgb(245 196 81 / 0.28)" : "rgb(232 236 246 / 0.08)";
          const text = polar(c, c, 75, i * 30 + 15);
          return (
            <g key={label}>
              {isBest && <path d={arcPath(c, c, 64, 50, start, end)} fill="#f5c451" opacity={0.6} filter="url(#month-glow)" />}
              <path d={arcPath(c, c, 64, 50, start, end)} fill={fill} />
              <text x={text.x} y={text.y} textAnchor="middle" dominantBaseline="central"
                className="font-display" fontSize={8.5} letterSpacing={0.4}
                fill={isBest ? "#f5c451" : "rgb(139 149 176)"}>
                {label.toUpperCase()}
              </text>
            </g>
          );
        })}
        <text x={c} y={c - 4} textAnchor="middle" className="font-display" fontSize={22} fontWeight={300} fill="#e8ecf6">
          {month ? MONTHS[month - 1] : "—"}
        </text>
        <text x={c} y={c + 15} textAnchor="middle" fontSize={10} fill="rgb(139 149 176)">
          {best ? `${Math.round(best.altitude)}° high` : "too low"}
        </text>
      </svg>
      <p className="text-sm leading-relaxed text-muted">
        {month && best ? (
          <>
            Best in <span className="text-ink">{MONTH_NAMES[month - 1]}</span>, when it stands{" "}
            <span className="tabular-nums text-ink">{Math.round(best.altitude)}°</span> above the horizon at 9 pm.
          </>
        ) : (
          <>From here it never climbs high enough to see well at 9 pm.</>
        )}
      </p>
    </div>
  );
}

// --------------------------------------------------------------- right now
/** Mini compass pointing at the constellation, plus an altitude gauge. */
export function NowPosition({ now }: { now: ApiConstellationDetail["now"] }) {
  const size = 120;
  const c = size / 2;
  const tip = polar(c, c, 40, now.az);
  const left = polar(c, c, 7, now.az - 90);
  const right = polar(c, c, 7, now.az + 90);
  const tail = polar(c, c, 14, now.az + 180);
  const up = now.alt > 0;

  // Altitude gauge: a quarter circle from the horizon (0°) to the zenith (90°).
  const g = { x: 12, y: 62, r: 54 };
  const altClamped = Math.max(-30, Math.min(90, now.alt));
  const dot = { x: r2(g.x + g.r * Math.cos(altClamped * DEG)), y: r2(g.y - g.r * Math.sin(altClamped * DEG)) };

  return (
    <div className="flex items-center gap-5">
      <svg viewBox={`0 0 ${size} ${size}`} className="h-28 w-28 shrink-0" role="img"
        aria-label={`Direction: ${Math.round(now.az)} degrees, ${now.direction}`}>
        <circle cx={c} cy={c} r={50} fill="none" stroke="rgb(232 236 246 / 0.14)" />
        {Array.from({ length: 8 }, (_, i) => {
          const a = polar(c, c, 50, i * 45);
          const b = polar(c, c, i % 2 ? 46 : 43, i * 45);
          return <line key={i} x1={a.x} y1={a.y} x2={b.x} y2={b.y} stroke="rgb(232 236 246 / 0.3)" />;
        })}
        {(["N", "E", "S", "W"] as const).map((label, i) => {
          const p = polar(c, c, 33, i * 90);
          return (
            <text key={label} x={p.x} y={p.y} textAnchor="middle" dominantBaseline="central"
              className="font-display" fontSize={9} fill={label === "N" ? "#e8ecf6" : "rgb(139 149 176)"}>
              {label}
            </text>
          );
        })}
        <polygon
          points={`${tip.x},${tip.y} ${left.x},${left.y} ${tail.x},${tail.y} ${right.x},${right.y}`}
          fill={up ? "#f5c451" : "rgb(139 149 176 / 0.7)"}
          className="transition-[fill] duration-500"
        />
        <circle cx={c} cy={c} r={2.5} fill="#05070f" stroke="rgb(232 236 246 / 0.6)" />
      </svg>

      <div className="min-w-0">
        <svg viewBox="0 0 96 92" className="h-20 w-[5.25rem]" role="img" aria-label={`Altitude: ${Math.round(now.alt)} degrees`}>
          <path d={`M${g.x + g.r} ${g.y}A${g.r} ${g.r} 0 0 0 ${g.x} ${g.y - g.r}`} fill="none" stroke="rgb(232 236 246 / 0.3)" />
          <line x1={g.x} y1={g.y} x2={g.x} y2={g.y - g.r} stroke="rgb(232 236 246 / 0.15)" />
          <line x1={2} y1={g.y} x2={g.x + g.r + 10} y2={g.y} stroke="rgb(232 236 246 / 0.55)" />
          <text x={g.x + g.r + 2} y={g.y + 11} fontSize={8} fill="rgb(139 149 176)" textAnchor="middle">0°</text>
          <text x={g.x + 6} y={g.y - g.r + 3} fontSize={8} fill="rgb(139 149 176)">90°</text>
          <line x1={g.x} y1={g.y} x2={dot.x} y2={dot.y} stroke={up ? "rgb(245 196 81 / 0.7)" : "rgb(139 149 176 / 0.6)"} strokeDasharray={up ? undefined : "2 2"} />
          <circle cx={dot.x} cy={dot.y} r={4} fill={up ? "#f5c451" : "rgb(139 149 176)"} />
        </svg>
        <p className="mt-1 text-sm text-ink">
          <span className="tabular-nums">{Math.round(now.az)}°</span>{" "}
          <span className="font-display text-xs tracking-[0.2em] text-muted">{now.direction}</span>
          <span className="mx-2 text-line">|</span>
          <span className="tabular-nums">{deg(now.alt)}</span>{" "}
          <span className="text-xs text-muted">{up ? "high" : "below"}</span>
        </p>
        <span className={`mt-2 inline-block rounded-full border px-2.5 py-0.5 text-[0.65rem] uppercase tracking-wider ${
          now.visible ? "border-gold/40 text-gold" : up ? "border-cyan/40 text-cyan" : "border-line text-muted"
        }`}>
          {now.visible ? "Visible now" : up ? "Low on the horizon" : "Below the horizon"}
        </span>
      </div>
    </div>
  );
}

// ----------------------------------------------------------------- tonight
interface Marker { key: string; label: string; time: number }

/** Rise → highest → set as a bar, with a "now" marker that moves. */
export function TonightTimeline({ tonight, tz }: { tonight: ApiConstellationDetail["tonight"]; tz: string }) {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), 60000);
    return () => clearInterval(id);
  }, []);

  const fmt = useMemo(() => new Intl.DateTimeFormat("en-GB", { hour: "2-digit", minute: "2-digit", timeZone: tz }), [tz]);
  const t = (iso: string | null) => (iso ? new Date(iso).getTime() : null);
  const rise = t(tonight.rise_utc);
  const transit = t(tonight.transit_utc);
  const set = t(tonight.set_utc);
  const H = 3600000;

  if (tonight.never_rises) {
    return <p className="text-sm text-muted">It never rises from this latitude — try it from closer to the equator.</p>;
  }

  // The window covers the time it is up, padded, and stretched to include "now"
  // when that is close enough to be useful.
  let start: number;
  let end: number;
  if (rise !== null && set !== null) {
    start = rise - H;
    end = set + H;
  } else {
    const mid = transit ?? now;
    start = mid - 12 * H;
    end = mid + 12 * H;
  }
  if (now < start && start - now < 8 * H) start = now - 0.5 * H;
  if (now > end && now - end < 8 * H) end = now + 0.5 * H;
  const span = end - start;
  const pct = (time: number) => Math.max(0, Math.min(100, ((time - start) / span) * 100));
  const nowInside = now >= start && now <= end;

  const upFrom = rise !== null ? pct(rise) : 0;
  const upTo = set !== null ? pct(set) : 100;

  const until = (time: number) => {
    const mins = Math.round(Math.abs(time - now) / 60000);
    const h = Math.floor(mins / 60);
    const m = mins % 60;
    return h ? `${h} h ${m} min` : `${m} min`;
  };
  let status: string | null = null;
  if (rise !== null && set !== null) {
    if (now < rise) status = `Rises in ${until(rise)}`;
    else if (now < set) status = `Up now · sets in ${until(set)}`;
    else status = "Already set for today";
  } else if (transit !== null) {
    status = now < transit ? `Highest in ${until(transit)}` : `Was highest ${until(transit)} ago`;
  }

  const markers: Marker[] = [];
  if (rise !== null) markers.push({ key: "rise", label: "Rises", time: rise });
  if (transit !== null) markers.push({ key: "transit", label: "Highest", time: transit });
  if (set !== null) markers.push({ key: "set", label: "Sets", time: set });

  return (
    <div>
      {status && <p className="mt-2 text-sm text-ink/85">{status}</p>}
      <div className="relative mx-1 mt-9 h-1.5 rounded-full bg-ink/10">
        <div
          className="absolute inset-y-0 rounded-full bg-gradient-to-r from-gold/30 via-gold to-gold/30 shadow-[0_0_14px_rgb(245_196_81/0.35)]"
          style={{ left: `${upFrom}%`, right: `${100 - upTo}%` }}
        />
        {markers.map((m) => (
          <span key={m.key} className="absolute top-1/2 h-3 w-3 -translate-x-1/2 -translate-y-1/2 rounded-full border-2 border-void bg-gold"
            style={{ left: `${pct(m.time)}%` }} aria-hidden="true" />
        ))}
        {nowInside && (
          <span className="absolute -top-7 flex -translate-x-1/2 flex-col items-center" style={{ left: `${pct(now)}%` }}>
            <span className="font-display text-[0.6rem] uppercase tracking-[0.2em] text-cyan">Now</span>
            <span className="mt-0.5 h-8 w-px bg-cyan shadow-[0_0_8px_rgb(92_225_230/0.8)]" />
          </span>
        )}
      </div>

      <dl className="mt-5 grid grid-cols-3 gap-3 text-center">
        {(["rise", "transit", "set"] as const).map((key) => {
          const m = markers.find((x) => x.key === key);
          const label = key === "rise" ? "Rises" : key === "transit" ? "Highest" : "Sets";
          return (
            <div key={key}>
              <dt className="label-caps !text-[0.6rem] !tracking-[0.24em]">{label}</dt>
              <dd className="mt-1 font-display text-lg font-light tabular-nums text-ink">
                {m ? fmt.format(m.time) : "—"}
              </dd>
              {key === "transit" && tonight.transit_altitude !== null && (
                <dd className="text-xs tabular-nums text-muted">{Math.round(tonight.transit_altitude)}° up</dd>
              )}
            </div>
          );
        })}
      </dl>
      {tonight.circumpolar && (
        <p className="mt-4 text-sm text-muted">
          <span className="text-ink">Circumpolar</span> from here: it circles the pole and never sets.
        </p>
      )}
    </div>
  );
}
