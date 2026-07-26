#!/usr/bin/env python3
"""Regression tests for the locked A-prime trainer materializer/launcher."""
from __future__ import annotations

import csv
import importlib.util
import json
import math
from pathlib import Path
import tempfile
import unittest

import numpy as np
import yaml


REPO = Path(__file__).resolve().parents[3]
DRIVER_PATH = REPO / "phases/p2-gsjso/scripts/fusion_w1_aprime_training_20260726.py"
SPEC = importlib.util.spec_from_file_location("aprime_training_driver", DRIVER_PATH)
assert SPEC is not None and SPEC.loader is not None
driver = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(driver)


def sample_preprocess() -> dict:
    root = (
        "phases/p2-gsjso/runs/20260726_fusion_w1_aprime/preprocess_aprime/"
        "aprime_pose_28b38383a0b6d826_class6_e005_k3_rooftin_v2/"
        "by_building/DEBY_LOD2_42364609"
    )
    names = ["view_a.JPG", "view_b.JPG", "view_c.JPG"]
    return {
        "data_root": root,
        "seed_canonical_npz": f"{root}/seed_class6_filtered_canonical.npz",
        "selected_names": names,
        "training_names": names,
        "evaluation_names": [],
    }


def write_csv(path: Path, fields: list[str], rows: list[dict]) -> None:
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


class AprimeTrainingContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.config_path = driver.DEFAULT_CONFIG
        cls.config = driver.load_config(cls.config_path)

    def build(self, arm: str, profile: str = "full", run: str = "r1") -> dict:
        return driver.build_training_config(
            repo=REPO,
            config=self.config,
            preprocess=sample_preprocess(),
            building_id="DEBY_LOD2_42364609",
            arm=arm,
            run=run,
            profile=profile,
            out_dir=REPO / "phases/p2-gsjso/runs/20260726_fusion_w1_aprime/_unit_out",
        )

    def test_full_recipe_and_v2_cache_are_locked(self) -> None:
        recipe = self.config["recipe"]
        self.assertTrue(self.config["inputs"]["preprocess_cache_namespace"].endswith("_v2"))
        self.assertEqual(recipe["max_iter"], 30_000)
        self.assertEqual(recipe["run_seeds"], {"r1": 1001, "r2": 1002})
        self.assertEqual(recipe["mvs_seed_init_opacity"], 0.1)
        self.assertFalse(recipe["seed_protect"])
        self.assertFalse(recipe["surface_seed_protect"])
        self.assertEqual(
            (recipe["prune_opa"], recipe["grow_grad2d"]), (0.005, 0.0002)
        )
        self.assertEqual(
            (
                recipe["refine_start_iter"],
                recipe["refine_stop_iter"],
                recipe["refine_every"],
                recipe["reset_every"],
            ),
            (500, 15_000, 100, 3_000),
        )

    def test_all_selected_views_train_and_eval_is_explicitly_empty(self) -> None:
        resolved = self.build("Aprime")
        self.assertEqual(resolved["visible_views"], sample_preprocess()["selected_names"])
        self.assertEqual(resolved["train_views"], sample_preprocess()["selected_names"])
        self.assertEqual(resolved["eval_views"], [])
        self.assertEqual(resolved["downscale"], 1.0)

    def test_aprime_and_b_differ_only_in_four_prior_weights(self) -> None:
        aprime = self.build("Aprime")
        arm_b = self.build("B")
        audit = driver.validate_ablation_pair(aprime, arm_b)
        self.assertEqual(set(audit["difference_keys"]), driver.ARM_DIFFERENCE_KEYS)
        self.assertEqual(
            {key: arm_b[key] for key in driver.ARM_DIFFERENCE_KEYS},
            {key: 0.0 for key in driver.ARM_DIFFERENCE_KEYS},
        )
        self.assertTrue(arm_b["load_depth"])
        self.assertTrue(arm_b["load_normal"])
        self.assertEqual(arm_b["photo_mask_dir"], aprime["photo_mask_dir"])

    def test_prior_and_surface_schedules_have_exact_boundaries(self) -> None:
        self.assertEqual(
            driver.schedule_weight_reference(
                base=0.5, final=0.05, iteration=14_999, transition=15_000, steps=15_000
            ),
            0.5,
        )
        self.assertEqual(
            driver.schedule_weight_reference(
                base=0.5, final=0.05, iteration=15_000, transition=15_000, steps=15_000
            ),
            0.5,
        )
        self.assertTrue(
            math.isclose(
                driver.schedule_weight_reference(
                    base=0.5,
                    final=0.05,
                    iteration=29_999,
                    transition=15_000,
                    steps=15_000,
                ),
                0.05,
                rel_tol=0.0,
                abs_tol=1e-12,
            )
        )
        self.assertEqual(
            driver.schedule_weight_reference(
                base=0.0, final=0.0, iteration=20_000, transition=15_000, steps=15_000
            ),
            0.0,
        )

    def test_mini_smoke_scales_only_registered_iteration_schedule(self) -> None:
        full = self.build("Aprime", "full")
        smoke = self.build("Aprime", "mini_smoke")
        expected_differences = set(self.config["mini_smoke_profile"]["overrides"])
        differences = {key for key in full if full[key] != smoke[key]}
        self.assertEqual(differences, expected_differences)
        self.assertEqual(smoke["max_iter"], 600)
        self.assertEqual(smoke["depth_warmup"], 300)
        self.assertEqual(smoke["nc_ramp_steps"], 100)
        self.assertEqual(
            (
                smoke["refine_start_iter"],
                smoke["refine_stop_iter"],
                smoke["refine_every"],
                smoke["reset_every"],
            ),
            (50, 500, 25, 300),
        )

    def test_queue_is_exact_21_job_preregistered_order(self) -> None:
        rows = driver.build_queue_rows(driver.read_targets(REPO, self.config), self.config)
        self.assertEqual(len(rows), 21)
        self.assertEqual([(row["arm"], row["replicate"]) for row in rows[:9]], [("Aprime", "r1")] * 9)
        self.assertEqual([(row["arm"], row["replicate"]) for row in rows[9:18]], [("Aprime", "r2")] * 9)
        self.assertEqual(
            [row["building_id"] for row in rows[18:]],
            ["DEBY_LOD2_42364609", "DEBY_LOD2_42364659", "DEBY_LOD2_4908023"],
        )
        self.assertEqual([(row["arm"], row["replicate"]) for row in rows[18:]], [("B", "r1")] * 3)

    def test_exact_Mj_triplet_accepts_identity_and_rejects_one_pixel(self) -> None:
        expected = np.array([[False, True], [True, False]], dtype=np.bool_)
        result = driver.validate_mask_triplet(
            image_name="view.JPG",
            expected=expected,
            depth_mask=expected.copy(),
            normal_mask=expected.copy(),
            photo_mask=expected.copy(),
        )
        self.assertEqual(result["mask_pixels_n"], 2)
        changed = expected.copy()
        changed[0, 0] = True
        with self.assertRaises(driver.ContractError):
            driver.validate_mask_triplet(
                image_name="view.JPG",
                expected=expected,
                depth_mask=changed,
                normal_mask=expected,
                photo_mask=expected,
            )

    def test_t2_contract_requires_full_identity_git_checks_inputs_and_artifacts(self) -> None:
        contract = self.config["preflight_gates"]["T2"]
        self.assertEqual(contract["identity"]["rehearsal_defaults"], True)
        self.assertEqual(len(contract["implementation_files"]), 4)
        self.assertIn("checkpoint_equals_training_final_step", contract["required_true_checks"])
        self.assertIn("training_data_root_equals_preprocess_data_root", contract["required_true_checks"])
        self.assertEqual(
            set(contract["required_current_inputs"]),
            {
                "config", "script", "checkpoint", "training_config", "preprocess_manifest",
                "class6_seed", "cameras_bin", "images_bin", "scene_reference_frame",
                "projection_datum_config",
            },
        )
        source = DRIVER_PATH.read_text(encoding="utf-8")
        for required_fragment in (
            "T2 receipt lacks the committed git_lock",
            "T2 receipt HEAD vs launch HEAD",
            "T2 receipt has non-true checks",
            "T2 checkpoint is not the bound training final.pt",
            "T2 consumed preprocess coverage",
            "T2 consumed preprocess artifact",
            "T2 output artifact",
            "T2 input {role}",
        ):
            self.assertIn(required_fragment, source)

    def test_completed_output_verifier_requires_positive_terms_and_actual_prune(self) -> None:
        scratch_parent = REPO / "phases/p2-gsjso/runs/20260726_fusion_w1_aprime"
        scratch_parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix=".training_test_", dir=scratch_parent) as raw:
            target = Path(raw)
            (target / "ckpt").mkdir()
            (target / "audit").mkdir()
            resolved = self.build("Aprime", "mini_smoke")
            resolved_path = target / "resolved_config.yaml"
            resolved_path.write_text(yaml.safe_dump(resolved, sort_keys=False), encoding="utf-8")
            checkpoint = target / "ckpt/step_000600.pt"
            checkpoint.write_bytes(b"full-state-test")
            checkpoint_sha = driver.sha256_file(checkpoint)
            (target / "ckpt/step_000600.pt.sha256").write_text(
                f"{checkpoint_sha}  step_000600.pt\n", encoding="utf-8"
            )
            (target / "ckpt/final.pt").write_bytes(b"final-test")
            (target / "full_state_manifest.json").write_text(
                json.dumps(
                    {
                        "schema": "jointbuildgs.stage2.resume_manifest.v1",
                        "process_completed": True,
                        "process_completed_steps": 600,
                        "last_completed_steps": 600,
                        "latest_full_checkpoint": {
                            "completed_steps": 600,
                            "sha256": checkpoint_sha,
                        },
                    }
                ),
                encoding="utf-8",
            )
            effective = {
                "distort_norm_denominator": 4.0,
                "depth_schedule": resolved["depth_schedule"],
                "depth_warmup": resolved["depth_warmup"],
                "depth_ramp_steps": resolved["depth_ramp_steps"],
                "depth_base_weight": resolved["w_depth"],
                "depth_final_weight": resolved["depth_final_weight"],
                "depth_prior_alignment": "alpha_lsq",
                "depth_alignment_detach_scale": True,
                "normal_prior_orientation": "signed",
                "normal_schedule": resolved["normal_schedule"],
                "normal_warmup": resolved["normal_warmup"],
                "normal_ramp_steps": resolved["normal_ramp_steps"],
                "normal_final_weight": resolved["normal_final_weight"],
                "w_nc": resolved["w_nc"],
                "nc_schedule": "ramp",
                "nc_warmup": resolved["nc_warmup"],
                "nc_ramp_steps": resolved["nc_ramp_steps"],
                "w_distort": resolved["w_distort"],
                "distort_normalization": "scene_scale_sq",
                "distort_schedule": "ramp",
                "distort_warmup": resolved["distort_warmup"],
                "distort_ramp_steps": resolved["distort_ramp_steps"],
                "surface_seed_protect": False,
                "legacy_mvs_seed_protect": False,
                "seed_protect": False,
                "seed_lineage_audit": True,
                "mvs_seed_init_opacity": 0.1,
                "seed_protected_lineage": "none",
                "prune_opa": resolved["prune_opa"],
                "grow_grad2d": resolved["grow_grad2d"],
                "refine_start_iter": resolved["refine_start_iter"],
                "refine_stop_iter": resolved["refine_stop_iter"],
                "refine_every": resolved["refine_every"],
                "reset_every": resolved["reset_every"],
                "final_prune_opa": 0.0,
                "elongation_filter": False,
            }
            (target / "effective_config.json").write_text(json.dumps(effective), encoding="utf-8")
            fields = [
                "step", "component", "raw_loss", "weight", "weighted_loss",
                "weighted_loss_share", "grad_norm", "grad_norm_share",
            ]
            write_csv(
                target / "audit/loss_grad_norms.csv",
                fields,
                [
                    {
                        "step": 400, "component": component, "raw_loss": 1.0,
                        "weight": 0.1, "weighted_loss": 0.1,
                        "weighted_loss_share": 0.1, "grad_norm": 0.1,
                        "grad_norm_share": 0.1,
                    }
                    for component in ("depth", "normal", "nc", "distort")
                ],
            )
            seed_fields = [
                "iteration", "scope", "gaussians_total", "seed_lineage_count",
                "opacity_median", "last_prune_step", "last_prune_candidates",
                "last_pruned", "last_prune_seed_protected", "cum_prune_candidates",
                "cum_pruned", "cum_prune_seed_protected", "seed_protect_active",
                "effective_prune_opa",
            ]
            write_csv(
                target / "audit/seed_lineage.csv",
                seed_fields,
                [
                    {
                        "iteration": 0, "scope": "all_seed_lineage",
                        "gaussians_total": 295, "seed_lineage_count": 295,
                        "opacity_median": 0.1, "last_prune_step": -1,
                        "last_prune_candidates": 0, "last_pruned": 0,
                        "last_prune_seed_protected": 0, "cum_prune_candidates": 0,
                        "cum_pruned": 0, "cum_prune_seed_protected": 0,
                        "seed_protect_active": "false", "effective_prune_opa": 0.005,
                    },
                    {
                        "iteration": 400, "scope": "all_seed_lineage",
                        "gaussians_total": 294, "seed_lineage_count": 294,
                        "opacity_median": 0.09, "last_prune_step": 400,
                        "last_prune_candidates": 1, "last_pruned": 1,
                        "last_prune_seed_protected": 0, "cum_prune_candidates": 1,
                        "cum_pruned": 1, "cum_prune_seed_protected": 0,
                        "seed_protect_active": "false", "effective_prune_opa": 0.005,
                    },
                ],
            )
            evidence = driver.verify_training_completion(
                repo=REPO,
                config=self.config,
                target=target,
                resolved_path=resolved_path,
                profile="mini_smoke",
            )
            self.assertEqual(evidence["completed_optimizer_updates"], 600)
            self.assertGreater(
                evidence["seed_lineage_audit"]["maximum_cumulative_pruned"], 0
            )
            self.assertEqual(
                set(evidence["mini_smoke_term_evidence"]["component_evidence"]),
                {"depth", "normal", "nc", "distort"},
            )

    def test_final_v2_42364609_dataloader_roundtrip_is_exact(self) -> None:
        snapshot = driver.validate_preprocess(
            REPO,
            self.config,
            "DEBY_LOD2_42364609",
            roundtrip=True,
            hash_artifacts=True,
        )
        self.assertEqual(snapshot["view_count"], 16)
        self.assertEqual(snapshot["seed_points_n"], 295)
        self.assertEqual(snapshot["evaluation_names"], [])
        self.assertTrue(
            snapshot["dataloader_roundtrip"][
                "all_depth_normal_photo_masks_exactly_equal_saved_M_j"
            ]
        )
        self.assertEqual(snapshot["dataloader_roundtrip"]["mask_pixels_total"], 4683)


if __name__ == "__main__":
    unittest.main(verbosity=2)
