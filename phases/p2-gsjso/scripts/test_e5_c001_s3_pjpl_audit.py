#!/usr/bin/env python3
"""Focused CPU contracts for the locked S3-A P-J/P-L gate audit."""

from __future__ import annotations

import csv
import importlib.util
import inspect
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import torch

from src.stage2.train import (
    _collect_pjpl_view_audit,
    _semantic_geometry_execution_flags,
    _update_pjpl_view_audit,
    _write_pjpl_view_audit,
    main as train_main,
)


ORCHESTRATOR_PATH = Path(__file__).with_name("e5_c001_s3_semantic_guided.py")
SPEC = importlib.util.spec_from_file_location("e5_c001_s3_semantic_guided_pjpl", ORCHESTRATOR_PATH)
assert SPEC is not None and SPEC.loader is not None
S3 = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(S3)


class S3PjplTrainingAuditTest(unittest.TestCase):
    def test_full_run_keeps_semantic_losses_active_but_disables_pjpl_sweep(self) -> None:
        flags = _semantic_geometry_execution_flags(
            w_semdepth_smooth=0.25,
            w_semdepth_plane=0.25,
            w_boundary_normal=0.01,
            gate_attempt=0,
        )
        self.assertEqual(flags, (True, True, True, False))
        self.assertEqual(
            _semantic_geometry_execution_flags(
                w_semdepth_smooth=0.25,
                w_semdepth_plane=0.25,
                w_boundary_normal=0.01,
                gate_attempt=1,
            ),
            (True, True, True, True),
        )

    def test_main_guards_keep_init_and_effective_config_for_full_but_sweep_gate_only(self) -> None:
        source = inspect.getsource(train_main)
        self.assertRegex(
            source,
            r"if semantic_geometry_enabled:\n\s+if not cfg\.get\(\"load_semantic\"",
        )
        self.assertRegex(
            source,
            r"if semantic_geometry_enabled:\n\s+effective_config\.update\(",
        )
        self.assertRegex(
            source,
            r"if pjpl_gate_sweep_enabled:\n\s+if semantic_region_cache is None:"
            r"\n\s+raise RuntimeError\(\"P-J/P-L final-view audit",
        )

    def test_joint_alpha_ldepth_count_uses_oracle_id_as_address_only(self) -> None:
        alpha = torch.ones(4, 5, dtype=torch.float32)
        alpha[0, 1] = 0.49
        region_ids = torch.tensor(
            [
                [1, 1, 0, 2, 2],
                [1, 1, 0, 2, 2],
                [0, 0, 0, 0, 0],
                [3, 3, 3, 0, 0],
            ],
            dtype=torch.int64,
        )
        cutline = torch.zeros_like(region_ids, dtype=torch.bool)
        cutline[1, 0] = True
        depth_mask = torch.ones_like(region_ids, dtype=torch.bool)
        depth_mask[0, 0] = False
        depth_mask[0, 3] = False
        result = {
            "region_ids": region_ids,
            "cutline_mask": cutline,
            "region_rows": [
                {"region_id": 1, "building_id": "DEBY_LOD2_4907199"},
                {"region_id": 2, "building_id": "4907199"},
                {"region_id": 3, "building_id": "8568391"},
            ],
        }
        latest: dict[tuple[str, str], dict[str, object]] = {}
        _update_pjpl_view_audit(
            latest,
            it=1500,
            view_name="images/view_a.jpg",
            result=result,
            alpha=alpha,
            depth_valid_mask=depth_mask,
            target_buildings={"4907199", "8568391", "8568392"},
            oracle_visible_roof_pixels={"4907199": 100, "8568391": 50},
            alpha_threshold=0.5,
        )

        row = latest[("4907199", "view_a")]
        self.assertEqual(row["source_region_count"], 2)
        self.assertEqual(row["address_pixel_count"], 7)
        self.assertEqual(row["alpha_valid_pixel_count"], 6)
        self.assertEqual(row["ldepth_valid_pixel_count"], 5)
        self.assertEqual(row["alpha_and_ldepth_valid_pixel_count"], 4)
        self.assertEqual(row["raycast_building_id_role"], "region_membership_only")
        self.assertEqual(row["raycast_id_depth_or_height_supervision"], "false")
        self.assertEqual(row["oracle_visible_roof_pixel_count"], 100)

        # A later observation of the same building/view replaces, rather than
        # double-counts, the earlier model state.
        _update_pjpl_view_audit(
            latest,
            it=2490,
            view_name="images/view_a.jpg",
            result=result,
            alpha=torch.zeros_like(alpha),
            depth_valid_mask=depth_mask,
            target_buildings={"4907199", "8568391", "8568392"},
            oracle_visible_roof_pixels={"4907199": 100, "8568391": 50},
            alpha_threshold=0.5,
        )
        self.assertEqual(latest[("4907199", "view_a")]["measurement_step"], 2490)
        self.assertEqual(
            latest[("4907199", "view_a")]["alpha_and_ldepth_valid_pixel_count"], 0
        )

    def test_writer_is_one_sorted_row_per_building_view(self) -> None:
        latest = {
            ("8568391", "v2"): {
                "schema": "jointbuildgs.s3a.pjpl_depth_anchor_views.v2",
                "building_id": "8568391",
                "view": "v2.jpg",
                "view_stem": "v2",
                "measurement_step": 2000,
                "source_region_count": 1,
                "retained_region_present": "true",
                "oracle_visible_roof_pixel_count": 20,
                "visibility_source": "oracle_address_check.by_building.true_roof_total",
                "address_pixel_count": 10,
                "alpha_valid_pixel_count": 9,
                "ldepth_valid_pixel_count": 8,
                "alpha_and_ldepth_valid_pixel_count": 7,
                "alpha_threshold": 0.5,
                "depth_mask_present": "true",
                "depth_valid_source": "batch.depth_mask_existing_L_depth",
                "valid_pixel_rule": "alpha>=0.5 AND existing_L_depth_valid",
                "view_aggregation_snapshot": "latest_active_sample_per_unique_view",
                "region_address_mode": "oracle_class_plus_raycast_building_id",
                "raycast_building_id_role": "region_membership_only",
                "raycast_id_depth_or_height_supervision": "false",
                "cutline_policy": "exclude_instance_cutline_plus_minus_7px",
            }
        }
        with tempfile.TemporaryDirectory() as tmp:
            path = _write_pjpl_view_audit(Path(tmp), latest)
            with path.open(encoding="utf-8") as fh:
                rows = list(csv.DictReader(fh))
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["building_id"], "8568391")
        self.assertEqual(rows[0]["alpha_and_ldepth_valid_pixel_count"], "7")

    def test_oracle_visible_view_without_retained_region_is_explicit_zero(self) -> None:
        latest: dict[tuple[str, str], dict[str, object]] = {}
        _update_pjpl_view_audit(
            latest,
            it=2499,
            view_name="visible_but_small.jpg",
            result={
                "region_ids": torch.zeros(3, 3, dtype=torch.int64),
                "cutline_mask": torch.zeros(3, 3, dtype=torch.bool),
                "region_rows": [],
            },
            alpha=torch.ones(3, 3),
            depth_valid_mask=torch.ones(3, 3, dtype=torch.bool),
            target_buildings={"4907199"},
            oracle_visible_roof_pixels={"4907199": 17},
            alpha_threshold=0.5,
            snapshot_kind="post_probe_full_training_view_sweep",
        )
        row = latest[("4907199", "visible_but_small")]
        self.assertEqual(row["retained_region_present"], "false")
        self.assertEqual(row["oracle_visible_roof_pixel_count"], 17)
        self.assertEqual(row["source_region_count"], 0)
        self.assertEqual(row["address_pixel_count"], 0)
        self.assertEqual(row["alpha_and_ldepth_valid_pixel_count"], 0)

    def test_post_probe_sweep_measures_each_training_view_at_one_state(self) -> None:
        class _Dataset:
            def __getitem__(self, idx: int):
                return {
                    "name": f"v{idx}.jpg",
                    "w2c": torch.eye(4),
                    "K": torch.eye(3),
                    "height": 2,
                    "width": 2,
                    "depth_mask": torch.ones(2, 2, dtype=torch.bool),
                }

        class _Cache:
            def get(self, _view, _height, _width, _device):
                return SimpleNamespace(
                    region_ids=torch.ones(2, 2, dtype=torch.int64),
                    cutline_mask=torch.zeros(2, 2, dtype=torch.bool),
                    metadata={
                        "regions": {
                            "1": {"building_id": "DEBY_LOD2_4907199"}
                        },
                        "oracle_address_check": {
                            "by_building": {
                                "DEBY_LOD2_4907199": {
                                    "true_roof_total": 4,
                                    "eligible_ge256_true_roof": 4,
                                }
                            }
                        },
                    },
                )

        fake_model = SimpleNamespace(active_sh_degree=0)
        with patch(
            "src.stage2.train.render",
            return_value={"alpha": torch.ones(2, 2)},
        ) as render_mock:
            rows = _collect_pjpl_view_audit(
                model=fake_model,
                ds=_Dataset(),
                view_indices=[0, 1, 2],
                device="cpu",
                region_cache=_Cache(),
                target_buildings={"4907199"},
                alpha_threshold=0.5,
                measurement_step=2499,
            )
        self.assertEqual(render_mock.call_count, 3)
        self.assertEqual(len(rows), 3)
        for row in rows.values():
            self.assertEqual(row["measurement_step"], 2499)
            self.assertEqual(row["alpha_and_ldepth_valid_pixel_count"], 4)
            self.assertEqual(
                row["view_aggregation_snapshot"],
                "post_probe_full_training_view_sweep",
            )

    def test_post_probe_sweep_skips_render_when_all_targets_are_invisible(self) -> None:
        class _Dataset:
            def __getitem__(self, _idx: int):
                return {
                    "name": "empty.jpg",
                    "w2c": torch.eye(4),
                    "K": torch.eye(3),
                    "height": 2,
                    "width": 2,
                    "depth_mask": torch.ones(2, 2, dtype=torch.bool),
                }

        class _Cache:
            def get(self, _view, _height, _width, _device):
                return SimpleNamespace(
                    region_ids=torch.zeros(2, 2, dtype=torch.int64),
                    cutline_mask=torch.zeros(2, 2, dtype=torch.bool),
                    metadata={
                        "regions": {},
                        "oracle_address_check": {
                            "by_building": {
                                "DEBY_LOD2_4907199": {
                                    "true_roof_total": 0,
                                    "eligible_ge256_true_roof": 0,
                                }
                            }
                        },
                    },
                )

        with patch("src.stage2.train.render") as render_mock:
            rows = _collect_pjpl_view_audit(
                model=SimpleNamespace(active_sh_degree=0),
                ds=_Dataset(),
                view_indices=[0],
                device="cpu",
                region_cache=_Cache(),
                target_buildings={"4907199"},
                alpha_threshold=0.5,
                measurement_step=2499,
            )
        render_mock.assert_not_called()
        self.assertEqual(rows, {})


