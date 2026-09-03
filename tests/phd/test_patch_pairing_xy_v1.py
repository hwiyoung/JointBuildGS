from __future__ import annotations

import unittest

import numpy as np

from scripts.phd.patch_pairing_xy_v1 import run as px
from scripts.phd.surface_patch_rg_v1 import run as rg


ALG = {"cell_size_m": 0.5, "min_points_per_cell_patch": 2, "layer_gap_m": 1.0, "wall_tilt_deg": 70.0, "wall_partner_min_tilt_deg": 30.0,
       "wall_pair_distance_m": 1.0, "wall_pair_min_fraction": 0.3, "same_surface_tolerance_m": 0.3, "min_cells_per_patch_pair": 4}
DOM = {"x": [-1, 21], "y": [-1, 21], "z": [-1, 12]}


def grid(x0, x1, y0, y1, z, s, hole=None):
    xs, ys = np.meshgrid(np.arange(x0, x1, s), np.arange(y0, y1, s), indexing="ij")
    pts = np.column_stack((xs.ravel(), ys.ravel(), np.full(xs.size, float(z))))
    if hole:
        keep = ~((pts[:, 0] >= hole[0]) & (pts[:, 0] < hole[1]) & (pts[:, 1] >= hole[2]) & (pts[:, 1] < hole[3]))
        pts = pts[keep]
    return pts


def wall(x, y0, y1, z0, z1, s):
    ys, zs = np.meshgrid(np.arange(y0, y1, s), np.arange(z0, z1, s), indexing="ij")
    return np.column_stack((np.full(ys.size, float(x)), ys.ravel(), zs.ravel()))


def make(points_by_patch, types, tilts, kinds):
    """Build per-point/patch arrays directly (patch ids 1..n)."""
    pts = np.concatenate(points_by_patch)
    per_point = np.zeros(len(pts), dtype=rg.POINT_DTYPE)
    per_point["patch_id"] = np.concatenate([np.full(len(p), i + 1) for i, p in enumerate(points_by_patch)])
    patches = np.zeros(len(points_by_patch), dtype=rg.PATCH_DTYPE)
    patches["patch_id"] = np.arange(1, len(points_by_patch) + 1)
    patches["type"] = types; patches["tilt_from_up_deg"] = tilts; patches["kind"] = kinds
    patches["point_count"] = [len(p) for p in points_by_patch]
    return pts, per_point, patches


