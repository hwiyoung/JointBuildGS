"""CPU unit tests for the S3-A semantic-addressed geometry losses.

Run in the repository container:
    python -m unittest phases/p2-gsjso/scripts/test_s3_semantic_guided_loss.py
"""
from __future__ import annotations

import json
import csv
from pathlib import Path
import tempfile
import unittest

import numpy as np
import torch

from src.stage2.loss.semantic_guided import (
    SemanticGuidedGeometry,
    SemanticRegionCache,
    class_boundary_band,
    masked_laplacian_smoothness,
    robust_plane_fit,
)


class SemanticGuidedLossTest(unittest.TestCase):
    def test_laplacian_masks_alpha_and_cutline_stencil(self):
        depth = torch.zeros(9, 9, dtype=torch.float32, requires_grad=True)
        with torch.no_grad():
            depth[4, 4] = 2.0
        alpha = torch.ones_like(depth)
        region = torch.ones(9, 9, dtype=torch.int64)
        cutline = torch.zeros(9, 9, dtype=torch.bool)

        active, stats = masked_laplacian_smoothness(
            depth, alpha, region, cutline
        )
        self.assertGreater(float(active), 0.0)
        self.assertGreater(stats["valid_stencil_count"], 0)

        alpha_invalid = alpha.clone()
        alpha_invalid[4, 4] = 0.49
        masked_alpha, _ = masked_laplacian_smoothness(
            depth, alpha_invalid, region, cutline
        )
        self.assertEqual(float(masked_alpha), 0.0)

        cut_invalid = cutline.clone()
        cut_invalid[4, 4] = True
        masked_cut, _ = masked_laplacian_smoothness(
            depth, alpha, region, cut_invalid
        )
        self.assertEqual(float(masked_cut), 0.0)

    def test_smooth_aggregate_is_sum_of_per_region_means(self):
        depth = torch.zeros(12, 24, dtype=torch.float32, requires_grad=True)
        with torch.no_grad():
            depth[5, 5] = 1.0
            depth[5, 17] = 3.0
        alpha = torch.ones_like(depth)
        cut = torch.zeros_like(depth, dtype=torch.bool)
        combined_ids = torch.zeros_like(depth, dtype=torch.int64)
        combined_ids[:, :11] = 1
        combined_ids[:, 13:] = 2

        combined, _ = masked_laplacian_smoothness(
            depth, alpha, combined_ids, cut
        )
        one_ids = torch.where(combined_ids == 1, torch.ones_like(combined_ids), 0)
        two_ids = torch.where(combined_ids == 2, torch.ones_like(combined_ids), 0)
        one, _ = masked_laplacian_smoothness(
            depth, alpha, one_ids, cut
        )
        two, _ = masked_laplacian_smoothness(
            depth, alpha, two_ids, cut
        )
        self.assertTrue(torch.allclose(combined, one + two, atol=1e-7))

    def test_boundary_band_is_class_only(self):
        semantic = torch.zeros(15, 15, dtype=torch.int64)
        semantic[3:12, 3:12] = 1
        band = class_boundary_band(semantic, roof_class=1, kernel_size=5)
        self.assertTrue(bool(band[3, 7]))
        self.assertFalse(bool(band[7, 7]))
        # There is deliberately no instance/cutline argument: internal cuts
        # cannot enter L_nb's address.

    def test_boundary_band_has_true_five_pixel_width(self):
        semantic = torch.zeros(11, 12, dtype=torch.int64)
        semantic[:, 5:] = 1
        band = class_boundary_band(semantic, roof_class=1, kernel_size=5)
        active_columns = torch.where(band.any(dim=0))[0].tolist()
        self.assertEqual(active_columns, [3, 4, 5, 6, 7])

    def test_boundary_band_does_not_invent_frame_exterior(self):
        self.assertFalse(
            bool(class_boundary_band(torch.zeros(9, 9, dtype=torch.int64)).any())
        )
        self.assertFalse(
            bool(class_boundary_band(torch.ones(9, 9, dtype=torch.int64)).any())
        )
        semantic = torch.zeros(9, 9, dtype=torch.int64)
        semantic[:, :3] = 1
        band = class_boundary_band(semantic, roof_class=1, kernel_size=5)
        # The real in-frame transition is roof column 2; dilation clips at the
        # left frame edge without treating the exterior as another boundary.
        self.assertEqual(torch.where(band.any(dim=0))[0].tolist(), [0, 1, 2, 3, 4])

    def test_robust_plane_fit_free_orientation(self):
        x, y = torch.meshgrid(
            torch.linspace(-2, 2, 20), torch.linspace(-3, 3, 20), indexing="ij"
        )
        z = 1.5 + 0.2 * x - 0.4 * y
        points = torch.stack((x, y, z), dim=-1).reshape(-1, 3)
        normal, offset = robust_plane_fit(points, huber_delta=0.5, irls_iterations=5)
        residual = (points @ normal + offset).abs()
        self.assertLess(float(residual.max()), 1e-5)
        self.assertFalse(normal.requires_grad)
        self.assertFalse(offset.requires_grad)

    def test_cache_metadata_plane_refit_and_normal_mask(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            metadata = {
                "regions": {
                    "1": {
                        "building_id": "DEBY_LOD2_4907199",
                        "source_component_id": 7,
                        "source_component_pixel_count": 400,
                        "pre_split_overlap_count": 2,
                    }
                },
                "raycast_assignment_check": {
                    "primary_actual_label_source": {
                        "provenance": "actual",
                        "misassignment_rate": 0.01,
                        "misassigned_building_pixels": 1,
                        "comparable_true_roof_pixels": 100,
                    },
                    "secondary_official_v2": {
                        "provenance": "official",
                        "misassignment_rate": 0.02,
                        "misassigned_building_pixels": 2,
                        "comparable_true_roof_pixels": 100,
                    },
                },
                "cutline_half_width_px": 7,
                "source_component_min_pixels": 256,
                "connectivity": 8,
                "footprint_buffer_m": 20.0,
            }
            np.savez_compressed(
                root / "view_a.npz",
                region_ids=np.ones((20, 20), dtype=np.int32),
                cutline_mask=np.zeros((20, 20), dtype=np.uint8),
                metadata_json=np.asarray(json.dumps(metadata)),
            )
            cache = SemanticRegionCache(root)
            cache.validate_files(["view_a.jpg"])
            with self.assertRaisesRegex(ValueError, "cutline_half_width_px"):
                SemanticRegionCache(
                    root, expected_cutline_half_width_px=6
                ).get("view_a.jpg", 20, 20, "cpu")
            loss = SemanticGuidedGeometry(cache)
            depth = torch.full((20, 20), 10.0, requires_grad=True)
            alpha = torch.ones(20, 20)
            K = torch.tensor([[100.0, 0.0, 10.0], [0.0, 100.0, 10.0], [0.0, 0.0, 1.0]])
            semantic = torch.ones(20, 20, dtype=torch.int64)
            normal_target = torch.zeros(20, 20, 3)
            normal_target[..., 2] = 1.0
            normal_render = normal_target.clone().requires_grad_(True)
            normal_mask = torch.ones(20, 20, dtype=torch.bool)
            anchors = torch.zeros(20, 20, dtype=torch.bool)
            anchors[:2] = True

            r1500 = loss(
                iteration=1500,
                view_key="view_a.jpg",
                depth=depth,
                alpha=alpha,
                K=K,
                semantic=semantic,
                normal_render=normal_render,
                normal_target=normal_target,
                normal_mask=normal_mask,
                depth_anchor_mask=anchors,
            )
            self.assertEqual(r1500["region_rows"][0]["plane_fitted_iteration"], 1500)
            self.assertEqual(r1500["region_rows"][0]["building_id"], "DEBY_LOD2_4907199")
            self.assertAlmostEqual(r1500["region_rows"][0]["depth_anchor_fraction"], 0.1)
            self.assertEqual(r1500["metadata"]["cutline_half_width_px"], 7)

            r1999 = loss(
                iteration=1999,
                view_key="view_a.jpg",
                depth=depth,
                alpha=alpha,
                K=K,
                semantic=semantic,
                normal_render=normal_render,
                normal_target=normal_target,
                normal_mask=normal_mask,
            )
            self.assertEqual(r1999["region_rows"][0]["plane_fitted_iteration"], 1500)
            r2000 = loss(
                iteration=2000,
                view_key="view_a.jpg",
                depth=depth,
                alpha=alpha,
                K=K,
                semantic=semantic,
                normal_render=normal_render,
                normal_target=normal_target,
                normal_mask=normal_mask,
            )
            self.assertEqual(r2000["region_rows"][0]["plane_fitted_iteration"], 2000)

    def test_pi_audit_logs_combined_depth_gradient_by_building(self):
        from src.stage2.train import _write_semantic_geometry_audit

        with tempfile.TemporaryDirectory() as tmp:
            depth = torch.ones(4, 4, requires_grad=True)
            weighted_semdepth = (depth.square()).mean()
            zero = depth.sum() * 0.0
            result = {
                "smooth": weighted_semdepth,
                "plane": zero,
                "boundary_normal": zero,
                "region_ids": torch.ones(4, 4, dtype=torch.int64),
                "cutline_mask": torch.zeros(4, 4, dtype=torch.bool),
                "region_rows": [
                    {
                        "region_id": 1,
                        "building_id": "DEBY_LOD2_4907199",
                        "region_pixel_count": 16,
                    }
                ],
                "metadata": {},
                "smooth_valid_stencil_count": 4,
                "boundary_valid_pixel_count": 0,
                "weight_smooth": 0.25,
                "weight_plane": 0.25,
                "weight_boundary_normal": 0.01,
                "weighted_smooth": float(weighted_semdepth.detach()),
                "weighted_plane": 0.0,
            }
            positive = _write_semantic_geometry_audit(
                out_dir=Path(tmp),
                it=1500,
                view_name="view_a.jpg",
                result=result,
                weighted_semdepth=weighted_semdepth,
                weighted_boundary_normal=zero,
                depth_pred=depth,
                target_buildings={"4907199", "8568391", "8568392"},
                target_observations={"4907199": 1, "8568391": 0, "8568392": 0},
            )
            with (Path(tmp) / "audit" / "semantic_geometry.csv").open() as fh:
                row = next(csv.DictReader(fh))
            self.assertEqual(row["building_id"], "4907199")
            self.assertEqual(row["is_pi_target"], "1")
            self.assertEqual(row["denominator_role"], "audit_only")
            self.assertEqual(int(row["semdepth_depth_grad_nonzero_pixel_count"]), 16)
            self.assertGreater(float(row["semdepth_depth_grad_norm"]), 0.0)
            self.assertEqual(positive, {"4907199"})

    def test_pi_audit_reads_nested_raycast_contract(self):
        from src.stage2.train import _write_semantic_geometry_audit

        with tempfile.TemporaryDirectory() as tmp:
            depth = torch.ones(4, 4, requires_grad=True)
            weighted_semdepth = depth.mean()
            zero = depth.sum() * 0.0
            result = {
                "smooth": weighted_semdepth,
                "plane": zero,
                "boundary_normal": zero,
                "region_ids": torch.ones(4, 4, dtype=torch.int64),
                "cutline_mask": torch.zeros(4, 4, dtype=torch.bool),
                "region_rows": [{"region_id": 1, "building_id": "4907199"}],
                "metadata": {
                    "raycast_assignment_check": {
                        "primary_actual_label_source": {
                            "provenance": "actual48",
                            "misassignment_rate": 0.125,
                            "misassigned_building_pixels": 5,
                            "comparable_true_roof_pixels": 40,
                        },
                        "secondary_official_v2": {
                            "provenance": "official45p7",
                            "misassignment_rate": 0.2,
                            "misassigned_building_pixels": 8,
                            "comparable_true_roof_pixels": 40,
                        },
                    }
                },
                "smooth_valid_stencil_count": 0,
                "boundary_valid_pixel_count": 0,
                "weight_smooth": 0.25,
                "weight_plane": 0.25,
                "weight_boundary_normal": 0.01,
                "weighted_smooth": float(weighted_semdepth.detach()),
                "weighted_plane": 0.0,
            }
            _write_semantic_geometry_audit(
                out_dir=Path(tmp),
                it=1500,
                view_name="view_a.jpg",
                result=result,
                weighted_semdepth=weighted_semdepth,
                weighted_boundary_normal=zero,
                depth_pred=depth,
                target_buildings={"4907199"},
                target_observations={"4907199": 1},
            )
            with (Path(tmp) / "audit" / "semantic_geometry.csv").open() as fh:
                row = next(csv.DictReader(fh))
            self.assertEqual(row["raycast_assignment_primary_provenance"], "actual48")
            self.assertEqual(row["raycast_misassignment_numerator"], "5")
            self.assertEqual(row["raycast_misassignment_denominator"], "40")
            self.assertEqual(row["raycast_official_provenance"], "official45p7")
            self.assertEqual(row["raycast_official_misassignment_numerator"], "8")

    def test_gate_denominator_excludes_smooth_plane_detail_rows(self):
        from src.stage2.train import _write_loss_grad_audit

        class _Writer:
            def add_scalar(self, *_args, **_kwargs):
                pass

        with tempfile.TemporaryDirectory() as tmp:
            p = torch.tensor(1.0, requires_grad=True)
            _write_loss_grad_audit(
                out_dir=Path(tmp),
                writer=_Writer(),
                it=1500,
                model=None,
                params=[p],
                rowspec={
                    "base": (p, 1.0, p),
                    "semdepth": (2.0 * p, 1.0, 2.0 * p),
                },
                audit_only_rowspec={
                    "semdepth_smooth": (3.0 * p, 1.0, 3.0 * p),
                },
                total_loss=3.0 * p,
                psnr_value=20.0,
                n_primitives=1,
            )
            with (Path(tmp) / "audit" / "loss_grad_norms.csv").open() as fh:
                rows = {row["component"]: row for row in csv.DictReader(fh)}
            self.assertEqual(rows["semdepth"]["denominator_role"], "primary")
            self.assertEqual(rows["semdepth_smooth"]["denominator_role"], "audit_only")
            # Primary denominator is |1|+|2|=3.  Detail |3| is measured against
            # that denominator but is not added to it.
            self.assertAlmostEqual(float(rows["semdepth"]["grad_norm_share"]), 2.0 / 3.0)
            self.assertAlmostEqual(float(rows["semdepth_smooth"]["grad_norm_share"]), 1.0)


if __name__ == "__main__":
    unittest.main()