class S3PjplGateSummaryTest(unittest.TestCase):
    @staticmethod
    def _row(building_id: str, view_number: int, count: int) -> dict[str, str]:
        view = f"DJI_{building_id}_{view_number:03d}.JPG"
        return {
            "schema": S3.PJPL_VIEW_AUDIT_SCHEMA,
            "building_id": building_id,
            "view": view,
            "view_stem": Path(view).stem,
            "measurement_step": "2499",
            "source_region_count": "1",
            "retained_region_present": "true",
            "oracle_visible_roof_pixel_count": str(max(count, 1)),
            "visibility_source": "oracle_address_check.by_building.true_roof_total",
            "address_pixel_count": str(max(count, 256)),
            "alpha_valid_pixel_count": str(count),
            "ldepth_valid_pixel_count": str(count),
            "alpha_and_ldepth_valid_pixel_count": str(count),
            "alpha_threshold": "0.5",
            "depth_mask_present": "true",
            "depth_valid_source": "batch.depth_mask_existing_L_depth",
            "valid_pixel_rule": "alpha>=0.5 AND existing_L_depth_valid",
            "view_aggregation_snapshot": "post_probe_full_training_view_sweep",
            "region_address_mode": S3.CACHE_ADDRESS_MODE,
            "raycast_building_id_role": "region_membership_only",
            "raycast_id_depth_or_height_supervision": "false",
            "cutline_policy": "exclude_instance_cutline_plus_minus_7px",
        }

    def _write_frozen_attempt1(
        self, root: Path, *, count: int = 10
    ) -> tuple[Path, Path, Path, dict[str, object]]:
        out_dir = root / "attempt1_out"
        raw_path = out_dir / "audit" / S3.PJPL_VIEW_AUDIT_FILENAME
        config_path = root / f"{S3.GATE_RUN}.yaml"
        gate_path = root / "committed_gate.csv"
        S3.dump_yaml(
            config_path,
            {
                "out_dir": str(out_dir),
                "s3_gate_attempt": 1,
            },
        )
        raw_rows = [
            self._row(building_id, view_number, count)
            for building_id in S3.PI_TARGETS
            for view_number in range(3)
        ]
        S3.write_csv(raw_path, raw_rows)
        pjpl = S3.summarize_pjpl_view_rows(raw_rows, active_end=2499)
        self.assertEqual(pjpl["status"], "pass")
        source_sha = S3.sha256_file(raw_path)
        lock_sha = S3.pjpl_attempt1_lock_sha256(
            pjpl, source_csv=raw_path, source_csv_sha256=source_sha
        )
        authority = {
            "run_name": S3.GATE_RUN,
            "active": 1,
            "source_csv": S3.rel(raw_path),
            "pjpl_authority": "attempt1_self",
            "pjpl_frozen_from_run": "",
            "pjpl_attempt1_lock_sha256": lock_sha,
        }
        committed_rows = [{**row, **authority} for row in pjpl["summary_rows"]]
        aggregate = S3.pjpl_summary_values(pjpl)
        committed_rows.append(
            {
                "run_name": S3.GATE_RUN,
                "record_type": "gate_summary",
                "evidence_scope": "canonical",
                **aggregate,
                "pjpl_diagnostic_status": pjpl["status"],
                "pjpl_diagnostic_target_classifications": aggregate[
                    "pjpl_target_classifications"
                ],
                "pjpl_diagnostic_boundary_case_buildings": aggregate[
                    "pjpl_boundary_case_buildings"
                ],
                "pjpl_diagnostic_source_view_rows": pjpl["source_view_rows"],
                "pjpl_source_csv": S3.rel(raw_path),
                "pjpl_source_csv_sha256": source_sha,
                "pjpl_diagnostic_source_csv": S3.rel(raw_path),
                "pjpl_diagnostic_source_csv_sha256": source_sha,
                "pjpl_authority": "attempt1_self",
                "pjpl_frozen_from_run": "",
                "pjpl_attempt1_lock_sha256": lock_sha,
            }
        )
        S3.write_csv(gate_path, committed_rows)
        return config_path, raw_path, gate_path, pjpl

    def test_locked_median_threshold_boundary_and_fixed_collapse_rows(self) -> None:
        rows = []
        for building_id, counts in {
            "4907199": [10, 64, 200],
            "8568391": [0, 10, 20],
            "8568392": [129, 130, 131],
        }.items():
            rows.extend(
                self._row(building_id, view_number, count)
                for view_number, count in enumerate(counts)
            )
        result = S3.summarize_pjpl_view_rows(rows, active_end=2499)
        self.assertEqual(result["status"], "pass")
        self.assertEqual(
            result["classifications"],
            {"4907199": "P-J", "8568391": "P-L", "8568392": "P-J"},
        )
        self.assertEqual(result["boundary_cases"], ["4907199"])
        by_id = {row["building_id"]: row for row in result["summary_rows"]}
        self.assertEqual(by_id["4907199"]["pjpl_view_median_valid_pixel_count"], 64.0)
        for building_id, seed_count in S3.PJPL_FIXED_PJ_TARGETS.items():
            self.assertEqual(by_id[building_id]["pjpl_classification"], "P-J")
            self.assertEqual(by_id[building_id]["pjpl_initial_gaussian_count"], seed_count)
            self.assertEqual(by_id[building_id]["pjpl_lock_status"], "preregistered_fixed")

    def test_contract_rejects_extra_side_channel_and_fewer_than_three_views(self) -> None:
        rows = [self._row("4907199", 0, 64)]
        rows[0]["raycast_depth_target"] = "123.0"
        result = S3.summarize_pjpl_view_rows(rows, active_end=2499)
        self.assertEqual(result["status"], "fail")
        self.assertTrue(any("schema fields mismatch" in error for error in result["errors"]))
        self.assertTrue(any("needs >=3 visible" in error for error in result["errors"]))

    def test_contract_rejects_impossible_intersection_and_missing_depth_mask_counts(self) -> None:
        rows = []
        for building_id in S3.PI_TARGETS:
            rows.extend(self._row(building_id, index, 6) for index in range(3))
        impossible = rows[0]
        impossible["address_pixel_count"] = "10"
        impossible["alpha_valid_pixel_count"] = "8"
        impossible["ldepth_valid_pixel_count"] = "8"
        impossible["alpha_and_ldepth_valid_pixel_count"] = "5"
        no_mask = rows[3]
        no_mask["depth_mask_present"] = "false"
        result = S3.summarize_pjpl_view_rows(rows, active_end=2499)
        self.assertEqual(result["status"], "fail")
        self.assertTrue(any("below set lower bound" in error for error in result["errors"]))
        self.assertTrue(any("missing depth mask" in error for error in result["errors"]))

    def test_half_once_freeze_rebinds_and_rejects_committed_row_tamper(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config_path, _raw_path, gate_path, pjpl = self._write_frozen_attempt1(root)
            committed_state = {"committed_unchanged": True}
            with (
                patch.object(S3, "CSV_GATE_AUDIT", gate_path),
                patch.object(S3, "run_name_config_path", return_value=config_path),
                patch.object(S3, "committed_unchanged", return_value=committed_state),
            ):
                frozen = S3.load_frozen_attempt1_pjpl()
            self.assertEqual(frozen["pjpl"]["classifications"], pjpl["classifications"])
            self.assertEqual(set(frozen["pjpl"]["classifications"].values()), {"P-L"})

            rows = S3.read_csv(gate_path)
            target = next(
                row
                for row in rows
                if row.get("record_type") == "pjpl_classification"
                and row.get("building_id") == S3.PI_TARGETS[0]
            )
            target["pjpl_classification"] = "P-J"
            S3.write_csv(gate_path, rows)
            with (
                patch.object(S3, "CSV_GATE_AUDIT", gate_path),
                patch.object(S3, "run_name_config_path", return_value=config_path),
                patch.object(S3, "committed_unchanged", return_value=committed_state),
                self.assertRaisesRegex(RuntimeError, "differs from raw source"),
            ):
                S3.load_frozen_attempt1_pjpl()

    def test_half_once_gate_keeps_attempt1_classification_and_marks_new_raw_diagnostic(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            attempt1_config, _raw_path, gate_path, _pjpl = self._write_frozen_attempt1(
                root, count=10
            )
            attempt2_config = root / "attempt2.yaml"
            loss_path = root / "loss.csv"
            semantic_path = root / "semantic.csv"
            attempt2_raw = root / "attempt2_pjpl.csv"
            train_log = root / "train.log"
            output = root / "attempt2_report.csv"
            S3.dump_yaml(
                attempt2_config,
                {
                    "max_iter": 2500,
                    "semantic_geometry_warmup": 1500,
                    "loss_grad_audit_every": 100,
                    "semantic_geometry_audit_every": 10,
                    "out_dir": str(root / "attempt2_out"),
                    "w_semdepth_smooth": 0.125,
                    "w_semdepth_plane": 0.125,
                    "w_boundary_normal": 0.005,
                    "s3_gate_attempt": 2,
                    "s3_semdepth_scale": 0.5,
                    "s3_nb_scale": 0.5,
                },
            )
            primary = sorted(S3.PRIMARY_AUDIT_COMPONENTS)
            denominator = float(len(primary))
            loss_rows = [
                {
                    "step": 1500,
                    "component": component,
                    "raw_loss": 1,
                    "weight": 1,
                    "weighted_loss": 1,
                    "weighted_loss_share": 1 / denominator,
                    "grad_norm": 1,
                    "grad_norm_share": 1 / denominator,
                    "grad_status": "",
                    "total_loss": 1,
                    "denominator_role": "primary",
                }
                for component in primary
            ]
            loss_rows.extend(
                {
                    "step": 1500,
                    "component": component,
                    "raw_loss": 1,
                    "weight": 0.125,
                    "weighted_loss": 0.125,
                    "weighted_loss_share": 0.125 / denominator,
                    "grad_norm": 1,
                    "grad_norm_share": 1 / denominator,
                    "grad_status": "",
                    "total_loss": 1,
                    "denominator_role": "audit_only",
                }
                for component in sorted(S3.DETAIL_AUDIT_COMPONENTS)
            )
            S3.write_csv(loss_path, loss_rows)
            S3.write_csv(semantic_path, [{"step": 1500, "building_id": "4907199"}])
            S3.write_csv(
                attempt2_raw,
                [
                    self._row(building_id, view_number, 200)
                    for building_id in S3.PI_TARGETS
                    for view_number in range(3)
                ],
            )
            train_log.write_text("RETURN_CODE=0\n", encoding="utf-8")
            args = SimpleNamespace(
                run_name="test_gate_half_once",
                loss_csv=str(loss_path),
                semantic_csv=str(semantic_path),
                pjpl_csv=str(attempt2_raw),
                train_log=str(train_log),
                output=str(output),
                test_mode=True,
            )

            def config_for(run_name: str) -> Path:
                return attempt1_config if run_name == S3.GATE_RUN else attempt2_config

            with (
                patch.object(S3, "CSV_GATE_AUDIT", gate_path),
                patch.object(S3, "run_name_config_path", side_effect=config_for),
                patch.object(
                    S3,
                    "committed_unchanged",
                    return_value={"committed_unchanged": True},
                ),
                patch.object(S3, "locked_base", return_value={}),
                patch.object(S3, "verify_exact_base"),
                patch.object(S3, "validate_s3_config"),
            ):
                S3.gate_audit(args)
            output_rows = S3.read_csv(output)

        summary = next(
            row for row in output_rows if row.get("record_type") == "gate_summary"
        )
        classifications = [
            row
            for row in output_rows
            if row.get("record_type") == "pjpl_classification"
        ]
        diagnostics = [
            row
            for row in output_rows
            if row.get("record_type") == "pjpl_view_measurement_diagnostic"
        ]
        self.assertEqual(summary["pjpl_authority"], "attempt1_frozen")
        self.assertTrue(summary["pjpl_target_classifications"].endswith("8568392:P-L"))
        self.assertTrue(
            summary["pjpl_diagnostic_target_classifications"].endswith("8568392:P-J")
        )
        self.assertEqual(len(classifications), 6)
        self.assertEqual(
            {row["pjpl_classification"] for row in classifications[:3]}, {"P-L"}
        )
        self.assertEqual(len(diagnostics), 9)

    def test_gate_report_merges_and_hashes_pjpl_source(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config_path = root / "gate.yaml"
            loss_path = root / "loss.csv"
            semantic_path = root / "semantic.csv"
            pjpl_path = root / "pjpl.csv"
            train_log = root / "train.log"
            output = root / "gate_report.csv"
            S3.dump_yaml(
                config_path,
                {
                    "max_iter": 2500,
                    "semantic_geometry_warmup": 1500,
                    "loss_grad_audit_every": 100,
                    "semantic_geometry_audit_every": 10,
                    "out_dir": str(root / "out"),
                    "w_semdepth_smooth": 0.25,
                    "w_semdepth_plane": 0.25,
                    "w_boundary_normal": 0.01,
                    "s3_gate_attempt": 1,
                    "s3_semdepth_scale": 1.0,
                    "s3_nb_scale": 1.0,
                },
            )
            primary = sorted(S3.PRIMARY_AUDIT_COMPONENTS)
            denominator = float(len(primary))
            loss_rows = [
                {
                    "step": 1500,
                    "component": component,
                    "raw_loss": 1,
                    "weight": 1,
                    "weighted_loss": 1,
                    "weighted_loss_share": 1 / denominator,
                    "grad_norm": 1,
                    "grad_norm_share": 1 / denominator,
                    "grad_status": "",
                    "total_loss": 1,
                    "denominator_role": "primary",
                }
                for component in primary
            ]
            loss_rows.extend(
                {
                    "step": 1500,
                    "component": component,
                    "raw_loss": 1,
                    "weight": 0.25,
                    "weighted_loss": 0.25,
                    "weighted_loss_share": 0.25 / denominator,
                    "grad_norm": 1,
                    "grad_norm_share": 1 / denominator,
                    "grad_status": "",
                    "total_loss": 1,
                    "denominator_role": "audit_only",
                }
                for component in sorted(S3.DETAIL_AUDIT_COMPONENTS)
            )
            S3.write_csv(loss_path, loss_rows)
            S3.write_csv(
                semantic_path,
                [{"step": 1500, "building_id": "4907199"}],
            )
            pjpl_rows = []
            for building_id in S3.PI_TARGETS:
                pjpl_rows.extend(
                    self._row(building_id, view_number, 64)
                    for view_number in range(3)
                )
            S3.write_csv(pjpl_path, pjpl_rows)
            train_log.write_text("RETURN_CODE=0\n", encoding="utf-8")
            args = SimpleNamespace(
                run_name="test_gate",
                loss_csv=str(loss_path),
                semantic_csv=str(semantic_path),
                pjpl_csv=str(pjpl_path),
                train_log=str(train_log),
                output=str(output),
                test_mode=True,
            )
            with (
                patch.object(S3, "run_name_config_path", return_value=config_path),
                patch.object(S3, "locked_base", return_value={}),
                patch.object(S3, "verify_exact_base"),
                patch.object(S3, "validate_s3_config"),
            ):
                S3.gate_audit(args)
            rows = S3.read_csv(output)
            pjpl_hash = S3.sha256_file(pjpl_path)
        summaries = [row for row in rows if row["record_type"] == "gate_summary"]
        classes = [row for row in rows if row["record_type"] == "pjpl_classification"]
        self.assertEqual(len(summaries), 1)
        self.assertEqual(summaries[0]["pjpl_classification_status"], "pass")
        self.assertEqual(summaries[0]["pjpl_source_csv_sha256"], pjpl_hash)
        self.assertEqual(len(classes), 6)


if __name__ == "__main__":
    unittest.main()
