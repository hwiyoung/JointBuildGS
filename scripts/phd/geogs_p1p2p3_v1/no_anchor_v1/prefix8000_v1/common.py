"""Shared proof helpers for the separately declared 8k diagnostic; no training."""
import ast
import hashlib
import json
import math
from pathlib import Path, PurePosixPath

POLICY_SHA = "a312c4999ff590d757116dc0f4a90695020e3ac70130df24fdf6e02a0eb769f0"
IMAGE = "sha256:c5445549fe7f6995e0478ab9b07565da09947c1f1d54e274802dca50aa1e7f8e"
TRAIN_SHA = "1680d6e357877a03811c912804d211fe7c4b77562ecf24999d573fb4897450cb"
STATE_SHA = "7114f78e6f429c9186ce44e81a0c40d18e5087994f99a52d81eeee18ab7fa570"
RENDER_SHA = "1b1f4c45bd4c3c68e9b2a557d9ea5d8cd843a8e09b5a0b62f20323b399de8734"
SELECTED = {"P1": "no_anchor_sfm_memory_recovery_v2", "P2": "no_anchor_sfm_memory_recovery_P2_v2",
            "P3": "no_anchor_sfm_memory_recovery_P3_v3"}
CONDITION = "SFM_noanchor_D005_Pnative"
ROLE = "SUPPLEMENTARY_PREFIX_DIAGNOSTIC"
PREFIX = 8000


class NotReady(RuntimeError):
    pass


