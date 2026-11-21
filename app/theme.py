"""Cosmic visual theme for the AstraGraph Streamlit app.

Adds, with CSS only (no JavaScript, so it works inside Streamlit's sandbox):

* an animated starfield behind every page — three layers of stars that drift
  at different speeds (parallax) and twinkle,
* a soft nebula glow and an occasional shooting star,
* glowing gradient headings, frosted-glass cards, alerts, tables and metrics,
* gold "starlight" buttons and a styled sidebar.

Animation is disabled for visitors whose system asks for reduced motion.
Star positions come from a fixed seed, so the sky looks the same on every run.
"""

from __future__ import annotations

import random
from functools import lru_cache

import streamlit as st

GOLD = "#ffbe28"
GOLD_SOFT = "#ffd36e"
ICE = "#9cc2ff"
VIOLET = "#9b7bff"
TEXT = "#e6ecff"
MUTED = "#8a97b8"
SKY_TOP = "#03050d"
SKY_BOTTOM = "#0b1230"

# Plot colours that sit on top of the starfield.
CHART_BG = "rgba(7, 11, 23, 0.55)"
CHART_PANEL = "rgba(13, 20, 38, 0.55)"


def _star_shadows(count: int, size_px: float, seed: int, area: int = 2000) -> str:
    """``box-shadow`` list placing ``count`` stars in an ``area``×``area`` tile."""
    rng = random.Random(seed)
    tints = ["#ffffff", "#ffffff", "#ffffff", "#cfe0ff", "#fff2d6", "#ffd9c2"]
    parts = []
    for _ in range(count):
        x, y = rng.randint(0, area), rng.randint(0, area)
        alpha = rng.uniform(0.45, 1.0)
        color = rng.choice(tints)
        r, g, b = int(color[1:3], 16), int(color[3:5], 16), int(color[5:7], 16)
        blur = size_px * (2.5 if size_px >= 2 else 1.0)
        parts.append(f"{x}px {y}px {blur:.1f}px rgba({r},{g},{b},{alpha:.2f})")
    return ", ".join(parts)


@lru_cache(maxsize=1)
def theme_css() -> str:
    """The full stylesheet (cached: star positions are generated once)."""
    small = _star_shadows(700, 1, seed=11)
    medium = _star_shadows(200, 2, seed=23)
    large = _star_shadows(70, 3, seed=37)
    return f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Orbitron:wght@600;800&family=Inter:wght@400;500;600&display=swap');

:root {{
  --ag-gold: {GOLD}; --ag-gold-soft: {GOLD_SOFT}; --ag-ice: {ICE};
  --ag-violet: {VIOLET}; --ag-text: {TEXT}; --ag-muted: {MUTED};
  --ag-glass: rgba(16, 24, 48, 0.55); --ag-glass-border: rgba(156, 194, 255, 0.16);
}}

