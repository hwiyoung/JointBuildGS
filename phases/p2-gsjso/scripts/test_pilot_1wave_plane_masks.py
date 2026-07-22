"""CPU tests for the locked P1W 04a/04b mask producer.

Run in the repository container:
    python -m unittest phases/p2-gsjso/scripts/test_pilot_1wave_plane_masks.py
"""
from __future__ import annotations

import copy
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

import numpy as np

from src.stage2.colmap_io import Camera, Image
from src.stage2.pilot_mask_schema import (
    BinaryMaskSet,
    MaskSchemaError,
    MaskPurpose,
    MaskSource,
    sha256_file as schema_sha256_file,
    write_binary_mask_set,
)
from src.stage2.pilot_plane_mask_producer import (
    CrossViewParameters,
    LoD2TriangleScene,
    MaskProducerError,
    ViewFrame,
    _git_tracked_source_attestation,
    _tree_receipt,
    collect_runtime_attestation,
    cross_view_consistent_masks,
    fuse_vision_roof_mask,
    fetch_asset_bundle,
    load_lod2_citygml_scene,
    load_producer_lock,
    raycast_lod2_roof_bool_mask,
    sha256_file,
    triangulate_surface_polygon,
    validate_04a_04b_control_pair,
    verify_asset_receipt,
)


REPO = Path(__file__).resolve().parents[3]
LOCK = REPO / "phases/p2-gsjso/configs/pilot_1wave_mask_producer_lock.json"
ZERO_SHA = "0" * 64


def pinhole_camera(width: int = 9, height: int = 9, focal: float = 20.0) -> Camera:
    return Camera(
        id=1,
        model="PINHOLE",
        width=width,
        height=height,
        params=np.asarray([focal, focal, width / 2.0, height / 2.0]),
    )


def image_at(view_id: int, centre: tuple[float, float, float]) -> Image:
    rotation = np.eye(3)
    centre_value = np.asarray(centre, dtype=np.float64)
    return Image(
        id=view_id,
        qvec=np.asarray([1.0, 0.0, 0.0, 0.0]),
        tvec=-rotation @ centre_value,
        camera_id=1,
        name=f"view_{view_id}.png",
    )