def require(value, message):
    if not value:
        raise ValueError(message)


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(8 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def read(path):
    return json.loads(Path(path).read_text())


def write(path, payload):
    with Path(path).open("x") as stream:
        json.dump(payload, stream, indent=2, ensure_ascii=False, allow_nan=False)
        stream.write("\n")


def relative(path):
    p = PurePosixPath(path)
    require(not p.is_absolute() and ".." not in p.parts and str(p) == path, "Non-canonical task-relative path")
    return path


def record(path, task_relative):
    return dict(path=relative(task_relative), bytes=Path(path).stat().st_size, sha256=sha(path))


def driver_hashes():
    root = Path(__file__).parent
    return {name: sha(root / name) for name in ("common.py", "validate.py", "export.py", "run.sh")}


def run_relative(region):
    return SELECTED[region] + "/runs/" + region + "/" + CONDITION


def scope():
    require(Path("/.dockerenv").exists(), "Docker required")
    require(not any(Path(p).exists() for p in ("/reference", "/task", "/artifacts/JointBuildGS")),
            "Broad task/artifact/reference mount is forbidden")


def policy(path):
    require(sha(path) == POLICY_SHA, "Frozen prefix policy hash differs")
    value = read(path)
    require(value["schema"] == "GEOGS_SFM_PREFIX_DIAGNOSTIC_POLICY_v1"
            and value["scientific_verdict"] is None and value["selected_attempts"] == SELECTED
            and value["prefix_iteration"] == PREFIX and value["producer_root"] == "completed_prefix8000_v1",
            "Prefix policy identity differs")
    return value


def closed_receipt(path, region, phase, iteration=None):
    if not path.is_file():
        raise NotReady(f"Selected {region} {phase} {iteration} has no closed producer receipt")
    value = read(path)
    require(value.get("region") == region and value.get("condition_id") == CONDITION
            and value.get("phase") == phase and value.get("iteration") == iteration
            and value.get("scientific_verdict") is None and value.get("status") in ("PASS", "FAIL"),
            "Closed producer identity/status differs")
    require(isinstance(value.get("finished_unix"), (int, float))
            and math.isfinite(value["finished_unix"]) and math.isfinite(value.get("started_unix", float("inf")))
            and value["finished_unix"] >= value.get("started_unix", float("inf")),
            "Missing producer completion time; controller disappearance is not a producer failure")
    for field in ("native_exit_code", "validated_exit_code"):
        require(type(value.get(field)) is int, "Missing actual producer exit status")
    passed = value["native_exit_code"] == 0 and value["validated_exit_code"] == 0
    require((value["status"] == "PASS") == passed, "Producer exit/status contradiction")
    return value


def activation_evidence(parents, policy_path):
    policy(policy_path)
    rows, failures, files = [], [], []
    for region in SELECTED:
        root = parents / region
        train = closed_receipt(root / "receipt.json", region, "train")
        train_record = record(root / "receipt.json", run_relative(region) + "/receipt.json")
        files.append(train_record)
        row = dict(region=region, selected_experiment=SELECTED[region], parent_training_status=train["status"],
                   parent_training_receipt=train_record, planned_exports=[])
        if train["status"] == "FAIL":
            failures.append(dict(region=region, phase="train", receipt=train_record))
            row["planned_exports"] = [dict(iteration=n, status="UNAVAILABLE_PARENT_TRAIN_FAILED") for n in (22000, 30000)]
        else:
            for n in (22000, 30000):
                export_path = root / "exports" / f"iteration_{n}" / "receipt.json"
                exported = closed_receipt(export_path, region, "export", n)
                require(exported["config_sha256"] == train["config_sha256"], "Export configuration differs from parent")
                rec = record(export_path, run_relative(region) + f"/exports/iteration_{n}/receipt.json")
                files.append(rec)
                row["planned_exports"].append(dict(iteration=n, status=exported["status"], receipt=rec))
                if exported["status"] == "FAIL":
                    failures.append(dict(region=region, phase="export", iteration=n, receipt=rec))
        rows.append(row)
    require(failures, "Policy not triggered: all selected planned reconstructions completed")
    return dict(schema="GEOGS_SFM_PREFIX_ACTIVATION_v1", status="PREFIX_DIAGNOSTIC_ACTIVATED",
                scientific_verdict=None, analysis_role=ROLE, prefix_iteration=PREFIX,
                selected_attempts=SELECTED, all_selected_producer_jobs_closed=True,
                failure_evidence=failures, regions=rows, files=files,
                producer_code_sha256=driver_hashes(), runtime_image_id=IMAGE,
                policy=record(policy_path, "contracts/sfm_prefix8000_diagnostic_v1.json"),
                main_completion_inferred=False, quality_or_reference_selection=False)


def verify_activation(path, parents, policy_path):
    value = read(path)
    current = activation_evidence(parents, policy_path)
    require(value == current, "Activation evidence changed or was not generated by closed producers")
    return value


def source_maps(source):
    return {str(p.relative_to(source)): sha(p) for p in sorted(source.rglob("*.py"))
            if not {".git", "__pycache__"}.intersection(p.relative_to(source).parts)}


def method_source_map(mapping):
    return {key: value for key, value in mapping.items() if "submodules" not in PurePosixPath(key).parts}


def assert_save_order(source):
    require(sha(source / "train.py") == TRAIN_SHA and sha(source / "jbgs_state.py") == STATE_SHA
            and sha(source / "render.py") == RENDER_SHA, "Frozen training/save/render implementation differs")
    text = (source / "train.py").read_text()
    positions = [text.index(s) for s in ("total_loss.backward()", "memory_recovery.before_optimizer_step",
        "gaussians.optimizer.step()", "memory_recovery.after_optimizer_step", "gaussians.densify_and_prune",
        "memory_recovery.after_step_boundary", "jbgs_no_anchor.audit_first_step", "if jbgs_state.after_step(locals())")]
    require(positions == sorted(positions), "Snapshot no longer follows optimizer/densification/protection")
    tree = ast.parse(text)
    count = sum(isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr == "step"
                and ast.unparse(n.func.value) == "gaussians.optimizer" for n in ast.walk(tree))
    require(count == 1, "Unexpected optimizer step multiplicity")
    state = (source / "jbgs_state.py").read_text()
    ordered = [state.index(s) for s in ("state = capture_state(env)", "torch.save(state, root / 'checkpoint.pth')",
                                      "g.save_ply(str(root / 'point_cloud.ply'))", "with (root / 'receipt.json').open('x')")]
    require(ordered == sorted(ordered), "Complete receipt no longer follows checkpoint and PLY writes")
    return dict(train_sha256=TRAIN_SHA, state_sha256=STATE_SHA, render_sha256=RENDER_SHA,
                optimizer_steps_per_loop=1, snapshot_after_optimizer_densification_protection=True,
                complete_receipt_after_both_payloads=True, snapshot_iteration_under_validation=PREFIX,
                reasoning="Source proves one optimizer step per loop; actual8000 requires separate closed-prefix checkpoint, counters and trace validation")


def check_finite_numbers(value):
    if isinstance(value, dict):
        for child in value.values():
            check_finite_numbers(child)
    elif isinstance(value, (list, tuple)):
        for child in value:
            check_finite_numbers(child)
    elif isinstance(value, float):
        require(math.isfinite(value), "Nonfinite scalar in checkpoint/trace metadata")
