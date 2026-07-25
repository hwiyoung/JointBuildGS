#!/usr/bin/env python3
"""Register Gate A v2 and publish corrected-pose qualitative overlays.

The locked coreg diagnostic numbers are verified and copied, never recomputed.
The visual path projects raw classified ALS through the already-corrected R1
poses.  It performs no image-edge extraction, residual matching, or gate test.
"""
from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys
from typing import Any, Mapping, Sequence

import numpy as np


REPO = Path(__file__).resolve().parents[3]
DEFAULT_CONFIG = REPO / "phases/p2-gsjso/configs/fusion_w1_gate_a_v2_registration_20260725.json"
SELF = Path(__file__).resolve()


class RegistrationError(RuntimeError):
    pass


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat()


def repo_path(value: str | Path) -> Path:
    value = Path(value)
    if value.is_absolute():
        raise RegistrationError(f"absolute path forbidden by R2 contract: {value}")
    candidate = REPO / value
    try:
        candidate.resolve().relative_to(REPO.resolve())
    except ValueError as exc:
        raise RegistrationError(f"path escapes repository: {value}") from exc
    return candidate


def relative(path: Path) -> str:
    return str(path.resolve().relative_to(REPO.resolve()))


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise RegistrationError(f"JSON root is not an object: {path}")
    return value


def truth(value: Any) -> bool:
    return value is True or str(value).strip().lower() == "true"


def atomic_bytes(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    with temporary.open("xb") as handle:
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)


def atomic_json(path: Path, payload: Mapping[str, Any]) -> None:
    atomic_bytes(
        path,
        (json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode(),
    )


def exclusive_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())


def read_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames:
            raise RegistrationError(f"CSV has no header: {path}")
        return [dict(row) for row in reader]


