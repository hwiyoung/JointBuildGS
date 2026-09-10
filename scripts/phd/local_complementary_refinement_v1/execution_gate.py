"""Freeze or verify the exact main experiment and its two successful probes.

CPU-only: no model import, checkpoint load, inference, or GPU access. Probe
receipts attest their validated payloads; this gate rechecks the receipts and
the exact configuration, input binding, source and execution helper bytes.
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import time

from common import read, record, require_docker, sha, write_new


SCHEMA = "JBGS_LOCAL_COMPLEMENTARY_EXECUTION_READY_v1"
REQUIRED_HELPERS = ("run_phase.py", "common.py", "run_phase.sh", "run_queue.sh", "execution_gate.py")
DEFAULT_PROBES = {"native": "P2_LC_D005_Pnative", "release": "P2_LC_D005_Prelease"}


def safe_probe_path(root, relative):
    relative = Path(relative)
    if relative.is_absolute() or ".." in relative.parts:
        raise ValueError("Probe path must be relative and may not traverse parents")
    result = Path(root) / relative
    if not result.resolve().is_relative_to(Path(root).resolve()):
        raise ValueError("Probe path escapes the mounted probe root")
    return result


def check(condition, message):
    if not condition:
        raise ValueError(message)


def source_hashes(source):
    return {str(path.relative_to(source)): sha(path) for path in sorted(source.rglob("*.py"))
            if "submodules" not in path.parts and "__pycache__" not in path.parts}


def inspect_state(contracts, source, scripts, probes, probe_names):
    """Build the current validated identity; no runtime files are changed."""
    contracts, source, scripts, probes = map(Path, (contracts, source, scripts, probes))
    config_path, binding_path = contracts / "experiment_v1.json", contracts / "input_binding.json"
    config, binding = read(config_path), read(binding_path)
    config_hash, binding_hash = sha(config_path), sha(binding_path)
    check(config.get("schema") == "jbgs.local_complementary_refinement.v1", "Unrecognized main config")
    check(binding.get("status") == "INPUTS_AND_COMMON_THRESHOLDS_FROZEN", "Main inputs and thresholds are not frozen")
    check(binding.get("task_id") == config.get("task_id"), "Binding belongs to another task")
    check(config.get("scientific_verdict") is None and binding.get("scientific_verdict") is None,
          "Technical gate must keep scientific_verdict null")
    check(binding.get("reference_accessed") is False, "Reference access is not allowed for input binding")
    check(binding["config"]["sha256"] == config_hash, "Binding was made for another config")
    tau0, tau1 = binding["tau0_m"], binding["tau1_m"]
    check(isinstance(tau0, (int, float)) and isinstance(tau1, (int, float))
          and math.isfinite(tau0) and math.isfinite(tau1) and 0 <= tau0 < tau1,
          "Main depth thresholds are invalid")
    provenance_path = source / "local_source_provenance.json"
    provenance = read(provenance_path)
    provenance_hash = sha(provenance_path)
    check(provenance.get("schema") == "JBGS_LOCAL_COMPLEMENTARY_SOURCE_v1", "Unrecognized prepared source")
    implementation = source_hashes(source)
    for name in ("train.py", "jbgs_state.py", "jbgs_local_depth.py"):
        check(name in implementation, "Prepared source lacks " + name)
    check(implementation == provenance["prepared_implementation_hashes"], "Prepared source changed")
    check(implementation["jbgs_local_depth.py"] == provenance["local_depth_module_sha256"],
          "Prepared local depth helper differs")
    helpers = {name: sha(scripts / name) for name in REQUIRED_HELPERS}
    identity = {"config": record(config_path), "input_binding": record(binding_path),
                "source_provenance": record(provenance_path), "implementation_hashes": implementation,
                "runtime_helper_hashes": helpers, "tau0_m": tau0, "tau1_m": tau1,
                "probe_names": dict(probe_names), "probes": {}}
    for protection in ("native", "release"):
        relative = probe_names[protection]
        path = safe_probe_path(probes, relative) / "probe_receipt.json"
        probe = read(path)
        prefix = protection + " probe: "
        expected_condition = "LC_D005_P" + protection
        check(probe.get("status") == "PASS" and probe.get("validated_exit_code") == 0
              and probe.get("native_exit_code") == 0, prefix + "not a validated success")
        check(probe.get("phase") == "probe" and probe.get("region") == "P2"
              and probe.get("condition") == expected_condition, prefix + "wrong test condition")
        check(probe.get("task_id") == config["task_id"] and probe.get("scientific_verdict") is None,
              prefix + "task or verdict differs")
        check(probe.get("training_start_iteration") == 8000 and probe.get("training_end_iteration") == 8001,
              prefix + "not the one-step complete-Anchor probe")
        check(probe.get("config_sha256") == config_hash and probe["config"]["sha256"] == config_hash,
              prefix + "configuration differs from main")
        check(probe["input_binding"]["sha256"] == binding_hash, prefix + "input binding differs from main")
        check(probe["source_provenance"]["sha256"] == provenance_hash
              and probe["implementation_hashes"] == implementation, prefix + "source differs from main")
        check(probe["driver"]["sha256"] == helpers["run_phase.py"], prefix + "execution driver changed after probe")
        check(probe["runtime_image_id"] == config["runtime"]["image_id"], prefix + "runtime image differs")
        check(probe.get("local_mode") == "complementary"
              and (probe.get("tau0_m"), probe.get("tau1_m")) == (tau0, tau1), prefix + "local policy differs")
        expected_anchor = binding["regions"]["P2"]["checkpoint"]["sha256"]
        check(probe["anchor"]["sha256"] == expected_anchor, prefix + "complete Anchor differs")
        env = probe["environment"]
        check(env.get("JBGS_LOCAL_DEPTH_MODE") == "complementary"
              and float(env["JBGS_LOCAL_TAU0"]) == tau0 and float(env["JBGS_LOCAL_TAU1"]) == tau1,
              prefix + "executed environment differs")
        check(env.get("PYTORCH_CUDA_ALLOC_CONF") == config["runtime"]["allocator"], prefix + "allocator differs")
        validated = [entry for entry in probe["validation"] if "restore" in entry]
        check(len(validated) == 1, prefix + "missing or ambiguous restore validation")
        validated = validated[0]
        restore = validated["restore"]
        check(restore["iteration"] == 8000 and restore["checkpoint_sha256"] == expected_anchor
              and restore["release"] == (protection == "release")
              and restore["lambda_lod_anchor"] == 0.005, prefix + "restored state or protection differs")
        for key in ("first_local_trace", "last_local_trace"):
            row = validated[key]
            check(row["iteration"] == 8001 and (row["tau0"], row["tau1"]) == (tau0, tau1)
                  and row["lambda_prior"] == 0.005 and row["mode"] == "complementary",
                  prefix + "observed local trace differs")
        identity["probes"][protection] = record(path)
    return {"task_id": config["task_id"], "identity": identity}


def freeze(contracts, source, scripts, probes, probe_names=None):
    ready_path = Path(contracts) / "execution_ready.json"
    if ready_path.exists():
        raise FileExistsError("Execution readiness already exists; preserve it and use a new contract revision")
    inspected = inspect_state(contracts, source, scripts, probes, probe_names or DEFAULT_PROBES)
    ready = dict(inspected, schema=SCHEMA, status="PASS", scientific_verdict=None,
                 frozen_unix=time.time(),
                 scope="exact configuration, binding, source, execution helpers, and P2 native/release one-step probes; not scientific performance")
    write_new(ready_path, ready)
    return ready


def verify(contracts, source, scripts, probes, probe_names=None):
    ready = read(Path(contracts) / "execution_ready.json")
    check(ready.get("schema") == SCHEMA and ready.get("status") == "PASS"
          and ready.get("scientific_verdict") is None, "Execution readiness is not a technical PASS")
    names = ready["identity"]["probe_names"] if probe_names is None else probe_names
    inspected = inspect_state(contracts, source, scripts, probes, names)
    check(inspected["task_id"] == ready["task_id"] and inspected["identity"] == ready["identity"],
          "Frozen execution identity changed; do not launch the main matrix")
    return ready


def main():
    require_docker()
    parser = argparse.ArgumentParser(description=__doc__)
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--freeze", action="store_true")
    action.add_argument("--verify", action="store_true")
    parser.add_argument("--contracts", default="/contracts/main_v1", type=Path)
    parser.add_argument("--source", default="/source", type=Path)
    parser.add_argument("--scripts", default="/audit", type=Path)
    parser.add_argument("--probes", default="/probes", type=Path)
    parser.add_argument("--native-probe", help="Relative directory below --probes")
    parser.add_argument("--release-probe", help="Relative directory below --probes")
    args = parser.parse_args()
    if (args.native_probe is None) != (args.release_probe is None):
        parser.error("Specify both probe directories or neither")
    names = None if args.native_probe is None else {"native": args.native_probe, "release": args.release_probe}
    ready = (freeze if args.freeze else verify)(args.contracts, args.source, args.scripts, args.probes, names)
    print(json.dumps({"status": "PASS_FROZEN" if args.freeze else "PASS_VERIFIED",
                      "task_id": ready["task_id"], "tau0_m": ready["identity"]["tau0_m"],
                      "tau1_m": ready["identity"]["tau1_m"], "scientific_verdict": None}), flush=True)


if __name__ == "__main__":
    main()
