from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest

import numpy as np
import open3d as o3d
from shapely.geometry import box

from scripts.p2.c3_full_scene_tsdf_semantic_texture_v1.run import (
    _extract_semantic_roof,
    _write_mesh,
    load_config,
    validate_config,
)


class FullSceneTsdfSemanticTextureContractTest(unittest.TestCase):
    def test_config_is_activated_and_prohibits_reexecution(self):
        config = load_config()
        validate_config(config)
        self.assertEqual(config["scope"]["condition_ids"], ["C3_1_SEM", "C3_2_SEM_DEPTH"])
        self.assertEqual(config["render"]["maximum_views_per_building"], 24)
        self.assertEqual(config["semantic_roof_extraction"]["roof_class"], 1)
        self.assertEqual(config["execution_counters"]["expected_gs_training_invocations"], 0)
        self.assertEqual(config["execution_counters"]["expected_roofer_invocations"], 0)
        self.assertIsNone(config["scientific_verdict"])

    def test_full_scene_tsdf_precedes_semantic_roof_extraction(self):
        source = Path(
            "scripts/p2/c3_full_scene_tsdf_semantic_texture_v1/run.py"
        ).read_text(encoding="utf-8")
        integration = source.index("volumes[stable_id].integrate")
        extraction = source.index("_semantic_vertex_projection(", integration)
        self.assertLess(integration, extraction)
        integration_block = source[source.index("valid = (", source.index("def _render_condition")):integration]
        self.assertNotIn("roof_class", integration_block)
        self.assertNotIn("argmax", integration_block)

    def test_post_tsdf_filter_keeps_roof_and_rejects_wall(self):
        mesh = o3d.geometry.TriangleMesh(
            o3d.utility.Vector3dVector(np.asarray([
                [0.0, 0.0, 5.0], [1.0, 0.0, 5.0], [0.0, 1.0, 5.0],
                [0.0, 0.0, 3.0], [0.0, 0.0, 4.0], [0.0, 1.0, 4.0],
            ])),
            o3d.utility.Vector3iVector(np.asarray([[0, 1, 2], [3, 4, 5]])),
        )
        probability = np.zeros((6, 4), dtype=np.float64)
        probability[:, 1] = 0.9
        support = np.full(6, 3, dtype=np.uint16)
        config = load_config()
        config["semantic_roof_extraction"].update({
            "minimum_component_area_m2": 0.1,
            "minimum_height_above_ground_m": 1.0,
        })
        roof, stats = _extract_semantic_roof(
            mesh, probability, support, SimpleNamespace(footprint=box(-1, -1, 2, 2)), 0.0, config,
        )
        self.assertEqual(len(roof.triangles), 1)
        self.assertEqual(stats["roof_candidate_triangle_count_before_component_filter"], 1)

    def test_empty_mesh_has_valid_add_once_ply(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "empty.ply"
            _write_mesh(path, o3d.geometry.TriangleMesh())
            self.assertIn("element vertex 0", path.read_text(encoding="ascii"))
            with self.assertRaises(RuntimeError):
                _write_mesh(path, o3d.geometry.TriangleMesh())


if __name__ == "__main__":
    unittest.main()