def git(*arguments: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        [
            "git",
            "-c",
            f"safe.directory={REPO}",
            "-C",
            str(REPO),
            *arguments,
        ],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if check and result.returncode:
        raise RegistrationError(
            result.stderr.strip() or result.stdout.strip() or "git failed"
        )
    return result


def verify_git_lock(
    config: Mapping[str, Any], outputs: Mapping[str, Path]
) -> dict[str, Any]:
    branch = git("branch", "--show-current").stdout.strip()
    head = git("rev-parse", "HEAD").stdout.strip()
    ancestor = git(
        "merge-base",
        "--is-ancestor",
        config["required_ancestor_commit"],
        head,
        check=False,
    ).returncode == 0
    allowed = {
        relative(path)
        for path in outputs.values()
        if path.exists() or path.is_symlink()
    }
    porcelain = git(
        "status", "--porcelain=v1", "--untracked-files=all"
    ).stdout.splitlines()
    unexpected = [
        row
        for row in porcelain
        if (row[3:].split(" -> ")[-1].strip('"') if len(row) > 3 else "")
        not in allowed
    ]
    required_files = [
        *config["implementation_files"],
        config["r1_consumer_contract"]["manifest"],
    ]
    file_rows = []
    files_ok = True
    for value in required_files:
        tracked = bool(git("ls-files", "--", value).stdout.strip())
        blob = git("cat-file", "-e", f"{head}:{value}", check=False)
        ok = tracked and blob.returncode == 0 and repo_path(value).is_file()
        file_rows.append({"path": value, "tracked_at_head": ok})
        files_ok = files_ok and ok
    if (
        branch != config["branch"]
        or not ancestor
        or unexpected
        or not files_ok
    ):
        raise RegistrationError("R2 committed-clean git lock failed")
    return {
        "branch": branch,
        "head": head,
        "required_ancestor": config["required_ancestor_commit"],
        "required_ancestor_of_head": ancestor,
        "allowed_generated_paths": sorted(allowed),
        "unexpected_porcelain": unexpected,
        "required_files": file_rows,
    }


def verify_small_inputs(config: Mapping[str, Any]) -> dict[str, str]:
    observed: dict[str, str] = {}
    for name, expected in config["input_sha256"].items():
        path = repo_path(name)
        if not path.is_file() or path.is_symlink():
            raise RegistrationError(f"locked input missing or symlinked: {name}")
        actual = sha256_file(path)
        if actual != expected:
            raise RegistrationError(f"locked input SHA drift: {name}")
        observed[name] = actual
    return observed


def validate_r1_consumer(config: Mapping[str, Any]) -> dict[str, Any]:
    contract = config["r1_consumer_contract"]
    manifest_path = repo_path(contract["manifest"])
    if not manifest_path.is_file() or manifest_path.is_symlink():
        raise RegistrationError("R1 adoption manifest is missing or symlinked")
    manifest = load_json(manifest_path)
    scalar_expectations = {
        "schema": contract["schema"],
        "status": contract["status"],
        "image_count": contract["image_count"],
        "application_scope": contract["application_scope"],
        "transform_application_count": contract["transform_application_count"],
        "als_source_modified": False,
        "source_pose_modified": False,
        "derived_pose_differs_from_source": True,
    }
    for key, expected in scalar_expectations.items():
        if manifest.get(key) != expected:
            raise RegistrationError(f"R1 consumer contract mismatch: {key}")
    authority = manifest.get("adoption_authority")
    if not isinstance(authority, dict):
        raise RegistrationError("R1 adoption_authority is absent")
    for key, expected in contract["adoption_authority"].items():
        if authority.get(key) != expected:
            raise RegistrationError(f"R1 adoption authority mismatch: {key}")
    derived_value = manifest.get("derived_sparse")
    if not isinstance(derived_value, str) or not derived_value:
        raise RegistrationError("R1 manifest has no derived_sparse")
    derived = repo_path(derived_value)
    if not derived.is_dir() or derived.is_symlink():
        raise RegistrationError("R1 derived_sparse is missing or symlinked")
    hashes = manifest.get("derived_sha256")
    if not isinstance(hashes, dict):
        raise RegistrationError("R1 derived_sha256 is absent")
    for name in ("cameras.bin", "images.bin", "points3D.bin"):
        expected = hashes.get(name)
        path = derived / name
        if not isinstance(expected, str) or sha256_file(path) != expected:
            raise RegistrationError(f"R1 derived sparse hash mismatch: {name}")
    pose_hash = hashes["images.bin"]
    arm = manifest.get("arm_pose_contract")
    if not isinstance(arm, dict) or arm.get("identical") is not True:
        raise RegistrationError("R1 arm pose contract is not identical")
    if {
        arm.get("arm_A_required_pose_sha256"),
        arm.get("arm_B_required_pose_sha256"),
    } != {pose_hash}:
        raise RegistrationError("R1 arm pose hashes differ from corrected images.bin")
    return {
        "manifest": manifest,
        "manifest_path": manifest_path,
        "manifest_sha256": sha256_file(manifest_path),
        "derived_sparse": derived,
        "pose_sha256": pose_hash,
        "camera_sha256": hashes["cameras.bin"],
    }


def locked_gate_slots(
    targets: Sequence[Mapping[str, str]],
    residuals: Sequence[Mapping[str, str]],
) -> dict[str, Any]:
    if len(targets) != 178 or len({row["building_id"] for row in targets}) != 178:
        raise RegistrationError("targets are not exactly 178 unique buildings")
    if len(residuals) != 178 or len({row["building_id"] for row in residuals}) != 178:
        raise RegistrationError("diagnostic rows are not exactly 178 unique buildings")
    target_ids = {row["building_id"] for row in targets}
    if target_ids != {row["building_id"] for row in residuals}:
        raise RegistrationError("target/diagnostic membership differs")
    if {int(row["n_threshold"]) for row in residuals} != {40}:
        raise RegistrationError("locked n threshold drifted")
    capable = [row for row in residuals if truth(row["correspondence_capable"])]
    passing = [row for row in capable if truth(row["after_matched_median_le_0p3"])]
    core_ids = {
        row["building_id"] for row in targets if row.get("cohort", "").lower() == "core"
    }
    core_capable = [row for row in capable if row["building_id"] in core_ids]
    core_passing = [row for row in passing if row["building_id"] in core_ids]
    incapable_counts = {"surface": 0, "height": 0, "outline": 0}
    for row in residuals:
        if not truth(row["correspondence_capable"]):
            incapable_counts[row["tier"]] += 1
    return {
        "status": "PASS",
        "n_threshold": 40,
        "population_n": len(residuals),
        "correspondence_capable_n": len(capable),
        "capable_matched_median_le_0p3_n": len(passing),
        "core_population_n": len(core_ids),
        "core_correspondence_capable_n": len(core_capable),
        "core_capable_matched_median_le_0p3_n": len(core_passing),
        "incapable_tier_counts": incapable_counts,
        "core_capable_building_ids": sorted(row["building_id"] for row in core_capable),
        "numeric_source_role": "reuse_only_no_remeasurement",
        "auxiliary_statistics_used_for_gate": False,
    }


def validate_locked_slots(config: Mapping[str, Any]) -> tuple[dict[str, Any], list[dict[str, str]]]:
    targets = read_rows(repo_path(config["inputs"]["targets_csv"]))
    residuals = read_rows(repo_path(config["inputs"]["diagnostic_residuals_csv"]))
    observed = locked_gate_slots(targets, residuals)
    expected = config["gate_a_v2_locked_slots"]
    for key, value in expected.items():
        if observed.get(key) != value:
            raise RegistrationError(f"locked Gate A v2 slot mismatch: {key}")
    return observed, targets


def load_gate_helper(config: Mapping[str, Any]):
    path = repo_path(config["inputs"]["alignment_helper_script"])
    spec = importlib.util.spec_from_file_location("fusion_w1_visual_helpers", path)
    if spec is None or spec.loader is None:
        raise RegistrationError("cannot load alignment visual helpers")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def deterministic_cap(points: np.ndarray, cap: int) -> np.ndarray:
    if len(points) <= cap:
        return points
    return points[np.linspace(0, len(points) - 1, cap).astype(np.int64)]


def inframe(uv: np.ndarray, front: np.ndarray, camera: Any) -> np.ndarray:
    return (
        front
        & (uv[:, 0] >= 0)
        & (uv[:, 0] < camera.width)
        & (uv[:, 1] >= 0)
        & (uv[:, 1] < camera.height)
    )


def choose_display_view(
    gate: Any,
    cloud: Any,
    cameras: Mapping[int, Any],
    images_by_name: Mapping[str, Any],
    scene_reference: Mapping[str, Any],
    contract: Mapping[str, Any],
) -> tuple[Any, Any, int]:
    sample = deterministic_cap(
        cloud.building_xyz, int(contract["selection_point_cap"])
    )
    choices: list[tuple[int, str, Any, Any]] = []
    for name, image in sorted(images_by_name.items()):
        camera = cameras[image.camera_id]
        uv, front = gate.project_base_points(
            sample,
            image,
            camera,
            scene_reference,
            contract["input_vertical_datum"],
            float(contract["fixed_geoid_zeta_m"]),
            (0.0, 0.0),
        )
        count = int(inframe(uv, front, camera).sum())
        choices.append((-count, name, image, camera))
    choices.sort(key=lambda value: (value[0], value[1]))
    negative_count, _name, image, camera = choices[0]
    count = -negative_count
    if count < int(contract["minimum_class6_inframe_for_render"]):
        raise RegistrationError(
            f"{cloud.building_id}: no corrected-pose class6 display view"
        )
    return image, camera, count


def render_visual_overlay(
    path: Path,
    gate: Any,
    cloud: Any,
    image: Any,
    camera: Any,
    image_path: Path,
    scene_reference: Mapping[str, Any],
    contract: Mapping[str, Any],
) -> dict[str, int]:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from PIL import Image

    values: dict[str, tuple[np.ndarray, np.ndarray]] = {}
    counts: dict[str, int] = {}
    for key, points in (
        ("class6", cloud.building_xyz),
        ("class2", cloud.ground_xyz),
    ):
        uv, front = gate.project_base_points(
            points,
            image,
            camera,
            scene_reference,
            contract["input_vertical_datum"],
            float(contract["fixed_geoid_zeta_m"]),
            (0.0, 0.0),
        )
        mask = inframe(uv, front, camera)
        values[key] = (uv, mask)
        counts[f"{key}_total"] = len(points)
        counts[f"{key}_inframe"] = int(mask.sum())
    visible = values["class6"][0][values["class6"][1]]
    if not len(visible):
        raise RegistrationError(f"{cloud.building_id}: class6 projection is empty")
    pad = int(contract["crop_padding_px"])
    x0 = max(0, int(np.floor(visible[:, 0].min())) - pad)
    y0 = max(0, int(np.floor(visible[:, 1].min())) - pad)
    x1 = min(camera.width, int(np.ceil(visible[:, 0].max())) + pad + 1)
    y1 = min(camera.height, int(np.ceil(visible[:, 1].max())) + pad + 1)
    with Image.open(image_path) as source:
        if source.size != (camera.width, camera.height):
            raise RegistrationError(f"image/COLMAP size mismatch: {image.name}")
        crop = np.asarray(source.convert("RGB"))[y0:y1, x0:x1]
    figure, axis = plt.subplots(figsize=(9, 7), dpi=130)
    axis.imshow(crop)
    cap = int(contract["display_point_cap_per_class"])
    for key, color, size, alpha in (
        ("class2", contract["class2_color"], 0.6, 0.25),
        ("class6", contract["class6_color"], 0.9, 0.45),
    ):
        points = values[key][0][values[key][1]]
        points = deterministic_cap(points, cap) - np.array([x0, y0])
        axis.scatter(points[:, 0], points[:, 1], s=size, c=color, alpha=alpha)
    axis.set_title(
        f"{cloud.building_id} | {image.name}\n{contract['figure_label']}",
        fontsize=9,
    )
    axis.axis("off")
    figure.tight_layout()
    figure.savefig(path)
    plt.close(figure)
    return counts


INDEX_FIELDS = [
    "processing_order", "building_id", "cohort", "correspondence_capable",
    "image_name", "pose_path", "pose_sha256", "camera_sha256",
    "image_sha256", "class6_total", "class6_inframe", "class2_total",
    "class2_inframe", "selection_rule", "selection_role", "png_path",
    "png_sha256", "role",
]


def csv_payload(rows: Sequence[Mapping[str, Any]]) -> bytes:
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=INDEX_FIELDS, lineterminator="\n")
    writer.writeheader()
    for row in rows:
        writer.writerow(row)
    return stream.getvalue().encode()


