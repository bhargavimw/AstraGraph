"""Interactive, animated sky chart (Plotly).

The chart is a planisphere: zenith in the centre, horizon on the rim, north
up and east on the left (as seen looking up). Every half hour across a
24-hour window is precomputed as an animation frame, so pressing ▶ plays the
turning sky smoothly in the browser without re-running the app. Hovering a
star shows its name, brightness and position.
"""

from __future__ import annotations

import sys
from collections.abc import Sequence
from datetime import datetime, timedelta, tzinfo
from pathlib import Path

import numpy as np
import plotly.graph_objects as go

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from astragraph.constellation_db import ConstellationDB  # noqa: E402
from astragraph.world_model import SkyWorldModel  # noqa: E402

GOLD = "#ffbe28"
LINE = "rgba(127, 168, 255, 0.85)"
LABEL = "#c9d6f2"
DEFAULT_HOURS = tuple(float(h) for h in np.arange(-12.0, 12.01, 0.5))


def _frame_traces(
    model: SkyWorldModel,
    db: ConstellationDB,
    moment: datetime,
    lat: float,
    lon: float,
    highlight: str | None,
) -> list[go.Scatterpolar]:
    """The four traces of one frame: stars, lines, highlighted lines, labels."""
    stars = [s for s in model.get_all_stars(moment, lat, lon) if s.altitude > 0]
    star_trace = go.Scatterpolar(
        r=[round(90 - s.altitude, 2) for s in stars],
        theta=[round(s.azimuth, 2) for s in stars],
        mode="markers",
        marker=dict(
            size=[round(max(3.0, 13 - 3.2 * s.magnitude), 1) for s in stars],
            color=["#fff2d6" if s.magnitude < 1 else "#f5f8ff" for s in stars],
            line=dict(width=0),
            opacity=0.95,
        ),
        customdata=[[s.name, s.magnitude, s.altitude, s.azimuth,
                     model.constellation_name(s.constellation)] for s in stars],
        hovertemplate=("<b>%{customdata[0]}</b><br>%{customdata[4]}"
                       "<br>magnitude %{customdata[1]:.2f}"
                       "<br>altitude %{customdata[2]:.0f}°, azimuth %{customdata[3]:.0f}°"
                       "<extra></extra>"),
        name="stars",
        showlegend=False,
    )

    lines: dict[bool, tuple[list, list]] = {False: ([], []), True: ([], [])}
    label_r, label_theta, label_text, label_color = [], [], [], []
    for name in db.list_constellations():
        graph = db[name]
        nodes = list(graph.nodes)
        pos = dict(zip(nodes, model.altaz_many(
            [graph.nodes[n]["ra"] for n in nodes], [graph.nodes[n]["dec"] for n in nodes],
            moment, lat, lon)))
        is_highlight = name == highlight
        rs, thetas = lines[is_highlight]
        for a, b in graph.edges:
            (az1, alt1), (az2, alt2) = pos[a], pos[b]
            if alt1 > 0 and alt2 > 0:
                rs += [round(90 - alt1, 2), round(90 - alt2, 2), None]
                thetas += [round(az1, 2), round(az2, 2), None]
        up = [(az, alt) for az, alt in pos.values() if alt > 0]
        if len(up) >= len(nodes) / 2:
            az, alt = max(up, key=lambda p: p[1])
            label_r.append(round(max(90 - alt - 4, 0), 2))
            label_theta.append(round(az, 2))
            label_text.append(name)
            label_color.append(GOLD if is_highlight else LABEL)

    def line_trace(highlighted: bool) -> go.Scatterpolar:
        rs, thetas = lines[highlighted]
        return go.Scatterpolar(
            r=rs or [None], theta=thetas or [None], mode="lines", hoverinfo="skip",
            line=dict(color=GOLD if highlighted else LINE, width=3 if highlighted else 1.4),
            showlegend=False,
        )

    labels = go.Scatterpolar(
        r=label_r or [None], theta=label_theta or [None], mode="text",
        text=label_text, textfont=dict(color=label_color or [LABEL], size=12),
        hoverinfo="skip", showlegend=False,
    )
    return [line_trace(False), line_trace(True), star_trace, labels]


