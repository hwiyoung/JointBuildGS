from pathlib import Path
import tempfile
import unittest

import numpy as np

from scripts.p2.c3_tsdf_roof_diagnostic_v1.contract import load_config, validate_config
from scripts.p2.c1_c2_oracle_c3_extract_v1.render_results import _read_binary_vertex_ply
from scripts.p2.c3_tsdf_roof_diagnostic_v1.finalize import _csv_bytes, _mesh_rows, _roofer_rows


class ContractTest(unittest.TestCase):
    def test_config_is_activated_and_bounded(self):
        result = validate_config(load_config())
        self.assertEqual(result["status"], "PASS")
        self.assertEqual(result["building_count"], 3)
        self.assertIsNone(result["scientific_verdict"])

    def test_tsdf_and_poisson_share_roof_evidence_contract(self):
        config = load_config()
        self.assertEqual(config["surface"]["semantic_roof_class"], 1)
        self.assertEqual(config["shared_view_plan"]["maximum_views_per_building"], 24)
        self.assertEqual(config["surface"]["minimum_distinct_views"], 2)
        self.assertGreaterEqual(
            config["surface"]["tsdf_truncation_m"],
            2 * config["surface"]["tsdf_voxel_m"],
        )

    def test_depth_is_only_substantive_condition_difference(self):
        left = "configs/p2/c1_c2_c3_utarget199_v1/c3_1_sem_seed0.yaml"
        right = "configs/p2/c1_c2_c3_utarget199_v1/c3_2_sem_depth_seed0_gpu0_recovery.yaml"
        from pathlib import Path
        import yaml

        a = yaml.safe_load(Path(left).read_text(encoding="utf-8"))
        b = yaml.safe_load(Path(right).read_text(encoding="utf-8"))
        ignored = {"out_dir", "load_depth", "w_depth"}
        self.assertEqual({k: v for k, v in a.items() if k not in ignored}, {k: v for k, v in b.items() if k not in ignored})
        self.assertFalse(a["load_depth"])
        self.assertTrue(b["load_depth"])
        self.assertEqual(a["w_depth"], 0.0)
        self.assertEqual(b["w_depth"], 0.03)

    def test_shared_ply_reader_preserves_ushort_field_and_stride(self):
        dtype = np.dtype([("x", "<f8"), ("view_count", "<u2")])
        rows = np.asarray([(1.25, 2), (9.5, 513)], dtype=dtype)
        header = (
            "ply\nformat binary_little_endian 1.0\n"
            "element vertex 2\nproperty double x\n"
            "property ushort view_count\nend_header\n"
        ).encode("ascii")
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "points.ply"
            path.write_bytes(header + rows.tobytes())
            loaded = _read_binary_vertex_ply(path)
            self.assertEqual(loaded.dtype.names, ("x", "view_count"))
            np.testing.assert_allclose(loaded["x"], [1.25, 9.5])
            np.testing.assert_array_equal(loaded["view_count"], [2, 513])

    def test_finalize_table_parsers_preserve_nulls_and_units(self):
        mesh = _mesh_rows([{
            "condition_id": "C3_1_SEM", "stable_id": "DEBY_LOD2_4907177", "status": "OK",
            "consensus_roof_point_count": "136", "footprint_coverage_fraction": "0.06",
            "poisson_triangle_count": "10", "poisson_component_count": "1", "poisson_largest_component_fraction": "1",
            "poisson_boundary_loop_count": "1", "poisson_hole_like_loop_count": "0", "poisson_evidence_distance_p95_m": "4.5", "poisson_far_gt_0p3m_fraction": "0.8",
            "tsdf_triangle_count": "5", "tsdf_component_count": "2", "tsdf_largest_component_fraction": "0.5",
            "tsdf_boundary_loop_count": "2", "tsdf_hole_like_loop_count": "", "tsdf_evidence_distance_p95_m": "0.25", "tsdf_far_gt_0p3m_fraction": "0",
        }])[0]
        self.assertEqual(mesh["roof_points"], 136)
        self.assertAlmostEqual(mesh["roof_coverage"], 0.06)
        self.assertIsNone(mesh["tsdf_hole_like_loops"])
        roofer = _roofer_rows([{
            "condition_id": "C3_2_SEM_DEPTH", "stable_id": "DEBY_LOD2_4907177", "status": "NOT_RUN",
            "class6_point_count": "0", "roof_surface_count": "", "assigned_point_fraction": "",
            "residual_median_m": "", "residual_p95_m": "", "small_surface_count_area_lt_1m2": "", "weak_surface_count_support_lt_100": "",
        }])[0]
        self.assertEqual(roofer["class6_points"], 0)
        self.assertIsNone(roofer["roof_surfaces"])
        csv_text = _csv_bytes([{"label": "지붕", "value": None}]).decode("utf-8")
        self.assertEqual(csv_text, "label,value\n지붕,\n")


if __name__ == "__main__":
    unittest.main()