class ProducerLockReceiptTest(unittest.TestCase):
    def test_lock_has_exact_model_cross_view_and_gt_archive_contract(self):
        lock = load_producer_lock(LOCK)
        bert = lock["runtime_assets"]["bert_base_uncased"]
        self.assertEqual(bert["repository"], "google-bert/bert-base-uncased")
        self.assertEqual(
            bert["revision"], "86b5e0934494bd15c9632b12f734a8a67f723594"
        )
        cross = lock["cross_view_consistency"]
        self.assertEqual(cross["minimum_support_views_including_source"], 2)
        self.assertEqual(cross["maximum_pose_neighbors_per_source"], 4)
        self.assertEqual(cross["maximum_optical_axis_angle_deg"], 20.0)
        self.assertEqual(cross["minimum_camera_baseline_m"], 0.5)
        self.assertEqual(cross["reprojection_mask_tolerance_px"], 3)
        self.assertIn("bool HxW mask only", lock["gt_upperbound"]["archive_contract"])

    def test_receipt_verifies_all_assets_and_detects_tamper(self):
        lock = load_producer_lock(LOCK)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            paths = {
                artifact_id: root / row["cache_relative_path"]
                for artifact_id, row in lock["runtime_assets"].items()
            }
            (paths["groundingdino_source"] / "groundingdino/config").mkdir(parents=True)
            runtime_dino = Path(lock["runtime_environment"]["groundingdino_source_root"])
            dino_config = paths["groundingdino_source"] / "groundingdino/config/GroundingDINO_SwinT_OGC.py"
            shutil.copyfile(
                runtime_dino / "groundingdino/config/GroundingDINO_SwinT_OGC.py",
                dino_config,
            )
            dino_model = paths["groundingdino_source"] / "groundingdino/models/GroundingDINO/groundingdino.py"
            dino_model.parent.mkdir(parents=True)
            shutil.copyfile(
                runtime_dino
                / "groundingdino/models/GroundingDINO/groundingdino.py",
                dino_model,
            )
            dino_tokenizer = paths["groundingdino_source"] / "groundingdino/util/get_tokenlizer.py"
            dino_tokenizer.parent.mkdir(parents=True)
            shutil.copyfile(
                runtime_dino / "groundingdino/util/get_tokenlizer.py",
                dino_tokenizer,
            )
            lock = copy.deepcopy(lock)
            (paths["segment_anything_source"] / "segment_anything").mkdir(parents=True)
            (paths["segment_anything_source"] / "segment_anything/__init__.py").write_text(
                "", encoding="utf-8"
            )
            for artifact_id in ("groundingdino_source", "segment_anything_source"):
                source = paths[artifact_id]
                subprocess.run(["git", "init", "-q", str(source)], check=True)
                subprocess.run(
                    ["git", "-C", str(source), "config", "user.name", "fixture"], check=True
                )
                subprocess.run(
                    ["git", "-C", str(source), "config", "user.email", "fixture@example.invalid"],
                    check=True,
                )
                subprocess.run(["git", "-C", str(source), "add", "."], check=True)
                subprocess.run(
                    ["git", "-C", str(source), "commit", "-q", "-m", "fixture"], check=True
                )
                revision = subprocess.run(
                    ["git", "-C", str(source), "rev-parse", "HEAD"],
                    check=True,
                    text=True,
                    capture_output=True,
                ).stdout.strip()
                lock["runtime_assets"][artifact_id]["revision"] = revision
            paths["groundingdino_swint_ogc"].parent.mkdir(parents=True, exist_ok=True)
            paths["groundingdino_swint_ogc"].write_bytes(b"dino weights fixture")
            paths["sam_vit_h"].write_bytes(b"sam weights fixture")
            paths["bert_base_uncased"].mkdir(parents=True)
            for filename in (
                "config.json",
                "tokenizer_config.json",
                "tokenizer.json",
                "vocab.txt",
                "model.safetensors",
            ):
                (paths["bert_base_uncased"] / filename).write_bytes(filename.encode())

            artifacts = {}
            for artifact_id, path in paths.items():
                locked = lock["runtime_assets"][artifact_id]
                if path.is_dir():
                    size, digest, _ = _tree_receipt(path)
                else:
                    size, digest = path.stat().st_size, sha256_file(path)
                row = {
                    "kind": locked["kind"],
                    "relative_path": path.relative_to(root).as_posix(),
                    "source": locked.get("repository", locked.get("url")),
                    "size_bytes": size,
                    "sha256": digest,
                }
                if "revision" in locked:
                    row["revision"] = locked["revision"]
                if locked["kind"] == "source_tree":
                    row["git"] = _git_tracked_source_attestation(
                        path, locked["revision"], include_root=False
                    )
                artifacts[artifact_id] = row
            receipt = {
                "schema": "jointbuildgs.pilot_1wave.mask_producer_asset_receipt.v1",
                "producer_lock_sha256": sha256_file(LOCK),
                "runtime_environment": lock["runtime_environment"],
                "runtime_attestation": collect_runtime_attestation(lock),
                "artifacts": artifacts,
            }
            receipt_path = root / "receipt.json"
            receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
            verified = verify_asset_receipt(lock, LOCK, root, receipt_path)
            self.assertEqual(set(verified), set(paths))
            # The explicit fetch path must reuse a byte-identical, receipt-verified
            # existing cache without touching the network.
            canonical_receipt = root / "asset_receipt.json"
            canonical_receipt.write_text(json.dumps(receipt), encoding="utf-8")
            reused = fetch_asset_bundle(lock, LOCK, root, REPO)
            self.assertTrue(reused["reused_existing"])
            paths["sam_vit_h"].write_bytes(b"tampered")
            with self.assertRaisesRegex(MaskProducerError, "differs from receipt"):
                verify_asset_receipt(lock, LOCK, root, receipt_path)


