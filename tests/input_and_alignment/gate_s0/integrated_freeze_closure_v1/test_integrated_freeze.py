from __future__ import annotations

import importlib.util
import json
import struct
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np


SCRIPT = Path("scripts/input_and_alignment/gate_s0/integrated_freeze_closure_v1/run_integrated_freeze.py")
SPEC = importlib.util.spec_from_file_location("integrated_freeze", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


class IntegratedFreezeUnitTests(unittest.TestCase):
    def test_epsg_transform_matches_proj_9_3_1_crosscheck(self) -> None:
        x = np.array([690791.74, 691154.65, 690953.0])
        y = np.array([5335864.05, 5336353.85, 5336071.0])
        tx, ty = MODULE.epsg32632_to_25832(x, y)
        expected_x = np.array([690791.740001741, 691154.650001744, 690953.000001742])
        expected_y = np.array([5335864.049877891, 5336353.849877889, 5336070.999877892])
        self.assertLess(float(np.max(np.abs(tx - expected_x))), 3e-4)
        self.assertLess(float(np.max(np.abs(ty - expected_y))), 3e-4)

    def test_repo_root_and_config_resolution(self) -> None:
        self.assertTrue((MODULE.REPO / ".git").is_dir())
        self.assertTrue(MODULE.CONFIG_PATH.is_file())

    def test_grid_classification_is_non_gt_min_max(self) -> None:
        grid = MODULE.GridSummary((0.0, 0.0, 2.0, 2.0), 1.0)
        grid.update(
            np.array([0.2, 0.3, 0.4, 1.2]),
            np.array([0.2, 0.3, 0.4, 1.2]),
            np.array([1.0, 4.0, 5.0, 2.0]),
            np.array([0, 0, 0, 2], dtype=np.uint8),
        )
        mask = grid.building_mask(2.5, 3)
        self.assertEqual(1, int(np.count_nonzero(mask)))
        self.assertEqual(1, int(np.sum(grid.raw_class2)))

    def test_binary_ply_is_hashed_and_processed_in_one_pass(self) -> None:
        dtype = np.dtype([("x", "<f4"), ("y", "<f4"), ("z", "<f4"), ("red", "u1"), ("green", "u1"), ("blue", "u1")])
        points = np.zeros(200, dtype=dtype)
        points["x"] = np.repeat(np.arange(10, dtype=np.float32), 20)
        points["y"] = np.tile(np.repeat(np.arange(10, dtype=np.float32), 2), 10)
        points["z"] = np.tile([0.0, 4.0], 100)
        header = (
            "ply\nformat binary_little_endian 1.0\n"
            "element vertex 200\nproperty float x\nproperty float y\nproperty float z\n"
            "property uchar red\nproperty uchar green\nproperty uchar blue\nend_header\n"
        ).encode("ascii")
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "cloud.ply"
            path.write_bytes(header + points.tobytes())
            grid = MODULE.GridSummary((100.0, 200.0, 111.0, 211.0), 1.0)
            record, gravity = MODULE.hash_ply_and_grid(path, grid, (100.0, 200.0, 0.0))
        self.assertEqual(len(header) + points.nbytes, record["bytes"])
        self.assertEqual(200, record["vertex_count"])
        self.assertGreater(gravity["terrain_cell_count"], 50)
        self.assertAlmostEqual(1.0, float(np.linalg.norm(gravity["gravity"])), places=9)

    def test_split_keeps_whole_groups(self) -> None:
        rows = [
            {"stable_id": "a", "spatial_group_id": "g1", "e_paired": "true"},
            {"stable_id": "b", "spatial_group_id": "g1", "e_paired": "true"},
            {"stable_id": "c", "spatial_group_id": "g2", "e_paired": "true"},
        ]
        assignment = MODULE.assign_splits(rows, "20260731")
        self.assertEqual({"g1", "g2"}, set(assignment))
        self.assertIn(assignment["g1"], {"development", "validation", "held_out"})

    def test_colmap_images_binary_camera_id_and_name_alignment(self) -> None:
        data = b"".join(
            [
                struct.pack("<Q", 1),
                struct.pack("<i", 7),
                struct.pack("<4d", 1.0, 0.0, 0.0, 0.0),
                struct.pack("<3d", 1.0, 2.0, 3.0),
                struct.pack("<i", 42),
                b"frame.jpg\0",
                struct.pack("<Q", 0),
            ]
        )
        parsed = MODULE.parse_colmap_images(data)
        self.assertEqual(42, parsed[0]["camera_id"])
        self.assertEqual("frame.jpg", parsed[0]["name"])

    def test_sparse_fingerprint_is_five_regular_files_and_stable(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "cameras.bin").write_bytes(struct.pack("<Q", 0))
            (root / "images.bin").write_bytes(struct.pack("<Q", 0))
            (root / "points3D.bin").write_bytes(b"points")
            (root / "project.ini").write_bytes(b"project")
            (root / "rigs.bin").write_bytes(b"rigs")
            first, _, _ = MODULE.fingerprint_sparse(root)
            second, _, _ = MODULE.fingerprint_sparse(root)
        self.assertEqual(5, first["files"])
        self.assertEqual(["cameras.bin", "images.bin", "points3D.bin", "project.ini", "rigs.bin"], [row["path"] for row in first["members"]])
        self.assertEqual(first["merkle_sha256"], second["merkle_sha256"])

    def test_partial_output_without_ledger_blocks_in_preflight(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            allowed = root / MODULE.ALLOWED_PREEXISTING_RELATIVE
            allowed.parent.mkdir(parents=True)
            allowed.write_bytes(b"accepted")
            started = root / MODULE.STARTED_RELATIVE
            started.parent.mkdir(parents=True)
            started.write_bytes(b"started")
            with self.assertRaisesRegex(RuntimeError, "partial output without completed ledger"):
                MODULE.no_repeat_preflight(root)

    def test_completed_ledger_reuse_counts_ledger_read_and_hash(self) -> None:
        data = MODULE.canonical_json_bytes({"operation_identity": {"operation_id": "op-1"}})
        receipt = MODULE.completed_ledger_reuse_receipt(data)
        self.assertEqual(len(data), receipt["ledger_lookup_bytes_read"])
        self.assertEqual(len(data), receipt["ledger_lookup_bytes_hashed"])
        self.assertEqual(0, receipt["external_scientific_payload_read_bytes"])
        self.assertEqual(0, receipt["non_ledger_output_bytes_read_or_hashed"])
        self.assertEqual(0, receipt["writes"])

    def test_candidate_identity_loader_never_returns_or_parses_bbox(self) -> None:
        path = MODULE.REPO / "docs/research/preregistration/gate_s0/remediation_r1/eligibility_funnel_v2.csv"
        stable_ids, accounting = MODULE.load_candidate_ids_after_reference_freeze(path)
        self.assertEqual(199, len(stable_ids))
        self.assertEqual(["stable_id"], accounting["parsed_columns"])
        self.assertEqual(0, accounting["lod2_bbox_columns_parsed_or_used"])
        self.assertTrue(all(item.startswith("DEBY_LOD2_") for item in stable_ids))


if __name__ == "__main__":
    unittest.main()
