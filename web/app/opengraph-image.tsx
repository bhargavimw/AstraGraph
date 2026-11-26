import { ImageResponse } from "next/og";

/**
 * Share image (link previews on WhatsApp, X, Slack…): a starry gradient with
 * the AstraGraph name, generated once at build time. No external assets.
 */

export const alt = "AstraGraph — your window to the night sky";
export const size = { width: 1200, height: 630 };
export const contentType = "image/png";

function seeded(seed: number) {
  let s = seed;
  return () => {
    s = (s * 16807) % 2147483647;
    return s / 2147483647;
  };
}

export default function OpenGraphImage() {
  const rand = seeded(42);
  const stars = Array.from({ length: 140 }, () => ({
    x: rand() * 1200,
    y: rand() * 630,
    r: 0.6 + rand() * rand() * 2.6,
    a: 0.3 + rand() * 0.7,
    warm: rand() < 0.25,
  }));
  // Orion's belt and shoulders as a small constellation accent.
  const orion = [[860, 170], [1010, 150], [905, 330], [935, 338], [965, 346], [870, 500], [1035, 480]] as const;

  return new ImageResponse(
    (
      <div
        style={{
          width: "100%",
          height: "100%",
          display: "flex",
          position: "relative",
          background: "radial-gradient(ellipse 90% 70% at 30% 0%, #1b2552 0%, #0a0f24 45%, #05070f 100%)",
          color: "#e8ecf6",
          fontFamily: "sans-serif",
        }}
      >
        {stars.map((s, i) => (
          <div
            key={i}
            style={{
              position: "absolute",
              left: s.x,
              top: s.y,
              width: s.r * 2,
              height: s.r * 2,
              borderRadius: "50%",
              background: s.warm ? "#ffd9a1" : "#eef3ff",
              opacity: s.a,
            }}
          />
        ))}
        <svg width="1200" height="630" style={{ position: "absolute", left: 0, top: 0 }}>
          {[[0, 1], [0, 2], [1, 4], [2, 3], [3, 4], [2, 5], [4, 6]].map(([a, b], i) => (
            <line key={i} x1={orion[a!]![0]} y1={orion[a!]![1]} x2={orion[b!]![0]} y2={orion[b!]![1]}
              stroke="#f5c451" strokeOpacity="0.7" strokeWidth="2" />
          ))}
          {orion.map(([x, y], i) => (
            <circle key={i} cx={x} cy={y} r={i === 0 ? 7 : 5} fill={i === 0 ? "#ffc69a" : "#dfe8ff"} />
          ))}
        </svg>
        <div style={{ display: "flex", flexDirection: "column", justifyContent: "center", padding: "0 90px", width: 760 }}>
          <div style={{ fontSize: 24, letterSpacing: 12, color: "#8b95b0" }}>ASTRAGRAPH</div>
          <div style={{ display: "flex", flexDirection: "column", fontSize: 76, lineHeight: 1.05, marginTop: 28, fontWeight: 300 }}>
            <span>Your window to</span>
            <span style={{ color: "#f5c451" }}>the night sky</span>
          </div>
          <div style={{ fontSize: 25, marginTop: 30, color: "#aab3cc" }}>
            Live camera · Time travel · Constellations · Wallpapers
          </div>
        </div>
      </div>
    ),
    size,
  );
}