class CrossViewAndFusionTest(unittest.TestCase):
    def test_cross_view_requires_other_depth_consistent_view(self):
        camera = pinhole_camera()
        depth = np.full((camera.height, camera.width), 10.0, dtype=np.float32)
        source = ViewFrame("source", camera, image_at(1, (0.0, 0.0, 0.0)), depth)
        target = ViewFrame("target", camera, image_at(2, (0.5, 0.0, 0.0)), depth)
        source_mask = np.zeros(depth.shape, dtype=bool)
        target_mask = np.zeros(depth.shape, dtype=bool)
        source_mask[4, 4] = True
        target_mask[4, 3:6] = True
        result, audit = cross_view_consistent_masks(
            {"source": source, "target": target},
            {"source": source_mask, "target": target_mask},
        )
        self.assertTrue(result["source"][4, 4])
        self.assertEqual(audit["source"].eligible_neighbor_ids, ("target",))
        self.assertFalse(audit["source"].no_valid_neighbor)

        target_bad = ViewFrame(
            "target", camera, image_at(2, (0.5, 0.0, 0.0)), np.full_like(depth, 8.0)
        )
        rejected, _ = cross_view_consistent_masks(
            {"source": source, "target": target_bad},
            {"source": source_mask, "target": target_mask},
        )
        self.assertFalse(rejected["source"].any())

    def test_no_neighbor_is_inconsistent(self):
        camera = pinhole_camera()
        depth = np.full((camera.height, camera.width), 10.0, dtype=np.float32)
        frame = ViewFrame("only", camera, image_at(1, (0.0, 0.0, 0.0)), depth)
        candidate = np.zeros(depth.shape, dtype=bool)
        candidate[4, 4] = True
        result, audit = cross_view_consistent_masks(
            {"only": frame}, {"only": candidate}
        )
        self.assertFalse(result["only"].any())
        self.assertTrue(audit["only"].no_valid_neighbor)

    def test_fusion_core_fallback_and_small_footprint_retry(self):
        shape = (25, 25)
        raw = np.zeros(shape, dtype=bool)
        consistent = np.zeros(shape, dtype=bool)
        large = np.zeros(shape, dtype=bool)
        large[5:20, 5:20] = True
        small = np.zeros(shape, dtype=bool)
        small[21:24, 21:24] = True
        fused, audit = fuse_vision_roof_mask(raw, consistent, [large, small])
        self.assertTrue(fused.any())
        self.assertTrue(audit["core_only_fallback"])
        self.assertEqual(audit["core_erosion_px_used"], [1, 5])
        self.assertFalse(audit["sam_candidate_present"])


