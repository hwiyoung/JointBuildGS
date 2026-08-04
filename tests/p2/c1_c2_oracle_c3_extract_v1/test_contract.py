from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

import numpy as np
import torch

from scripts.p2.c1_c2_oracle_c3_extract_v1.contract import (
    BuildingReference,
    classify_oracle_crop,
    display_proxy_mask,
    footprint_geojson,
    gaussian_full_ply,
    load_building_references,
    validate_config,
)


def _state() -> dict[str, torch.Tensor]:
    return {
        "means": torch.tensor([[0.0, 0.0, 1.0], [1.0, 2.0, 3.0]], dtype=torch.float32),
        "quats": torch.tensor([[1.0, 0.0, 0.0, 0.0], [1.0, 0.0, 0.0, 0.0]], dtype=torch.float32),
        "log_scales": torch.log(torch.tensor([[0.2, 0.3, 0.01], [4.0, 0.2, 0.01]], dtype=torch.float32)),
        "opacities_raw": torch.tensor([[2.0], [-3.0]], dtype=torch.float32),
        "sh0": torch.zeros((2, 1, 3), dtype=torch.float32),
        "shN": torch.zeros((2, 15, 3), dtype=torch.float32),
        "sem_logits": torch.tensor([[0.0, 3.0, 1.0, 0.0], [2.0, 0.0, 1.0, 0.0]], dtype=torch.float32),
    }


