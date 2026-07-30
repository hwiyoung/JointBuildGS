#!/usr/bin/env python3
from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import struct
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np


REPO = Path(__file__).resolve().parents[2]
SCRIPT = (
    REPO
    / "phases/p2-gsjso/scripts/fusion_w1/fusion_w1_pose_adoption_v2_20260725.py"
)
CONFIG = (
    REPO
    / "phases/p2-gsjso/configs/fusion_w1/fusion_w1_pose_adoption_v2_20260725.json"
)
COREG = REPO / "phases/p2-gsjso/scripts/fusion_w1/fusion_w1_coreg_lock1.py"
R0_BASE_CONFIG = (
    REPO / "phases/p2-gsjso/configs/fusion_w1/fusion_w1_preflight_resume_v1.json"
)


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def write_points3d(path: Path, records):
    with path.open("wb") as handle:
        handle.write(struct.pack("<Q", len(records)))
        for point_id, xyz, rgb, error, track in records:
            handle.write(struct.pack("<Q", point_id))
            handle.write(struct.pack("<ddd", *xyz))
            handle.write(struct.pack("<BBB", *rgb))
            handle.write(struct.pack("<d", error))
            handle.write(struct.pack("<Q", len(track)))
            for image_id, point2d_index in track:
                handle.write(struct.pack("<II", image_id, point2d_index))


