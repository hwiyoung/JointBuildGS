#!/usr/bin/env python3
"""Contract tests for the two-GPU A-prime v3 continuation."""
from __future__ import annotations

import copy
import fcntl
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock


REPO = Path(__file__).resolve().parents[2]
DRIVER = REPO / "phases/p2-gsjso/scripts/fusion_w1/fusion_w1_aprime_queue_continuation_v3_20260727.py"
CONFIG = REPO / "phases/p2-gsjso/configs/fusion_w1/fusion_w1_aprime_queue_continuation_v3_20260727.json"
WRAPPER = REPO / "phases/p2-gsjso/scripts/fusion_w1/run_fusion_w1_aprime_queue_continuation_v3_20260727.sh"

spec = importlib.util.spec_from_file_location("aprime_v3_under_test", DRIVER)
if spec is None or spec.loader is None:
    raise RuntimeError("cannot import v3 driver")
v3 = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = v3
spec.loader.exec_module(v3)


class V3ContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.config = v3.load_config(CONFIG)
        cls.source, _record = v3.source_plan(cls.config)
        cls.entries, cls.pairs = v3.build_v3_plan(cls.source["entries"])

    def test_01_config_shape(self) -> None:
        self.assertEqual(self.config["schema"], v3.CONFIG_SCHEMA)
        self.assertEqual(self.config["resources"]["maximum_concurrent_training"], 2)
        self.assertTrue(self.config["resources"]["readout_global_serial"])
        self.assertFalse(self.config["resources"]["readout_concurrent_with_training"])
        self.assertTrue(
            self.config["outputs"]["root"].endswith(
                "unattended_queue_continuation_v3_repair1"
            )
        )

    def test_02_all_locked_sha256_match(self) -> None:
        for record in self.config["locked_inputs"].values():
            self.assertEqual(v3.sha256_file(v3.repo_path(record["path"])), record["sha256"])

    def test_03_plan_population(self) -> None:
        self.assertEqual(len(self.entries), 20)
        self.assertEqual(sum(not row["reuse_source_v2"] for row in self.entries), 19)
        self.assertEqual(len(self.pairs), 11)
        self.assertEqual(sum(len(pair["members"]) for pair in self.pairs), 19)

    def test_04_pairs_never_cross_stage(self) -> None:
        for pair in self.pairs:
            self.assertLessEqual(len(pair["members"]), 2)
            self.assertEqual({member["stage_key"] for member in pair["members"]}, {pair["stage_key"]})

    def test_05_lane_assignment_is_deterministic(self) -> None:
        for pair in self.pairs:
            self.assertEqual([member["physical_gpu"] for member in pair["members"]], list(range(len(pair["members"]))))

    def test_06_stage_pair_counts(self) -> None:
        counts = {stage: sum(pair["stage_key"] == stage for pair in self.pairs) for stage in ("aprime_r1", "aprime_r2", "B_r1")}
        self.assertEqual(counts, {"aprime_r1": 4, "aprime_r2": 5, "B_r1": 2})

    def test_07_source_reuse_is_exact(self) -> None:
        records = v3.verify_source_reuse(self.config, self.entries[0])
        self.assertEqual(set(records), {"stage_record", "training_complete", "readout_complete", "primary_score"})

    def test_08_operational_override_only_two_keys(self) -> None:
        module, base, _path = v3.training_context(self.config)
        del module
        before = copy.deepcopy(base)
        effective, changes = v3.operational_training_config(self.config, base, 0)
        self.assertEqual(base, before)
        self.assertEqual(set(changes), {"outputs.foreground_lock", "launch_contract.writable_environment_root"})
        restored = copy.deepcopy(effective)
        restored["outputs"]["foreground_lock"] = base["outputs"]["foreground_lock"]
        restored["launch_contract"]["writable_environment_root"] = base["launch_contract"]["writable_environment_root"]
        self.assertEqual(restored, base)

    def test_09_source_lock_probe_does_not_touch_inode(self) -> None:
        with tempfile.TemporaryDirectory(dir=REPO) as raw:
            path = Path(raw) / "lock"
            path.write_bytes(b"locked")
            before = path.stat()
            self.assertFalse(v3.lock_is_busy_readonly(path, require_exists=True))
            after = path.stat()
            self.assertEqual((before.st_ino, before.st_size, before.st_mtime_ns), (after.st_ino, after.st_size, after.st_mtime_ns))
            with path.open("a+b") as held:
                fcntl.flock(held.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                self.assertTrue(v3.lock_is_busy_readonly(path, require_exists=True))

    def _temp_config(self, root: Path) -> dict:
        config = copy.deepcopy(self.config)
        config["outputs"]["root"] = v3.relative(root)
        return config

    def test_10_action_failure_invocation_is_idempotent(self) -> None:
        with tempfile.TemporaryDirectory(dir=REPO) as raw:
            config = self._temp_config(Path(raw))
            entry = self.entries[1]
            first = v3.record_action_failure(config, entry, invocation_id="same.id", action="MATERIALIZE_TRAINING", error_type="E", message="m", return_code=2, log_path=None)
            second = v3.record_action_failure(config, entry, invocation_id="same.id", action="MATERIALIZE_TRAINING", error_type="E", message="m", return_code=2, log_path=None)
            self.assertEqual(first["attempt"], 1)
            self.assertTrue(second["publication_reused"])
            self.assertEqual(len(v3.action_failures(config, entry)), 1)

    def test_11_three_identical_failures_skip_only_at_three(self) -> None:
        with tempfile.TemporaryDirectory(dir=REPO) as raw:
            config = self._temp_config(Path(raw)); entry = self.entries[1]
            for index in range(2):
                v3.record_action_failure(config, entry, invocation_id=f"id.{index}", action="RUN_READOUT", error_type="E", message="same", return_code=2, log_path=None)
            self.assertIsNone(v3.three_same_action_failure(config, entry))
            v3.record_action_failure(config, entry, invocation_id="id.2", action="RUN_READOUT", error_type="E", message="same", return_code=2, log_path=None)
            self.assertEqual(v3.three_same_action_failure(config, entry)["error_type"], "E")

    def test_12_mixed_failure_signatures_do_not_skip(self) -> None:
        with tempfile.TemporaryDirectory(dir=REPO) as raw:
            config = self._temp_config(Path(raw)); entry = self.entries[1]
            for index, message in enumerate(("a", "b", "a")):
                v3.record_action_failure(config, entry, invocation_id=f"mix.{index}", action="RUN_READOUT", error_type="E", message=message, return_code=2, log_path=None)
            self.assertIsNone(v3.three_same_action_failure(config, entry))

    def test_13_stage_stop_is_three_consecutive_same_type(self) -> None:
        rows = [({"building_id": str(i)}, {"status": "SKIPPED", "error_type": "E"}) for i in range(3)]
        self.assertEqual(v3.consecutive_skip_stop(rows)["consecutive_buildings"], ["0", "1", "2"])
        mixed = copy.deepcopy(rows); mixed[1][1]["error_type"] = "F"
        self.assertIsNone(v3.consecutive_skip_stop(mixed))
        measured = copy.deepcopy(rows); measured[1][1]["status"] = "MEASURED"
        self.assertIsNone(v3.consecutive_skip_stop(measured))

    def test_14_gpu0_daemon_new_pid_is_allowed(self) -> None:
        allow = self.config["resources"]["gpu_boundary_gate"]["gpu0_exact_allowlist"]
        app = {"pid": 999999, "process_name": "/usr/libexec/gnome-remote-desktop-daemon", "cmdline": ["/usr/libexec/gnome-remote-desktop-daemon"], "owner_uid": os.getuid(), "used_memory_mib": 260}
        self.assertTrue(v3.gpu_app_is_allowlisted(app, allow, current_uid=os.getuid()))

    def test_15_gpu_allowlist_rejects_identity_drift(self) -> None:
        allow = self.config["resources"]["gpu_boundary_gate"]["gpu0_exact_allowlist"]
        base = {"pid": 1, "process_name": "/usr/libexec/gnome-remote-desktop-daemon", "cmdline": ["/usr/libexec/gnome-remote-desktop-daemon"], "owner_uid": os.getuid(), "used_memory_mib": 260}
        for key, value in (("process_name", "/tmp/fake"), ("cmdline", ["/tmp/fake"]), ("owner_uid", os.getuid() + 1), ("used_memory_mib", 513)):
            app = dict(base); app[key] = value
            self.assertFalse(v3.gpu_app_is_allowlisted(app, allow, current_uid=os.getuid()))

    def test_16_gpu1_allowlist_is_empty_and_vram_floor_locked(self) -> None:
        gate = self.config["resources"]["gpu_boundary_gate"]
        self.assertEqual(gate["gpu1_exact_allowlist"], [])
        self.assertEqual(gate["minimum_free_memory_mib"], 22000)

    def test_17_qualitative_validator_checks_all_components_and_interpretation(self) -> None:
        with tempfile.TemporaryDirectory(dir=REPO) as raw:
            root = Path(raw); config = copy.deepcopy(self.config); entry = self.entries[0]
            receipt = root / "review" / entry["building_id"] / f"arm_{entry['arm']}" / entry["replicate"] / "complete.json"
            config["qualitative_hook"]["receipt_template"] = v3.relative(receipt.parent / "complete.json").replace(entry["building_id"], "{building_id}").replace(entry["arm"], "{arm}").replace(entry["replicate"], "{replicate}")
            receipt.parent.mkdir(parents=True)
            source = root / "readout.json"; source.write_text("source\n")
            outputs = {}
            for key in ("panel", "opacity_csv", "canonical_roofer_cityjson"):
                path = receipt.parent / f"{key}.dat"; path.write_text(key + "\n"); outputs[key] = v3.file_record(path)
            payload = {"schema": v3.QUAL_SCHEMA, "state": "COMPLETE", "measurement_state": "MEASURED", "identity": {"run_id": config["run_id"], "building_id": entry["building_id"], "arm": entry["arm"], "replicate": entry["replicate"]}, "placeholder_count": 0, "components": {key: True for key in "ABCDEFGHI"}, "source_readout_complete": v3.file_record(source), "outputs": outputs, "scientific_verdict": None, "interpretation": None, "interpretation_or_verdict": None}
            receipt.write_text(json.dumps(payload))
            renderer = mock.Mock(); renderer.verify_bundle.return_value = payload
            with mock.patch.object(v3, "qualitative_context", return_value=(renderer, {})):
                self.assertIsNotNone(v3.verify_qualitative_complete(config, entry))
                renderer.verify_bundle.assert_called_once_with(
                    {}, entry["building_id"], entry["arm"], entry["replicate"], None
                )
                payload["interpretation"] = "forbidden"; receipt.write_text(json.dumps(payload))
                with self.assertRaises(v3.V3Error): v3.verify_qualitative_complete(config, entry)

    def test_18_skipped_terminal_rehashes_evidence(self) -> None:
        with tempfile.TemporaryDirectory(dir=REPO) as raw:
            root = Path(raw); config = self._temp_config(root); entry = self.entries[1]
            receipts = []
            for index in range(3):
                path = root / f"e{index}.json"; path.write_text("{}\n"); receipts.append(v3.file_record(path))
            payload = {"status": "SKIPPED", "components": None, "source_receipts": receipts, "same_signature_attempts": 3, "error_signature": "s", "error_type": "E"}
            v3.verify_stage_payload(config, entry, payload)
            (root / "e1.json").unlink()
            with self.assertRaises(v3.V3Error): v3.verify_stage_payload(config, entry, payload)

    def test_19_existing_complete_path_calls_full_verifier(self) -> None:
        source = DRIVER.read_text(encoding="utf-8")
        block = source[source.index("def finalize("):source.index("def verify_complete_payload(")]
        self.assertIn("verify_complete_payload(config, payload)", block)

    def test_20_wrapper_has_two_lane_barrier_then_serial_readout(self) -> None:
        source = WRAPPER.read_text(encoding="utf-8")
        run = source[source.index("run_queue()") :]
        self.assertIn("drive_training_member", run)
        self.assertIn("&", run)
        self.assertIn("wait", run)
        self.assertLess(run.index("pair-training-ready"), run.index("drive_post_training_member"))
        self.assertIn("assert-no-training", run)
        self.assertIn("flock \"$READOUT_LOCK\"", source)

    def test_21_wrapper_uses_fixed_qualitative_cli(self) -> None:
        source = WRAPPER.read_text(encoding="utf-8")
        self.assertIn('bash "$QUALITATIVE_WRAPPER" one "$building_id" "$arm" "$replicate"', source)

    def test_22_wrapper_syntax(self) -> None:
        result = subprocess.run(["bash", "-n", str(WRAPPER)], check=False)
        self.assertEqual(result.returncode, 0)

    def test_23_source_boundary_output_is_locked(self) -> None:
        self.assertEqual(self.config["outputs"]["source_boundary_receipt"], "source_boundary_receipt.json")
        source = DRIVER.read_text(encoding="utf-8")
        self.assertIn("remaining_canonical_outputs_absent_at_boundary", source)
        self.assertIn("source_v2_driver_lock_free", source)

    def test_24_gpu_and_process_boundaries_run_in_host_namespace(self) -> None:
        source = WRAPPER.read_text(encoding="utf-8")
        launch_block = source[source.index("launch_lane()") : source.index("drive_training_member()")]
        self.assertIn('/usr/bin/python3 "$DRIVER" --config "$CONFIG" wait-gpu-boundary', launch_block)
        self.assertNotIn('run_tools "$DRIVER" --config "$CONFIG" gpu-boundary', launch_block)
        self.assertIn('/usr/bin/python3 "$DRIVER" --config "$CONFIG" assert-no-training', source)

    def test_25_stage_stop_is_checked_before_and_after_each_post_job(self) -> None:
        source = WRAPPER.read_text(encoding="utf-8")
        run = source[source.index("run_queue()") :]
        barrier = run.index('pair-training-ready --pair-id "$current_pair"')
        post_loop = run.index('for row in "${current_rows[@]}"; do', barrier)
        pre_post = run[barrier:post_loop]
        self.assertIn('stage-stop-check', pre_post)
        self.assertIn('[[ -f "$QUEUE_ROOT/stage_stop.json" ]]', pre_post)
        post_body = run[post_loop:run.index('run_tools "$DRIVER" --config "$CONFIG" status', post_loop)]
        self.assertLess(post_body.index("drive_post_training_member"), post_body.index("stage-stop-check"))
        self.assertIn('[[ ! -f "$QUEUE_ROOT/stage_stop.json" ]] || break', post_body)

    def test_26_action_log_diagnostic_is_bounded_and_distinguishes_errors(self) -> None:
        source = WRAPPER.read_text(encoding="utf-8")
        block = source[source.index("normalize_action_diagnostic()") : source.index("record_failure()")]
        with tempfile.TemporaryDirectory(dir=REPO) as raw:
            first = Path(raw) / "first.log"; second = Path(raw) / "second.log"
            first.write_text("header\nERROR: CUDA out of memory\n", encoding="utf-8")
            second.write_text("header\nERROR: permission denied\n", encoding="utf-8")
            def observed(path: Path) -> str:
                command = block + f"\nnormalize_action_diagnostic {path}\n"
                return subprocess.run(["bash", "-c", command], text=True, stdout=subprocess.PIPE, check=True).stdout.strip()
            one = observed(first); one_again = observed(first); two = observed(second)
            self.assertEqual(one, one_again)
            self.assertNotEqual(one, two)
            self.assertLessEqual(len(one), 512)
        self.assertIn('external action diagnostic: $diagnostic', source)

    def test_27_service_log_has_one_append_owner(self) -> None:
        source = WRAPPER.read_text(encoding="utf-8")
        block = source[source.index("start_service_log()") : source.index("allocate_action_log()")]
        self.assertIn('${INVOCATION_ID:-}', block)
        systemd_branch = block[block.index('if [[ -n'):block.index('else')]
        manual_branch = block[block.index('else'):block.index('fi\n', block.index('else'))]
        self.assertNotIn('tee -a "$SERVICE_LOG"', systemd_branch)
        self.assertIn('tee -a "$SERVICE_LOG"', manual_branch)

    def test_28_gpu_boundary_polls_without_job_failure_or_cutoff(self) -> None:
        source = WRAPPER.read_text(encoding="utf-8")
        block = source[source.index("launch_lane()") : source.index("drive_training_member()")]
        self.assertIn('/usr/bin/python3 "$DRIVER" --config "$CONFIG" wait-gpu-boundary', block)
        self.assertLess(block.index("wait-gpu-boundary"), block.index("launch-training"))
        self.assertNotIn("record_failure", block)
        self.assertIsNone(self.config["resources"]["gpu_boundary_gate"]["time_cutoff"])

    def test_29_action_failure_type_is_action_specific(self) -> None:
        source = WRAPPER.read_text(encoding="utf-8")
        self.assertIn('--error-type "${action}ExternalError"', source)
        self.assertNotIn("--error-type ExternalActionError", source)

    def test_30_post_complete_status_and_finalize_are_immutable(self) -> None:
        with tempfile.TemporaryDirectory(dir=REPO) as raw:
            root = Path(raw); config = self._temp_config(root)
            status_path = root / config["outputs"]["status_json"]
            status_path.write_text(json.dumps({"schema": v3.STATUS_SCHEMA, "counts": {"MEASURED": 20}}) + "\n")
            csv_path = root / config["outputs"]["status_csv"]; csv_path.write_text("state\n")
            events = root / config["outputs"]["events"]; events.write_text("{}\n")
            complete_path = root / config["outputs"]["complete"]
            complete_path.write_text(json.dumps({"schema": v3.COMPLETE_SCHEMA, "status_json": v3.file_record(status_path)}) + "\n")
            before_status = status_path.read_bytes(); before_complete = complete_path.read_bytes()
            before_mtime = (status_path.stat().st_mtime_ns, complete_path.stat().st_mtime_ns)
            with mock.patch.object(v3, "verify_complete_payload", return_value=None):
                first_status = v3.publish_status(config)
                first_finalize = v3.finalize(config)
                second_status = v3.publish_status(config)
                second_finalize = v3.finalize(config)
            self.assertTrue(first_status["publication_reused"] and second_status["publication_reused"])
            self.assertTrue(first_finalize["publication_reused"] and second_finalize["publication_reused"])
            self.assertEqual(status_path.read_bytes(), before_status)
            self.assertEqual(complete_path.read_bytes(), before_complete)
            self.assertEqual((status_path.stat().st_mtime_ns, complete_path.stat().st_mtime_ns), before_mtime)

    def test_31_publication_lock_serializes_status_and_finalize(self) -> None:
        with tempfile.TemporaryDirectory(dir=REPO) as raw:
            root = Path(raw); config = self._temp_config(root)
            lock_path = root / config["outputs"]["publication_lock"]
            with v3.publication_lock(config):
                self.assertTrue(v3.lock_is_busy_readonly(lock_path, require_exists=True))
            self.assertFalse(v3.lock_is_busy_readonly(lock_path, require_exists=True))
        source = DRIVER.read_text(encoding="utf-8")
        finalize_block = source[source.index("def finalize(") : source.index("def verify_complete_payload(")]
        self.assertIn("with publication_lock(config):", finalize_block)

    def test_32_wait_gpu_boundary_retries_only_contention(self) -> None:
        ready = {"state": "READY"}
        with (
            mock.patch.object(v3, "gpu_boundary", side_effect=[v3.GpuBoundaryUnavailable("busy"), ready]) as probe,
            mock.patch.object(v3.time, "sleep") as sleeper,
        ):
            result = v3.wait_gpu_boundary(self.config, "pair", 0, require_host=False)
        self.assertEqual(result["wait_attempts"], 2)
        self.assertEqual(probe.call_count, 2)
        sleeper.assert_called_once_with(30)
        with (
            mock.patch.object(v3, "gpu_boundary", side_effect=v3.V3Error("malformed")),
            mock.patch.object(v3.time, "sleep") as fatal_sleep,
            self.assertRaisesRegex(v3.V3Error, "malformed"),
        ):
            v3.wait_gpu_boundary(self.config, "pair", 0, require_host=False)
        fatal_sleep.assert_not_called()

    def test_33_committed_continuation_contract_binds_source_and_pairs(self) -> None:
        result = v3.verify_continuation_contract(self.config, self.entries, self.pairs)
        self.assertTrue(result["source_head_is_ancestor"])
        self.assertTrue(result["pair_schedule_verified"])
        self.assertEqual(result["contract"]["sha256"], self.config["locked_inputs"]["continuation_contract"]["sha256"])

    def test_34_qualitative_source_mutation_failure_is_propagated(self) -> None:
        renderer = mock.Mock()
        renderer.verify_bundle.side_effect = RuntimeError("source_records SHA drift")
        with (
            mock.patch.object(v3, "qualitative_context", return_value=(renderer, {})),
            mock.patch.object(v3, "qualitative_path", return_value=REPO / "synthetic_complete.json"),
            mock.patch.object(v3, "load_json", return_value={}),
            mock.patch.object(v3.Path, "exists", return_value=True),
            mock.patch.object(v3.Path, "is_symlink", return_value=False),
            self.assertRaisesRegex(v3.V3Error, "full bundle verification failed"),
        ):
            v3.verify_qualitative_complete(self.config, self.entries[0])

    def test_35_pair_wait_reaps_every_child_and_preserves_first_failure(self) -> None:
        source = WRAPPER.read_text(encoding="utf-8")
        start = source.index("wait_for_training_pair()")
        block = source[start : source.index("run_queue()", start)]
        command = block + """
set -Eeuo pipefail
bash -c 'exit 125' & first=$!
bash -c 'exit 9' & second=$!
wait_for_training_pair "$first" "$second"
"""
        result = subprocess.run(
            ["bash", "-c", command],
            check=False,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        self.assertEqual(result.returncode, 125)
        self.assertRegex(result.stdout, r"training pair children reaped statuses=\d+:125,\d+:9")
        run = source[source.index("run_queue()") :]
        self.assertIn('wait_for_training_pair "${pids[@]}"', run)
        self.assertNotIn('for row in "${pids[@]}"; do wait "$row"; done', run)

    def test_36_pair_schedule_producer_failure_is_not_masked(self) -> None:
        source = WRAPPER.read_text(encoding="utf-8")
        start = source.index("load_pair_schedule()")
        block = source[start : source.index("wait_for_training_pair()", start)]
        command = """
set -Eeuo pipefail
DRIVER=driver.py
CONFIG=config.json
run_tools() { return 23; }
rows=()
""" + block + "\nload_pair_schedule rows\n"
        result = subprocess.run(
            ["bash", "-c", command],
            check=False,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        self.assertEqual(result.returncode, 23)
        self.assertIn("pair schedule producer failed with status=23", result.stderr)
        run = source[source.index("run_queue()") :]
        self.assertIn("load_pair_schedule pair_rows", run)
        self.assertNotIn("< <(run_tools", run)
        self.assertIn('[[ "${#target_rows[@]}" -ne 19 ]]', block)
        self.assertIn('[[ "${#unique_pair_ids[@]}" -ne 11 ]]', block)

    def test_37_verify_returns_locked_full_preflight_validation(self) -> None:
        training_config = {"preflight_gates": {}}
        module = mock.Mock()
        module.committed_method_gate.return_value = {"head": v3.git("rev-parse", "HEAD").stdout.strip()}
        module.validate_preflight_gates.return_value = {
            "status": "PASSED",
            "profile": "full",
            "required_gates": ["five_pin", "T1", "T2", "T3"],
            "records": {},
        }
        with mock.patch.object(v3, "training_context", return_value=(module, training_config, CONFIG)):
            observed = v3.verify_training_preflight(self.config)
        module.validate_preflight_gates.assert_called_once_with(v3.REPO, training_config, "full")
        self.assertEqual(observed["gates"], module.validate_preflight_gates.return_value)
        source = DRIVER.read_text(encoding="utf-8")
        block = source[source.index("def verify(") : source.index("def add_entry_args(")]
        self.assertIn('"training_preflight": verify_training_preflight(config)', block)

    def test_38_repair_lock_binds_failed_generation_and_schedule(self) -> None:
        result = v3.verify_repair_contract(self.config, self.entries, self.pairs)
        self.assertFalse(result["scientific_recipe_changed"])
        self.assertFalse(result["target_list_changed"])
        self.assertFalse(result["pair_schedule_changed"])
        self.assertEqual(
            result["contract"]["sha256"],
            self.config["locked_inputs"]["repair_contract"]["sha256"],
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