class ContractTests(unittest.TestCase):
    def test_config_discloses_oracle_and_exact_two_c3_runs(self) -> None:
        result = validate_config(require_activation=False)
        self.assertEqual(result["c1_c2_building_method_record_count"], 6)
        self.assertEqual(result["c1_c2_expected_roofer_operation_count"], 4)
        self.assertEqual(result["c1_c2_expected_alignment_failure_count"], 2)
        self.assertEqual(result["c3_completed_training_runs"], 2)
        self.assertEqual(result["c3_training_invocations_this_task"], 0)
        self.assertEqual(result["execution_authority_mode"], "DIRECT_HUMAN_INSTRUCTION_SINGLE_EXPERIMENT_HOST")
        self.assertFalse(result["write_ownership_transfer_performed"])
        self.assertIsNone(result["scientific_verdict"])

    def test_local_execution_authority_does_not_fabricate_handoff_receipts(self) -> None:
        config = json.loads(
            (Path(__file__).resolve().parents[3] / "configs/p2/c1_c2_oracle_c3_extract_v1/run_v1.json").read_text(encoding="utf-8")
        )
        authority = config["execution_authority"]
        self.assertEqual(authority["execution_host_role"], "experiment_host")
        self.assertFalse(authority["write_ownership_transfer_performed"])
        self.assertFalse(authority["two_host_receipt_required"])
        launcher = (
            Path(__file__).resolve().parents[3] / "scripts/p2/c1_c2_oracle_c3_extract_v1/run_host.sh"
        ).read_text(encoding="utf-8")
        self.assertNotIn("100-accepted.json", launcher)
        self.assertNotIn("validate_two_host_handoff.py", launcher)

    def test_groundsurface_xy_parser_does_not_substitute_roofsurface(self) -> None:
        gml = """<core:CityModel xmlns:core="core" xmlns:bldg="bldg" xmlns:gml="gml">
      <bldg:Building gml:id="DEBY_LOD2_TEST">
        <bldg:boundedBy><bldg:GroundSurface><bldg:lod2MultiSurface><gml:MultiSurface><gml:surfaceMember>
          <gml:Polygon><gml:exterior><gml:LinearRing><gml:posList srsDimension="3">0 0 10 4 0 10 4 4 10 0 4 10 0 0 10</gml:posList></gml:LinearRing></gml:exterior></gml:Polygon>
        </gml:surfaceMember></gml:MultiSurface></bldg:lod2MultiSurface></bldg:GroundSurface></bldg:boundedBy>
        <bldg:boundedBy><bldg:RoofSurface><bldg:lod2MultiSurface><gml:MultiSurface><gml:surfaceMember>
          <gml:Polygon><gml:exterior><gml:LinearRing><gml:posList srsDimension="3">0 0 20 4 0 20 4 4 22 0 4 22 0 0 20</gml:posList></gml:LinearRing></gml:exterior></gml:Polygon>
        </gml:surfaceMember></gml:MultiSurface></bldg:lod2MultiSurface></bldg:RoofSurface></bldg:boundedBy>
      </bldg:Building></core:CityModel>"""
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "test.gml"
            path.write_text(gml, encoding="utf-8")
            ref = load_building_references(path, ["DEBY_LOD2_TEST"])["DEBY_LOD2_TEST"]
        self.assertEqual(ref.footprint.area, 16.0)
        self.assertEqual(len(ref.ground_rings_xyz), 1)
        self.assertEqual(len(ref.roof_rings_xyz), 1)
        self.assertGreaterEqual(set(footprint_geojson(ref)["features"][0]["geometry"]), {"type", "coordinates"})

    def test_oracle_classification_retains_dense_plane_samples(self) -> None:
        from shapely.geometry import Polygon

        reference = BuildingReference(
            stable_id="B1",
            footprint=Polygon([(0, 0), (4, 0), (4, 4), (0, 4)]),
            ground_rings_xyz=(),
            roof_rings_xyz=(),
            surface_rings=(),
        )
        roof_xy = np.asarray([(x, y) for x in np.linspace(0.2, 3.8, 20) for y in np.linspace(0.2, 3.8, 20)])
        roof = np.column_stack((roof_xy, 10.0 + 0.1 * roof_xy[:, 0]))
        ground_xy = np.asarray([(x, y) for x in np.linspace(-3, 7, 30) for y in np.linspace(-3, 7, 30) if not (0 <= x <= 4 and 0 <= y <= 4)])
        ground = np.column_stack((ground_xy, np.zeros(len(ground_xy))))
        building, terrain, stats = classify_oracle_crop(
            np.vstack((roof, ground)),
            reference,
            crop_buffer_m=3.0,
            ground_ring_inner_buffer_m=0.5,
            minimum_building_height_m=2.5,
            ground_cell_m=1.0,
            ground_keep_above_m=0.75,
            voxel_m=0.2,
        )
        self.assertGreater(len(building), 100)
        self.assertGreater(len(terrain), 100)
        self.assertEqual(stats["local_ground_z"], 0.0)
        self.assertEqual(stats["building_class6_count"], len(building))

    def test_full_gaussian_ply_contains_native_parameters_and_proxy_is_explicit(self) -> None:
        state = _state()
        data = gaussian_full_ply(state, (690953.0, 5336071.0, 604.0))
        header = data.split(b"end_header\n", 1)[0]
        for field in (
            b"property float quat_w",
            b"property float scale_x",
            b"property float opacity",
            b"property float semantic_logit_3",
        ):
            self.assertIn(field, header)
        self.assertIn(b"element vertex 2", header)
        mask = display_proxy_mask(
            state,
            (690953.0, 5336071.0, 604.0),
            opacity_min=0.1,
            maximum_in_plane_scale_m=2.0,
            aoi_bbox=(690900.0, 5336000.0, 691100.0, 5336200.0),
        )
        self.assertEqual(mask.tolist(), [True, False])

    def test_config_forbids_wrong_reuse_paths_and_old_quad_mesh(self) -> None:
        config = json.loads(
            (Path(__file__).resolve().parents[3] / "configs/p2/c1_c2_oracle_c3_extract_v1/run_v1.json").read_text(encoding="utf-8")
        )
        text = json.dumps(config, sort_keys=True)
        self.assertNotIn("utarget199_contract_results_v1", text)
        self.assertNotIn("native_gaussian_surfel_mesh_v1", text)
        self.assertTrue(config["presentation"]["input_output_policy"].startswith("GT_GROUNDSURFACE_XY_FOOTPRINT_ONLY"))


if __name__ == "__main__":
    unittest.main()
