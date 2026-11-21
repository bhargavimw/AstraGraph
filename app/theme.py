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
.ag-logo {{ display: flex; align-items: center; gap: 0.7rem; margin: 0.2rem 0 0.4rem 0; }}
.ag-logo .orb {{ width: 40px; height: 40px; border-radius: 50%;
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
.ag-logo .name {{ font-family: 'Orbitron', sans-serif; font-weight: 800; font-size: 1.45rem;
  letter-spacing: 0.08em; background: linear-gradient(90deg, #fff, var(--ag-gold-soft));
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

/* ---------- comfort ---------- */
@media (prefers-reduced-motion: reduce) {{
  .ag-stars, .ag-stars::after, .ag-nebula, .ag-shooting, .ag-logo .orb, .ag-logo .orb::after {{
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


def apply_theme() -> None:
    """Inject the stylesheet and the animated sky. Call once per script run."""
    st.markdown(theme_css(), unsafe_allow_html=True)
    st.markdown(SKY_HTML, unsafe_allow_html=True)


def sidebar_logo() -> None:
    st.sidebar.markdown(LOGO_HTML, unsafe_allow_html=True)


def subtitle(text: str) -> None:
    """Muted one-line introduction under a page heading."""
    st.markdown(f'<p class="ag-subtitle">{text}</p>', unsafe_allow_html=True)
