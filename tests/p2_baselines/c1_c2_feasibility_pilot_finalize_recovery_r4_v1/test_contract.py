from __future__ import annotations

import copy
import hashlib
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from scripts.p2_baselines.c1_c2_feasibility_pilot_finalize_recovery_r4_v1 import contract
from scripts.p2_baselines.c1_c2_feasibility_pilot_v1 import contract as source_contract


NATIVE_CITYJSONSEQ = (
    b'{"CityObjects":{},"transform":{"scale":[0.001,0.001,0.001],"translate":[690000,5335000,0]},"type":"CityJSON","version":"2.0","vertices":[]}\n'
    b'{"CityObjects":{"building":{"geometry":[{"boundaries":[[[[4,5,6,7]],[[0,1,5,4]],[[1,2,6,5]],[[2,3,7,6]],[[3,0,4,7]],[[0,3,2,1]]]],"lod":"2.2","semantics":{"surfaces":[{"type":"RoofSurface"},{"type":"WallSurface"},{"type":"GroundSurface"}],"values":[[0,1,1,1,1,2]]},"type":"Solid"}],"type":"Building"}},"id":"feature","type":"CityJSONFeature","vertices":[[0,0,0],[2000000,0,0],[2000000,2000000,0],[0,2000000,0],[0,0,10000],[2000000,0,10000],[2000000,2000000,10000],[0,2000000,10000]]}\n'
)
NATIVE_CITYJSONSEQ_SHA256 = "e122fcca3c62f7960ecdc433a5b091bca30ad9bd0a701cd5944f6b78727d7c8b"


def _record(relative: str, data: bytes) -> dict[str, object]:
    return {
        "path": relative,
        "bytes": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
    }


