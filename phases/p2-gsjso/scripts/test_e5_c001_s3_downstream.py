#!/usr/bin/env python3
"""Contract tests for the S3-A downstream adapter (Docker-only)."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import numpy as np
import torch
from matplotlib.path import Path as PolygonPath

import e5_c001_s3_downstream as downstream


class S3DownstreamContractTests(unittest.TestCase):
    def test_write_guard_accepts_s3_and_rejects_s2p(self) -> None:
        self.assertEqual(downstream.guard_write(downstream.CSV_TIMELINE), downstream.CSV_TIMELINE)
        with self.assertRaisesRegex(RuntimeError, "write-path guard rejected"):
            downstream.guard_write(downstream.BASE_405_BUILDING)
        with self.assertRaisesRegex(RuntimeError, "write-path guard rejected"):
            downstream.guard_write(
                downstream.REPO / "phases/p0-audit/runs/e5p_s2p_interaction_20260710_C001/x"
            )

    def test_gaussian_count_is_exact_footprint_without_semantic_or_z_filter(self) -> None:
        shift = downstream.s2p.s2.SHIFT_UTM
        local = np.asarray(
            [
                [1.0, 1.0, -200.0],
                [3.0, 3.0, 500.0],
            ],
            dtype=np.float32,
        )
        polygon_xy = np.asarray(
            [
                [shift[0], shift[1]],
                [shift[0] + 2.0, shift[1]],
                [shift[0] + 2.0, shift[1] + 2.0],
                [shift[0], shift[1] + 2.0],
                [shift[0], shift[1]],
            ],
            dtype=np.float64,
        )
        footprints = {
            "DEBY_LOD2_1": {
                "bbox": (
                    float(shift[0]), float(shift[1]),
                    float(shift[0] + 2.0), float(shift[1] + 2.0),
                ),
                "paths": [PolygonPath(polygon_xy)],
            }
        }
        payload = {
            "state_dict": {
                "means": torch.from_numpy(local),
                "opacities_raw": torch.zeros((2, 1), dtype=torch.float32),
            }
        }
        rows = downstream.gaussian_stats_from_payload(payload, footprints, ["1"])
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["n_gaussians_in_footprint"], 1)
        self.assertAlmostEqual(rows[0]["z_p50"], float(shift[2] - 200.0), places=5)
        self.assertAlmostEqual(rows[0]["opacity_p50"], 0.5, places=6)
        self.assertIn("no semantic-class or roof-height filter", downstream.COUNT_DEFINITION)

    def test_checkpoint_loader_rejects_wrong_iteration(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            checkpoint = Path(directory) / "step.pt"
            torch.save(
                {
                    "it": 5000,
                    "state_dict": {
                        "means": torch.zeros((1, 3)),
                        "opacities_raw": torch.zeros((1, 1)),
                    },
                },
                checkpoint,
            )
            payload = downstream._torch_load_safely(
                checkpoint, 5000, attempts=1, retry_seconds=0.0
            )
            self.assertEqual(payload["it"], 5000)
            with self.assertRaisesRegex(RuntimeError, "iteration mismatch"):
                downstream._torch_load_safely(
                    checkpoint, 4999, attempts=1, retry_seconds=0.0
                )

    def test_checkpoint_loader_exhausts_partial_file(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            checkpoint = Path(directory) / "partial.pt"
            checkpoint.write_bytes(b"PK\x03\x04partial")
            with self.assertRaisesRegex(RuntimeError, "did not become readable"):
                downstream._torch_load_safely(
                    checkpoint, 5000, attempts=2, retry_seconds=0.0
                )

    def test_azimuth_match_wraps_at_north(self) -> None:
        hit, delta = downstream.azimuth_hit("359.0", "1.0")
        self.assertTrue(hit)
        self.assertAlmostEqual(delta or 0.0, 2.0)

    def test_parser_locks_wave2_and_exposes_final_commands(self) -> None:
        parser = downstream.build_parser()
        args = parser.parse_args(["wave2-roofcrop"])
        self.assertEqual(args.run_name, downstream.FULL_RUNS[0])
        self.assertEqual(args.step, 5000)
        for command in [
            "timeline-roofcrop", "checkpoint-gradient-pairing", "densify-log",
            "readout", "assemble", "evaluate",
            "repair-405", "gable-mode", "panels-8way", "arm-cells", "inventory",
        ]:
            parsed = parser.parse_args([command])
            self.assertEqual(parsed.cmd, command)

    def test_static_namespaces_and_panel_count(self) -> None:
        downstream._assert_readout_namespace()
        self.assertEqual(len(downstream.TIMELINE_IDS), 7)
        self.assertEqual(len(downstream._s3_panel_sources()), 10)
        self.assertIn("Roofer assembly", downstream.PIPELINE_ORDER)
        self.assertLess(
            downstream.PIPELINE_ORDER.index("Roofer assembly"),
            downstream.PIPELINE_ORDER.index("405 overlay"),
        )
        for _label, path, _schema in downstream._downstream_artifact_specs():
            self.assertIn("e5_c001_s3", path.name)

    def test_real_arm1p_score_and_405_schemas_are_compatible(self) -> None:
        base_runs = set(downstream.ARM1P_BASE_RUNS.values())
        metrics = downstream._metric_rows_by_run(downstream.BASE_405_BUILDING, base_runs)
        repairs = downstream._repair_by_run(downstream.BASE_405_REPAIR, base_runs)
        self.assertEqual(len(metrics), 36)
        self.assertEqual(set(repairs), base_runs)

    def test_readout_adapter_overrides_fragile_run_name_parsing(self) -> None:
        downstream.configure_readout()
        harness = downstream.s2p.s2.ab
        self.assertEqual(harness.P0_RUN_ID, downstream.P0_RUN_ID)
        self.assertEqual(harness.CKPT_ROOT, downstream.CKPT_ROOT)
        self.assertEqual([setting.key for setting in harness.SETTINGS], ["base"])
        self.assertEqual(harness.run_names(), downstream.FULL_RUNS)
        source = harness.source_for(harness.SETTINGS[0], downstream.FULL_RUNS[0])
        self.assertEqual(source.source_group, "gs_s3a")
        self.assertEqual(source.replicate, "r1")
        fingerprint = harness.readout_fingerprint(
            harness.SETTINGS[0], downstream.FULL_RUNS[0],
            {
                "npz": downstream.READOUT_ROOT / "missing.npz",
                "coverage": downstream.READOUT_ROOT / "missing.csv",
                "metrics": downstream.READOUT_ROOT / "missing.json",
                "log": downstream.READOUT_ROOT / "missing.log",
            },
        )
        self.assertEqual(fingerprint["arm"], "s3a")
        self.assertEqual(fingerprint["replicate"], "r1")


if __name__ == "__main__":
    unittest.main()
