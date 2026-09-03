from __future__ import annotations

import unittest

import numpy as np

from scripts.phd.surface_patch_rg_v1 import run as rg


PARAMS = {"k_neighbors": 20, "smoothness_deg": 10.0, "curvature_threshold": 0.03,
          "min_cluster_points": 30, "euclidean_tolerance_m": 0.5, "euclidean_min_points": 10}
TYPING = {"planar_max_rmse_m": 0.15, "linearity_min": 0.8}
UP = np.array([0.0, 0.0, 1.0])


def grid(x0, x1, y0, y1, z, s, hole=None):
    xs, ys = np.meshgrid(np.arange(x0, x1, s), np.arange(y0, y1, s), indexing="ij")
    pts = np.column_stack((xs.ravel(), ys.ravel(), np.full(xs.size, float(z))))
    if hole:
        keep = ~((pts[:, 0] >= hole[0]) & (pts[:, 0] < hole[1]) & (pts[:, 1] >= hole[2]) & (pts[:, 1] < hole[3]))
        pts = pts[keep]
    return pts


class SurfacePatchRGTest(unittest.TestCase):
    def test_smooth_surfaces_become_regions_curved_included(self):
        rng = np.random.default_rng(0)
        ground = grid(0, 12, 0, 12, 0.0, 0.2, hole=(4, 8, 4, 8))
        roof = grid(4, 8, 4, 8, 4.0, 0.2)
        # a curved surface (half-cylinder "tank") must also be one smooth region
        t = np.linspace(0, np.pi, 40); xs = np.arange(9, 12, 0.15)
        tank = np.array([[x, 1.5 + 1.2 * np.cos(a), 1.2 * np.sin(a)] for x in xs for a in t])
        pts = np.concatenate([ground, roof, tank]) + rng.normal(0, 0.01, (len(ground) + len(roof) + len(tank), 3))
        normals, curvature, neighbours = rg.knn_normals(pts, PARAMS["k_neighbors"])
        labels = rg.region_growing(pts, normals, curvature, neighbours, 10.0, 0.03, 30)
        for sel in (slice(0, len(ground)), slice(len(ground), len(ground) + len(roof)), slice(len(ground) + len(roof), None)):
            ids, counts = np.unique(labels[sel][labels[sel] > 0], return_counts=True)
            self.assertGreater(counts.max() / max(1, (labels[sel] > 0).sum()), 0.9)  # one dominant region each
        self.assertEqual(len(set(np.unique(labels[:len(ground)])) & set(np.unique(labels[len(ground):len(ground) + len(roof)])) - {0}), 0)

    def test_scattered_points_become_euclidean_clusters_or_noise(self):
        rng = np.random.default_rng(1)
        tree = rng.uniform([0, 0, 0], [3, 3, 4], size=(3000, 3))
        stray = np.array([[20.0, 20.0, 20.0], [30.0, 30.0, 30.0]])
        pts = np.concatenate([tree, stray])
        per_point, patches, acc = rg.segment_source(pts, PARAMS, TYPING, UP)
        self.assertEqual(acc["points_noise"], 2)
        self.assertGreater(acc["points_in_euclidean_clusters"] + acc["points_in_smooth_regions"], 2900)
        self.assertEqual(int(per_point["patch_id"][-1]), 0)

    def test_typing_planar_vs_scattered_and_determinism(self):
        rng = np.random.default_rng(2)
        pts = np.concatenate([grid(0, 6, 0, 6, 0.0, 0.2), rng.uniform([8, 0, 0], [11, 3, 3], size=(2000, 3))])
        a = rg.segment_source(pts, PARAMS, TYPING, UP)
        b = rg.segment_source(pts, PARAMS, TYPING, UP)
        self.assertEqual(rg.array_digest(a[0]), rg.array_digest(b[0]))
        patches = a[1]
        types = {int(p["type"]) for p in patches}
        self.assertIn(rg.TYPE_PLANAR, types)
        self.assertIn(rg.TYPE_SCATTERED, types)
        ground_patch = patches[patches["patch_id"] == a[0]["patch_id"][0]][0]  # patch holding the first ground point
        self.assertEqual(int(ground_patch["type"]), rg.TYPE_PLANAR)
        self.assertLess(float(ground_patch["tilt_from_up_deg"]), 5.0)
        block_labels = a[0]["patch_id"][-2000:]
        block_patch = patches[patches["patch_id"] == np.bincount(block_labels[block_labels > 0]).argmax()][0]
        self.assertEqual(int(block_patch["type"]), rg.TYPE_SCATTERED)

    def test_config_contract(self):
        cfg = rg.load_config()
        self.assertIsNone(cfg["scientific_verdict"])
        self.assertIn("CROSS_SOURCE_PAIRING", cfg["not_decided_here"])


if __name__ == "__main__":
    unittest.main()
