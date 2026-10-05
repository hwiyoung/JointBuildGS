"""Build a new regional SfM initialization without changing sealed ALS inputs.

The source SfM was reconstructed with the historical full image set. Selecting
points with at least two regional training tracks does not undo that provenance.
Only standard-library dependencies are needed; execution is Docker-only.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import struct
import sys
import time


SOURCE_POINTS_SHA256 = "bf93766e9773bdc59ce393cf1a36de4b3801cadc1bf834ea705396f5e9a706c3"
SOURCE_POINT_COUNT = 371808


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(8 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def unpack(stream, fmt):
    size = struct.calcsize("<" + fmt)
    data = stream.read(size)
    if len(data) != size:
        raise ValueError("Truncated COLMAP input")
    return struct.unpack("<" + fmt, data)


def image_metadata(path):
    result = {}
    with Path(path).open("rb") as stream:
        for _ in range(unpack(stream, "Q")[0]):
            row = unpack(stream, "idddddddi")
            name = bytearray()
            while True:
                character = stream.read(1)
                if not character:
                    raise ValueError("Truncated COLMAP image name")
                if character == b"\0":
                    break
                name.extend(character)
            count = unpack(stream, "Q")[0]
            stream.seek(count * 24, 1)
            if row[0] in result:
                raise ValueError("Duplicate COLMAP image ID")
            result[row[0]] = (row, name.decode("utf-8"), count)
        if stream.read(1):
            raise ValueError("Trailing COLMAP images bytes")
    return result


def points(path):
    with Path(path).open("rb") as stream:
        count = unpack(stream, "Q")[0]
        if count != SOURCE_POINT_COUNT:
            raise ValueError("Frozen SfM point count changed")
        for _ in range(count):
            row = unpack(stream, "QdddBBBdQ")
            track = [unpack(stream, "ii") for _ in range(row[-1])]
            yield row[:-1], track
        if stream.read(1):
            raise ValueError("Trailing COLMAP points bytes")


def write_json(path, data):
    with Path(path).open("x") as stream:
        json.dump(data, stream, indent=2, ensure_ascii=False, allow_nan=False)
        stream.write("\n")


def record(path):
    path = Path(path)
    return {"path": str(path), "bytes": path.stat().st_size, "sha256": sha(path)}


def prepare(args):
    started = time.monotonic()
    if not Path("/.dockerenv").is_file():
        raise RuntimeError("Project input generation requires Docker")
    original = args.original_input.resolve()
    sparse = args.sparse.resolve()
    output = args.output.absolute()
    if output.exists() or output.is_symlink():
        raise FileExistsError(f"Refusing existing output: {output}")
    if original == output or original in output.parents:
        raise ValueError("Output must be separate from original input")
    cfg = json.loads(args.base_config.read_text())
    region_cfg = cfg["regions"][args.region]
    experiment = None
    if args.experiment_config is not None:
        experiment = json.loads(args.experiment_config.read_text())
        if experiment["base_config_sha256"] != sha(args.base_config):
            raise ValueError("Experiment base config identity differs")
        init = experiment["initialization"]
        if init["points3D_sha256"] != SOURCE_POINTS_SHA256 or init["min_regional_train_track_observations"] != 2:
            raise ValueError("Experiment SfM selection differs from this frozen adapter")
    if cfg["crs"]["world_shift"] != [690953, 5336071, 604]:
        raise ValueError("Frozen scene frame changed")
    source_records = {}
    for name, expected in {
        "cameras.bin": cfg["camera_hashes"]["cameras"],
        "images.bin": cfg["camera_hashes"]["images"],
        "points3D.bin": SOURCE_POINTS_SHA256,
    }.items():
        item = record(sparse / name)
        if item["sha256"] != expected:
            raise ValueError(f"Frozen SfM source changed: {name}")
        source_records[name] = item
    sealed_manifest = json.loads((original / "input_manifest.json").read_text())
    if sealed_manifest["region"] != args.region:
        raise ValueError("Sealed regional input identity differs")
    split_path = original / sealed_manifest["split_path"]
    if sha(split_path) != sealed_manifest["split_sha256"]:
        raise ValueError("Sealed split hash differs")
    split = json.loads(split_path.read_text())
    train_ids = {int(view["image_id"]) for view in split["train"]}
    eval_ids = {int(view["image_id"]) for view in split["evaluation"]}
    if train_ids & eval_ids:
        raise ValueError("Training and evaluation memberships overlap")
    if (len(train_ids), len(eval_ids)) != (region_cfg["expected_train"], region_cfg["expected_test"]):
        raise ValueError("Frozen split cardinality changed")
    source_images = image_metadata(sparse / "images.bin")
    scene_source = original / "scene"
    regional_sparse = scene_source / "sparse/0"
    regional_images = image_metadata(regional_sparse / "images.bin")
    if set(regional_images) != train_ids | eval_ids:
        raise ValueError("Regional COLMAP images differ from split")
    if sha(regional_sparse / "cameras.bin") != cfg["camera_hashes"]["cameras"]:
        raise ValueError("Regional camera calibration differs from frozen source")
    for image_id, (row, name, _) in regional_images.items():
        source_row, source_name, _ = source_images[image_id]
        if row != source_row or name != source_name:
            raise ValueError("Regional pose differs from frozen full-source SfM")
    box = [region_cfg["context_domain"][key] for key in ("x", "y", "z")]
    selected = []
    ledger = {"source_points": SOURCE_POINT_COUNT, "outside_context": 0,
              "inside_context": 0, "dropped_fewer_than_two_regional_train_tracks": 0,
              "retained": 0, "retained_with_regional_eval_tracks": 0,
              "retained_with_outside_region_tracks": 0,
              "retained_with_only_regional_train_tracks": 0}
    for row, track in points(sparse / "points3D.bin"):
        xyz = row[1:4]
        if not all(math.isfinite(value) for value in (*xyz, row[-1])):
            raise ValueError("Nonfinite frozen SfM point")
        # Source points and camera translations are ALREADY in this local frame.
        # Applying world_shift a second time would move every point off scene.
        if not all(lo <= value <= hi for (lo, hi), value in zip(box, xyz)):
            ledger["outside_context"] += 1
            continue
        ledger["inside_context"] += 1
        observed = {image_id for image_id, _ in track}
        regional_train = observed & train_ids
        if len(regional_train) < 2:
            ledger["dropped_fewer_than_two_regional_train_tracks"] += 1
            continue
        for image_id, point2d_idx in track:
            if image_id not in source_images or not 0 <= point2d_idx < source_images[image_id][2]:
                raise ValueError("Source SfM track points outside source image observations")
        regional_eval = observed & eval_ids
        outside = observed - train_ids - eval_ids
        ledger["retained"] += 1
        ledger["retained_with_regional_eval_tracks"] += bool(regional_eval)
        ledger["retained_with_outside_region_tracks"] += bool(outside)
        ledger["retained_with_only_regional_train_tracks"] += observed <= train_ids
        selected.append((row, track, sorted(regional_train), sorted(regional_eval), sorted(outside)))
    if not selected:
        raise ValueError("No regional SfM points satisfy frozen context/train-track selection")
    output.mkdir(parents=True, exist_ok=False)
    try:
        shutil.copyfile(Path(__file__), output / "prepare_sfm_snapshot.py")
        shutil.copyfile(args.base_config, output / "base_config_snapshot.json")
        if args.experiment_config is not None:
            shutil.copyfile(args.experiment_config, output / "experiment_config_snapshot.json")
        scene = output / "scene"
        target_sparse = scene / "sparse/0"
        target_sparse.mkdir(parents=True)
        camera_records = {}
        for name in ("cameras.bin", "images.bin", "cameras.txt", "images.txt"):
            source = regional_sparse / name
            if source.is_file():
                shutil.copyfile(source, target_sparse / name)
                if sha(source) != sha(target_sparse / name):
                    raise ValueError("Regional camera/pose copy failed integrity check")
                camera_records[name] = record(target_sparse / name)
        linked_inputs = {}
        for name in ("images", "jbgs_calibration.json", "scene_reference_frame.json",
                     "split_manifest.json", "split_manifest_v2.json", "split_manifest_da3_v2.json"):
            source = scene_source / name
            if source.exists():
                os.symlink(str(source), str(scene / name), target_is_directory=source.is_dir())
                linked_inputs[name] = str(source)
        ply_path = target_sparse / "points3D.ply"
        header = ("ply\nformat binary_little_endian 1.0\n"
                  f"element vertex {len(selected)}\n"
                  "property float x\nproperty float y\nproperty float z\n"
                  "property float nx\nproperty float ny\nproperty float nz\n"
                  "property uchar red\nproperty uchar green\nproperty uchar blue\nend_header\n")
        rounding_max = 0.0
        with ply_path.open("xb") as stream:
            stream.write(header.encode("ascii"))
            for row, *_ in selected:
                xyz = row[1:4]
                packed = struct.pack("<ffffffBBB", *xyz, 0.0, 0.0, 0.0, *row[4:7])
                rounded = struct.unpack_from("<fff", packed)
                rounding_max = max(rounding_max, *(abs(a-b) for a, b in zip(xyz, rounded)))
                stream.write(packed)
        with (output / "source_points.csv").open("x", newline="") as stream:
            writer = csv.writer(stream)
            writer.writerow(["output_vertex_index", "source_point_id", "x", "y", "z", "red", "green", "blue",
                             "source_reprojection_error", "source_track_count", "regional_train_view_count",
                             "regional_eval_view_count", "outside_region_view_count"])
            for index, (row, track, train, evaluation, outside) in enumerate(selected):
                writer.writerow([index, *row, len(track), len(train), len(evaluation), len(outside)])
        with (output / "source_tracks.jsonl").open("x") as stream:
            for index, (row, track, train, evaluation, outside) in enumerate(selected):
                stream.write(json.dumps({"output_vertex_index": index, "source_point_id": row[0],
                    "original_tracks_image_id_point2d_idx": track, "regional_train_image_ids": train,
                    "regional_eval_image_ids": evaluation, "outside_region_image_ids": outside}) + "\n")
        write_json(output / "selection_loss_ledger.json", ledger)
        manifest = {
            "schema": "jointbuildgs.geogs.sfm_initialization.v1", "status": "SFM_INITIALIZATION_PREPARED",
            "region": args.region, "scientific_verdict": None,
            "source_kind": "image_sfm", "contains_als_points": False,
            "point_count": len(selected), "points_ply_path": "scene/sparse/0/points3D.ply",
            "points_ply_sha256": sha(ply_path), "source_points3D_sha256": SOURCE_POINTS_SHA256,
            "source_files": source_records, "source_image_count": len(source_images),
            "original_input_manifest": record(original / "input_manifest.json"),
            "original_split": record(split_path), "base_config": record(args.base_config),
            "script": record(Path(__file__)), "command": sys.argv,
            "script_snapshot": record(output / "prepare_sfm_snapshot.py"),
            "base_config_snapshot": record(output / "base_config_snapshot.json"),
            "experiment_config_snapshot": (record(output / "experiment_config_snapshot.json")
                                           if experiment is not None else None),
            "runtime": {"python": sys.version, "docker": True,
                        "image_id": os.environ.get("GEOGS_SFM_INPUT_IMAGE_ID")},
            "context_domain": region_cfg["context_domain"], "minimum_regional_train_observations": 2,
            "selection_order": "original points3D.bin record order; no subsampling, voxel merge, or reference selection",
            "coordinate_frame": {"working_crs": "EPSG:25832", "already_scene_local": True,
                "world_shift_for_global_interpretation_only": cfg["crs"]["world_shift"],
                "applied_translation": [0, 0, 0], "applied_scale": 1.0,
                "source_double_to_ply_float32_max_abs_rounding_m": rounding_max},
            "color_policy": "Original SfM RGB retained; historical full-source image aggregation, not recomputed from current training split",
            "geometry_provenance": "Historical full-source SfM triangulation/optimization; track filtering does not remove historical evaluation-image influence",
            "evaluation_images_used_in_current_preparation": False,
            "historical_evaluation_image_influence_removed": False,
            "independent_confirmatory": False, "reference_geometry_read": False,
            "normals": "zero placeholders required by the official PLY loader; not measured normal supervision",
            "colmap_graph": "Only existing PLY is used for initialization. No points3D.bin/txt is synthesized because regional images.bin intentionally has zero 2D observations; source tracks are preserved separately.",
            "camera_files": camera_records, "linked_original_scene_inputs": linked_inputs,
            "training_requires_original_regional_input_at": str(original),
            "selection_loss_ledger": ledger,
            "provenance_files": [record(output / name) for name in
                                 ("source_points.csv", "source_tracks.jsonl", "selection_loss_ledger.json")],
            "elapsed_seconds": time.monotonic() - started,
        }
        write_json(output / "initialization_manifest.json", manifest)
        print(json.dumps({key: manifest[key] for key in
            ("status", "region", "point_count", "points_ply_sha256", "selection_loss_ledger")}, indent=2))
    except Exception as error:
        failure = output / "PREPARATION_FAILURE.json"
        if not failure.exists():
            write_json(failure, {"status": "FAIL", "error_type": type(error).__name__,
                                "error": str(error), "scientific_verdict": None})
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--original-input", required=True, type=Path)
    parser.add_argument("--sparse", required=True, type=Path)
    parser.add_argument("--base-config", required=True, type=Path)
    parser.add_argument("--experiment-config", type=Path)
    parser.add_argument("--region", required=True, choices=("P1", "P2", "P3"))
    parser.add_argument("--output", required=True, type=Path)
    prepare(parser.parse_args())


if __name__ == "__main__":
    main()
