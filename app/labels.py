"""Collision-avoiding label placement for star charts.

Stars that sit close together (Orion's belt, for example) get overlapping
names when every label goes in the same spot. :func:`place_labels` tries the
eight positions around each star and greedily picks the one whose estimated
text box overlaps least with labels already placed and with other stars.
Brighter stars are placed first, so they get the best spots.

Boxes are estimated in data units from the chart's size and font size, which
is accurate enough to separate labels without measuring rendered text.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

Point = tuple[float, float]

# Plotly textposition -> (horizontal anchor, vertical anchor) of the box
# relative to the point: -1 = box extends left/down, 0 = centred, 1 = right/up.
POSITIONS: dict[str, tuple[int, int]] = {
    "top center": (0, 1),
    "bottom center": (0, -1),
    "middle right": (1, 0),
    "middle left": (-1, 0),
    "top right": (1, 1),
    "top left": (-1, 1),
    "bottom right": (1, -1),
    "bottom left": (-1, -1),
}


@dataclass(frozen=True)
class Box:
    x0: float
    y0: float
    x1: float
    y1: float

    def overlap(self, other: "Box") -> float:
        w = min(self.x1, other.x1) - max(self.x0, other.x0)
        h = min(self.y1, other.y1) - max(self.y0, other.y0)
        return w * h if w > 0 and h > 0 else 0.0


def label_box(
    point: Point, text: str, position: str, char_w: float, line_h: float, gap: float
) -> Box:
    """Estimated rectangle a label occupies for a given Plotly textposition."""
    x, y = point
    hx, vy = POSITIONS[position]
    width = max(len(text), 1) * char_w
    if hx == 0:
        x0 = x - width / 2
    elif hx > 0:
        x0 = x + gap
    else:
        x0 = x - gap - width
    if vy == 0:
        y0 = y - line_h / 2
    elif vy > 0:
        y0 = y + gap
    else:
        y0 = y - gap - line_h
    return Box(x0, y0, x0 + width, y0 + line_h)


def label_scale(
    points: Mapping[str, Point], width_px: float, height_px: float, font_px: float,
    equal_aspect: bool = True,
) -> tuple[float, float, float]:
    """(character width, line height, gap) in data units for these points."""
    xs = [p[0] for p in points.values()]
    ys = [p[1] for p in points.values()]
    per_px_x = ((max(xs) - min(xs)) or 1.0) * 1.3 / width_px
    per_px_y = ((max(ys) - min(ys)) or 1.0) * 1.3 / height_px
    if equal_aspect:
        per_px_x = per_px_y = max(per_px_x, per_px_y)
    return 0.6 * font_px * per_px_x, 1.25 * font_px * per_px_y, 6.0 * min(per_px_x, per_px_y)


def place_labels(
    points: Mapping[str, Point],
    *,
    width_px: float = 600.0,
    height_px: float = 560.0,
    font_px: float = 12.0,
    priority: Mapping[str, float] | None = None,
    equal_aspect: bool = True,
) -> dict[str, str]:
    """Choose a Plotly ``textposition`` for each labelled point.

    Args:
        points: Label text → data coordinates of its point.
        width_px, height_px: Approximate plot area in pixels.
        font_px: Label font size in pixels.
        priority: Lower value = placed first (e.g. magnitude, so bright
            stars get first choice). Defaults to input order.
        equal_aspect: The chart locks x and y to the same scale (as star
            charts do), so one pixel covers the same distance on both axes.

    Returns:
        Label text → textposition (one of :data:`POSITIONS`).
    """
    if not points:
        return {}
    xs = [p[0] for p in points.values()]
    ys = [p[1] for p in points.values()]
    span_x = (max(xs) - min(xs)) or 1.0
    span_y = (max(ys) - min(ys)) or 1.0
    # Charts add ~15% padding around the data; convert pixels to data units.
    per_px_x = span_x * 1.3 / width_px
    per_px_y = span_y * 1.3 / height_px
    if equal_aspect:  # the tighter axis sets the scale for both
        per_px_x = per_px_y = max(per_px_x, per_px_y)
    char_w = 0.6 * font_px * per_px_x
    line_h = 1.25 * font_px * per_px_y
    gap = 6.0 * min(per_px_x, per_px_y)
    marker = 6.0 * per_px_x, 6.0 * per_px_y

    order = list(points)
    if priority is not None:
        order.sort(key=lambda name: priority.get(name, 0.0))

    star_boxes = {
        name: Box(x - marker[0], y - marker[1], x + marker[0], y + marker[1])
        for name, (x, y) in points.items()
    }
    placed: list[Box] = []
    chosen: dict[str, str] = {}
    for name in order:
        best: tuple[float, int, str] | None = None
        for rank, position in enumerate(POSITIONS):
            box = label_box(points[name], name, position, char_w, line_h, gap)
            cost = sum(box.overlap(other) for other in placed) * 4.0
            cost += sum(box.overlap(sb) for other, sb in star_boxes.items() if other != name)
            key = (cost, rank, position)  # ties: prefer the conventional order
            if best is None or key < best:
                best = key
        assert best is not None
        chosen[name] = best[2]
        placed.append(label_box(points[name], name, best[2], char_w, line_h, gap))
    return chosen