def animated_sky_chart(
    model: SkyWorldModel,
    db: ConstellationDB,
    start: datetime,
    lat: float,
    lon: float,
    tz: tzinfo,
    *,
    hours: Sequence[float] = DEFAULT_HOURS,
    initial_hours: float = 0.0,
    highlight: str | None = None,
    height: int = 640,
) -> go.Figure:
    """Planisphere with one animation frame per entry of ``hours``."""
    if not hours:
        raise ValueError("Need at least one time step")
    initial_index = int(np.argmin([abs(h - initial_hours) for h in hours]))
    frames = []
    for h in hours:
        moment = start + timedelta(hours=h)
        frames.append(go.Frame(
            data=_frame_traces(model, db, moment, lat, lon, highlight),
            name=f"{h:+.1f}",
        ))
    labels = [(start + timedelta(hours=h)).astimezone(tz).strftime("%H:%M") for h in hours]

    # Plotly plays frames in list order and, before any interaction, starts at
    # the first one. Rotating the list to begin at the opening time makes ▶ Play
    # run forward from there (looping round the 24 h); the slider keeps
    # chronological order because its steps name frames explicitly.
    ordered = frames[initial_index:] + frames[:initial_index]
    fig = go.Figure(data=frames[initial_index].data, frames=ordered)
    play = dict(frame=dict(duration=280, redraw=True), transition=dict(duration=0),
                fromcurrent=True, mode="immediate")
    fig.update_layout(
        height=height,
        paper_bgcolor="rgba(0,0,0,0)",
        font=dict(color=LABEL),
        margin=dict(l=20, r=20, t=30, b=40),
        polar=dict(
            bgcolor="rgba(13, 20, 38, 0.55)",
            radialaxis=dict(range=[0, 90], showticklabels=False, ticks="",
                            gridcolor="rgba(42, 58, 94, 0.8)", tickvals=[30, 60, 90]),
            angularaxis=dict(rotation=90, direction="counterclockwise",
                             tickvals=[0, 45, 90, 135, 180, 225, 270, 315],
                             ticktext=["N", "NE", "E", "SE", "S", "SW", "W", "NW"],
                             gridcolor="rgba(42, 58, 94, 0.8)",
                             linecolor="rgba(156, 194, 255, 0.4)",
                             tickfont=dict(size=13, color="#e6ecff")),
        ),
        updatemenus=[dict(
            type="buttons", direction="left", x=0.0, y=-0.02, xanchor="left", yanchor="top",
            pad=dict(r=8, t=34), showactive=False, bgcolor="rgba(255,190,40,0.15)",
            bordercolor="rgba(255,190,40,0.6)", font=dict(color="#ffd36e"),
            buttons=[
                dict(label="▶ Play", method="animate", args=[None, play]),
                dict(label="⏸ Pause", method="animate",
                     args=[[None], dict(frame=dict(duration=0, redraw=False),
                                        mode="immediate", transition=dict(duration=0))]),
            ],
        )],
        sliders=[dict(
            active=initial_index, x=0.2, y=-0.02, len=0.8, yanchor="top",
            pad=dict(t=8),
            currentvalue=dict(prefix="Local time ", xanchor="right",
                              font=dict(color=GOLD, size=14)),
            bgcolor="rgba(255,190,40,0.25)", activebgcolor=GOLD,
            bordercolor="rgba(156,194,255,0.3)", tickcolor="#8a97b8",
            font=dict(color="#8a97b8", size=10),
            steps=[dict(method="animate", label=label,
                        args=[[frame.name], dict(mode="immediate",
                                                 frame=dict(duration=0, redraw=True),
                                                 transition=dict(duration=0))])
                   for label, frame in zip(labels, frames)],
        )],
    )
    return fig


def constellation_figure(graph, name: str, *, height: int = 520) -> go.Figure:
    """Themed, hoverable stick-figure chart of one constellation.

    Stars are placed by tangent-plane projection (east left, north up, as in
    the sky), sized by brightness, and labelled without overlaps.
    """
    from astragraph.geometry import sky_to_plane
    from labels import place_labels

    names = list(graph.nodes)
    plane = sky_to_plane([graph.nodes[n]["ra"] for n in names],
                         [graph.nodes[n]["dec"] for n in names])
    pos = {n: (float(x), float(-y)) for n, (x, y) in zip(names, plane)}  # y up
    mags = {n: float(graph.nodes[n]["magnitude"]) for n in names}

    xs, ys = [], []
    for a, b in graph.edges:
        xs += [pos[a][0], pos[b][0], None]
        ys += [pos[a][1], pos[b][1], None]
    fig = go.Figure(go.Scatter(x=xs, y=ys, mode="lines", hoverinfo="skip",
                               line=dict(color="rgba(127,168,255,0.9)", width=2.5),
                               showlegend=False))
    placement = place_labels(pos, width_px=560, height_px=height, font_px=13, priority=mags)
    fig.add_trace(go.Scatter(
        x=[pos[n][0] for n in names], y=[pos[n][1] for n in names],
        mode="markers+text", text=names, textposition=[placement[n] for n in names],
        textfont=dict(color="#dbe5ff", size=13),
        marker=dict(size=[max(8.0, 26 - 5 * mags[n]) for n in names],
                    color=["#fff2d6" if mags[n] < 1 else "#f5f8ff" for n in names],
                    line=dict(width=6, color="rgba(156,194,255,0.18)")),
        customdata=[[n, graph.nodes[n].get("designation", ""), mags[n]] for n in names],
        hovertemplate=("<b>%{customdata[0]}</b><br>%{customdata[1]}"
                       "<br>magnitude %{customdata[2]:.2f}<extra></extra>"),
        showlegend=False,
    ))
    fig.update_layout(
        height=height, title=dict(text=name, x=0.5, font=dict(size=20, color="#ffd36e")),
        paper_bgcolor="rgba(7, 11, 23, 0.55)", plot_bgcolor="rgba(13, 20, 38, 0.55)",
        margin=dict(l=16, r=16, t=56, b=16), dragmode=False,
        xaxis=dict(visible=False), yaxis=dict(visible=False, scaleanchor="x"),
    )
    return fig