class PoseAdoptionV2Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.module = load_module("fusion_w1_pose_adoption_v2_test", SCRIPT)
        cls.coreg = load_module("fusion_w1_coreg_lock1_pose_test", COREG)
        cls.config = json.loads(CONFIG.read_text(encoding="utf-8"))

    def test_r0_gate_is_sha_and_commit_locked(self):
        self.assertEqual(
            self.config["required_ancestor_commit"],
            "03f6a71c883ea2bb5e371f6cb185e4d921841d8e",
        )
        self.assertEqual(
            self.config["r0_gate"]["sha256"],
            "d82bd7b824b45b5e77306bd4322fb4e96b86638a9b33d026fb740d4ade51f95e",
        )
        self.assertEqual(self.config["r0_gate"]["status"], "PASSED")

    def test_pose_consumer_manifest_contract_is_stable(self):
        outputs = self.config["outputs"]
        self.assertEqual(
            outputs["manifest"],
            "phases/p2-gsjso/runs/fusion_w1/20260724_fusion_w1/resume_v2/"
            "r1_pose_adoption_manifest.json",
        )
        self.assertEqual(
            outputs["derived_sparse"],
            "results/tum_transfer/fusion_w1_pose_adoption_v2/"
            "derived_sparse/0",
        )

    def test_only_global_single_application_is_authorized(self):
        contract = self.config["transform_contract"]
        self.assertEqual(contract["application_scope"], "all_937_camera_poses_once")
        self.assertTrue(contract["block_transforms_required_empty"])
        self.assertTrue(contract["per_building_transforms_forbidden"])
        self.assertFalse(contract["zeta_applied_during_pose_publication"])
        self.assertEqual(contract["orthometric_to_ellipsoidal_zeta_m"], 45.7)

    def test_all_user_named_immutable_inputs_are_locked(self):
        immutable = self.config["immutable_inputs"]
        roles = [row["role"] for row in immutable["files"]]
        self.assertEqual(roles.count("als_laz"), 4)
        self.assertEqual(roles.count("footprint_gpkg"), 1)
        self.assertEqual(roles.count("reference_gml"), 2)
        self.assertEqual(roles.count("projection_datum_config"), 1)
        r0 = json.loads(R0_BASE_CONFIG.read_text(encoding="utf-8"))
        r0_rows = {
            row["path"]: row
            for row in r0["canonical_inputs"]["files"]
            if row["role"] in {"als_laz", "footprint_gpkg", "reference_gml"}
        }
        r1_rows = {
            row["path"]: row
            for row in immutable["files"]
            if row["role"] in {"als_laz", "footprint_gpkg", "reference_gml"}
        }
        self.assertEqual(r1_rows, r0_rows)
        image_set = immutable["training_image_set"]
        self.assertEqual(image_set["file_count"], 937)
        self.assertEqual(image_set["total_bytes"], 910980034)
        self.assertEqual(
            image_set["sha256sum_stream_aggregate"],
            "dedc4251e491a9ae40d7c91073410cbf504023b6fe3143238b2528dc3146308a",
        )
        self.assertEqual(image_set, r0["canonical_inputs"]["training_image_set"])

    def test_image_aggregate_uses_logical_symlink_labels(self):
        run_root = REPO / "phases/p2-gsjso/runs"
        with tempfile.TemporaryDirectory(dir=run_root) as directory:
            root = Path(directory)
            physical = root / "physical"
            physical.mkdir()
            payload = b"logical-label-regression"
            (physical / "a.jpg").write_bytes(payload)
            logical = root / "logical_images"
            logical.symlink_to(physical, target_is_directory=True)
            aggregate, count, total_bytes = (
                self.module.sha256sum_stream_aggregate(logical)
            )
            image_sha = hashlib.sha256(payload).hexdigest()
            label = (logical / "a.jpg").relative_to(REPO).as_posix()
            expected = hashlib.sha256(
                f"{image_sha}  {label}\n".encode("utf-8")
            ).hexdigest()
        self.assertEqual((aggregate, count, total_bytes), (expected, 1, len(payload)))

    def test_projection_datum_semantics_fail_closed(self):
        payload = json.loads(
            (REPO / "configs/input_and_alignment/projection_datum.json").read_text(encoding="utf-8")
        )
        receipt = self.module.validate_coordinate_datum_payload(
            self.config, payload
        )
        self.assertEqual(receipt["geo_crs"], "EPSG:25832")
        self.assertEqual(receipt["orthometric_geoid_m"], 45.7)
        for key, bad in (
            ("geo_crs", "EPSG:4326"),
            ("input_vertical_datum_default", "ellipsoidal"),
            ("orthometric_geoid_m", 48.125535),
        ):
            changed = copy.deepcopy(payload)
            changed[key] = bad
            with self.assertRaises(self.module.PoseAdoptionError):
                self.module.validate_coordinate_datum_payload(
                    self.config, changed
                )

    def test_arm_configs_resolve_one_corrected_pose_binding(self):
        receipt = self.module.verify_arm_pose_configs(self.config)
        self.assertTrue(receipt["identical_pose_binding"])
        self.assertEqual(
            receipt["pose_binding"]["manifest"],
            self.config["outputs"]["manifest"],
        )
        self.assertEqual(
            receipt["arm_A_depth_normal_initial_weights"], [0.5, 0.05]
        )
        self.assertTrue(receipt["arm_B_depth_normal_supervision_removed"])

    def test_candidate_is_loaded_from_fit_and_three_way_exact(self):
        fit = self.module.load_json(self.config["inputs"]["fit_candidate"])
        global_selection = self.module.load_json(
            self.config["inputs"]["global_selection"]
        )
        block_selection = self.module.load_json(
            self.config["inputs"]["block_selection"]
        )
        matrix, receipt = self.module.extract_and_validate_candidate(
            self.config,
            self.coreg,
            fit,
            global_selection,
            block_selection,
        )
        self.assertEqual(matrix.shape, (4, 4))
        self.assertTrue(receipt["three_way_exact_matrix_match"])
        self.assertEqual(
            receipt["matrix_sha256"],
            self.config["transform_contract"]["matrix_sha256"],
        )

    def test_three_way_mismatch_fails_closed(self):
        fit = self.module.load_json(self.config["inputs"]["fit_candidate"])
        global_selection = self.module.load_json(
            self.config["inputs"]["global_selection"]
        )
        block_selection = self.module.load_json(
            self.config["inputs"]["block_selection"]
        )
        block_selection["selected_photo_to_als_global_pivot_matrix"][0][3] += 1.0
        with self.assertRaises(self.module.PoseAdoptionError):
            self.module.extract_and_validate_candidate(
                self.config,
                self.coreg,
                fit,
                global_selection,
                block_selection,
            )

    def test_pose_update_roundtrip_uses_inverse_world_transform(self):
        old_q = self.coreg.rotmat_to_qvec(
            self.coreg.rotation_exp([0.02, -0.01, 0.005])
        )
        old_t = np.array([1.0, 2.0, -3.0])
        transform = np.eye(4)
        transform[:3, :3] = self.coreg.rotation_exp(
            [0.001, -0.002, 0.0005]
        )
        transform[:3, 3] = [0.04, 0.02, -0.10]
        new_q, new_t = self.coreg.update_colmap_pose(old_q, old_t, transform)
        back_q, back_t = self.coreg.update_colmap_pose(
            new_q, new_t, np.linalg.inv(transform)
        )
        self.assertTrue(
            np.allclose(
                self.coreg.qvec_to_rotmat(back_q),
                self.coreg.qvec_to_rotmat(old_q),
                atol=1e-10,
            )
        )
        self.assertTrue(np.allclose(back_t, old_t, atol=1e-10))

    def test_points3d_transform_preserves_all_non_xyz_bytes(self):
        records = [
            (
                11,
                (1.0, 2.0, 3.0),
                (10, 20, 30),
                0.125,
                [(1, 2), (3, 4)],
            ),
            (
                12,
                (-4.0, 5.0, 6.0),
                (40, 50, 60),
                0.25,
                [(5, 6)],
            ),
        ]
        transform = np.eye(4)
        transform[:3, :3] = self.coreg.rotation_exp(
            [0.001, 0.002, -0.001]
        )
        transform[:3, 3] = [0.04, 0.02, -0.10]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.bin"
            target = root / "target.bin"
            write_points3d(source, records)
            count = self.coreg.transform_points3d_bin(
                source, target, transform
            )
            validation = self.module.validate_points3d_transform(
                source,
                target,
                transform,
                forward_tolerance=1e-12,
                roundtrip_tolerance=1e-12,
            )
        self.assertEqual(count, 2)
        self.assertEqual(validation["record_count"], 2)
        self.assertTrue(validation["ids_rgb_error_tracks_byte_identical"])

    def test_exact_once_claim_rejects_second_writer(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "claim.json"
            self.module.exclusive_json(path, {"state": "STARTED"})
            with self.assertRaises(FileExistsError):
                self.module.exclusive_json(path, {"state": "STARTED"})

    def test_existing_claim_is_a_conflict_not_a_run_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = copy.deepcopy(self.config)
            config["outputs"] = {
                key: str(root / key)
                for key in (
                    "claim",
                    "event_log",
                    "failure",
                    "diagnostic_reproduction",
                    "manifest",
                    "runtime_dir",
                    "staging_dir",
                    "derived_sparse",
                )
            }
            Path(config["outputs"]["claim"]).write_text("{}", encoding="utf-8")
            with self.assertRaises(self.module.ClaimConflictError):
                self.module.check_outputs_absent(config)

    def test_issue_append_is_pure_and_rejects_duplicate(self):
        entries = self.config["issues_contract"]["entries"]
        self.assertEqual(len(entries), 2)
        self.assertTrue(entries[0].startswith("## FUS-W1-COREGDIAG-002"))
        self.assertTrue(entries[1].startswith("## FUS-W1-COREG-ADOPT-001"))
        for token in ("표면 2·높이 11·윤곽 33", "§5"):
            self.assertIn(token, entries[0])
        for token in (
            "0.0300055814 m",
            "19.6795%",
            "0.05 m",
            "20%",
            "choice=none",
            "§4",
        ):
            self.assertIn(token, entries[1])
        rendered = self.module.render_issue_append("# issues\n", entries)
        for entry in entries:
            self.assertEqual(rendered.count(entry), 1)
        with self.assertRaises(self.module.PoseAdoptionError):
            self.module.render_issue_append(rendered, entries)

    def test_diagnostic_contract_locks_expected_counts_and_values(self):
        contract = self.config["diagnostic_reproduction"]
        self.assertEqual(contract["expected_n_threshold"], 40)
        self.assertEqual(contract["expected_correspondence_capable_n"], 132)
        self.assertEqual(contract["expected_matched_median_le_0p3_n"], 132)
        self.assertEqual(contract["expected_core_correspondence_capable_n"], 24)
        self.assertEqual(contract["expected_core_matched_median_le_0p3_n"], 24)
        self.assertEqual(
            contract["expected_building_balanced_median_m"],
            0.0723671171799,
        )
        self.assertEqual(
            contract["expected_t5_total_residual_m_rounded"], 0.004186
        )

    def test_script_never_calls_exact_once_measure_command(self):
        source = SCRIPT.read_text(encoding="utf-8")
        self.assertNotIn("diagnostic.measure(", source)
        self.assertIn("diagnostic.evaluate_building(", source)

    def test_manifest_schema_and_required_consumer_fields_are_literal(self):
        source = SCRIPT.read_text(encoding="utf-8")
        required = (
            "jointbuildgs.fusion_w1.pose_adoption_v2.manifest.v1",
            '"transform_application_count": 1',
            '"als_source_modified": False',
            '"image_pixels_modified": False',
            '"footprint_modified": False',
            '"reference_gml_modified": False',
            '"source_pose_modified": False',
            '"derived_pose_differs_from_source": True',
            '"arm_pose_contract"',
        )
        for token in required:
            self.assertIn(token, source)


if __name__ == "__main__":
    unittest.main()
