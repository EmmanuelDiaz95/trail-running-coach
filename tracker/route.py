from __future__ import annotations

import math
import re
from typing import Optional

# Padding inside the 240x200 viewBox
_VIEWBOX_W = 240
_VIEWBOX_H = 200
_PAD = 10

_SVG_PATH_RE = re.compile(r'^[ML0-9., -]+$')


def _rdp(points: list[tuple[float, float]], epsilon: float) -> list[tuple[float, float]]:
    """Ramer-Douglas-Peucker line simplification."""
    if len(points) <= 2:
        return list(points)

    # Find the point with max distance from the line between first and last
    start, end = points[0], points[-1]
    max_dist = 0.0
    max_idx = 0

    dx = end[0] - start[0]
    dy = end[1] - start[1]
    line_len_sq = dx * dx + dy * dy

    for i in range(1, len(points) - 1):
        if line_len_sq == 0:
            dist = math.hypot(points[i][0] - start[0], points[i][1] - start[1])
        else:
            t = max(0, min(1, ((points[i][0] - start[0]) * dx + (points[i][1] - start[1]) * dy) / line_len_sq))
            proj_x = start[0] + t * dx
            proj_y = start[1] + t * dy
            dist = math.hypot(points[i][0] - proj_x, points[i][1] - proj_y)
        if dist > max_dist:
            max_dist = dist
            max_idx = i

    if max_dist > epsilon:
        left = _rdp(points[:max_idx + 1], epsilon)
        right = _rdp(points[max_idx:], epsilon)
        return left[:-1] + right
    else:
        return [start, end]


def polyline_to_svg(points: list[tuple[float, float]], epsilon: float = 1.5) -> Optional[str]:
    """Convert GPS (lat, lon) points to an SVG path d-attribute string.

    Returns None if fewer than 2 distinct points.
    Projection: equirectangular with cos(mid_lat) correction.
    Output fits within a 240x200 viewBox with 10px padding.
    """
    if len(points) < 2:
        return None

    # Deduplicate consecutive identical points
    deduped = [points[0]]
    for p in points[1:]:
        if p != deduped[-1]:
            deduped.append(p)
    if len(deduped) < 2:
        return None

    # Equirectangular projection: correct longitude by cos(mid_latitude)
    mid_lat = sum(p[0] for p in deduped) / len(deduped)
    cos_lat = math.cos(math.radians(mid_lat))

    projected = [(p[1] * cos_lat, -p[0]) for p in deduped]  # lon->x, -lat->y (north up)

    # Normalize to viewBox
    min_x = min(p[0] for p in projected)
    max_x = max(p[0] for p in projected)
    min_y = min(p[1] for p in projected)
    max_y = max(p[1] for p in projected)

    range_x = max_x - min_x
    range_y = max_y - min_y

    if range_x == 0 and range_y == 0:
        return None

    draw_w = _VIEWBOX_W - 2 * _PAD
    draw_h = _VIEWBOX_H - 2 * _PAD

    # Scale preserving aspect ratio
    if range_x == 0:
        scale = draw_h / range_y
    elif range_y == 0:
        scale = draw_w / range_x
    else:
        scale = min(draw_w / range_x, draw_h / range_y)

    # Center within viewBox
    scaled_w = range_x * scale
    scaled_h = range_y * scale
    offset_x = _PAD + (draw_w - scaled_w) / 2
    offset_y = _PAD + (draw_h - scaled_h) / 2

    normalized = [
        ((p[0] - min_x) * scale + offset_x, (p[1] - min_y) * scale + offset_y)
        for p in projected
    ]

    # RDP simplification (epsilon is in viewBox coordinate space)
    simplified = _rdp(normalized, epsilon)

    if len(simplified) < 2:
        return None

    # Build SVG path
    parts = [f"M{simplified[0][0]:.1f},{simplified[0][1]:.1f}"]
    for p in simplified[1:]:
        parts.append(f"L{p[0]:.1f},{p[1]:.1f}")

    path = " ".join(parts)

    # Validate output
    if not _SVG_PATH_RE.match(path):
        return None

    return path
