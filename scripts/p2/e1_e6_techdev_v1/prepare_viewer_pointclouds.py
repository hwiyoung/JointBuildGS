from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path

import laspy
import numpy as np


WORLD_SHIFT = np.asarray([690953.0, 5336071.0, 604.0], dtype=np.float64)
MAX_DISPLAY_POINTS = 600_000
SCHEMA = "jointbuildgs.p2.e1_e6.viewer_roofer_pointclouds.v1"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def atomic_json(path: Path, value: dict) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def sources(artifacts: Path, task: Path) -> dict[str, dict]:
    baseline = artifacts / (
        "phase-payloads/p2/c1_c2_shared_footprint_199_v3/"
        "P2-C1-C2-SHARED-FOOTPRINT-199-ORIGINAL-GLOBAL-v3-replay-20260806a/work"
    )
    output = {}
    for condition, run_name in (("E1", "C1_L_upper"), ("E2", "C2_MVS")):
        receipt = load_json(baseline / run_name / "classified_scene_receipt.json")
        output[condition] = {
            "path": baseline / run_name / "classified_scene.laz",
            "sha256": receipt["classified_scene"]["sha256"],
            "point_count": int(receipt["point_count"]),
            "class_counts": receipt["class_counts"],
        }
    for condition, run_name in (
        ("E3", "E3_GS_IMAGE"),
        ("E4", "E4_GS_ALS_UNWEIGHTED"),
        ("E5", "E5_GS_ALS_WB"),
        ("E6", "E6_GS_LOD2_PLANES_DIAGNOSTIC"),
    ):
        root = task / "runs" / run_name / "roofer"
        classified = load_json(root / "classified_scene_receipt.json")
        roofer = load_json(root / "receipt.json")
        output[condition] = {
            "path": root / "classified_scene.laz",
            "sha256": roofer["classified_scene"]["sha256"],
            "point_count": int(classified["point_count"]),
            "class_counts": classified["class_counts"],
        }
    variants_path = task / "viewer/e3_local_variants.json"
    if variants_path.is_file():
        variants = load_json(variants_path)
        for variant in variants["variants"]:
            condition = f"E3_{variant['id']}"
            source = variant["classified_scene"]
            output[condition] = {
                "path": Path(source["path"]),
                "sha256": source["sha256"],
                "point_count": int(source["point_count"]),
                "class_counts": source["class_counts"],
            }
    return output


def sample_classes(source: Path, step: int) -> tuple[np.ndarray, np.ndarray, int]:
    ground_parts: list[np.ndarray] = []
    building_parts: list[np.ndarray] = []
    selected_offset = 0
    with laspy.open(source) as reader:
        for chunk in reader.chunk_iterator(2_000_000):
            classification = np.asarray(chunk.classification)
            selected = np.flatnonzero((classification == 2) | (classification == 6))
            if len(selected) == 0:
                continue
            positions = selected_offset + np.arange(len(selected), dtype=np.int64)
            keep = positions % step == 0
            chosen = selected[keep]
            if len(chosen):
                xyz = np.column_stack((
                    np.asarray(chunk.x)[chosen],
                    np.asarray(chunk.y)[chosen],
                    np.asarray(chunk.z)[chosen],
                ))
                xyz = (xyz - WORLD_SHIFT).astype(np.float32)
                chosen_classes = classification[chosen]
                if np.any(chosen_classes == 2):
                    ground_parts.append(xyz[chosen_classes == 2])
                if np.any(chosen_classes == 6):
                    building_parts.append(xyz[chosen_classes == 6])
            selected_offset += len(selected)
    ground = np.concatenate(ground_parts) if ground_parts else np.empty((0, 3), dtype=np.float32)
    building = np.concatenate(building_parts) if building_parts else np.empty((0, 3), dtype=np.float32)
    return ground, building, selected_offset


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifact-root", type=Path, required=True)
    parser.add_argument("--task-root", type=Path, required=True)
    args = parser.parse_args()
    artifacts = args.artifact_root.resolve()
    task = args.task_root.resolve()
    assets = task / "viewer/assets"
    assets.mkdir(parents=True, exist_ok=True)
    receipt_path = task / "viewer/roofer_pointclouds.json"
    source_map = sources(artifacts, task)
    expected_identity = {key: value["sha256"] for key, value in source_map.items()}
    previous_conditions = {}
    if receipt_path.is_file():
        receipt = load_json(receipt_path)
        if receipt.get("schema") == SCHEMA:
            previous_conditions = receipt.get("conditions", {})
        if (
            receipt.get("schema") == SCHEMA
            and receipt.get("source_identity") == expected_identity
            and all((task / "viewer" / item).is_file() for record in receipt["conditions"].values() for item in record["assets"].values())
        ):
            return 0

    conditions = {}
    for condition, source in source_map.items():
        previous = previous_conditions.get(condition)
        if (
            previous
            and previous.get("exact_source_sha256") == source["sha256"]
            and all((task / "viewer" / item).is_file() for item in previous.get("assets", {}).values())
        ):
            conditions[condition] = previous
            print(f"[viewer cloud] reuse {condition}", flush=True)
            continue
        for required in (source["path"],):
            if not required.is_file():
                raise FileNotFoundError(required)
        class_counts = source["class_counts"]
        class_2_or_6 = int(class_counts.get("2", 0)) + int(class_counts.get("6", 0))
        step = max(1, int(math.ceil(class_2_or_6 / MAX_DISPLAY_POINTS)))
        print(f"[viewer cloud] {condition} selected={class_2_or_6} step={step}", flush=True)
        ground, building, observed_selected = sample_classes(source["path"], step)
        if observed_selected != class_2_or_6:
            raise RuntimeError(
                f"{condition} class-count mismatch: receipt={class_2_or_6}, observed={observed_selected}"
            )
        ground_path = assets / f"{condition}_roofer_ground_xyz_f32.bin"
        building_path = assets / f"{condition}_roofer_building_xyz_f32.bin"
        ground.tofile(ground_path)
        building.tofile(building_path)
        conditions[condition] = {
            "exact_source": str(source["path"]),
            "exact_source_sha256": source["sha256"],
            "exact_point_count": source["point_count"],
            "exact_class_counts": class_counts,
            "display_classes": [2, 6],
            "display_decimation": f"DETERMINISTIC_CLASS_STREAM_EVERY_{step}TH_POINT",
            "display_point_count": int(len(ground) + len(building)),
            "display_class_counts": {"2": int(len(ground)), "6": int(len(building))},
            "assets": {
                "ground": f"assets/{ground_path.name}",
                "building": f"assets/{building_path.name}",
            },
            "asset_sha256": {
                "ground": sha256(ground_path),
                "building": sha256(building_path),
            },
        }
    receipt = {
        "schema": SCHEMA,
        "role": "DISPLAY_ADAPTERS_OF_EXACT_ROOFER_INPUT_CLASSIFIED_SCENES",
        "source_identity": expected_identity,
        "world_to_viewer_shift": (-WORLD_SHIFT).tolist(),
        "max_display_points_per_condition": MAX_DISPLAY_POINTS,
        "conditions": conditions,
        "exact_roofer_inputs_modified": False,
        "scientific_verdict": None,
    }
    atomic_json(receipt_path, receipt)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
