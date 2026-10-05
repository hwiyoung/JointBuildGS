"""Prepare one calibrated, geometry-selected stereo pair per fixed crop.

Only sealed GeoGS train RGB/cameras and original ALS acquisition arrays are read.
This is an explicit single-pair/common-frame input adaptation, not a multi-pair
or full-scene reproduction. Run only in a reference-free Docker container.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import platform
import time
import traceback

import cv2
import numpy as np

from src.phd.srdm_p1p2p3_v1.geometry import (
    disparity_bounds, inside_box, rectify_rgb, roi_projection_mask,
    select_pair, sparse_als_projection,
)


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(8 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def verify(path, expected):
    if not expected:
        raise ValueError(f"Missing expected source SHA256: {path}")
    actual = sha256(path)
    if actual != expected:
        raise ValueError(f"Sealed input SHA256 mismatch: {path}")
    return {"path": str(path), "sha256": actual, "bytes": Path(path).stat().st_size}


def write_json(path, value):
    with Path(path).open("x") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")


def resolve(root, relative):
    value = Path(relative)
    return value if value.is_absolute() else Path(root) / value


def require_isolation(root):
    if not Path("/.dockerenv").exists():
        raise RuntimeError("Project execution requires Docker")
    forbidden = [
        "phase-payloads/p0-audit/data/raw/tum2twin",
        "phase-payloads/phd/wu_vallet_regions_v4/PHD-WU-VALLET-REGIONS-EVALUATION-v4",
        "phase-payloads/phd/wu_vallet_p3_v1/PHD-WU-VALLET-P3-EVALUATION-v1-r2",
    ]
    if any((Path(root) / p).exists() for p in forbidden):
        raise RuntimeError("Raw/cropped UAS references must not be mounted during input preparation")


def prepare(config_path, artifact_root, output_root, region):
    started = time.monotonic()
    require_isolation(artifact_root)
    cfg = json.loads(Path(config_path).read_text())
    source_path = Path(cfg["source_config"])
    source = json.loads(source_path.read_text())
    als_source_path = Path(cfg.get("als_source_config", "configs/phd/mvs_als_source_relation_v1/run_v1.json"))
    als_source = json.loads(als_source_path.read_text())["inputs"]["existing_als"]
    source_file_names = sorted(als_source["files"])
    if float(als_source["z_shift_m"]) != float(source["crs"]["als_z_bridge_m"]):
        raise ValueError("ALS source metadata and common-frame vertical bridge differ")
    spec = source["regions"][region]
    roi = spec["domain"]
    bbox_min = np.array([roi[key][0] for key in ("x", "y", "z")])
    bbox_max = np.array([roi[key][1] for key in ("x", "y", "z")])
    task = resolve(artifact_root, cfg["geogs_task_relative"])
    input_root = task / "inputs" / region
    input_manifest_path = input_root / "input_manifest.json"
    records = [verify(input_manifest_path, cfg["geogs_input_manifest_sha256"][region])]
    manifest = json.loads(input_manifest_path.read_text())
    if manifest["region"] != region or manifest["status"] != "INPUTS_SEALED_FOR_EXECUTION":
        raise ValueError("Unexpected GeoGS input seal identity/status")
    split_path = input_root / manifest["split_path"]
    records.append(verify(split_path, manifest["split_sha256"]))
    split = json.loads(split_path.read_text())
    train = split["train"]
    evaluation_ids = {int(view["image_id"]) for view in split["evaluation"]}
    train_ids = [int(view["image_id"]) for view in train]
    if len(train_ids) != len(set(train_ids)) or set(train_ids) & evaluation_ids:
        raise ValueError("Train/evaluation membership is not disjoint")
    if len(train) != spec["expected_train"] or len(evaluation_ids) != spec["expected_test"]:
        raise ValueError("Frozen train/evaluation membership count mismatch")
    image_seals = {item["name"]: item for item in manifest["images"]}
    for view in train:
        if image_seals[view["name"]]["role"] != "train" or image_seals[view["name"]]["sha256"] != view["sha256"]:
            raise ValueError("Split train role/hash differs from input manifest")
    settings = cfg["pair_selection"]
    left, right, rect, selected, ledger = select_pair(train, bbox_min, bbox_max, settings)
    if left["image_id"] in evaluation_ids or right["image_id"] in evaluation_ids:
        raise ValueError("Selected evaluation view")
    rgb_images = []
    for view in (left, right):
        path = input_root / "scene/images" / view["name"]
        records.append(verify(path, view["sha256"]))
        bgr = cv2.imread(str(path), cv2.IMREAD_COLOR)
        if bgr is None or bgr.shape != (view["height"], view["width"], 3):
            raise ValueError(f"Unexpected native RGB size: {path}")
        rgb_images.append(cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB))
    left_rgb, left_valid = rectify_rgb(rgb_images[0], left["K"], rect["R1"], rect["P1"])
    right_rgb, right_valid = rectify_rgb(rgb_images[1], right["K"], rect["R2"], rect["P2"])
    minimum, maximum = disparity_bounds(bbox_min, bbox_max, left, right, rect, settings["disparity_margin_px"])
    roi_mask = roi_projection_mask(bbox_min, bbox_max, left, rect, left_valid.shape) & left_valid
    if not roi_mask.any():
        raise ValueError("Selected pair has no rectified ROI pixels")
    acquisition_path = resolve(artifact_root, spec["acquisition_npz"])
    records.append(verify(acquisition_path, spec["acquisition_sha256"]))
    context = spec["context_domain"]
    context_min = np.array([context[key][0] for key in ("x", "y", "z")])
    context_max = np.array([context[key][1] for key in ("x", "y", "z")])
    with np.load(acquisition_path, allow_pickle=False) as acquisition:
        full_xyz = acquisition["context_xyz"]
        keep = inside_box(full_xyz, context_min, context_max)
        context_rows = np.flatnonzero(keep)
        als_xyz = np.asarray(full_xyz[keep], np.float64)
        source_row = np.asarray(acquisition["context_original_row"][keep], np.int64)
        source_file = np.asarray(acquisition["context_original_file_index"][keep], np.int16)
    if not len(als_xyz):
        raise ValueError("No preserved ALS points in the declared context")
    if (source_file < 0).any() or (source_file >= len(source_file_names)).any():
        raise ValueError("ALS source file index lacks a recorded source file")
    source_keys = np.rec.fromarrays([source_file, source_row])
    if len(np.unique(source_keys)) != len(als_xyz):
        raise ValueError("Duplicate original ALS source rows")
    projection = sparse_als_projection(als_xyz, source_row, source_file, left, right, rect,
                                       left_valid, right_valid, minimum, maximum)
    if not np.isfinite(projection["sparse_disparity"]).any():
        raise ValueError("Selected camera pair provides no sparse ALS seed; pair is not reselected using ALS")
    arrays = {key: rect[key] for key in ("Q", "P1", "P2", "R1", "R2")}
    arrays.update(projection)
    arrays.update(left_rgb=left_rgb, right_rgb=right_rgb,
                  left_valid_mask=left_valid, right_valid_mask=right_valid, roi_mask=roi_mask,
                  K1=np.asarray(left["K"]), K2=np.asarray(right["K"]),
                  world_to_left_R=np.asarray(left["R"]), world_to_left_t=np.asarray(left["t"]),
                  world_to_right_R=np.asarray(right["R"]), world_to_right_t=np.asarray(right["t"]),
                  rectified_left_to_world_R=np.asarray(left["R"]).T @ rect["R1"].T,
                  rectified_left_to_world_t=-np.asarray(left["R"]).T @ np.asarray(left["t"]),
                  bbox_min=bbox_min, bbox_max=bbox_max, context_bbox_min=context_min, context_bbox_max=context_max,
                  disparity_min=np.asarray(minimum, np.int32), disparity_max=np.asarray(maximum, np.int32),
                  left_image_id=np.asarray(left["image_id"], np.int64), right_image_id=np.asarray(right["image_id"], np.int64),
                  als_xyz=als_xyz, als_source_row=source_row, als_source_file_index=source_file,
                  als_acquisition_context_row=context_rows, als_in_roi=inside_box(als_xyz, bbox_min, bbox_max))
    output = Path(output_root) / region
    output.mkdir(parents=True, exist_ok=False)
    np.savez_compressed(output / "pair.npz", **arrays)
    write_json(output / "pair_selection.json", {"rule": settings, "selected": selected, "candidates": ledger})
    metadata = dict(
        schema="jointbuildgs.srdm.single_pair_inputs.v1", task_id=cfg["task_id"], region=region,
        scientific_verdict=None, status="INPUT_PAIR_PREPARED", created_utc=datetime.now(timezone.utc).isoformat(),
        source_config={"path": str(source_path), "sha256": sha256(source_path)},
        als_source_config={"path": str(als_source_path), "sha256": sha256(als_source_path)},
        als_source_files=[{"file_index": i, "name": name, "recorded_sha256": als_source["files"][name]}
                          for i, name in enumerate(source_file_names)],
        als_raw_files_reopened=False,
        config={"path": str(config_path), "sha256": sha256(config_path)}, input_records=records,
        source_scripts=[{"path": str(Path(__file__)), "sha256": sha256(__file__)},
                        {"path": "src/phd/srdm_p1p2p3_v1/geometry.py", "sha256": sha256("src/phd/srdm_p1p2p3_v1/geometry.py")}],
        versions={"python": platform.python_version(), "numpy": np.__version__, "opencv": cv2.__version__},
        selected_pair=selected, left={k: left[k] for k in ("image_id", "camera_id", "name", "sha256", "K", "R", "t", "width", "height")},
        right={k: right[k] for k in ("image_id", "camera_id", "name", "sha256", "K", "R", "t", "width", "height")},
        pair_selection_settings=settings, pair_count=len(ledger), eligible_pair_count=sum(x["status"] == "ELIGIBLE" for x in ledger),
        rectification={"alpha": settings["rectification_alpha"], "native_size": list(left_rgb.shape[:2][::-1]),
                       "resized": False, "interpolation": "OpenCV INTER_LINEAR inverse remap of already undistorted RGB",
                       "distortion": "zero; source already undistorted", "signed_disparity": "u_left - u_right; positive",
                       "valid_rect_left": rect["valid_rect_left"], "valid_rect_right": rect["valid_rect_right"]},
        disparity_search={"minimum_inclusive": minimum, "maximum_inclusive": maximum,
                          "source": "extrema of fixed 3D ROI corners in calibrated rectified geometry, with declared pixel margin",
                          "full_volume_float32_gib": left_rgb.shape[0]*left_rgb.shape[1]*(maximum-minimum+1)*4/(1024**3)},
        crs=source["crs"], roi=roi, context_domain=context,
        als_counts={"context": len(als_xyz), "in_roi": int(arrays["als_in_roi"].sum()),
                    "sparse": int(np.isfinite(projection["sparse_disparity"]).sum()),
                    "projection_state": {str(i): int((projection["als_projection_state"] == i).sum()) for i in (0, 2, 3, 4)}},
        projection_state_definition={"0": "behind/outside/either rectified remap invalid", "2": "loses either ALS point z buffer", "3": "selected sparse seed", "4": "outside fixed ROI disparity bounds"},
        sparse_projection_limitations="Nearest pixel, nearest raw ALS depth in both views; no current-scene visibility or temporal-validity inference. Sparse depth is sampled at rounded left pixel, with subpixel original projections retained.",
        deviations=["Single selected stereo pair per region, not full multi-pair scene fusion",
                    "Existing common-frame ALS/camera coordinates retained; no new registration, pose fitting, or datum calibration",
                    "Geometry-only pair selection values are adapter choices, not claimed SRDM paper constants",
                    "Original ALS retained; no surface densification before sparse projection"],
        evaluation_reference_accessed=False, new_training_executed=False,
        pair_npz={"path": str(output / "pair.npz"), "sha256": sha256(output / "pair.npz")},
        seconds=time.monotonic()-started,
    )
    write_json(output / "metadata.json", metadata)
    print(json.dumps({"region": region, "status": metadata["status"], "selected_pair": selected,
                      "disparity_search": metadata["disparity_search"], "als_counts": metadata["als_counts"]}), flush=True)
    return metadata


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True)
    parser.add_argument("--artifact-root", required=True)
    parser.add_argument("--output-root", required=True)
    parser.add_argument("--region", required=True, choices=("P1", "P2", "P3"))
    args = parser.parse_args()
    try:
        prepare(args.config, args.artifact_root, args.output_root, args.region)
    except Exception as error:
        # No existing region is overwritten, including on failure.
        failure = Path(args.output_root) / f"{args.region}_preparation_failure_{time.time_ns()}.json"
        failure.parent.mkdir(parents=True, exist_ok=True)
        write_json(failure, {"status": "FAILED", "scientific_verdict": None, "error": str(error), "traceback": traceback.format_exc()})
        raise


if __name__ == "__main__":
    main()
