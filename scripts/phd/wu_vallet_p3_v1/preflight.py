"""P3 input freeze and original Wu--Vallet reproduction readiness, Docker only.

This program does not perform source decisions, registration or reconstruction.
Missing validated sensor topology closes the original-method reproduction gate.
All existing sources are read-only; only a new output directory is written.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import re
import shutil
import time
import traceback

import laspy
import numpy as np

from src.stage2.colmap_io import read_cameras_bin, read_images_bin
from scripts.phd.mvs_als_source_relation_v1.run import (
    in_domain, parse_binary_ply_vertices, tile_indices,
)

REPO = Path(__file__).resolve().parents[3]


def read(path):
    return json.loads(Path(path).read_text())


def write(path, value):
    with Path(path).open("x") as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2, allow_nan=False)
        handle.write("\n")


def record(path, expected=None):
    path = Path(path)
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(8 << 20), b""):
            digest.update(block)
    result = dict(path=str(path), bytes=path.stat().st_size, sha256=digest.hexdigest())
    if expected is not None and result["sha256"] != expected:
        raise ValueError(f"Input hash mismatch: {path}")
    return result


def depth_header(path):
    with Path(path).open("rb") as handle:
        header = bytearray()
        while header.count(b"&") < 3 and len(header) < 128:
            byte = handle.read(1)
            if not byte:
                raise ValueError(f"Incomplete COLMAP array header: {path}")
            header.extend(byte)
    if header.count(b"&") != 3:
        raise ValueError(f"Invalid COLMAP array header: {path}")
    width, height, channels = map(int, bytes(header).split(b"&")[:3])
    if Path(path).stat().st_size != len(header) + width * height * channels * 4:
        raise ValueError(f"COLMAP array byte count differs: {path}")
    return dict(width=width, height=height, channels=channels, header_bytes=len(header))


def bounded_search(root, cfg):
    pattern = re.compile(cfg["name_pattern"])
    scanned, candidates, truncated = 0, [], False
    if not root.exists():
        return dict(root=str(root), exists=False, entries_scanned=0, candidates=[])
    for current, dirs, names in os.walk(root, followlinks=False):
        depth = len(Path(current).relative_to(root).parts)
        dirs[:] = sorted(d for d in dirs if not d.startswith(".")) if depth < cfg["maximum_depth"] else []
        for name in sorted(names):
            scanned += 1
            if scanned > cfg["maximum_entries_per_root"]:
                truncated = True
                break
            if pattern.search(name):
                path = Path(current) / name
                candidates.append(dict(path=str(path), bytes=path.stat().st_size, role="UNVALIDATED_FILENAME_CANDIDATE"))
        if truncated:
            break
    return dict(root=str(root), exists=True, entries_scanned=min(scanned, cfg["maximum_entries_per_root"]),
                limit_reached=truncated, maximum_depth=cfg["maximum_depth"], candidates=candidates)


def las_metadata(path, maximum):
    with laspy.open(path) as handle:
        header = handle.header
        dimensions = list(header.point_format.dimension_names)
        sample = handle.read_points(min(header.point_count, maximum))
        stats = {}
        for name in ["gps_time", "point_source_id", "return_number", "number_of_returns", "scan_angle", "scan_angle_rank", "scanner_channel", "scan_direction_flag", "edge_of_flight_line"]:
            if name not in dimensions:
                continue
            values = np.asarray(sample[name])
            finite = values[np.isfinite(values)]
            stats[name] = dict(count=len(values), finite_count=len(finite),
                               minimum=float(finite.min()) if len(finite) else None,
                               maximum=float(finite.max()) if len(finite) else None,
                               sampled_unique_count=len(np.unique(finite)))
        return dict(path=str(path), point_count=header.point_count, point_format=header.point_format.id,
                    dimensions=dimensions, bounds=[header.mins.tolist(), header.maxs.tolist()],
                    global_encoding_value=header.global_encoding.value,
                    vlrs=[dict(user_id=v.user_id, record_id=v.record_id, description=v.description) for v in header.vlrs],
                    first_points_sample_count=len(sample), sample_stats=stats,
                    interpretation="GPS time/strip fields, if present, do not establish the sensor origin or scan adjacency required for an acquisition sensor mesh")


def raw_membership(root, source_cfg, source, tile, selected, tile_xy, records):
    """Replay the exact source-to-tile route and recover every selected original row."""
    shift = np.asarray(source_cfg["frame"]["world_shift_xyz_m"])
    fields = {"original_row": [], "original_file_index": []}
    if source == "mvs":
        fields["rgb"] = []
    offset, names = 0, []

    def accept(xyz, raw_offset, file_index, rgb=None):
        nonlocal offset
        world_xy = xyz[:, :2].astype(np.float64) + shift[:2]
        tx, ty = tile_indices(source_cfg, world_xy)
        membership = in_domain(source_cfg, world_xy) & (tx == tile_xy[0]) & (ty == tile_xy[1])
        raw_rows = np.flatnonzero(membership)
        local = xyz[membership].astype("<f4")
        if not np.array_equal(local, tile[offset:offset + len(local)]):
            raise ValueError(f"Original-to-tile exact replay mismatch: {source}, tile row {offset}")
        wanted = selected[(selected >= offset) & (selected < offset + len(local))] - offset
        fields["original_row"].append(raw_rows[wanted].astype(np.int64) + raw_offset)
        fields["original_file_index"].append(np.full(len(wanted), file_index, dtype=np.int16))
        if rgb is not None:
            fields["rgb"].append(rgb[raw_rows[wanted]])
        offset += len(local)

    if source == "mvs":
        spec = source_cfg["inputs"]["mvs"]
        path = root / spec["relative_path"]
        records.append(record(path, spec["sha256"]))
        names.append(str(path))
        vertices, properties, _ = parse_binary_ply_vertices(path)
        for start in range(0, len(vertices), 2_000_000):
            chunk = vertices[start:start + 2_000_000]
            accept(np.column_stack([chunk[k] for k in ["x", "y", "z"]]), start, 0,
                   np.column_stack([chunk[k] for k in ["red", "green", "blue"]]))
        source_topology = dict(vertex_properties=properties,
                               acquisition_pixel_lineage_in_ply=False,
                               note="Fused XYZ/RGB has no originating image and depth pixel fields; existing raster depth is audited separately")
    else:
        spec = source_cfg["inputs"]["existing_als"]
        for index, name in enumerate(sorted(spec["files"])):
            path = root / spec["relative_root"] / name
            records.append(record(path, spec["files"][name]))
            names.append(str(path))
            raw_offset = 0
            with laspy.open(path) as handle:
                for chunk in handle.chunk_iterator(2_000_000):
                    xyz = np.column_stack([np.asarray(chunk.x), np.asarray(chunk.y), np.asarray(chunk.z) + spec["z_shift_m"]]) - shift
                    accept(xyz, raw_offset, index)
                    raw_offset += len(chunk)
        source_topology = dict(trajectory_embedded_in_xyz_partition=False)
    if offset != len(tile):
        raise ValueError(f"Incomplete raw tile reconstruction: {source}")
    fields = {key: np.concatenate(value) for key, value in fields.items()}
    if len(fields["original_row"]) != len(selected):
        raise ValueError(f"Incomplete original row membership: {source}")
    return fields, dict(raw_files=names, native_selected_points=len(selected), tile_points=len(tile),
                        exact_raw_to_tile_replay=True, topology=source_topology)


def main(config_path, output_override=None):
    if not Path("/.dockerenv").exists():
        raise RuntimeError("Run inside the pinned project Docker image")
    cfg = read(config_path)
    root = Path(cfg["artifact_root"])
    output = Path(output_override) if output_override else root / cfg["output_relative_root"]
    if output.exists():
        if any(output.iterdir()):
            raise ValueError("New empty output directory required")
    else:
        output.mkdir(parents=True, exist_ok=False)
    started = time.monotonic()
    write(output / "STARTED.json", dict(task_id=cfg["task_id"], utc=datetime.now(timezone.utc).isoformat(), scientific_verdict=None))
    try:
        records = [record(config_path), record(__file__),
                   record(REPO / "src/stage2/colmap_io.py"),
                   record(REPO / "scripts/phd/mvs_als_source_relation_v1/run.py")]
        patch = read(REPO / cfg["patch_config"])
        camera_cfg = read(REPO / cfg["camera_config"])
        source_cfg = read(REPO / cfg["source_config"])
        for key in ["patch_config", "camera_config", "source_config", "image_member_inventory", "derivative_lineage"]:
            records.append(record(REPO / cfg[key]))
        patch_root = root / patch["output_relative_root"]
        relation_root = root / patch["inputs"]["source_relation_relative_root"]
        patch_manifest_path = patch_root / "artifact_manifest.json"
        records.append(record(patch_manifest_path, cfg["patch_manifest_sha256"]))
        patch_manifest = read(patch_manifest_path)
        arrays, membership = {}, {}
        for source in ["mvs", "als"]:
            spec = patch["inputs"]["partitions"][source]
            path = relation_root / spec["relative_path"]
            records.append(record(path, spec["sha256"]))
            tile = np.memmap(path, mode="r", dtype="<f4").reshape(-1, 3)
            keep = np.ones(len(tile), dtype=bool)
            for axis, name in enumerate(["x", "y", "z"]):
                keep &= (tile[:, axis] >= patch["domain"][name][0]) & (tile[:, axis] < patch["domain"][name][1])
            rows = np.flatnonzero(keep)
            old = {}
            for name in [f"point_rows_{source}.npy", f"points_{source}.npy", f"patches_{source}.npy"]:
                records.append(record(patch_root / name, patch_manifest["outputs"][name]["sha256"]))
                old[name] = np.load(patch_root / name, allow_pickle=False)
            if not np.array_equal(rows, old[f"point_rows_{source}.npy"]):
                raise ValueError(f"P3 frozen native membership differs: {source}")
            if len(rows) != cfg["native_expected_points"][source]:
                raise ValueError(f"P3 frozen count differs: {source}")
            points = old[f"points_{source}.npy"]
            values = dict(xyz=np.asarray(tile[rows]), tile_rows=rows, patch_id=points["patch_id"],
                          normals=np.column_stack([points[key] for key in ["nx", "ny", "nz"]]))
            originals, membership[source] = raw_membership(root, source_cfg, source, tile, rows, cfg["tile_xy"], records)
            values.update(originals)
            arrays.update({source + "_" + key: value for key, value in values.items()})
            print(json.dumps(dict(stage="native_membership", source=source, points=len(rows))), flush=True)
        common = output / "common"
        common.mkdir()
        np.savez_compressed(common / "native.npz", **arrays)

        evidence_root = root / camera_cfg["output_relative_root"]
        ep = evidence_root / "artifact_manifest.json"
        records.append(record(ep, cfg["evidence_manifest_sha256"]))
        ev = evidence_root / "evidence_views.json"
        records.append(record(ev, read(ep)["outputs"]["evidence_views.json"]["sha256"]))
        frozen = read(ev)["views"]
        cc = camera_cfg["inputs"]["current_cameras"]
        camera_root = root / cc["camera_root_relative_path"]
        for name, hash_key in [("cameras", "cameras_bin_sha256"), ("images", "images_bin_sha256")]:
            records.append(record(camera_root / f"sparse/{name}.bin", cc[hash_key]))
        crosswalk_path = REPO / cc["exact_937_crosswalk_git_relative_path"]
        records.append(record(crosswalk_path, cc["exact_937_crosswalk_sha256"]))
        exact = {int(row["colmap_image_id"]): row for row in read(crosswalk_path)["rows"]}
        cameras = read_cameras_bin(camera_root / "sparse/cameras.bin")
        images = read_images_bin(camera_root / "sparse/images.bin")
        split = cfg["view_split"]
        if len(exact) != 937 or len(frozen) != sum(split[k] for k in ["decision_count", "train_count", "appearance_eval_count", "reserve_count"]):
            raise ValueError("Frozen view membership/count differs")
        views = []
        ordered = sorted(frozen, key=lambda row: hashlib.sha256((split["seed"] + str(row["colmap_image_id"])).encode()).hexdigest())
        for rank, row in enumerate(ordered):
            iid = int(row["colmap_image_id"])
            im = images[iid]
            cam = cameras[im.camera_id]
            if iid not in exact or im.name != row["name"] or cam.model not in ["PINHOLE", "SIMPLE_PINHOLE"]:
                raise ValueError(f"Frozen camera mismatch: {iid}")
            image_path = camera_root / "images" / im.name
            image_record = record(image_path, row["image_sha256"])
            records.append(image_record)
            role = "reserve"
            boundary = 0
            for candidate in ["decision", "train", "appearance_eval", "reserve"]:
                boundary += split[candidate + "_count"]
                if rank < boundary:
                    role = candidate
                    break
            maps = {}
            for kind in ["depth", "normal"]:
                mp = camera_root / f"stereo/{kind}_maps/{im.name}.geometric.bin"
                if mp.exists():
                    mr = record(mp)
                    records.append(mr)
                    mh = depth_header(mp)
                    K = cam.K().copy()
                    K[0] *= mh["width"] / cam.width
                    K[1] *= mh["height"] / cam.height
                    maps[kind] = dict(**mr, **mh, K=K.tolist(), frame="CAMERA_FRAME" if kind == "normal" else "CAMERA_Z", pixel_lineage="EXACT_IMAGE_ID_AND_ORIGINAL_RASTER_INDEX", sensor_mesh_built=False)
                else:
                    maps[kind] = dict(path=str(mp), exists=False)
            raw_path = root / cfg["raw_image_relative_root"] / im.name
            views.append(dict(image_id=iid, camera_id=im.camera_id, role=role, hash_rank=rank, name=im.name,
                              path=str(image_path), sha256=image_record["sha256"], K=cam.K().tolist(), R=im.R().tolist(), t=im.tvec.tolist(),
                              width=cam.width, height=cam.height, camera_model=cam.model, maps=maps,
                              raw_image=dict(path=str(raw_path), exists=raw_path.exists(), role="AVAILABLE_HIGH_RESOLUTION_SOURCE_NOT_RECTIFIED_BY_PREFLIGHT")))
        write(common / "views.json", dict(views=views, split=split, coordinate_frame="SCENE_LOCAL_XYZ", scientific_verdict=None))
        print(json.dumps(dict(stage="views_frozen", count=len(views))), flush=True)

        als = source_cfg["inputs"]["existing_als"]
        headers = [las_metadata(root / als["relative_root"] / name, cfg["trajectory_search"]["sample_las_points"]) for name in sorted(als["files"])]
        searches = [bounded_search(root / value, cfg["trajectory_search"]) for value in cfg["trajectory_search"]["roots"]]
        write(output / "als_acquisition_audit.json", dict(headers=headers, trajectory_search=searches,
              sensor_origin_recovered=False, scan_topology_validated=False, no_new_source_decision=True, scientific_verdict=None))
        gp = root / cfg["gravity_relative_path"]
        records.append(record(gp, cfg["gravity_sha256"]))
        gravity_doc = read(gp)
        gravity = gravity_doc["payload"]["gravity"]
        if gravity["hardcoded_gravity"]:
            raise ValueError("Frozen gravity source is hardcoded")
        reference_cfg_path = REPO / cfg["reference_config"]
        records.append(record(reference_cfg_path))
        reference = read(reference_cfg_path)["inputs"]["c1_current_uas_lidar"]
        requirements = [
            dict(requirement="Exact P3 native MVS/ALS, raw membership and coordinate route", status="PASS"),
            dict(requirement="Current oriented imagery and original per-image depth grids", status="PASS" if all(v["maps"]["depth"].get("sha256") for v in views) else "PARTIAL"),
            dict(requirement="ALS acquisition sensor origins and scan topology", status="BLOCKED", reason="No validated sensor trajectory/topology is configured. LAS GPS/strip fields alone do not establish this topology."),
            dict(requirement="Current image sensor mesh from native raster depth topology", status="BLOCKED", reason="Per-image grids are available, but no validated Wu--Vallet mesh construction and edge rejection artifact is configured. Fused PLY or a generic spatial triangulation is not an exact substitute."),
            dict(requirement="Pinned original-method implementation and parameter/processing equivalence", status="BLOCKED", reason="Not supplied to this preflight; requires paper/code audit and an explicit executable binding."),
            dict(requirement="Metric registration/datum/epoch uncertainty", status="UNRESOLVED", reason="Existing scalar Z+45.7m ALS bridge retained; small source differences do not validate ALS accuracy or currentness."),
        ]
        readiness = dict(status="BLOCKED_ORIGINAL_METHOD_REPRODUCTION", requirements=requirements,
                         preflight_status="COMMON_INPUT_FREEZE_COMPLETE", original_method_executed=False,
                         approximate_baseline_executed=False, updated_point_cloud_created=False,
                         scientific_verdict=None)
        write(output / "reproduction_readiness.json", readiness)
        versions = dict(python=platform.python_version(), numpy=np.__version__, laspy=laspy.__version__)
        for package in ["torch", "gsplat", "opencv-python", "scipy"]:
            try:
                versions[package] = importlib.metadata.version(package)
            except importlib.metadata.PackageNotFoundError:
                versions[package] = None
        for name in ["config.json", "preflight.py"]:
            shutil.copyfile(config_path if name == "config.json" else __file__, output / name)
        outputs = {str(p.relative_to(output)): record(p) for p in sorted(output.rglob("*")) if p.is_file()}
        manifest = dict(schema=cfg["schema"], task_id=cfg["task_id"], status="PREFLIGHT_COMPLETE_ORIGINAL_REPRODUCTION_BLOCKED", scientific_verdict=None,
                        input_records=records, frame=patch["frame"], domain=patch["domain"], membership=membership, gravity=gravity,
                        gravity_note="Reuses frozen terrain-MVS estimate; original source differs from later recovered MVS; no new estimate",
                        source_transform=dict(mvs="Native scene-local XYZ", als="Raw XYZ with Z+45.7m, minus world shift; additional correction zero"),
                        view_split=split, reference=dict(**reference, role=cfg["reference_role"], bytes_accessed=False),
                        original_reproduction=readiness, versions=versions,
                        git_head=os.environ.get("JBGS_SOURCE_GIT_HEAD"), docker_image_id=os.environ.get("JBGS_CONTAINER_IMAGE_ID"),
                        outputs=outputs, elapsed_seconds=time.monotonic()-started,
                        prohibited_operations_executed=[], evaluation_reference_accessed=False)
        write(output / "manifest.json", manifest)
        write(output / "preflight.json", manifest)
        print(json.dumps(dict(status=manifest["status"], output=str(output), elapsed_seconds=manifest["elapsed_seconds"])), flush=True)
    except Exception as exc:
        write(output / "FAILED.json", dict(error=repr(exc), traceback=traceback.format_exc(), scientific_verdict=None))
        raise


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    main(args.config, args.output)
