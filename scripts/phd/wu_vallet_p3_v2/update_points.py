"""Run GS-free Wu--Vallet paper-based updates with explicit input adaptations."""
from __future__ import annotations

import argparse
from dataclasses import asdict
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import time
import traceback

import numpy as np
from scipy.spatial import Delaunay

from src.phd.wu_vallet_p3_v1.sensor_mesh import image_depth_to_sensor_mesh, ImageMeshConfig
from src.phd.wu_vallet_p3_v2.ray_runtime import SensorMesh, RuntimeConfig, classify_and_update


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(8 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def write(path, value):
    with Path(path).open("x") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")


def inside(xyz, domain):
    return np.logical_and.reduce([(xyz[:, i] >= domain[key][0]) &
                                  (xyz[:, i] < domain[key][1])
                                  for i, key in enumerate(("x", "y", "z"))])


def build_old(acq, context_indices, mesh_config):
    """Keep all context vertices; triangulate separate strip/return sensor layers."""
    xyz = acq["context_xyz"][context_indices]
    pulse = acq["context_pulse_id"][context_indices]
    scan = acq["pulse_scan_id"][pulse]
    beam = acq["pulse_beam_coordinate"][pulse]
    complete = acq["pulse_complete_scan"][pulse]
    strip = acq["context_strip"][context_indices]
    returns = acq["context_return_number"][context_indices]
    parts, audits = [], []
    for sid in np.unique(strip):
        for return_number in np.unique(returns[strip == sid]):
            ids = np.flatnonzero((strip == sid) & (returns == return_number) & complete)
            if len(ids) < 3:
                audits.append(dict(strip=int(sid), return_number=int(return_number), vertices=len(ids), faces=0))
                continue
            uv = np.column_stack((beam[ids], scan[ids]))
            unique, counts = np.unique(uv, axis=0, return_counts=True)
            if len(unique) != len(uv):
                raise ValueError("Ambiguous duplicated scan/beam within one return layer")
            if np.linalg.matrix_rank(uv - uv[0]) < 2:
                audits.append(dict(strip=int(sid), return_number=int(return_number), vertices=len(ids), faces=0,
                                   reason="single_scan_or_collinear"))
                continue
            candidate = ids[Delaunay(uv).simplices]
            vertices = xyz[candidate]
            edges = np.stack((vertices[:, 1] - vertices[:, 0], vertices[:, 2] - vertices[:, 1],
                              vertices[:, 0] - vertices[:, 2]), axis=1)
            length = np.linalg.norm(edges, axis=2).max(axis=1)
            area2 = np.linalg.norm(np.cross(edges[:, 0], -edges[:, 2]), axis=1)
            bad_scan = np.ptp(scan[candidate], axis=1) > mesh_config["max_scan_gap"]
            bad_beam = np.ptp(beam[candidate], axis=1) > mesh_config["max_beam_coordinate_gap"]
            bad_edge = length > mesh_config["max_edge_length_m"]
            bad_area = area2 <= 1e-12
            keep = ~(bad_scan | bad_beam | bad_edge | bad_area)
            parts.append(candidate[keep])
            audits.append(dict(strip=int(sid), return_number=int(return_number), vertices=len(ids),
                               candidate_faces=len(candidate), faces=int(keep.sum()),
                               scan_gap=int(bad_scan.sum()), beam_gap=int(bad_beam.sum()),
                               long_edge=int(bad_edge.sum()), degenerate=int(bad_area.sum())))
    triangles = np.concatenate(parts) if parts else np.empty((0, 3), np.int64)
    return xyz, triangles, audits


def build_new(cfg):
    views_path = Path(cfg["common_root"]) / "views.json"
    row = next(r for r in json.loads(views_path.read_text())["views"] if r["image_id"] == cfg["image_id"])
    assert row["role"] == "decision"
    spec = row["maps"]["depth"]
    path = Path(spec["path"])
    if sha(path) != spec["sha256"]:
        raise ValueError("Current depth hash mismatch")
    width, height, channels = spec["width"], spec["height"], spec["channels"]
    assert channels == 1
    with path.open("rb") as stream:
        stream.seek(spec["header_bytes"])
        depth = np.fromfile(stream, dtype=np.float32).reshape((width, height, channels), order="F").transpose(1, 0, 2)[..., 0]
    result = image_depth_to_sensor_mesh(depth, np.asarray(spec["K"]), np.asarray(row["R"]),
                                       np.asarray(row["t"]), ImageMeshConfig(**cfg["image_mesh"]),
                                       image_id=str(row["image_id"]))
    return result, row, {str(views_path): sha(views_path), str(path): sha(path)}


def ply(path, points, source):
    data = np.empty(len(points), dtype=[("x", "<f8"), ("y", "<f8"), ("z", "<f8"),
                                       ("source", "u1")])
    for axis, key in enumerate(("x", "y", "z")):
        data[key] = points[:, axis]
    data["source"] = source
    header = ("ply\nformat binary_little_endian 1.0\ncomment source 0 retained ALS 1 admitted image\n"
              f"element vertex {len(points)}\nproperty double x\nproperty double y\nproperty double z\n"
              "property uchar source\nend_header\n")
    with path.open("xb") as stream:
        stream.write(header.encode()); data.tofile(stream)


def label_counts(labels):
    unique, counts = np.unique(labels, return_counts=True)
    return {str(k): int(v) for k, v in zip(unique, counts)}


def run(config_path, output):
    if not Path("/.dockerenv").exists():
        raise RuntimeError("Docker execution required")
    output.mkdir(parents=True, exist_ok=False)
    cfg = json.loads(Path(config_path).read_text())
    write(output / "config.json", cfg)
    write(output / "STARTED.json", {"scientific_verdict": None})
    started = time.monotonic()
    try:
        ap = Path(cfg["acquisition_root"]) / "acquisition.npz"
        ar = Path(cfg["acquisition_root"]) / "receipt.json"
        acq = np.load(ap)
        native_path = Path(cfg["common_root"]) / "native.npz"
        native = np.load(native_path)
        if not np.array_equal(acq["p3_xyz"].astype(np.float32), native["als_xyz"]):
            raise ValueError("P3 ALS original rows do not replay exact frozen XYZ")
        if not np.array_equal(acq["p3_original_row"], native["als_original_row"]):
            raise ValueError("P3 original row mismatch")
        if not np.array_equal(acq["p3_original_file_index"], native["als_original_file_index"]):
            raise ValueError("P3 original file index mismatch")
        old_p3 = native["als_xyz"].astype(np.float64)
        context_indices = np.flatnonzero(inside(acq["context_xyz"], cfg["context_domain"]))
        old_xyz, old_triangles, mesh_audit = build_old(acq, context_indices, cfg["als_mesh"])
        inverse = np.full(len(acq["context_xyz"]), -1, np.int64)
        inverse[context_indices] = np.arange(len(context_indices))
        p3_lookup = inverse[acq["p3_context_row"]]
        assert (p3_lookup >= 0).all()
        old_xyz[p3_lookup] = old_p3  # preserve frozen input bytes after raw replay
        old_meshed = np.zeros(len(old_xyz), bool); old_meshed[old_triangles.ravel()] = True
        new_result, view, image_hashes = build_new(cfg)
        new_base = new_result["mesh"]
        new_mesh = SensorMesh(new_base.vertices, new_base.triangles, new_base.optical_origins, new_base.native_rows)
        new_inside = inside(new_mesh.vertices, cfg["domain"])
        new_p3 = new_mesh.vertices[new_inside]
        new_pixels = new_mesh.native_rows[new_inside]
        np.savez_compressed(output / "common.npz", old_xyz=old_p3, new_xyz=new_p3,
                            new_pixel_id=new_pixels, old_original_row=acq["p3_original_row"],
                            old_original_file_index=acq["p3_original_file_index"])
        np.savez_compressed(output / "meshes.npz", old_xyz=old_xyz, old_triangles=old_triangles,
                            old_context_indices=context_indices, old_p3_lookup=p3_lookup,
                            new_xyz=new_mesh.vertices, new_triangles=new_mesh.triangles,
                            new_pixel_id=new_mesh.native_rows, new_optical_origins=new_mesh.optical_origins)
        origins = None
        trajectory_hashes = {}
        trajectory_path = Path(cfg["trajectory_root"]) / "estimated_origins.npz"
        if trajectory_path.is_file():
            trajectory_hashes[str(trajectory_path)] = sha(trajectory_path)
            for name in ("receipt.json", "fits.json"):
                path = Path(cfg["trajectory_root"]) / name
                if path.is_file():
                    trajectory_hashes[str(path)] = sha(path)
            data = np.load(trajectory_path)
            context_valid = data["context_valid"][context_indices]
            if data["p3_valid"].all():
                origins = data["context_origins"][context_indices]
                assert np.array_equal(np.isfinite(origins).all(axis=1), context_valid)
                write(output / "TRAJECTORY_SCOPE.json", {
                    "context_valid": int(context_valid.sum()), "context_total": len(context_valid),
                    "p3_valid": int(data["p3_valid"].sum()),
                    "policy": "Retain all target geometry, skip source rays with unsupported origins; all P3 origins supported",
                    "scientific_verdict": None})
            else:
                # Do not fill unobserved origins with invented locations.
                write(output / "TRAJECTORY_SCOPE.json", {
                    "context_valid": int(context_valid.sum()), "context_total": len(context_valid),
                    "p3_valid": int(data["p3_valid"].sum()),
                    "reason": "Complete context origins required by the bidirectional interface",
                    "scientific_verdict": None})
        write(output / "mesh_receipt.json", {
            "old_vertices": len(old_xyz), "old_faces": len(old_triangles), "old_layers": mesh_audit,
            "old_p3_meshed": int(old_meshed[p3_lookup].sum()), "old_p3_total": len(old_p3),
            "new_context_vertices": len(new_mesh.vertices), "new_context_faces": len(new_mesh.triangles),
            "new_p3_vertices": len(new_p3), "new_preprocessing": new_result["diagnostics"],
            "image_id": view["image_id"], "image_mesh_scope": new_result["reproduction_scope"],
            "reference_accessed": False, "scientific_verdict": None})
        print(json.dumps({"phase": "meshes_ready", "old_faces": len(old_triangles),
                          "new_faces": len(new_mesh.triangles), "bidirectional_available": origins is not None}), flush=True)
        directions = ["ONLY_CURRENT_IMAGE_RAYS"]
        if origins is not None:
            directions.append("BIDIRECTIONAL")
        arms = []
        for direction in directions:
            old_mesh = SensorMesh(old_xyz, old_triangles, origins if direction == "BIDIRECTIONAL" else None,
                                  context_indices)
            for tolerance in cfg["distance_tolerances_m"]:
                for area in cfg["small_region_area_m2"]:
                    name = ("estimated_bidir" if direction == "BIDIRECTIONAL" else "image_direction")
                    name += f"_d{tolerance:g}_a{area:g}"
                    dest = output / name; dest.mkdir()
                    algorithm = RuntimeConfig(tolerance, direction_mode=direction, small_region_area_m2=area)
                    result = classify_and_update(old_mesh, new_mesh, algorithm)
                    old_labels = result["old_vertex_labels"][p3_lookup].copy()
                    old_labels[~old_meshed[p3_lookup]] = "unassessed"
                    new_labels = result["new_vertex_labels"][new_inside]
                    old_keep, new_keep = old_labels != "changed", new_labels != "consistent"
                    points = np.concatenate((old_p3[old_keep], new_p3[new_keep]))
                    sources = np.concatenate((np.zeros(int(old_keep.sum()), np.uint8), np.ones(int(new_keep.sum()), np.uint8)))
                    assert len(points) == int(old_keep.sum()) + int(new_keep.sum())
                    assert np.array_equal(points[:int(old_keep.sum())], old_p3[old_keep])
                    np.savez_compressed(dest / "updated_points.npz", updated_points=points, updated_source=sources,
                                        old_labels=old_labels, new_labels=new_labels,
                                        old_keep_mask=old_keep, new_keep_mask=new_keep,
                                        old_original_row=acq["p3_original_row"],
                                        old_original_file_index=acq["p3_original_file_index"], new_pixel_id=new_pixels,
                                        updated_original_row=np.concatenate((acq["p3_original_row"][old_keep],
                                                                           np.full(int(new_keep.sum()), -1, np.int64))),
                                        updated_original_file_index=np.concatenate((acq["p3_original_file_index"][old_keep],
                                                                                  np.full(int(new_keep.sum()), -1, np.int16))),
                                        updated_pixel_id=np.concatenate((np.full(int(old_keep.sum()), -1, np.int64), new_pixels[new_keep])))
                    np.savez_compressed(dest / "face_decisions.npz", old_face_labels=result["old_face_labels"],
                                        new_face_labels=result["new_face_labels"],
                                        raw_old_face_labels=result["raw_old_face_labels"],
                                        raw_new_face_labels=result["raw_new_face_labels"],
                                        conflict_pairs=result["conflict_pairs"])
                    ply(dest / "updated_points.ply", points, sources)
                    counts = {"old_total": len(old_p3), "new_total": len(new_p3),
                              "old_retained": int(old_keep.sum()), "old_removed": int((~old_keep).sum()),
                              "new_admitted": int(new_keep.sum()), "new_excluded_consistent": int((~new_keep).sum()),
                              "updated_points": len(points), "old_labels": label_counts(old_labels),
                              "new_labels": label_counts(new_labels)}
                    row = {"name": name, "direction_mode": direction, "tolerance_m": tolerance,
                           "small_region_area_m2": area, "counts": counts,
                           "config": asdict(algorithm), "diagnostics": result["diagnostics"],
                           "scope": result["reproduction_scope"], "scientific_verdict": None,
                           "inputs_are_sensor_origin_estimates": direction == "BIDIRECTIONAL",
                           "native_PSMNet_matching": False,
                           "outputs": {p.name: sha(p) for p in dest.iterdir() if p.is_file()}}
                    write(dest / "result.json", row); arms.append(row)
                    print(json.dumps({"name": name, "counts": counts}), flush=True)
        receipt = {"status": "PAPER_BASED_POINT_UPDATE_COMPLETE", "task_id": cfg["task_id"],
                   "scientific_verdict": None, "arms": arms, "elapsed_seconds": time.monotonic() - started,
                   "image_id": cfg["image_id"], "domain": cfg["domain"], "working_crs": cfg["working_crs"],
                   "context_domain": cfg["context_domain"], "reference_accessed": False, "GS_executed": False,
                   "full_author_reproduction": False, "estimated_bidirectional_executed": origins is not None,
                   "adaptations": ["COLMAP replaces PSMNet matching", "estimated ALS optical centers if available",
                                   "separate return-number sensor triangulation layers", "finite sampled rays",
                                   "declared distance/area/filter/aggregation choices", "bounded context occlusion"],
                   "input_hashes": {str(ap): sha(ap), str(ar): sha(ar), str(native_path): sha(native_path),
                                    str(config_path): sha(config_path), **image_hashes, **trajectory_hashes},
                   "source_git_head": os.environ.get("JBGS_SOURCE_GIT_HEAD"),
                   "container_image": os.environ.get("JBGS_CONTAINER_IMAGE_ID"),
                   "source_snapshot_manifest": os.environ.get("JBGS_SOURCE_SNAPSHOT_MANIFEST"),
                   "versions": {k: importlib.metadata.version(k) for k in ("numpy", "scipy", "open3d")}}
        write(output / "receipt.json", receipt)
    except Exception as error:
        write(output / "FAILED.json", {"error": repr(error), "traceback": traceback.format_exc(), "scientific_verdict": None})
        raise


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    run(args.config, args.output)
