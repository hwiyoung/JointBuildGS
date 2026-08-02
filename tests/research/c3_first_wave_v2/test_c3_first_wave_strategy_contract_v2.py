import hashlib
import json
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
V2_DIR = REPO_ROOT / "docs/research/preregistration/c3_first_wave_v2"
CONTRACT_PATH = V2_DIR / "c3_first_wave_strategy_contract_draft_v2.json"
DRAFT_PATH = V2_DIR / "C3_FIRST_WAVE_STRATEGY_DRAFT_v2.md"


class TestC3FirstWaveStrategyContractV2(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.contract = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
        cls.draft = DRAFT_PATH.read_text(encoding="utf-8")

    def test_draft_has_no_execution_or_scientific_authority(self):
        self.assertEqual(
            self.contract["schema"],
            "jointbuildgs.c3_first_wave_strategy_contract_draft.v2",
        )
        self.assertEqual(self.contract["status"], "DRAFT_NOT_EXECUTION_AUTHORITY")
        self.assertFalse(self.contract["execution_authority"])
        self.assertFalse(self.contract["handoff_authorized"])
        self.assertFalse(self.contract["producer_implementation_in_scope"])
        self.assertEqual(self.contract["authorized_run_ids"], [])
        self.assertIsNone(self.contract["scientific_verdict"])
        self.assertIn("scientific_verdict: null", self.draft)

    def test_exact_common_source_and_aoi_are_frozen(self):
        base = self.contract["common_base"]
        self.assertEqual(base["id"], "B_CURRENT_CANDIDATE_c205892c390997b5")
        self.assertEqual(
            (base["available_images"], base["exact_whole_scene_image_pose_pairs"], base["excluded_images"]),
            (962, 937, 25),
        )
        self.assertEqual(
            base["included_basename_set_sha256"],
            "dd9b446e11c978ef8223858f08571bfea832e0d33517b24c1e573060244f4e2c",
        )
        self.assertEqual(
            base["included_image_camera_pair_sha256"],
            "7d1f90ecb79ee19acfbfedb0b7cf78083349c7669678a1f883c5034a41a89ccc",
        )
        self.assertEqual(base["aoi"]["crs"], "EPSG:25832")
        self.assertEqual(base["sfm_sparse_points"], 371808)
        self.assertEqual(base["dense_mvs_source"]["points"], 43942554)
        self.assertFalse(base["dense_mvs_source"]["direct_full_initialization_allowed"])

    def test_whole_scene_training_but_development_only_scoring(self):
        scope = self.contract["scope"]
        roster = scope["frozen_roster"]
        self.assertTrue(scope["whole_scene_training"])
        self.assertEqual(scope["training_view_count"], 937)
        self.assertEqual(roster["total"], 72)
        self.assertEqual(
            roster["development"] + roster["validation"] + roster["held_out"],
            roster["total"],
        )
        self.assertEqual((roster["development"], roster["validation"], roster["held_out"]), (51, 11, 10))
        self.assertEqual(scope["scoring_split"], "DEVELOPMENT_ONLY")
        self.assertEqual(scope["scored_buildings"], 51)
        self.assertFalse(scope["validation_access"])
        self.assertFalse(scope["held_out_access"])

    def test_mixed_initialization_and_one_read_preflight(self):
        init = self.contract["initialization"]
        preflight = init["dense_preflight"]
        self.assertTrue(init["all_sfm_sparse_included"])
        self.assertFalse(init["sparse_only_allowed"])
        self.assertFalse(init["full_dense_direct_allowed"])
        self.assertFalse(init["random_subsampling_allowed"])
        self.assertEqual(preflight["source_natural_read_count"], 1)
        self.assertEqual(preflight["candidate_voxel_m_ascending"], [0.1, 0.2, 0.4])
        self.assertEqual(
            preflight["selection_rule"],
            "FINEST_ASCENDING_CANDIDATE_WITH_DENSE_POINTS_LE_3000000_AND_24GB_VRAM_PREFLIGHT_PASS",
        )
        self.assertIsNone(preflight["selected_voxel_m"])
        self.assertIsNone(preflight["selected_dense_point_count"])
        self.assertFalse(preflight["uses_scientific_outcomes"])
        self.assertFalse(preflight["opens_evaluation_reference"])
        self.assertIn("ENGINEERING_FALLBACK", preflight["voxel_0p40_role"])
        self.assertIn("NOT_PAST_QUALITY_OPTIMUM", preflight["voxel_0p40_role"])
        self.assertEqual(init["max_dense_seed_points"], 3000000)
        self.assertEqual(init["max_total_primitives"], 4000000)
        self.assertEqual(init["at_primitive_cap"], {"growth": "STOP", "pruning": "CONTINUE"})

    def test_image_only_semantic_contract_is_common_c3_to_c5(self):
        sem = self.contract["semantic_producer"]
        self.assertEqual(sem["producer"], "GROUNDED_SAM_IMAGE_ONLY")
        self.assertEqual(sem["common_for_conditions"], ["C3", "C4", "C5"])
        self.assertEqual(sem["input"], "EXACT_937_COLMAP_UNDISTORTED_TRAINING_RGB")
        self.assertEqual(sem["membership_manifest"], "CROSSWALK_ONLY_NO_RGB_PRE_READ")
        self.assertEqual(
            sem["rgb_identity"],
            "BYTES_AND_SHA256_FROM_SAME_NATURAL_INFERENCE_READ",
        )
        self.assertFalse(sem["resizing_allowed"])
        self.assertFalse(sem["legacy_raw_completion_reuse_allowed"])
        self.assertEqual(
            sem["dimension_checks_before_inference"],
            [
                "COLMAP_CAMERA_WIDTH_HEIGHT",
                "CORRESPONDING_GEOMETRIC_DEPTH_WIDTH_HEIGHT_CHANNEL_1",
            ],
        )
        self.assertEqual(
            sem["classes"],
            {
                "0": "UNKNOWN_IGNORE",
                "1": "ROOF",
                "2": "FACADE_WALL",
                "3": "GROUND_ROAD_PAVEMENT",
            },
        )
        self.assertTrue(sem["unknown_ignored_by_loss"])
        self.assertEqual(
            sem["prompt_order_by_class"],
            {"1": ["roof"], "2": ["facade", "wall"], "3": ["ground", "road", "pavement"]},
        )
        self.assertEqual(sem["groundingdino_revision"], "856dde20aee659246248e20734ef9ba5214f5e44")
        self.assertEqual(sem["segment_anything_revision"], "dca509fe793f601edb92606367a655c15ac00fdf")
        self.assertTrue(sem["must_verify_pinned_runtime_and_assets_before_inference"])
        self.assertIn(
            "EXACT_937_COLMAP_UNDISTORTED_RGB",
            self.contract["stage_mount_allowlists"]["training"],
        )
        for forbidden in ("FOOTPRINT", "BUILDING_ID", "UAS", "ALS", "LOD1", "LOD2"):
            self.assertIn(forbidden, sem["prohibited_guidance"])

    def test_numeric_recipe_and_caps_are_exact(self):
        training = self.contract["training"]
        loss = training["loss"]
        self.assertEqual((training["seed"], training["max_iterations"]), (0, 30000))
        self.assertEqual(training["checkpoint_iterations"], [5000, 10000, 20000, 30000])
        self.assertEqual(loss["depth"], {"weight": 0.03, "warmup_iterations": 5000, "linear_ramp_iterations": 5000})
        self.assertEqual(loss["external_normal_map"], 0.0)
        self.assertEqual(loss["intrinsic_normal_consistency"], {"weight": 0.05, "start_iteration": 7000, "schedule_after_start": "CONSTANT"})
        self.assertEqual(loss["distortion"]["weight"], 100.0)
        self.assertEqual(loss["distortion"]["normalization"], "MEAN_REND_DIST_DIV_SCENE_SCALE_SQUARED")
        self.assertEqual(loss["structure"]["grouping"], "g2")
        self.assertFalse(loss["structure"]["g2_geometry_allowed"])
        self.assertEqual(loss["semantic"], {"weight": 0.1, "detach_geometry": False})
        for key in ("mutual", "confidence", "monocular", "mvc", "separate_semantic_depth"):
            self.assertEqual(loss[key], 0.0)
        caps = self.contract["caps"]
        self.assertEqual((caps["strategy_variants"], caps["training_seeds"], caps["training_jobs"]), (1, 1, 1))
        self.assertEqual((caps["vram_gb"], caps["max_dense_seed_points"], caps["max_total_primitives"]), (24, 3000000, 4000000))

    def test_protected_sources_and_outcomes_are_forbidden(self):
        prohibited = set(self.contract["prohibited_inputs_or_outcomes"])
        expected = {
            "VALIDATION_REFERENCE_OR_OUTCOME",
            "HELD_OUT_REFERENCE_OR_OUTCOME",
            "FUSION_W1_RESULT",
            "LOD1",
            "LOD2",
            "CURRENT_UAS_LIDAR_BEFORE_SEALED_DEVELOPMENT_SCORING",
            "EXISTING_ALS",
            "R_EXT",
        }
        self.assertTrue(expected.issubset(prohibited))
        self.assertFalse(self.contract["stage_mount_allowlists"]["whole_artifact_root_mount_allowed"])

    def test_v1_files_are_immutable(self):
        expected = {
            "C3_FIRST_WAVE_HUMAN_DECISION_SUMMARY_v1.md": "f88262885859c38ef8410fd9abfb4cd9378d798a1988a2fa1f89fce6b6cf8f12",
            "c3_first_wave_strategy_contract_draft_v1.json": "993c62783c9b5dd7f2772d391781f499a3d8a87d5c11c9a07d02b070a3bf411a",
            "C3_FIRST_WAVE_STRATEGY_DRAFT_v1.md": "10d2ef342607135fd3c39615d8b32a0739216f8cd2cebffcf09f40b3223a5f4b",
        }
        v1_dir = REPO_ROOT / "docs/research/preregistration/c3_first_wave_v1"
        for name, digest in expected.items():
            with self.subTest(name=name):
                actual = hashlib.sha256((v1_dir / name).read_bytes()).hexdigest()
                self.assertEqual(actual, digest)


if __name__ == "__main__":
    unittest.main()
