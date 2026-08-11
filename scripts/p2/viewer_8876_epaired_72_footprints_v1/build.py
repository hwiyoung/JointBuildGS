#!/usr/bin/env python3
"""Replace the mistaken 58-building overlay with the frozen E_paired 72 footprints."""
from __future__ import annotations

from collections import Counter
import csv
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path


REPO = Path("/workspace/JointBuildGS")
AR = Path("/artifacts/JointBuildGS")
CONFIG = REPO / "configs/p2/viewer_8876_epaired_72_footprints_v1/viewer.json"
SOURCE = REPO / "scripts/p2/viewer_8876_epaired_72_footprints_v1/build.py"
TASK = AR / "phase-payloads/p2/viewer_8876_epaired_72_footprints_v1/P2-VIEWER-8876-EPAIRED-72-FOOTPRINTS-v1"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def verify(path: Path, expected: str) -> dict:
    if not path.is_file():
        raise RuntimeError(f"missing input: {path}")
    actual = sha256(path)
    if actual != expected:
        raise RuntimeError(f"sha256 drift: {path}: {actual} != {expected}")
    return {"path": str(path), "bytes": path.stat().st_size, "sha256": actual}


def atomic_text(path: Path, body: str) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(body)
    os.replace(temporary, path)


def atomic_json(path: Path, body: object) -> None:
    atomic_text(path, json.dumps(body, indent=2, sort_keys=True) + "\n")


