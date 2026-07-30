#!/usr/bin/env python3
"""Contract tests for the recovered-smoke non-placeholder panel adapter."""
from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from PIL import Image


REPO = Path(__file__).resolve().parents[2]
MODULE_PATH = (
    REPO
    / "phases/p2-gsjso/scripts/fusion_w1/fusion_w1_aprime_smoke_qualitative_20260727.py"
)
SPEC = importlib.util.spec_from_file_location("fusion_w1_aprime_smoke_qualitative", MODULE_PATH)
if SPEC is None or SPEC.loader is None:  # pragma: no cover - import setup guard
    raise RuntimeError(f"cannot import {MODULE_PATH}")
qualitative = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = qualitative
SPEC.loader.exec_module(qualitative)


class QualitativeContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.config = qualitative.load_config()
        cls.report = qualitative.load_report_module(cls.config)
        cls.inspection = qualitative.inspect_sources(cls.config, cls.report)

    def test_scope_and_output_are_exactly_recovery_attempt_005(self) -> None:
        self.assertEqual(self.config["scope"], qualitative.EXPECTED_SCOPE)
        self.assertEqual(
            self.config["outputs"]["root"], qualitative.EXPECTED_OUTPUT_ROOT
        )
        self.assertEqual(
            set(self.config["outputs"]),
            {"root", "panel", "opacity", "receipt", "strict_publications"},
        )
        output_root = qualitative.repo_path(self.config["outputs"]["root"])
        recovery_root = qualitative.repo_path(
            self.config["source_roots"]["recovery"]
        )
        self.assertTrue(qualitative.is_within(output_root, recovery_root))
        for _, record in qualitative.iter_locked_records(self.config):
            self.assertFalse(
                qualitative.is_within(qualitative.repo_path(record["path"]), output_root)
            )

    def test_all_real_visual_sources_are_nonempty(self) -> None:
        self.assertEqual(
            self.inspection["components"],
            {name: True for name in qualitative.EXPECTED_COMPONENTS},
        )
        self.assertEqual(self.inspection["input_crop"]["mask_pixels_n"], 643)
        self.assertGreater(self.inspection["input_crop"]["width"], 0)
        self.assertGreater(self.inspection["input_crop"]["height"], 0)
        self.assertEqual(self.inspection["seed"]["points_n"], 295)
        self.assertGreater(self.inspection["tsdf_mesh"]["points_n"], 3)
        self.assertGreater(self.inspection["tsdf_samples"]["points_n"], 3)
        self.assertGreater(self.inspection["tsdf_samples"]["span_xyz"][2], 0.0)
        self.assertGreater(self.inspection["cityjson"]["rings_n"], 0)
        self.assertGreater(self.inspection["reference_gml"]["rings_n"], 0)

    def test_opacity_is_actual_initial_plus_dynamics_trajectory(self) -> None:
        opacity = self.inspection["opacity"]
        self.assertEqual(opacity["state"], "measured")
        self.assertGreaterEqual(opacity["initial_rows_n"], 1)
        self.assertGreaterEqual(opacity["dynamics_rows_n"], 2)
        self.assertLessEqual(opacity["minimum_iteration"], 15000)
        self.assertGreaterEqual(opacity["maximum_iteration"], 20000)
        self.assertGreater(opacity["maximum_cumulative_pruned"], 0)

    def test_report_module_helpers_are_hash_locked_and_reused(self) -> None:
        record = self.config["locked_inputs"]["report_module"]
        self.assertEqual(
            qualitative.sha256_file(qualitative.repo_path(record["path"])),
            record["sha256"],
        )
        for name in (
            "generate_visuals",
            "input_crop",
            "npz_xyz_rgb",
            "ply_vertices",
            "cityjson_rings",
            "gml_rings_by_building",
            "load_opacity_rows",
            "plot_opacity",
        ):
            self.assertTrue(callable(getattr(self.report, name)))

    def test_blank_or_placeholder_like_png_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "blank.png"
            Image.new("RGB", (800, 400), color="white").save(path)
            with self.assertRaisesRegex(
                qualitative.QualitativeContractError, "blank|variation|placeholder"
            ):
                qualitative.png_stats(path, minimum_size=(100, 100))

    def test_scope_tamper_is_rejected_before_file_use(self) -> None:
        tampered = copy.deepcopy(self.config)
        tampered["scope"]["attempt"] = 4
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "tampered.json"
            path.write_text(json.dumps(tampered), encoding="utf-8")
            with self.assertRaisesRegex(
                qualitative.QualitativeContractError, "scope drift"
            ):
                qualitative.load_config(path, verify_files=False)

    def test_wrapper_enforces_docker_nonroot_no_network_and_ro_sources(self) -> None:
        wrapper = (
            REPO
            / "phases/p2-gsjso/scripts/fusion_w1/run_fusion_w1_aprime_smoke_qualitative_20260727.sh"
        ).read_text(encoding="utf-8")
        self.assertIn("--network=none", wrapper)
        self.assertIn("--read-only", wrapper)
        self.assertIn('--user "$(id -u):$(id -g)"', wrapper)
        self.assertIn('--volume "$REPO_ROOT:$CONTAINER_REPO:ro"', wrapper)
        self.assertIn("EXPECTED_IMAGE_ID=", wrapper)
        self.assertIn("GIT_COMMON_DIR=", wrapper)
        self.assertIn("--pull=never", wrapper)
        self.assertNotIn("--gpus", wrapper)
        self.assertNotIn("fusion_w1_aprime_training_20260726.py", wrapper)
        for mode in (
            "test)",
            "check)",
            "build)",
            "verify)",
            "strict-check)",
            "publish-strict)",
            "verify-strict)",
        ):
            self.assertIn(mode, wrapper)

    def test_publication_policy_is_strict_and_verdict_free(self) -> None:
        publication = self.config["publication"]
        self.assertFalse(publication["placeholders_allowed"])
        self.assertFalse(publication["partial_publication_allowed"])
        self.assertTrue(publication["receipt_written_last"])
        self.assertTrue(publication["source_inputs_rehashed_after_render"])
        self.assertTrue(publication["legacy_top_level_append_only"])
        strict = publication["strict_head_publications"]
        self.assertEqual(strict["key"], "full_git_head")
        self.assertTrue(strict["require_implementation_tracked_at_head"])
        self.assertTrue(strict["require_implementation_worktree_matches_head"])
        self.assertTrue(strict["same_head_is_verify_only"])
        self.assertFalse(strict["overwrite_allowed"])
        self.assertTrue(strict["legacy_top_level_must_remain_unchanged"])
        self.assertIsNone(publication["scientific_verdict"])

    def test_strict_head_context_accepts_committed_bytes_and_rejects_drift(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary)
            subprocess.run(
                ["git", "init", "-q", "-b", "exp/fusion-w1", str(repo)],
                check=True,
            )
            implementation = ["config.json", "tool.py", "run.sh", "test.py"]
            for index, path_value in enumerate(implementation):
                (repo / path_value).write_text(f"implementation-{index}\n", encoding="utf-8")
            report_path = repo / "report.py"
            report_path.write_text("locked-report\n", encoding="utf-8")
            subprocess.run(["git", "-C", str(repo), "add", "."], check=True)
            subprocess.run(
                [
                    "git",
                    "-C",
                    str(repo),
                    "-c",
                    "user.name=Codex Test",
                    "-c",
                    "user.email=codex-test@example.invalid",
                    "commit",
                    "-q",
                    "-m",
                    "fixture",
                ],
                check=True,
            )
            report_bytes = report_path.read_bytes()
            fixture = {
                "branch": "exp/fusion-w1",
                "implementation_files": implementation,
                "locked_inputs": {
                    "report_module": {
                        "path": "report.py",
                        "sha256": hashlib.sha256(report_bytes).hexdigest(),
                        "bytes": len(report_bytes),
                    }
                },
            }
            context = qualitative.strict_head_context(fixture, repo=repo)
            self.assertEqual(context["branch"], "exp/fusion-w1")
            self.assertEqual(context["publication_key"], context["head"])
            self.assertEqual(len(context["files"]), 5)
            self.assertTrue(context["all_tracked_at_head"])
            self.assertTrue(context["all_worktree_match_head"])

            (repo / "tool.py").write_text("worktree-drift\n", encoding="utf-8")
            with self.assertRaisesRegex(
                qualitative.QualitativeContractError, "differs from HEAD"
            ):
                qualitative.strict_head_context(fixture, repo=repo)


if __name__ == "__main__":
    unittest.main()