def publish(config: Mapping[str, Any]) -> dict[str, Any]:
    outputs = {key: repo_path(value) for key, value in config["outputs"].items()}
    for key, path in outputs.items():
        if path.exists() or path.is_symlink():
            raise RegistrationError(f"R2 exact-once output already exists: {key}")
    exclusive_json(
        outputs["start_claim"],
        {
            "schema": "jointbuildgs.fusion_w1.gate_a_v2_registration.start.v1",
            "task_id": config["task_id"],
            "started_at": now_iso(),
            "numeric_remeasurement_started": 0,
            "edge_matching_started": 0,
            "learning_runs_started": 0,
        },
    )
    try:
        git_lock = verify_git_lock(config, outputs)
        observed_inputs = verify_small_inputs(config)
        r1 = validate_r1_consumer(config)
        slots, target_rows = validate_locked_slots(config)
        gate = load_gate_helper(config)
        helper_config = load_json(repo_path(config["inputs"]["alignment_helper_config"]))
        core_targets = gate.load_targets(
            repo_path(config["inputs"]["targets_csv"]), helper_config, "core"
        )
        if len(core_targets) != int(config["overlay_contract"]["expected_buildings"]):
            raise RegistrationError("qualitative core overlay population is not 28")
        footprint_path = repo_path(config["inputs"]["footprint_xy"])
        footprints = gate.load_footprints(
            footprint_path,
            [target.building_id for target in core_targets],
            helper_config["inputs"]["footprint_id_field"],
            helper_config["inputs"]["footprint_layer"],
            helper_config,
        )
        store = gate.ALSStore(
            [repo_path(value) for value in config["inputs"]["als_files"]],
            helper_config["input_locks"]["als_ground_class"],
            helper_config["input_locks"]["als_building_class"],
        )
        cameras, _images, images_by_name, image_paths = gate.load_training_inventory(
            r1["derived_sparse"],
            repo_path(config["inputs"]["training_image_dir"]),
            int(config["r1_consumer_contract"]["image_count"]),
        )
        scene = load_json(repo_path(config["inputs"]["scene_reference_frame"]))
        scene_reference = scene.get("base_to_canonical")
        if not isinstance(scene_reference, dict):
            raise RegistrationError("scene reference lacks base_to_canonical")
        residual_by_id = {
            row["building_id"]: row
            for row in read_rows(repo_path(config["inputs"]["diagnostic_residuals_csv"]))
        }
        staging_overlay = outputs["staging"] / "overlays"
        staging_overlay.mkdir(parents=True, exist_ok=False)
        index_rows: list[dict[str, Any]] = []
        for target in core_targets:
            cloud = store.target_cloud(
                target.building_id,
                footprints[target.building_id],
                helper_config["als_evidence"],
            )
            image, camera, _selection_count = choose_display_view(
                gate, cloud, cameras, images_by_name, scene_reference,
                config["overlay_contract"],
            )
            filename = (
                f"{target.processing_order:03d}__{target.building_id}__"
                f"{Path(image.name).stem}.png"
            )
            staged_png = staging_overlay / filename
            counts = render_visual_overlay(
                staged_png, gate, cloud, image, camera, image_paths[image.name],
                scene_reference, config["overlay_contract"],
            )
            row = {
                "processing_order": target.processing_order,
                "building_id": target.building_id,
                "cohort": target.cohort,
                "correspondence_capable": str(
                    truth(residual_by_id[target.building_id]["correspondence_capable"])
                ).lower(),
                "image_name": image.name,
                "pose_path": relative(r1["derived_sparse"] / "images.bin"),
                "pose_sha256": r1["pose_sha256"],
                "camera_sha256": r1["camera_sha256"],
                "image_sha256": sha256_file(image_paths[image.name]),
                **counts,
                "selection_rule": config["overlay_contract"]["selection_rule"],
                "selection_role": config["overlay_contract"]["selection_role"],
                "png_path": relative(outputs["overlay_dir"] / filename),
                "png_sha256": sha256_file(staged_png),
                "role": "qualitative_only_no_gate",
            }
            index_rows.append(row)
        if len(index_rows) != 28 or len({row["building_id"] for row in index_rows}) != 28:
            raise RegistrationError("R2 did not produce exactly one overlay for 28 core buildings")
        observed_inputs_after = verify_small_inputs(config)
        r1_after = validate_r1_consumer(config)
        if observed_inputs_after != observed_inputs:
            raise RegistrationError("locked R2 source changed during overlay rendering")
        if (
            r1_after["manifest_sha256"] != r1["manifest_sha256"]
            or r1_after["pose_sha256"] != r1["pose_sha256"]
            or r1_after["camera_sha256"] != r1["camera_sha256"]
        ):
            raise RegistrationError("R1 pose consumer changed during R2")
        staged_index = outputs["staging"] / "r2_overlay_index.csv"
        atomic_bytes(staged_index, csv_payload(index_rows))
        os.replace(staging_overlay, outputs["overlay_dir"])
        os.replace(staged_index, outputs["overlay_index"])
        outputs["staging"].rmdir()
        manifest = {
            "schema": "jointbuildgs.fusion_w1.gate_a_v2_registration.manifest.v1",
            "task_id": config["task_id"],
            "run_id": config["run_id"],
            "created_at": now_iso(),
            "status": "PASS",
            "gate_a_version": "v2",
            "gate_slots": slots,
            "numeric_measurement": {
                "reused_from": config["inputs"]["diagnostic_residuals_csv"],
                "reused_sha256": observed_inputs[
                    config["inputs"]["diagnostic_residuals_csv"]
                ],
                "new_residuals_measured": 0,
                "edge_matches_computed": 0,
            },
            "r1_pose_consumer": {
                "manifest_path": relative(r1["manifest_path"]),
                "manifest_sha256": r1["manifest_sha256"],
                "derived_sparse": relative(r1["derived_sparse"]),
                "pose_sha256": r1["pose_sha256"],
                "transform_application_count_in_r1": 1,
                "additional_transform_applied_by_r2": False,
                "als_transform_applied_by_r2": False,
                "projection_xy_shift_m": [0.0, 0.0],
            },
            "qualitative_overlays": {
                "population": "all_core_28",
                "count": len(index_rows),
                "index_path": relative(outputs["overlay_index"]),
                "index_sha256": sha256_file(outputs["overlay_index"]),
                "overlay_dir": relative(outputs["overlay_dir"]),
                "png_sha256": {
                    Path(row["png_path"]).name: row["png_sha256"] for row in index_rows
                },
                "role": "qualitative_only_not_a_gate",
            },
            "forbidden_call_audit": {
                "functions": config["overlay_contract"]["forbidden_calls"],
                "called": False,
            },
            "input_sha256": observed_inputs,
            "source_immutability": {
                "input_sha256_before": observed_inputs,
                "input_sha256_after": observed_inputs_after,
                "unchanged": True,
                "r1_manifest_sha256_before": r1["manifest_sha256"],
                "r1_manifest_sha256_after": r1_after["manifest_sha256"],
                "r1_pose_sha256_before": r1["pose_sha256"],
                "r1_pose_sha256_after": r1_after["pose_sha256"],
            },
            "git_lock": git_lock,
            "publication": {
                "exact_once": True,
                "manifest_written_last": True,
                "issues_md_modified": False,
            },
        }
        atomic_json(outputs["manifest"], manifest)
        return manifest
    except Exception as exc:
        if not outputs["failure"].exists():
            atomic_json(
                outputs["failure"],
                {
                    "schema": "jointbuildgs.fusion_w1.gate_a_v2_registration.failure.v1",
                    "task_id": config["task_id"],
                    "failed_at": now_iso(),
                    "status": "BLOCKED",
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                    "manifest_published": outputs["manifest"].exists(),
                },
            )
        raise


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default=str(DEFAULT_CONFIG))
    parser.add_argument("command", choices=("publish",))
    args = parser.parse_args()
    config = load_json(Path(args.config))
    manifest = publish(config)
    print(json.dumps({
        "status": manifest["status"],
        "overlay_count": manifest["qualitative_overlays"]["count"],
        "manifest": config["outputs"]["manifest"],
    }, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