def main() -> None:
    cfg = json.loads(CONFIG.read_text())
    if TASK.exists():
        raise RuntimeError(f"add-once task exists: {TASK}")
    viewer = AR / cfg["viewer_root"]
    before = {name: verify(viewer / name, expected) for name, expected in cfg["expected_before"].items()}
    membership_path = REPO / cfg["membership_csv"]
    footprint_path = AR / cfg["shared_footprints"]
    building_path = AR / cfg["building_manifest"]
    bindings = {
        "membership_csv": verify(membership_path, cfg["membership_csv_sha256"]),
        "shared_footprints": verify(footprint_path, cfg["shared_footprints_sha256"]),
        "building_manifest": verify(building_path, cfg["building_manifest_sha256"]),
    }
    with membership_path.open(newline="") as stream:
        membership = list(csv.DictReader(stream))
    if len(membership) != int(cfg["expected_target_count"]):
        raise RuntimeError(f"E_paired count drifted: {len(membership)}")
    split_counts = Counter(row["split"] for row in membership)
    if dict(split_counts) != cfg["expected_split_counts"]:
        raise RuntimeError(f"split count drifted: {dict(split_counts)}")

    footprints = json.loads(footprint_path.read_text())
    footprint_by_id = {feature["properties"]["stable_id"]: feature for feature in footprints["features"]}
    buildings = [json.loads(line) for line in building_path.read_text().splitlines() if line]
    building_by_id = {row["building_id"]: row for row in buildings}
    shift_x, shift_y, shift_z = map(float, cfg["world_shift_xyz"])
    target_footprints = []
    for row in membership:
        stable_id = row["stable_id"]
        geometry = footprint_by_id[stable_id]["geometry"]
        if geometry["type"] != "Polygon":
            raise RuntimeError(f"unsupported geometry: {stable_id}: {geometry['type']}")
        z_min, z_max = map(float, building_by_id[stable_id]["z_range_ellipsoidal_m"])
        target_footprints.append({
            "stable_id": stable_id,
            "rings_local_xy": [
                [[float(x) - shift_x, float(y) - shift_y] for x, y in ring]
                for ring in geometry["coordinates"]
            ],
            "z_local": (z_min + z_max) / 2.0 - shift_z + float(cfg["display_z_offset_m"]),
            "z_source": "EVALUATION_BUILDING_Z_RANGE_DISPLAY_ALIGNMENT_ONLY_NOT_MODEL_INPUT",
            "membership": "E_paired",
            "split": row["split"],
            "display_style": "E_PAIRED_UNIFORM_NO_SPLIT_ENCODING",
            "color": cfg["target_color"],
        })

    manifest_path = viewer / "viewer_manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["target_building_footprints"] = target_footprints
    manifest["target_building_footprint_contract"] = {
        "membership": "E_paired",
        "target_rule": cfg["target_rule"],
        "target_count": len(target_footprints),
        "split_counts": dict(split_counts),
        "default_visible": bool(cfg["default_visible"]),
        "all_199_building_index_role": cfg["all_199_role"],
        "only_epaired_72_footprints_are_rendered": True,
        "split_not_encoded_in_display_style": True,
        "outline_width_m": float(cfg["outline_width_m"]),
        "evaluation_z_used_for_display_alignment_only": True,
        "supersedes_mistaken_sparse_present_mvs_raw_support_58_overlay": True,
        "roofer_inputs_modified": False,
        "scientific_verdict": None,
    }
    manifest["roofer_inputs_modified"] = False
    manifest["scientific_verdict"] = None
    atomic_json(manifest_path, manifest)

    app_path = viewer / "app.js"
    app = app_path.read_text()
    app = app.replace(
        "opacity: row.strength === 'strong' ? 0.98 : 0.90,",
        "opacity: 0.98,",
    )
    app = app.replace("대상58 footprint", "대상72 footprint")
    app = app.replace(
        "MVS raw support 부족 + sparse seed 존재 58동만 표시 · strong 51 cyan / weak 7 amber",
        "현재 영상 MVS와 독립 UAS LiDAR 지원이 함께 있는 E_paired 72동만 표시",
    ).replace("대상 58동 footprint 숨김", "E_paired 72동 footprint 숨김")
    app = app.replace(
        "표면 mesh 로드 완료 · 대상 footprint 58동만 ON (strong 51 / weak 7)",
        "표면 mesh 로드 완료 · image/LiDAR 공통 대상 E_paired 72동 footprint ON",
    ).replace(
        "8개 패널 로드 완료 · 대상 footprint 58동만 ON (strong 51 / weak 7)",
        "8개 패널 로드 완료 · image/LiDAR 공통 대상 E_paired 72동 footprint ON",
    )
    atomic_text(app_path, app)

    index_path = viewer / "index.html"
    index = index_path.read_text()
    index = index.replace("대상58 footprint ON", "대상72 footprint ON")
    index = index.replace(
        '<span><i style="background:#00e5ff"></i>대상 strong 51</span><span><i style="background:#ffb020"></i>대상 weak 7</span>',
        '<span><i style="background:#00e5ff"></i>image/LiDAR 공통 대상 72</span>',
    )
    index = index.replace(
        "app.js?v=e1e6-20260810-target-footprints-58-v1",
        "app.js?v=e1e6-20260810-epaired-72-footprints-v1",
    )
    atomic_text(index_path, index)

    after = {name: {"bytes": (viewer / name).stat().st_size, "sha256": sha256(viewer / name)} for name in cfg["expected_before"]}
    TASK.mkdir(parents=True)
    receipt = {
        "schema": "jointbuildgs.p2.viewer_8876_epaired_72_footprints.receipt.v1",
        "task_id": cfg["task_id"],
        "created_at": datetime.now(timezone.utc).isoformat(),
        "config": {"path": str(CONFIG), "sha256": sha256(CONFIG)},
        "script": {"path": str(SOURCE), "sha256": sha256(SOURCE)},
        "bindings": bindings,
        "counts": {"E_paired": len(target_footprints), "split": dict(split_counts)},
        "viewer_before": before,
        "viewer_after": after,
        "only_epaired_72_footprints_rendered": True,
        "mistaken_58_overlay_removed_from_live_view": True,
        "all_199_index_preserved_for_non_visible_camera_lookup": True,
        "roofer_inputs_modified": False,
        "scientific_verdict": None,
    }
    atomic_json(TASK / "receipt.json", receipt)
    print(json.dumps(receipt, indent=2))


if __name__ == "__main__":
    main()