/* ---------- sky background ---------- */
.stApp {{
  background: radial-gradient(ellipse at 20% 0%, #10183a 0%, transparent 55%),
              radial-gradient(ellipse at 85% 100%, #1a1240 0%, transparent 50%),
              linear-gradient(180deg, {SKY_TOP} 0%, {SKY_BOTTOM} 100%) !important;
  background-attachment: fixed !important;
  color: var(--ag-text);
  font-family: 'Inter', 'Segoe UI', system-ui, sans-serif;
}}
[data-testid="stAppViewContainer"], [data-testid="stMain"], [data-testid="stHeader"] {{
  background: transparent !important;
}}
.ag-sky {{ position: fixed; inset: 0; z-index: 0; pointer-events: none; overflow: hidden; }}
.ag-stars {{ position: absolute; top: 0; left: 0; border-radius: 50%; background: transparent; }}
.ag-stars::after {{ content: ""; position: absolute; top: 2000px; left: 0;
  width: inherit; height: inherit; border-radius: 50%; box-shadow: inherit; }}
.ag-stars.s1 {{ width: 1px; height: 1px; box-shadow: {small};
  animation: ag-drift 240s linear infinite, ag-twinkle 6s ease-in-out infinite; }}
.ag-stars.s2 {{ width: 2px; height: 2px; box-shadow: {medium};
  animation: ag-drift 160s linear infinite, ag-twinkle 9s ease-in-out infinite 2s; }}
.ag-stars.s3 {{ width: 3px; height: 3px; box-shadow: {large};
  animation: ag-drift 110s linear infinite, ag-twinkle 4s ease-in-out infinite 1s; }}
@keyframes ag-drift {{ from {{ transform: translateY(0); }} to {{ transform: translateY(-2000px); }} }}
@keyframes ag-twinkle {{ 0%, 100% {{ opacity: 1; }} 50% {{ opacity: 0.55; }} }}

.ag-nebula {{ position: absolute; border-radius: 50%; filter: blur(70px); opacity: 0.35;
  animation: ag-breathe 18s ease-in-out infinite; }}
.ag-nebula.n1 {{ width: 520px; height: 520px; top: -120px; right: -80px;
  background: radial-gradient(circle, rgba(155,123,255,0.55), transparent 70%); }}
.ag-nebula.n2 {{ width: 640px; height: 640px; bottom: -220px; left: 10%;
  background: radial-gradient(circle, rgba(64,140,255,0.40), transparent 70%);
  animation-delay: -9s; }}
@keyframes ag-breathe {{ 0%, 100% {{ transform: scale(1); opacity: 0.30; }}
                         50% {{ transform: scale(1.12); opacity: 0.45; }} }}

.ag-shooting {{ position: absolute; height: 2px; width: 160px; border-radius: 999px;
  background: linear-gradient(90deg, rgba(255,255,255,0.95), rgba(156,194,255,0));
  filter: drop-shadow(0 0 6px rgba(255,255,255,0.7)); opacity: 0;
  transform: rotate(-35deg); }}
.ag-shooting.m1 {{ top: 12%; left: 70%; animation: ag-shoot 11s ease-in infinite 3s; }}
.ag-shooting.m2 {{ top: 30%; left: 95%; animation: ag-shoot 17s ease-in infinite 9s; }}
.ag-shooting.m3 {{ top: 5%; left: 45%; animation: ag-shoot 23s ease-in infinite 15s; }}
@keyframes ag-shoot {{
  0% {{ opacity: 0; transform: rotate(-35deg) translateX(0); }}
  2% {{ opacity: 1; }}
  7% {{ opacity: 0; transform: rotate(-35deg) translateX(-620px); }}
  100% {{ opacity: 0; transform: rotate(-35deg) translateX(-620px); }}
}}

/* page content above the sky */
[data-testid="stMain"] .block-container, [data-testid="stSidebar"] > div {{
  position: relative; z-index: 1;
}}

/* ---------- typography ---------- */
h1, h2, [data-testid="stHeading"] h2 {{
  font-family: 'Orbitron', 'Inter', sans-serif !important; letter-spacing: 0.04em;
  background: linear-gradient(90deg, #ffffff 0%, var(--ag-gold-soft) 45%, var(--ag-ice) 100%);
  -webkit-background-clip: text; background-clip: text; color: transparent !important;
  text-shadow: 0 0 28px rgba(255, 190, 40, 0.18);
}}
h3, h4 {{ color: var(--ag-gold-soft) !important; letter-spacing: 0.02em; }}
p, li, label, .stMarkdown {{ color: var(--ag-text); }}
[data-testid="stCaptionContainer"], .stCaption {{ color: var(--ag-muted) !important; }}
.ag-subtitle {{ color: var(--ag-muted); font-size: 1.05rem; margin: -0.6rem 0 1.2rem 0;
  max-width: 62rem; }}

/* ---------- sidebar ---------- */
[data-testid="stSidebar"] {{
  background: linear-gradient(180deg, rgba(10,16,38,0.92), rgba(6,9,22,0.96)) !important;
  border-right: 1px solid var(--ag-glass-border);
  backdrop-filter: blur(8px);
}}
.ag-logo {{ display: flex; align-items: center; gap: 0.8rem; margin: 0.2rem 0 0.4rem 0;
  padding-left: 10px; }}
.ag-logo .orb {{ flex: 0 0 40px; width: 40px; height: 40px; border-radius: 50%;
  background: radial-gradient(circle at 35% 30%, #fff8dc 0%, var(--ag-gold) 35%, #b8640a 75%, #3b1d00 100%);
  box-shadow: 0 0 18px rgba(255,190,40,0.65), 0 0 46px rgba(255,190,40,0.25);
  animation: ag-pulse 4s ease-in-out infinite; position: relative; }}
.ag-logo .orb::after {{ content: ""; position: absolute; inset: -9px; border-radius: 50%;
  border: 1px solid rgba(156,194,255,0.45); transform: rotateX(70deg);
  animation: ag-orbit 9s linear infinite; }}
@keyframes ag-pulse {{ 0%, 100% {{ box-shadow: 0 0 14px rgba(255,190,40,0.55), 0 0 40px rgba(255,190,40,0.2); }}
                       50% {{ box-shadow: 0 0 24px rgba(255,190,40,0.85), 0 0 60px rgba(255,190,40,0.35); }} }}
@keyframes ag-orbit {{ from {{ transform: rotateX(70deg) rotateZ(0deg); }}
                       to {{ transform: rotateX(70deg) rotateZ(360deg); }} }}
.ag-logo .name {{ font-family: 'Orbitron', sans-serif; font-weight: 800; font-size: 1.2rem;
  letter-spacing: 0.06em; white-space: nowrap; background: linear-gradient(90deg, #fff, var(--ag-gold-soft));
  -webkit-background-clip: text; background-clip: text; color: transparent; }}
.ag-tagline {{ color: var(--ag-muted); font-size: 0.85rem; margin-bottom: 0.8rem; }}

/* ---------- glass surfaces ---------- */
[data-testid="stVerticalBlockBorderWrapper"]:has(> div > [data-testid="stVerticalBlock"]) {{
  border-color: var(--ag-glass-border) !important;
}}
[data-testid="stExpander"], [data-testid="stAlert"], [data-testid="stDataFrame"],
[data-testid="stMetric"], div[data-testid="stVerticalBlockBorderWrapper"][style*="border"] {{
  background: var(--ag-glass) !important; backdrop-filter: blur(10px);
  border: 1px solid var(--ag-glass-border) !important; border-radius: 14px !important;
}}
[data-testid="stMetric"] {{ padding: 0.8rem 1rem; transition: transform .25s ease, box-shadow .25s ease; }}
[data-testid="stMetric"]:hover {{ transform: translateY(-3px);
  box-shadow: 0 10px 30px rgba(0,0,0,0.35), 0 0 18px rgba(156,194,255,0.18); }}
[data-testid="stMetricValue"] {{ color: var(--ag-gold-soft) !important;
  font-family: 'Orbitron', sans-serif; text-shadow: 0 0 12px rgba(255,190,40,0.35); }}
[data-testid="stImage"] img, .js-plotly-plot, [data-testid="stPyplot"] img {{
  border-radius: 14px; box-shadow: 0 12px 40px rgba(0,0,0,0.45), 0 0 0 1px var(--ag-glass-border);
}}

/* ---------- controls ---------- */
.stButton > button, [data-testid="stBaseButton-secondary"] {{
  border-radius: 999px !important; border: 1px solid rgba(255,190,40,0.35) !important;
  background: rgba(255,190,40,0.06) !important; color: var(--ag-text) !important;
  transition: all .25s ease;
}}
.stButton > button:hover {{ border-color: var(--ag-gold) !important;
  box-shadow: 0 0 16px rgba(255,190,40,0.35); transform: translateY(-1px); }}
.stButton > button[kind="primary"], [data-testid="stBaseButton-primary"] {{
  background: linear-gradient(90deg, #ffb31a, #ffd36e) !important; color: #1b1203 !important;
  font-weight: 600 !important; border: none !important;
  box-shadow: 0 0 18px rgba(255,190,40,0.45);
}}
[data-testid="stTabs"] button[aria-selected="true"] p {{ color: var(--ag-gold) !important; }}

/* ---------- home page ---------- */
.ag-hero {{ display: grid; grid-template-columns: minmax(0, 1.4fr) minmax(0, 1fr); gap: 2rem;
  align-items: center; padding: 1.6rem 2rem; margin-bottom: 1.4rem; border-radius: 22px;
  background: linear-gradient(135deg, rgba(20,30,64,0.65), rgba(30,16,60,0.45));
  border: 1px solid var(--ag-glass-border); backdrop-filter: blur(10px);
  box-shadow: 0 20px 60px rgba(0,0,0,0.4); }}
.ag-hero .kicker {{ color: var(--ag-ice); letter-spacing: 0.25em; font-size: 0.78rem;
  text-transform: uppercase; }}
.ag-hero .title {{ font-family: 'Orbitron', sans-serif; font-weight: 800; line-height: 1.15;
  font-size: clamp(1.8rem, 3.6vw, 3rem); margin: 0.4rem 0 0.8rem 0;
  background: linear-gradient(90deg, #ffffff, var(--ag-gold-soft) 55%, var(--ag-ice));
  -webkit-background-clip: text; background-clip: text; color: transparent; }}
.ag-hero .lead {{ color: #c9d6f2; font-size: 1.05rem; max-width: 38rem; }}
.ag-orrery {{ position: relative; width: min(280px, 100%); aspect-ratio: 1; margin: 0 auto; }}
.ag-orrery .sun {{ position: absolute; inset: 41%; border-radius: 50%;
  background: radial-gradient(circle at 35% 30%, #fffbe6, var(--ag-gold) 45%, #c26a00);
  box-shadow: 0 0 30px rgba(255,190,40,0.8), 0 0 80px rgba(255,150,20,0.35);
  animation: ag-pulse 4s ease-in-out infinite; }}
.ag-orrery .ring {{ position: absolute; border-radius: 50%;
  border: 1px dashed rgba(156,194,255,0.28); animation: ag-spin linear infinite; }}
.ag-orrery .ring::after {{ content: ""; position: absolute; top: -6px; left: 50%;
  width: 12px; height: 12px; margin-left: -6px; border-radius: 50%;
  background: var(--planet, #9cc2ff); box-shadow: 0 0 12px var(--planet, #9cc2ff); }}
.ag-orrery .r1 {{ inset: 28%; animation-duration: 7s; --planet: #9cc2ff; }}
.ag-orrery .r2 {{ inset: 14%; animation-duration: 13s; --planet: #ff9f7a; }}
.ag-orrery .r3 {{ inset: 0%; animation-duration: 22s; --planet: #c7a8ff; }}
@keyframes ag-spin {{ from {{ transform: rotate(0deg); }} to {{ transform: rotate(360deg); }} }}

.ag-card {{ height: 100%; padding: 1.1rem 1.2rem 0.6rem 1.2rem; border-radius: 18px;
  background: var(--ag-glass); border: 1px solid var(--ag-glass-border);
  backdrop-filter: blur(10px); transition: transform .3s ease, box-shadow .3s ease, border-color .3s; }}
.ag-card:hover {{ transform: translateY(-4px); border-color: rgba(255,190,40,0.45);
  box-shadow: 0 16px 40px rgba(0,0,0,0.45), 0 0 24px rgba(255,190,40,0.15); }}
.ag-card .icon {{ font-size: 1.9rem; }}
.ag-card .name {{ font-family: 'Orbitron', sans-serif; font-weight: 600; color: var(--ag-gold-soft);
  margin: 0.3rem 0 0.35rem 0; letter-spacing: 0.04em; }}
.ag-card .desc {{ color: #b9c5e4; font-size: 0.92rem; min-height: 4.2em; }}

.ag-tonight {{ padding: 1.3rem 1.5rem; border-radius: 20px; margin-bottom: 1.4rem;
  background: linear-gradient(135deg, rgba(12,22,52,0.75), rgba(10,14,34,0.6));
  border: 1px solid rgba(255,190,40,0.25); backdrop-filter: blur(10px); }}
.ag-tonight .head {{ display: flex; justify-content: space-between; align-items: baseline;
  flex-wrap: wrap; gap: 0.5rem; }}
.ag-tonight .head .t {{ font-family: 'Orbitron', sans-serif; color: var(--ag-gold-soft);
  font-size: 1.25rem; letter-spacing: 0.05em; }}
.ag-tonight .head .where {{ color: var(--ag-muted); font-size: 0.9rem; }}
.ag-tonight .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(190px, 1fr));
  gap: 0.9rem; margin-top: 0.9rem; }}
.ag-stat {{ background: rgba(255,255,255,0.03); border: 1px solid rgba(156,194,255,0.12);
  border-radius: 14px; padding: 0.75rem 0.9rem; }}
.ag-stat .k {{ color: var(--ag-muted); font-size: 0.78rem; text-transform: uppercase;
  letter-spacing: 0.12em; }}
.ag-stat .v {{ color: #fff; font-size: 1.15rem; font-weight: 600; margin-top: 0.15rem; }}
.ag-stat .s {{ color: #b9c5e4; font-size: 0.86rem; margin-top: 0.15rem; }}
.ag-chips {{ display: flex; flex-wrap: wrap; gap: 0.45rem; margin-top: 0.9rem; }}
.ag-chip {{ padding: 0.25rem 0.7rem; border-radius: 999px; font-size: 0.85rem;
  background: rgba(156,194,255,0.10); border: 1px solid rgba(156,194,255,0.25); color: #dbe5ff; }}
.ag-chip.gold {{ background: rgba(255,190,40,0.12); border-color: rgba(255,190,40,0.45);
  color: var(--ag-gold-soft); }}
@media (max-width: 760px) {{
  .ag-hero {{ grid-template-columns: 1fr; padding: 1.2rem; }}
  .ag-orrery {{ width: 180px; }}
}}

/* ---------- quiz starburst ---------- */
.ag-burst {{ position: fixed; left: 50%; top: 45%; width: 0; height: 0; z-index: 9999;
  pointer-events: none; }}
.ag-burst span {{ position: absolute; left: 0; top: 0; width: 6px; height: 6px; border-radius: 50%;
  background: var(--ag-gold); box-shadow: 0 0 12px var(--ag-gold), 0 0 24px rgba(255,190,40,0.6);
  transform: rotate(var(--a)) translateX(0); opacity: 0;
  animation: ag-burst 1.6s cubic-bezier(.15,.7,.3,1) forwards; animation-delay: var(--d); }}
.ag-burst span:nth-child(3n) {{ background: #9cc2ff; box-shadow: 0 0 12px #9cc2ff; }}
.ag-burst span:nth-child(4n) {{ background: #ffffff; box-shadow: 0 0 12px #ffffff; }}
.ag-burst .core {{ position: absolute; left: -60px; top: -60px; width: 120px; height: 120px;
  border-radius: 50%; background: radial-gradient(circle, rgba(255,240,200,0.9), rgba(255,190,40,0) 70%);
  animation: ag-flash 1.2s ease-out forwards; opacity: 0; }}
@keyframes ag-burst {{
  0% {{ opacity: 1; transform: rotate(var(--a)) translateX(0) scale(1.4); }}
  80% {{ opacity: 1; }}
  100% {{ opacity: 0; transform: rotate(var(--a)) translateX(var(--r)) scale(0.4); }} }}
@keyframes ag-flash {{ 0% {{ opacity: 0.95; transform: scale(0.3); }}
                       100% {{ opacity: 0; transform: scale(3); }} }}

/* ---------- comfort ---------- */
@media (prefers-reduced-motion: reduce) {{
  .ag-stars, .ag-stars::after, .ag-nebula, .ag-shooting, .ag-logo .orb, .ag-logo .orb::after,
  .ag-orrery .sun, .ag-orrery .ring, .ag-burst span, .ag-burst .core {{
    animation: none !important; }}
  .ag-shooting {{ display: none; }}
}}
@media (max-width: 640px) {{
  .ag-nebula {{ display: none; }}
  h1, h2, [data-testid="stHeading"] h2 {{ letter-spacing: 0.01em; }}
}}
</style>
"""


SKY_HTML = """
<div class="ag-sky" aria-hidden="true">
  <div class="ag-nebula n1"></div><div class="ag-nebula n2"></div>
  <div class="ag-stars s1"></div><div class="ag-stars s2"></div><div class="ag-stars s3"></div>
  <div class="ag-shooting m1"></div><div class="ag-shooting m2"></div>
  <div class="ag-shooting m3"></div>
</div>
"""

LOGO_HTML = """
<div class="ag-logo"><div class="orb"></div><div class="name">ASTRAGRAPH</div></div>
<div class="ag-tagline">Learn &amp; explore the night sky</div>
"""


def _starburst_html(rays: int = 36, seed: int = 5) -> str:
    rng = random.Random(seed)
    spans = "".join(
        f'<span style="--a:{i * 360 / rays + rng.uniform(-4, 4):.1f}deg;'
        f'--r:{rng.randint(160, 340)}px;--d:{rng.uniform(0, 0.25):.2f}s"></span>'
        for i in range(rays)
    )
    return f'<div class="ag-burst" aria-hidden="true"><div class="core"></div>{spans}</div>'


STARBURST_HTML = _starburst_html()


def apply_theme() -> None:
    """Inject the stylesheet and the animated sky. Call once per script run."""
    st.markdown(theme_css(), unsafe_allow_html=True)
    st.markdown(SKY_HTML, unsafe_allow_html=True)


def sidebar_logo() -> None:
    st.sidebar.markdown(LOGO_HTML, unsafe_allow_html=True)


def subtitle(text: str) -> None:
    """Muted one-line introduction under a page heading."""
    st.markdown(f'<p class="ag-subtitle">{text}</p>', unsafe_allow_html=True)


def html(markup: str) -> None:
    """Render trusted, app-generated HTML."""
    st.markdown(markup, unsafe_allow_html=True)