class PairingXYTest(unittest.TestCase):
    def test_states_compatible_prior_above_prior_only_current_only(self):
        # MVS: ground everywhere except x>=16 (MVS hole), plus a new car roof at [2,4]x[2,4] z=1.5
        mvs = make([grid(0, 16, 0, 20, 0.0, 0.25), grid(2, 4, 2, 4, 1.5, 0.25)], [1, 1], [0, 0], [1, 1])
        # ALS: ground everywhere except x<2 (ALS gap), old shed roof at [8,12]x[8,12] z=2.5
        als = make([grid(2, 20, 0, 20, 0.05, 0.25, hole=(8, 12, 8, 12)), grid(8, 12, 8, 12, 2.5, 0.25)], [1, 1], [0, 20], [1, 1])  # ~4 pts per 0.5 m cell like real ALS (5.5)
        res = px.run_pairing({"mvs": mvs[0], "als": als[0]}, {"mvs": mvs[1], "als": als[1]}, {"mvs": mvs[2], "als": als[2]}, DOM, ALG)
        cells = res["cells"]; top = cells[cells["layer"] == 0]
        def state_at(x, y):
            ix, iy = int((x - DOM["x"][0]) / 0.5), int((y - DOM["y"][0]) / 0.5)
            row = top[(top["ix"] == ix) & (top["iy"] == iy)]
            return int(row["state"][0]) if len(row) else None
        self.assertEqual(state_at(6, 6), px.STATE_COMPATIBLE)
        self.assertEqual(state_at(10, 10), px.STATE_PRIOR_ABOVE)      # shed roof (2022) over ground (2024)
        self.assertEqual(state_at(3, 3), px.STATE_CURRENT_ABOVE)      # car (2024) over ground (2022)
        self.assertEqual(state_at(18, 10), px.STATE_PRIOR_ONLY)       # MVS hole
        self.assertEqual(state_at(1, 10), px.STATE_CURRENT_ONLY)      # ALS gap
        pairs = res["pairs"]
        shed = pairs[(pairs["als_patch"] == 2)]
        self.assertEqual(len(shed), 1); self.assertEqual(int(shed["state"][0]), px.STATE_PRIOR_ABOVE)
        self.assertAlmostEqual(float(shed["dz_median_m"][0]), 2.5, delta=0.05)
        self.assertEqual(res["accounting"]["state_area_m2_top"]["EMPTY"] if "EMPTY" in res["accounting"]["state_area_m2_top"] else 0, 0)

    def test_second_layer_and_wall_exception(self):
        # both sources: ground + a tree canopy cluster above it -> bottom layer pair exists; MVS wall excluded from columns
        canopy_m = np.column_stack((np.random.default_rng(0).uniform(5, 9, (600, 2)), np.random.default_rng(1).uniform(3, 6, 600)))
        canopy_a = np.column_stack((np.random.default_rng(2).uniform(5, 9, (400, 2)), np.random.default_rng(3).uniform(3, 6, 400)))
        mvs = make([grid(0, 12, 0, 12, 0.0, 0.25), canopy_m, wall(10.0, 2, 8, 0, 4, 0.2)], [1, 3, 1], [0, 0, 89], [1, 2, 1])
        als = make([grid(0, 12, 0, 12, 0.05, 0.25), canopy_a], [1, 3], [0, 0], [1, 2])
        res = px.run_pairing({"mvs": mvs[0], "als": als[0]}, {"mvs": mvs[1], "als": als[1]}, {"mvs": mvs[2], "als": als[2]}, DOM, ALG)
        cells = res["cells"]
        self.assertGreater(int(np.count_nonzero(cells["layer"] == 1)), 10)
        bottom = cells[cells["layer"] == 1]
        self.assertTrue(np.all(bottom["state"] == px.STATE_COMPATIBLE))
        top_under_tree = cells[(cells["layer"] == 0) & (cells["ix"] == int((7 - DOM["x"][0]) / 0.5)) & (cells["iy"] == int((7 - DOM["y"][0]) / 0.5))]
        self.assertEqual(int(top_under_tree["rough"][0]), 1)
        walls = res["walls"]
        self.assertEqual(len(walls), 1); self.assertEqual(int(walls["wall_state"][0]), px.WALL_ONLY)  # ground at the wall foot is not a partner
        # an ALS wall at the same place pairs in 3D
        als2 = make([grid(0, 12, 0, 12, 0.05, 0.25), canopy_a, wall(10.1, 2, 8, 0, 4, 0.4)], [1, 3, 1], [0, 0, 88], [1, 2, 1])
        res2 = px.run_pairing({"mvs": mvs[0], "als": als2[0]}, {"mvs": mvs[1], "als": als2[1]}, {"mvs": mvs[2], "als": als2[2]}, DOM, ALG)
        self.assertTrue(np.all(res2["walls"]["wall_state"] == px.WALL_PAIRED))
        # the wall must not have created CURRENT_ABOVE cells along its line
        line = cells[(cells["layer"] == 0) & (cells["ix"] == int((10 - DOM["x"][0]) / 0.5))]
        self.assertTrue(np.all(line["state"] != px.STATE_CURRENT_ABOVE))

    def test_determinism_and_config(self):
        mvs = make([grid(0, 6, 0, 6, 0.0, 0.25)], [1], [0], [1]); als = make([grid(0, 6, 0, 6, 0.1, 0.25)], [1], [0], [1])
        a = px.run_pairing({"mvs": mvs[0], "als": als[0]}, {"mvs": mvs[1], "als": als[1]}, {"mvs": mvs[2], "als": als[2]}, DOM, ALG)
        b = px.run_pairing({"mvs": mvs[0], "als": als[0]}, {"mvs": mvs[1], "als": als[1]}, {"mvs": mvs[2], "als": als[2]}, DOM, ALG)
        self.assertEqual(px.array_digest(a["cells"]), px.array_digest(b["cells"]))
        cfg = px.load_config(); self.assertIsNone(cfg["scientific_verdict"]); self.assertIn("TEMPORAL_CHANGE", cfg["not_decided_here"])


if __name__ == "__main__":
    unittest.main()