class FinalizeRecoveryContractTest(unittest.TestCase):
    maxDiff = None

    @staticmethod
    def _commit(repo: Path, message: str) -> str:
        subprocess.run(["git", "-C", str(repo), "add", "-A"], check=True)
        subprocess.run(["git", "-C", str(repo), "commit", "-q", "-m", message], check=True)
        return subprocess.run(
            ["git", "-C", str(repo), "rev-parse", "HEAD"],
            check=True, capture_output=True, text=True,
        ).stdout.strip()

    def test_exact_native_cityjsonseq_fixture_and_parser(self) -> None:
        self.assertEqual(NATIVE_CITYJSONSEQ_SHA256, hashlib.sha256(NATIVE_CITYJSONSEQ).hexdigest())
        triangles = contract.roof_triangles_from_cityjsonseq("native.city.jsonl", NATIVE_CITYJSONSEQ)
        self.assertEqual(2, len(triangles))
        self.assertEqual([690000.0, 5335000.0, 10.0], triangles[0][0].tolist())
        header, feature = NATIVE_CITYJSONSEQ.splitlines()
        second = feature.replace(b'"id":"feature"', b'"id":"feature-2"')
        multiple = header + b"\n" + feature + b"\n" + second + b"\n"
        self.assertEqual(4, len(contract.roof_triangles_from_cityjsonseq("native-multiple.city.jsonl", multiple)))

    def test_native_cityjsonseq_strict_negatives(self) -> None:
        header, feature = NATIVE_CITYJSONSEQ.splitlines()
        invalid = {
            "feature-before-header": feature + b"\n" + header + b"\n",
            "duplicate-header": header + b"\n" + header + b"\n" + feature + b"\n",
            "missing-cityobjects": header.replace(b'"CityObjects":{},', b"") + b"\n" + feature + b"\n",
            "nonempty-header": header.replace(b'"vertices":[]', b'"vertices":[[0,0,0]]') + b"\n" + feature + b"\n",
            "empty-feature": header + b"\n" + feature[:feature.index(b'"vertices":')] + b'"vertices":[]}' + b"\n",
            "bad-transform": header.replace(b'"scale":[0.001,0.001,0.001]', b'"scale":[0.001,0.001]') + b"\n" + feature + b"\n",
            "feature-transform": header + b"\n" + feature.replace(
                b'"type":"CityJSONFeature"',
                b'"transform":{"scale":[1,1,1],"translate":[0,0,0]},"type":"CityJSONFeature"',
            ) + b"\n",
            "bad-index": header + b"\n" + feature.replace(b"[[[4,5,6,7]]", b"[[[4,5,6,9]]") + b"\n",
            "no-roof": header + b"\n" + feature.replace(b'"RoofSurface"', b'"WallSurface"') + b"\n",
            "missing-semantics": header + b"\n" + feature.replace(
                b',"semantics":{"surfaces":[{"type":"RoofSurface"},{"type":"WallSurface"},{"type":"GroundSurface"}],"values":[[0,1,1,1,1,2]]}',
                b"",
            ) + b"\n",
            "malformed-semantics": header + b"\n" + feature.replace(
                b'"values":[[0,1,1,1,1,2]]', b'"values":[0]',
            ) + b"\n",
        }
        for name, data in invalid.items():
            with self.subTest(name=name), self.assertRaises(RuntimeError):
                contract.roof_triangles_from_cityjsonseq("native.city.jsonl", data)

    def test_point_count_is_derived_without_opening_las(self) -> None:
        valid = {"path": "operations/C2_MVS/u/work/input.las", "bytes": 227 + 34 * 123, "sha256": "a" * 64}
        self.assertEqual(123, contract._point_count_from_record(valid))
        for bad in (
            {**valid, "bytes": valid["bytes"] + 1},
            {**valid, "path": "operations/C2_MVS/u/work/input.laz"},
            {**valid, "sha256": "not-a-digest"},
            {**valid, "bytes": 227},
        ):
            with self.assertRaises(RuntimeError):
                contract._point_count_from_record(bad)

    def test_source_manifest_reader_enforces_allowlist_identity_and_single_read(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "control").mkdir()
            data = b'{"status":"PREPARED"}\n'
            (root / "control/prepared.json").write_bytes(data)
            config = {
                "source_manifest_allowlist": {
                    "exact_paths": ["control/prepared.json"],
                    "path_patterns": [],
                    "expected_files_read": 1,
                    "maximum_files_read": 1,
                    "maximum_bytes_read": len(data),
                }
            }
            expected = _record("control/prepared.json", data)
            reader = contract.SourceManifestReader(root, config, {"control/prepared.json": expected})
            self.assertEqual(data, reader.read("control/prepared.json", expected))
            self.assertEqual(data, reader.read("control/prepared.json", expected))
            self.assertEqual(1, len(reader.records))
            self.assertEqual(len(data), reader.total_bytes)
            for path in ("../control/prepared.json", "control/other.json", "/control/prepared.json"):
                with self.assertRaises(RuntimeError):
                    reader.read(path)
            with self.assertRaises(RuntimeError):
                contract.SourceManifestReader(root, config, {"control/prepared.json": expected}).read(
                    "control/prepared.json", {**expected, "sha256": "b" * 64},
                )

    def test_accepted_receipt_must_bind_exact_experiment_host_rehash_manifest(self) -> None:
        config = copy.deepcopy(contract.load_config())
        prefix = config["source_r3"]["external_namespace"]
        frozen = contract._frozen_source_manifest(config)
        accepted = {"artifacts": {"records": [{
            "uri": prefix + relative,
            "bytes": record["bytes"],
            "sha256": record["sha256"],
            "verification_method": "sha256_rehash",
            "verified_by": "experiment_host",
            "verified_at": "2026-08-02T12:30:00+09:00",
        } for relative, record in sorted(frozen.items())]}}
        manifest = contract._accepted_source_manifest(accepted, config)
        self.assertEqual(frozen, manifest)
        for field, value in (
            ("verification_method", "closed_attestation_reuse"),
            ("verified_by", "work_host"),
            ("uri", "artifact://JointBuildGS/original/Images.zip"),
        ):
            bad = copy.deepcopy(accepted)
            bad["artifacts"]["records"][0][field] = value
            with self.assertRaises(RuntimeError):
                contract._accepted_source_manifest(bad, config)

    def test_git_authority_binds_direct_source_activation_offer_accept_chain(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary) / "repo"
            repo.mkdir()
            subprocess.run(["git", "init", "-q", str(repo)], check=True)
            subprocess.run(["git", "-C", str(repo), "config", "user.name", "R4 Test"], check=True)
            subprocess.run(["git", "-C", str(repo), "config", "user.email", "r4@example.invalid"], check=True)
            packet = repo / contract.PACKET_PATH
            packet.parent.mkdir(parents=True)
            packet.write_text("- status: `DRAFT_NOT_EXECUTION_AUTHORITY`\n- user_approval: `NOT_YET_ACTIVATED`\n- source_commit: `PENDING`\n", encoding="utf-8")
            source_commit = self._commit(repo, "source")
            project_image = contract.load_config()["project_image_id"]
            packet.write_text(
                "\n".join((
                    "- status: `APPROVED_FOR_EXECUTION`",
                    "- user_approval: `APPROVED_FOR_EXECUTION`",
                    f"- source_commit: `{source_commit}`",
                    f"- project_image_id: `{project_image}`",
                    f"- run_id: `{contract.RUN_ID}`",
                    f"- execution_mode: `{contract.EXECUTION_MODE}`",
                    "",
                )), encoding="utf-8",
            )
            activation_commit = self._commit(repo, "activation")
            handoff = repo / f"artifacts/manifests/handoffs/{contract.HANDOFF_ID}"
            handoff.mkdir(parents=True)
            offered_path = handoff / "000-offered.json"
            offered_path.write_bytes(source_contract.canonical_json_bytes({
                "state": "offered",
                "commits": {"base_main": activation_commit, "offered_head": "SELF"},
            }))
            offered_commit = self._commit(repo, "offered")
            accepted_path = handoff / "100-accepted.json"
            accepted = {
                "state": "accepted",
                "previous_receipt": {
                    "path": f"artifacts/manifests/handoffs/{contract.HANDOFF_ID}/000-offered.json",
                    "sha256": hashlib.sha256(offered_path.read_bytes()).hexdigest(),
                },
                "commits": {"base_main": activation_commit, "offered_head": offered_commit},
            }
            accepted_path.write_bytes(source_contract.canonical_json_bytes(accepted))
            accepted_commit = self._commit(repo, "accepted")
            subprocess.run(["git", "-C", str(repo), "update-ref", "refs/remotes/origin/main", accepted_commit], check=True)
            lineage = contract._validate_r4_git_authority(
                accepted_path, accepted, source_commit=source_commit, accepted_commit=accepted_commit,
                project_image_id=project_image, run_id=contract.RUN_ID, repo_root=repo,
            )
            self.assertEqual({
                "source_commit": source_commit,
                "activation_commit": activation_commit,
                "offered_commit": offered_commit,
                "accepted_commit": accepted_commit,
            }, lineage)
            with self.assertRaisesRegex(RuntimeError, "accepted receipt commit"):
                contract._validate_r4_git_authority(
                    accepted_path, accepted, source_commit=source_commit, accepted_commit=offered_commit,
                    project_image_id=project_image, run_id=contract.RUN_ID, repo_root=repo,
                )

    def _build_sealed_r3(self, root: Path) -> tuple[Path, Path, dict[str, bytes]]:
        config = contract.load_config()
        source = config["source_r3"]
        store = source_contract.AddOnceStore(root)
        roster = source_contract.read_csv(source_contract.REPO / config["result"]["development_roster_path"])
        score_scope = source_contract.read_csv(source_contract.REPO / config["result"]["development_score_scope_path"])

        c1_unit = "C1_COMPONENT_SHARED|C1_R_DERIVED_SHARED"
        c2_units = [f"C2_COMPONENT_{index}|C2_R_DERIVED_{index}" for index in range(6)]
        unit_ids = [c1_unit, *c2_units]
        component_by_unit = {unit_id: f"COMPONENT_{index}" for index, unit_id in enumerate(unit_ids)}
        units = []
        components = []
        for index, unit_id in enumerate(unit_ids):
            condition = "C1_L_upper" if index == 0 else "C2_MVS"
            output_directory = f"operations/{condition}/unit_{index}/work/out"
            components.append({"component_id": component_by_unit[unit_id], "condition_id": condition, "point_count": 100 + index})
            units.append({
                "operation_unit_id": unit_id,
                "condition_id": condition,
                "component_id": component_by_unit[unit_id],
                "output_directory": output_directory,
                "input": {
                    "path": f"operations/{condition}/unit_{index}/work/input.las",
                    "bytes": 227 + 34 * (1000 + index),
                    "sha256": f"{index + 1:x}" * 64,
                },
                "reference_or_bbox_used_to_derive_input": False,
                "stable_id_used_to_derive_input": False,
            })

        unassociated_id = "DEBY_LOD2_4907183"
        mappings = []
        c2_index = 0
        for item in roster:
            mappings.append({
                "building_id": item["stable_id"], "group_id": item["group_id"], "split": "development",
                "method_id": "C1_L_upper", "component_id": component_by_unit[c1_unit],
                "operation_unit_id": c1_unit, "reference_cell_count": 0,
                "component_overlap_reference_cells": 0,
                "association_role": "SCORE_IDENTITY_ONLY_AFTER_FROZEN_CONDITION_GEOMETRY",
                "pre_roofer_failure": None,
            })
            if item["stable_id"] == unassociated_id:
                component_id = unit_id = None
            else:
                unit_id = c2_units[c2_index % len(c2_units)]
                component_id = component_by_unit[unit_id]
                c2_index += 1
            mappings.append({
                "building_id": item["stable_id"], "group_id": item["group_id"], "split": "development",
                "method_id": "C2_MVS", "component_id": component_id, "operation_unit_id": unit_id,
                "reference_cell_count": 0, "component_overlap_reference_cells": 0,
                "association_role": "SCORE_IDENTITY_ONLY_AFTER_FROZEN_CONDITION_GEOMETRY",
                "pre_roofer_failure": "NO_OVERLAPPING_C2_COMPONENT" if unit_id is None else None,
            })

        cells = []
        for scope in score_scope:
            count = int(scope["expected_score_cells"])
            x = (float(scope["bbox_min_x"]) + float(scope["bbox_max_x"])) / 2
            y = (float(scope["bbox_min_y"]) + float(scope["bbox_max_y"])) / 2
            for index in range(count):
                cells.append({
                    "stable_id": scope["stable_id"], "group_id": scope["group_id"],
                    "patch_id": "UASPATCH_" + f"{index:020x}"[-20:], "flat_index": index,
                    "cell_ix": index, "cell_iy": 0, "cell_x": x, "cell_y": y,
                    "top_z": 5.0, "normal_x": 0.0, "normal_y": 0.0, "normal_z": 1.0,
                })
        self.assertEqual(21714, len(cells))
        counts = {row["stable_id"]: int(row["expected_score_cells"]) for row in score_scope}
        for mapping in mappings:
            mapping["reference_cell_count"] = counts[mapping["building_id"]]
            mapping["component_overlap_reference_cells"] = 0 if mapping["operation_unit_id"] is None else counts[mapping["building_id"]]

        component_record = store.add("freeze/condition_components_v1.jsonl", source_contract.jsonl_bytes(components))
        mapping_record = store.add("freeze/development_score_association_with_pre_roofer_status_v1.jsonl", source_contract.jsonl_bytes(mappings))
        cell_record = store.add("freeze/development_score_cells_v1.jsonl", source_contract.jsonl_bytes(cells))
        unit_record = store.add("freeze/execution_units_v1.jsonl", source_contract.jsonl_bytes(units))
        store.add_json("checkpoints/120-condition_components_and_r_derived_frozen.json", {
            "stage": "condition_components_and_all_r_derived_frozen",
            "reference_score_cells_opened_before_checkpoint": False,
        })
        store.add_json(source["synthetic_smoke_path"], {
            "status": "PASS", "G0_generated": True, "G1_schema_semantic": True, "scientific_verdict": None,
        })
        store.add_json(source["preselected_cases_path"], {
            "chosen_before_score_outcomes": True, "cases": source_contract.representative_cases(roster),
        })
        for index, unit in enumerate(units):
            sequence_path = f"{unit['output_directory']}/result.city.jsonl"
            sequence_record = store.add(sequence_path, NATIVE_CITYJSONSEQ)
            store.add_json(f"operation_records/{source_contract._unit_slug(unit['operation_unit_id'])}/final_v1.json", {
                "operation_unit_id": unit["operation_unit_id"], "condition_id": unit["condition_id"],
                "component_id": unit["component_id"], "status": "COMPLETE", "attempt_count": 1,
                "retry_count": 0, "runtime_seconds": 1.0 + index, "peak_memory_bytes": None,
                "peak_memory_unavailable_reason": "ROOFER_IMAGE_GNU_TIME_UNAVAILABLE_VERIFIED_IMMUTABLE_IMAGE",
                "output_bytes": len(NATIVE_CITYJSONSEQ), "output_records": [sequence_record],
                "G0_generated": True, "G1_schema_semantic": True, "G1_failure_reasons": [],
                "geometry_ring_diagnostic": True, "failure_reasons": [], "scientific_verdict": None,
            })
        store.add_json(source["prepared_path"], {
            "status": "PREPARED", "source_commit": source["source_commit"], "run_id": source["run_id"],
            "operation_id": source["operation_id"], "result_rows": 102, "unique_execution_units": 7,
            "duplicate_roofer_calculations_prevented": 94, "validation_payload_accesses": 0,
            "held_out_payload_accesses": 0, "raw_dim_dense_accesses": 0, "scientific_verdict": None,
            "execution_authority": {"accepted_commit": source["accepted_commit"]},
            "condition_components": component_record, "development_score_association": mapping_record,
            "development_score_cells": cell_record, "execution_units": unit_record,
            "input_records": {"sealed_r3": True},
        })
        closed_receipt = root.parent / "r3-300-closed.json"
        closed_receipt.write_bytes(subprocess.run(
            ["git", "-C", str(contract.REPO), "show", f"{source['closed_commit']}:{source['closed_receipt_path']}"],
            check=True, capture_output=True,
        ).stdout)
        snapshot = {
            path.relative_to(root).as_posix(): path.read_bytes()
            for path in root.rglob("*") if path.is_file()
        }
        self.assertEqual(22, len(snapshot))
        accepted_records = [{
            "uri": source["external_namespace"] + relative,
            "bytes": len(data),
            "sha256": hashlib.sha256(data).hexdigest(),
            "verification_method": "sha256_rehash",
            "verified_by": "experiment_host",
            "verified_at": "2026-08-02T12:30:00+09:00",
        } for relative, data in sorted(snapshot.items())]
        accepted_receipt = root.parent / "r4-100-accepted.json"
        accepted_receipt.write_bytes(source_contract.canonical_json_bytes({
            "schema": "jointbuildgs.two_host_handoff.v1", "template_only": False,
            "handoff_id": contract.HANDOFF_ID, "task_id": contract.TASK_ID,
            "created_at": "2026-08-02T12:30:00+09:00", "direction": "work_to_experiment",
            "sender_role": "work_host", "receiver_role": "experiment_host", "state": "accepted",
            "previous_receipt": {"path": f"artifacts/manifests/handoffs/{contract.HANDOFF_ID}/000-offered.json", "sha256": "a" * 64},
            "transport": {"mode": "serialized_main", "branch": "main", "target_branch": "main", "exclusive_writer_ack": True},
            "commits": {"base_main": "1" * 40, "offered_head": "2" * 40, "receipt_head": "SELF"},
            "scope": {"allowed_paths": ["docs/experiments/p2/test"], "protected_paths": [], "dirty_wip": False, "snapshot_manifest": None},
            "verification": {
                "level": "artifact_verified", "verifier_role": "experiment_host",
                "docker_image_digest": contract.load_config()["project_image_id"],
                "commands": [f"bind finalization run_id={contract.RUN_ID} execution_mode={contract.EXECUTION_MODE}"],
                "tests": [{"name": "exact 22-record pre/post acceptance rehash", "passed": 2, "failed": 0}],
            },
            "artifacts": {
                "required_for_task": True,
                "availability": {"work_host": "manifest_only", "experiment_host": "verified_local"},
                "records": accepted_records,
            },
            "scientific": {"technical_state": "pending", "scientific_verdict": None, "promotion_status": "not_requested"},
            "receiver_ack": {"role": "experiment_host", "accepted_at": "2026-08-02T12:30:00+09:00", "status": "accepted", "issue": None},
        }))
        return closed_receipt, accepted_receipt, snapshot

    def test_full_finalize_reuses_sealed_r3_and_preserves_102_row_identity(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            source_root = base / "sealed-r3"
            destination_root = base / "fresh-r4"
            repository = base / "repository"
            repository.mkdir()
            subprocess.run(["git", "init", "-q", str(repository)], check=True)
            subprocess.run(["git", "-C", str(repository), "config", "user.name", "R4 Test"], check=True)
            subprocess.run(["git", "-C", str(repository), "config", "user.email", "r4@example.invalid"], check=True)
            (repository / ".gitkeep").write_text("", encoding="utf-8")
            subprocess.run(["git", "-C", str(repository), "add", ".gitkeep"], check=True)
            subprocess.run(["git", "-C", str(repository), "commit", "-q", "-m", "fixture"], check=True)
            accepted_commit = subprocess.run(
                ["git", "-C", str(repository), "rev-parse", "HEAD"],
                check=True, capture_output=True, text=True,
            ).stdout.strip()
            closed, accepted, before = self._build_sealed_r3(source_root)
            toy_manifest = {
                relative: _record(relative, data) for relative, data in before.items()
            }
            lineage = {"source_commit": "c" * 40, "activation_commit": "1" * 40, "offered_commit": "2" * 40, "accepted_commit": accepted_commit}
            with (
                mock.patch.object(contract, "_frozen_source_manifest", return_value=toy_manifest),
                mock.patch.object(contract, "_accepted_source_manifest", return_value=toy_manifest),
                mock.patch.object(contract, "_validate_r4_git_authority", return_value=lineage),
            ):
                result = contract.finalize_recovery(
                    source_contract.AddOnceStore(destination_root),
                    source_root=source_root,
                    source_closed_receipt_path=closed,
                    accepted_receipt_path=accepted,
                    source_commit="c" * 40,
                    accepted_commit=accepted_commit,
                    project_image_id=contract.load_config()["project_image_id"],
                    run_id=contract.RUN_ID,
                    handoff_id=contract.HANDOFF_ID,
                    artifact_root_token="artifact://JointBuildGS",
                )
            after = {
                path.relative_to(source_root).as_posix(): path.read_bytes()
                for path in source_root.rglob("*") if path.is_file()
            }
            rows = source_contract.parse_jsonl(
                source_contract.AddOnceStore(destination_root).read_verified(result["metrics"]),
            )
            reuse = json.loads((destination_root / "control/source_reuse_manifest_v1.json").read_bytes())

            self.assertEqual(before, after)
            self.assertEqual(102, len(rows))
            self.assertEqual(102, len({(row["building_id"], row["method_id"]) for row in rows}))
            self.assertTrue(all(row["run_id"] == contract.SOURCE_R3_RUN_ID for row in rows))
            self.assertTrue(all(row["operation_id"] == contract.load_config()["source_r3"]["operation_id"] for row in rows))
            self.assertEqual(contract.RUN_ID, result["finalization_run_id"])
            self.assertNotEqual(result["finalization_operation_id"], rows[0]["operation_id"])
            unassociated = [row for row in rows if row["operation_unit_id"] is None]
            self.assertEqual([("DEBY_LOD2_4907183", "C2_MVS", 14)], [
                (row["building_id"], row["method_id"], row["metrics"]["reference_cell_count"])
                for row in unassociated
            ])
            self.assertFalse(unassociated[0]["G0_generated"])
            self.assertEqual(0, reuse["source_operation_las_reads_or_hashes"])
            self.assertEqual(0, reuse["original_scientific_source_reads_or_hashes"])
            self.assertEqual(0, reuse["roofer_invocations"])
            self.assertEqual(len(reuse["source_records"]), len({row["path"] for row in reuse["source_records"]}))
            self.assertTrue(all(row["full_read_and_digest_passes"] == 1 for row in reuse["source_records"]))
            promoted = contract.promote_recovery(
                source_contract.AddOnceStore(destination_root), repository, accepted_commit,
            )
            metric_csv = repository / contract.load_config()["result"]["promotion_prefix"] / "building_method_metrics_v1.csv"
            header = metric_csv.read_text(encoding="utf-8").splitlines()[0]
            self.assertIn("height_error_signed_mean_m", header)
            self.assertIn("normal_angular_error_p95_deg", header)
            self.assertEqual(102, promoted["result_rows"])
            self.assertEqual(0, promoted["r4_roofer_invocations"])
            self.assertEqual(6, len(promoted["promoted_records"]))
            promoted_fast = contract.promote_recovery(
                source_contract.AddOnceStore(destination_root), repository, accepted_commit,
            )
            self.assertTrue(promoted_fast["fast_path"])
            self.assertEqual(0, promoted_fast["source_r3_reopens"])
            self.assertEqual(0, promoted_fast["new_writes"])
            fast = contract.finalize_recovery(
                source_contract.AddOnceStore(destination_root), source_root=Path("missing"),
                source_closed_receipt_path=Path("missing"), accepted_receipt_path=Path("missing"),
                source_commit="0" * 40, accepted_commit="0" * 40, project_image_id="missing",
                run_id="missing", handoff_id="missing", artifact_root_token="missing",
            )
            self.assertTrue(fast["fast_path"])
            self.assertEqual(0, fast["source_r3_reopens"])
            self.assertEqual(0, fast["new_writes"])

    def test_started_or_partial_destination_is_terminal_without_retry(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            destination = source_contract.AddOnceStore(Path(temporary))
            destination.add_json("control/finalize_started_v1.json", {"status": "STARTED_ADD_ONCE_NO_RETRY"})
            with self.assertRaisesRegex(RuntimeError, "retry is prohibited"):
                contract.finalize_recovery(
                    destination, source_root=Path("missing"), source_closed_receipt_path=Path("missing"),
                    accepted_receipt_path=Path("missing"), source_commit="a" * 40,
                    accepted_commit="b" * 40, project_image_id="sha256:" + "c" * 64,
                    run_id="run", handoff_id=contract.HANDOFF_ID,
                    artifact_root_token="artifact://JointBuildGS",
                )

    def test_fresh_invocation_rejects_unfrozen_run_id_before_receipt_or_source_access(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            destination = source_contract.AddOnceStore(Path(temporary) / "fresh-r4")
            with self.assertRaisesRegex(RuntimeError, "invocation identity mismatch"):
                contract.finalize_recovery(
                    destination, source_root=Path(temporary) / "missing-r3",
                    source_closed_receipt_path=Path("missing"), accepted_receipt_path=Path("missing"),
                    source_commit="a" * 40, accepted_commit="b" * 40,
                    project_image_id=contract.load_config()["project_image_id"],
                    run_id="ARBITRARY-RUN", handoff_id=contract.HANDOFF_ID,
                    artifact_root_token="artifact://JointBuildGS",
                )

    def test_cli_wrapper_and_config_expose_finalize_only_isolated_surface(self) -> None:
        root = contract.REPO
        cli = (root / "scripts/p2_baselines/c1_c2_feasibility_pilot_finalize_recovery_r4_v1/run_recovery.py").read_text()
        wrapper = (root / "scripts/p2_baselines/c1_c2_feasibility_pilot_finalize_recovery_r4_v1/run_finalize_recovery_host.sh").read_text()
        config = contract.load_config()
        self.assertIn('sub.add_parser("recover-finalize")', cli)
        self.assertIn('sub.add_parser("promote")', cli)
        self.assertIn('sub.add_parser("authority-preflight")', cli)
        for prohibited in ('sub.add_parser("prepare-scientific")', 'sub.add_parser("next-attempt")', "3dgi/roofer"):
            self.assertNotIn(prohibited, cli)
        self.assertIn('${R3_ROOT}:/r3_source:ro', wrapper)
        self.assertIn('${R4_ROOT}:/r4_output:rw', wrapper)
        self.assertEqual(1, wrapper.count('${R3_ROOT}:/r3_source:ro'))
        self.assertNotIn("validate_two_host_handoff.py", wrapper)
        self.assertIn("run_recovery.py promote", wrapper)
        self.assertIn('${R4_ROOT}:/r4_output:ro', wrapper)
        for prohibited in ("ROOFER_IMAGE", "/pilot_inputs", "Images.zip", "OPF.zip", "dim_dense.ply"):
            self.assertNotIn(prohibited, wrapper)
        self.assertTrue(config["result"]["promotion_prefix"].endswith("finalize_recovery_r4_v1"))
        self.assertTrue(config["result"]["manifest_path"].endswith("finalize_recovery_r4_v1/technical_result_manifest_v1.json"))
        self.assertEqual(contract.RUN_ID, config["run_id"])
        self.assertEqual(contract.EXECUTION_MODE, config["execution_mode"])
        frozen = contract._frozen_source_manifest(config)
        self.assertEqual(22, len(frozen))
        self.assertEqual(12920322, sum(record["bytes"] for record in frozen.values()))
        self.assertTrue(all(not path.endswith(".las") for path in frozen))
        self.assertIsNone(config["scientific_verdict"])


if __name__ == "__main__":
    unittest.main()