class GtRaycastAndControlledPairTest(unittest.TestCase):
    def test_citygml_loader_applies_official_geoid_coordinate_rule(self):
        fixture = """<?xml version='1.0'?>
<core:CityModel xmlns:core='urn:core' xmlns:bldg='urn:bldg' xmlns:gml='http://www.opengis.net/gml'>
  <bldg:Building gml:id='DEBY_LOD2_1'>
    <bldg:boundedBy><bldg:RoofSurface><gml:Polygon>
      <gml:exterior><gml:LinearRing><gml:posList>
        690952 5336070 550 690954 5336070 550 690954 5336072 550 690952 5336072 550 690952 5336070 550
      </gml:posList></gml:LinearRing></gml:exterior>
    </gml:Polygon></bldg:RoofSurface></bldg:boundedBy>
  </bldg:Building>
</core:CityModel>"""
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "fixture.gml"
            path.write_text(fixture, encoding="utf-8")
            scene = load_lod2_citygml_scene([path], ["1"])
        self.assertEqual(scene.selected_building_ids, ("1",))
        self.assertTrue(scene.triangle_selected_building.all())
        self.assertTrue(np.allclose(scene.triangles_local[:, :, 2], -8.3))

    def test_polygon_triangulation_preserves_citygml_hole(self):
        exterior = np.asarray(
            [[0.0, 0.0, 3.0], [10.0, 0.0, 3.0], [10.0, 10.0, 3.0], [0.0, 10.0, 3.0]]
        )
        interior = np.asarray(
            [[4.0, 4.0, 3.0], [6.0, 4.0, 3.0], [6.0, 6.0, 3.0], [4.0, 6.0, 3.0]]
        )
        triangles = triangulate_surface_polygon([exterior, interior])
        area = 0.5 * np.abs(
            np.cross(
                triangles[:, 1, :2] - triangles[:, 0, :2],
                triangles[:, 2, :2] - triangles[:, 0, :2],
            )
        ).sum()
        self.assertAlmostEqual(float(area), 96.0, places=8)

    def test_raycast_returns_only_selected_roof_bool(self):
        roof = np.asarray(
            [
                [[-2.0, -2.0, 10.0], [2.0, -2.0, 10.0], [2.0, 2.0, 10.0]],
                [[-2.0, -2.0, 10.0], [2.0, 2.0, 10.0], [-2.0, 2.0, 10.0]],
            ],
            dtype=np.float32,
        )
        scene = LoD2TriangleScene(
            triangles_local=roof,
            triangle_class=np.asarray([1, 1], dtype=np.uint8),
            triangle_selected_building=np.asarray([True, True]),
            selected_building_ids=("1",),
        )
        camera = pinhole_camera(width=9, height=9, focal=12.0)
        # 180 degrees about camera X: +camera-Z looks down world -Z.
        image = Image(
            id=1,
            qvec=np.asarray([0.0, 1.0, 0.0, 0.0]),
            tvec=np.asarray([0.0, 0.0, 20.0]),
            camera_id=1,
            name="down.png",
        )
        mask = raycast_lod2_roof_bool_mask(scene, camera, image, ray_chunk_size=20)
        self.assertEqual(mask.dtype, np.bool_)
        self.assertEqual(mask.shape, (9, 9))
        self.assertTrue(mask[4, 4])

    def test_controlled_pair_rejects_every_non_mask_difference(self):
        base = {
            "seed": 1001,
            "w_plane": 1.25,
            "plane_region_mask": {
                "source": MaskSource.VISION_GROUNDEDSAM_ROOF.value,
                "manifest_path": "a/mask_manifest.json",
                "manifest_sha256": ZERO_SHA,
            },
        }
        upper = copy.deepcopy(base)
        upper["plane_region_mask"] = {
            "source": MaskSource.LOD2_ROOFSURFACE_GT_UPPERBOUND.value,
            "manifest_path": "b/mask_manifest.json",
            "manifest_sha256": "1" * 64,
        }
        result = validate_04a_04b_control_pair(base, upper)
        self.assertEqual(len(result["controlled_pair_equal_except"]), 3)
        upper["w_plane"] = 1.30
        with self.assertRaisesRegex(MaskProducerError, "differ outside"):
            validate_04a_04b_control_pair(base, upper)

    def test_controlled_pair_checks_binary_manifest_inventory_and_no_side_channels(self):
        mask = np.zeros((5, 6), dtype=bool)
        mask[2, 3] = True
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            vision_manifest = write_binary_mask_set(
                root / "vision",
                {"v.png": mask},
                purpose=MaskPurpose.PLANE_REGION,
                source=MaskSource.VISION_GROUNDEDSAM_ROOF,
                source_disclosure="vision fixture",
                input_sha256=ZERO_SHA,
                config_sha256=ZERO_SHA,
                geometry_sha256_by_view={"v.png": ZERO_SHA},
            )
            gt_manifest = write_binary_mask_set(
                root / "gt",
                {"v.png": mask},
                purpose=MaskPurpose.PLANE_REGION,
                source=MaskSource.LOD2_ROOFSURFACE_GT_UPPERBOUND,
                source_disclosure="GT upper-bound fixture",
                input_sha256="1" * 64,
                config_sha256="1" * 64,
                geometry_sha256_by_view={"v.png": ZERO_SHA},
            )
            base = {
                "seed": 1001,
                "plane_region_mask": {
                    "source": MaskSource.VISION_GROUNDEDSAM_ROOF.value,
                    "manifest_path": str(vision_manifest),
                    "manifest_sha256": schema_sha256_file(vision_manifest),
                },
            }
            upper = copy.deepcopy(base)
            upper["plane_region_mask"] = {
                "source": MaskSource.LOD2_ROOFSURFACE_GT_UPPERBOUND.value,
                "manifest_path": str(gt_manifest),
                "manifest_sha256": schema_sha256_file(gt_manifest),
            }
            result = validate_04a_04b_control_pair(
                base, upper, repository_root=root
            )
            self.assertEqual(result["view_inventory"]["count"], 1)

    def test_gt_upperbound_archive_allows_empty_view_but_vision_does_not(self):
        empty = np.zeros((5, 6), dtype=bool)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            manifest = write_binary_mask_set(
                root / "gt_empty_view",
                {"occluded.png": empty},
                purpose=MaskPurpose.PLANE_REGION,
                source=MaskSource.LOD2_ROOFSURFACE_GT_UPPERBOUND,
                source_disclosure="GT upper-bound occluded-view fixture",
                input_sha256=ZERO_SHA,
                config_sha256=ZERO_SHA,
                geometry_sha256_by_view={"occluded.png": ZERO_SHA},
            )
            loaded = BinaryMaskSet(manifest).load("occluded.png")
            self.assertEqual(loaded.dtype, np.bool_)
            self.assertFalse(loaded.any())
            with self.assertRaisesRegex(MaskSchemaError, "empty projected mask"):
                write_binary_mask_set(
                    root / "vision_empty_view",
                    {"occluded.png": empty},
                    purpose=MaskPurpose.PLANE_REGION,
                    source=MaskSource.VISION_GROUNDEDSAM_ROOF,
                    source_disclosure="vision empty fixture",
                    input_sha256=ZERO_SHA,
                    config_sha256=ZERO_SHA,
                    geometry_sha256_by_view={"occluded.png": ZERO_SHA},
                )


if __name__ == "__main__":
    unittest.main()
