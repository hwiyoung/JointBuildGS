#!/usr/bin/env python3
"""Unit tests for actual-XYZ TIN support-boundary extraction."""
from __future__ import annotations

import importlib.util
import inspect
from pathlib import Path
import sys
import unittest
from unittest import mock

import numpy as np


REPO = Path(__file__).resolve().parents[2]
MODULE_PATH = (
    REPO
    / "phases/p2-gsjso/scripts/fusion_w1/roof_boundary_overlay.py"
)
SPEC = importlib.util.spec_from_file_location("roof_boundary_overlay", MODULE_PATH)
if SPEC is None or SPEC.loader is None:  # pragma: no cover
    raise RuntimeError(f"cannot import {MODULE_PATH}")
overlay = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = overlay
SPEC.loader.exec_module(overlay)


def build(points: np.ndarray, maximum_edge: float = 1.5) -> overlay.RoofBoundary:
    return overlay.build_roof_boundary(
        points,
        maximum_xy_edge_m=maximum_edge,
        maximum_slope_deg=75.0,
        minimum_xy_triangle_area_m2=0.01,
    )


class RoofBoundaryOverlayTests(unittest.TestCase):
    def test_sloped_roof_preserves_actual_vertex_z(self) -> None:
        points = np.asarray(
            [
                [0.0, 0.0, 10.0],
                [1.0, 0.0, 10.4],
                [1.0, 1.0, 10.6],
                [0.0, 1.0, 10.2],
            ],
            dtype=np.float64,
        )
        result = build(points)

        self.assertEqual(result.boundary_segments_xyz.shape, (4, 2, 3))
        self.assertEqual(len(result.components), 1)
        self.assertGreater(float(np.ptp(result.boundary_segments_xyz[..., 2])), 0.5)
        expected_z = {(float(x), float(y)): float(z) for x, y, z in points}
        for endpoint in result.boundary_segments_xyz.reshape(-1, 3):
            self.assertAlmostEqual(
                float(endpoint[2]), expected_z[(float(endpoint[0]), float(endpoint[1]))]
            )
        self.assertFalse(result.boundary_segments_xyz.flags.writeable)

    def test_separated_components_do_not_gain_convex_hull_bridges(self) -> None:
        left = np.asarray(
            [[0.0, 0.0, 5.0], [1.0, 0.0, 5.0], [1.0, 1.0, 5.0], [0.0, 1.0, 5.0]]
        )
        right = np.asarray(
            [[4.0, 0.0, 6.0], [5.0, 0.0, 6.0], [5.0, 1.0, 6.0], [4.0, 1.0, 6.0]]
        )
        result = build(np.vstack((left, right)), maximum_edge=1.5)

        self.assertEqual(len(result.components), 2)
        self.assertEqual(result.tin_stats["boundary_components_n"], 2)
        for segment in result.boundary_segments_xyz:
            self.assertLessEqual(abs(float(segment[1, 0] - segment[0, 0])), 1.5)
        component_x_ranges = sorted(
            (
                float(component.segments_xyz[..., 0].min()),
                float(component.segments_xyz[..., 0].max()),
            )
            for component in result.components
        )
        self.assertEqual(component_x_ranges, [(0.0, 1.0), (4.0, 5.0)])

    def test_public_builder_reuses_v1_tin_without_forbidden_inputs(self) -> None:
        parameters = inspect.signature(overlay.build_roof_boundary).parameters
        self.assertEqual(
            list(parameters),
            [
                "points_xyz",
                "maximum_xy_edge_m",
                "maximum_slope_deg",
                "minimum_xy_triangle_area_m2",
            ],
        )
        forbidden_tokens = ("gt", "gml", "cityjson", "reference", "mask", "m_j")
        self.assertFalse(
            any(token in name.lower() for name in parameters for token in forbidden_tokens)
        )
        points = np.asarray(
            [[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, 1.0, 0.0]]
        )
        with mock.patch.object(
            overlay.V1, "build_tin", wraps=overlay.V1.build_tin
        ) as locked_builder:
            build(points)
        locked_builder.assert_called_once()
        with self.assertRaises(TypeError):
            overlay.build_roof_boundary(
                points,
                maximum_xy_edge_m=1.5,
                maximum_slope_deg=75.0,
                minimum_xy_triangle_area_m2=0.01,
                cityjson={"forbidden": True},
            )

    def test_nonfinite_xyz_fails_closed_before_tin_construction(self) -> None:
        points = np.asarray(
            [[0.0, 0.0, 0.0], [1.0, 0.0, np.nan], [0.0, 1.0, 0.0]]
        )
        with mock.patch.object(overlay.V1, "build_tin") as locked_builder:
            with self.assertRaisesRegex(overlay.RoofBoundaryError, "finite"):
                build(points)
        locked_builder.assert_not_called()


if __name__ == "__main__":
    unittest.main(verbosity=2)
