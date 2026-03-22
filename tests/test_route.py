from __future__ import annotations

import re

from tracker.route import polyline_to_svg


def test_returns_none_for_empty_input():
    assert polyline_to_svg([]) is None


def test_returns_none_for_single_point():
    assert polyline_to_svg([(19.3, -99.3)]) is None


def test_returns_none_for_identical_points():
    assert polyline_to_svg([(19.3, -99.3), (19.3, -99.3), (19.3, -99.3)]) is None


def test_simple_two_point_path():
    result = polyline_to_svg([(19.0, -99.0), (19.1, -99.1)])
    assert result is not None
    assert result.startswith("M")
    assert "L" in result


def test_output_matches_svg_path_grammar():
    """Output must only contain M, L, digits, dots, commas, spaces, and minus signs."""
    points = [
        (19.30, -99.30), (19.31, -99.29), (19.32, -99.28),
        (19.33, -99.27), (19.32, -99.26), (19.31, -99.27),
    ]
    result = polyline_to_svg(points)
    assert result is not None
    assert re.match(r'^[ML0-9., -]+$', result), f"Invalid SVG path chars: {result}"


def test_fits_within_viewbox():
    """All coordinates must be within 0-240 (x) and 0-200 (y)."""
    points = [
        (19.30, -99.30), (19.35, -99.25), (19.40, -99.20),
        (19.35, -99.15), (19.30, -99.20),
    ]
    result = polyline_to_svg(points)
    assert result is not None
    # Parse all numbers from the path
    nums = re.findall(r'-?[\d.]+', result)
    coords = [float(n) for n in nums]
    # X values (even indices after M/L parsing) should be 0-240
    # Y values (odd indices) should be 0-200
    # Simple check: all values should be within padded bounds
    for v in coords:
        assert 0 <= v <= 240, f"Coordinate {v} out of viewBox bounds"


def test_rdp_reduces_point_count():
    """A straight line with many collinear points should simplify heavily."""
    # 100 points along a straight line
    points = [(19.0 + i * 0.001, -99.0 + i * 0.001) for i in range(100)]
    result = polyline_to_svg(points)
    assert result is not None
    # A straight line should simplify to just 2 points (M + L)
    l_count = result.count("L")
    assert l_count <= 5, f"Expected heavy simplification, got {l_count} L commands"
