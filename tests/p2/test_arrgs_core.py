"""ARRGS core tests (CPU-only): arrangement construction, gate wiring, S5 export."""
import json
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts/p2/arrgs_v1"))

from arrangement import build_arrangement, label_cells_by_solid  # noqa: E402


def gable_planes():
    c = 1.0 / np.hypot(6, 4.0)
    nL = np.array([0.0, -4 * c, 6 * c]); nL /= np.linalg.norm(nL)
    nR = np.array([0.0, 4 * c, 6 * c]); nR /= np.linalg.norm(nR)
    planes = [
        {"id": "roofL", "n": list(nL), "d": float(nL @ [0, 0, 6.0]), "source": "gt", "prior": None},
        {"id": "roofR", "n": list(nR), "d": float(nR @ [0, 12, 6.0]), "source": "gt", "prior": None},
    ]
    fp = [(0, 0), (20, 0), (20, 12), (0, 12)]
    for i, (a, b) in enumerate(zip(fp, fp[1:] + fp[:1])):
        e = np.array([b[0] - a[0], b[1] - a[1], 0.0])
        n = np.array([e[1], -e[0], 0.0]); n /= np.linalg.norm(n)
        planes.append({"id": f"wall{i}", "n": list(n), "d": float(n[:2] @ np.asarray(a)),
                       "source": "footprint", "prior": None})
    return planes, fp


class TestArrangement(unittest.TestCase):
    def setUp(self):
        self.planes, self.fp = gable_planes()
        self.arr = build_arrangement(self.planes, self.fp, 0.0, 13.0, margin=1.5)

    def test_counts_sane(self):
        cells = self.arr["cells"]
        free = [c for c in cells if c["fixed"] is None]
        self.assertGreater(len(free), 2)
        self.assertLess(len(cells), 200)
        self.assertGreater(len(self.arr["faces"]), 10)

    def test_faces_pair_opposite_sides(self):
        cells = self.arr["cells"]
        for f in self.arr["faces"]:
            if f["cell_b"] < 0:
                continue
            n, d = np.asarray(f["n"]), f["d"]
            sa = np.asarray(cells[f["cell_a"]]["centroid"]) @ n - d
            sb = np.asarray(cells[f["cell_b"]]["centroid"]) @ n - d
            self.assertLess(sa, 0.0)
            self.assertGreater(sb, 0.0)

    def test_outside_footprint_fixed_empty(self):
        from shapely.geometry import Point, Polygon
        poly = Polygon(self.fp)
        for c in self.arr["cells"]:
            inside = poly.contains(Point(c["centroid"][0], c["centroid"][1]))
            if not inside:
                self.assertEqual(c["fixed"], 0.0)

    def test_gt_labels_gable(self):
        def inside(p):
            if not (0 <= p[0] <= 20 and 0 <= p[1] <= 12):
                return False
            top = 6.0 + 4.0 * (1 - abs(p[1] - 6.0) / 6.0)
            return 0 <= p[2] <= top
        labels = label_cells_by_solid(self.arr, inside)
        solid_free = [c for c, l in zip(self.arr["cells"], labels)
                      if l > 0.5 and c["fixed"] is None]
        self.assertGreater(len(solid_free), 0)

    def test_nonfinite_plane_rejected(self):
        bad = self.planes + [{"id": "bad", "n": [float("nan"), 0, 1], "d": 1.0,
                              "source": "x", "prior": None}]
        with self.assertRaises(ValueError):
            build_arrangement(bad, self.fp, 0.0, 13.0)


class TestGateAndExport(unittest.TestCase):
    def test_face_gate_and_obj(self):
        import torch  # noqa: F401
        from arrgs_model import ArrgsModel, seed_faces
        from arrgs_train import export_obj, solid_boundary_faces
        planes, fp = gable_planes()
        arr = build_arrangement(planes, fp, 0.0, 13.0, margin=1.5)
        for c in arr["cells"]:
            if c["fixed"] is None:
                c["o_init"] = 0.8
        seeds = seed_faces(arr, target_total=400)
        model = ArrgsModel(arr, planes, seeds, device="cpu")
        v, oa, ob = model.face_gate()
        self.assertEqual(len(v), len(seeds["renderable_faces"]))
        self.assertTrue((v >= 0).all() and (v <= 1).all())
        # boundary faces vs fixed-empty neighbours must be visible at o=0.8
        self.assertGreater(float(v.max()), 0.7)
        # smooth prior loss is finite at the init point (acos regression guard)
        for p in planes[:2]:
            p["prior"] = {"n0": p["n"], "d0": p["d"], "w": 1.0}
        model2 = ArrgsModel(arr, planes, seeds, device="cpu")
        loss = model2.prior_loss()
        loss.backward()
        self.assertTrue(bool(np.isfinite(float(loss))))
        self.assertTrue(bool(np.isfinite(model2.plane_n_raw.grad.numpy()).all()))
        # S5 export writes a grouped OBJ
        o_hard = [1.0 if c["fixed"] is None else 0.0 for c in arr["cells"]]
        faces_solid = solid_boundary_faces(arr, o_hard)
        with tempfile.TemporaryDirectory() as td:
            counts = export_obj(faces_solid, Path(td) / "t.obj", 0.0)
            txt = (Path(td) / "t.obj").read_text()
        self.assertIn("g roof", txt)
        self.assertGreater(counts["roof"], 0)
        self.assertGreater(counts["wall"], 0)


if __name__ == "__main__":
    unittest.main()
