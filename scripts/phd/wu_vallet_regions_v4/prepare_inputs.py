"""Freeze native P1/P2 inputs and choose a master by P3's geometric coverage rule."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import time

import numpy as np

from scripts.phd.wu_vallet_p3_v1.preflight import raw_membership, record, depth_header
from scripts.phd.wu_vallet_p3_v3.analyze_filtered_update import sha, write
from src.stage2.colmap_io import read_cameras_bin, read_images_bin
from src.phd.wu_vallet_p3_v1.sensor_mesh import image_depth_to_sensor_mesh, ImageMeshConfig


def inside(xyz, domain):
    return np.logical_and.reduce([(xyz[..., i] >= domain[k][0]) & (xyz[..., i] < domain[k][1])
                                  for i, k in enumerate(("x", "y", "z"))])


def read_depth(spec):
    with Path(spec["path"]).open("rb") as f:
        f.seek(spec["header_bytes"])
        data = np.fromfile(f, dtype=np.float32)
    return data.reshape((spec["width"], spec["height"], spec["channels"]), order="F").transpose(1, 0, 2)[..., 0].copy()


def run(config_path, region_id, output):
    if not Path("/.dockerenv").exists():
        raise RuntimeError("Docker required")
    started = time.monotonic()
    cfg = json.loads(Path(config_path).read_text())
    region = cfg["regions"][region_id]
    root = Path(cfg["artifact_root"])
    output.mkdir(parents=True, exist_ok=False)
    write(output / "config.json", cfg)
    patch = json.loads(Path(region["patch_config"]).read_text())
    camera_cfg = json.loads(Path(region["camera_config"]).read_text())
    source_cfg = json.loads(Path(cfg["source_config"]).read_text())
    for key in ("x", "y", "z"):
        assert region["domain"][key] == patch["domain"][key]
    patch_root = root / patch["output_relative_root"]
    relation_root = root / patch["inputs"]["source_relation_relative_root"]
    manifest_path = patch_root / "artifact_manifest.json"
    records = [record(config_path), record(__file__), record(manifest_path, region["patch_manifest_sha256"])]
    manifest = json.loads(manifest_path.read_text())
    common = output / "common"
    common.mkdir()
    arrays, membership = {}, {}
    for source in ("als", "mvs"):
        spec = patch["inputs"]["partitions"][source]
        path = relation_root / spec["relative_path"]
        records.append(record(path, spec["sha256"]))
        tile = np.memmap(path, mode="r", dtype="<f4").reshape(-1, 3)
        rows = np.flatnonzero(inside(tile, region["domain"]))
        rowpath = patch_root / f"point_rows_{source}.npy"
        records.append(record(rowpath, manifest["outputs"][rowpath.name]["sha256"]))
        assert np.array_equal(rows, np.load(rowpath))
        original, membership[source] = raw_membership(root, source_cfg, source, tile, rows, region["tile_xy"], records)
        arrays[f"{source}_xyz"] = np.array(tile[rows])
        arrays[f"{source}_tile_rows"] = rows
        arrays.update({f"{source}_{key}": value for key, value in original.items()})
        # Publish exact ALS rows early so acquisition recovery can proceed independently.
        if source == "als":
            np.savez_compressed(common / "als_native.npz", **arrays)
            write(common / "ALS_READY.json", dict(region_id=region_id, points=len(rows),
                  sha256=sha(common / "als_native.npz"), reference_accessed=False, scientific_verdict=None))
        print(json.dumps({"phase": "native_membership", "region": region_id, "source": source, "points": len(rows)}), flush=True)
    np.savez_compressed(common / "native.npz", **arrays)
    write(common / "NATIVE_READY.json", dict(region_id=region_id, sha256=sha(common / "native.npz"),
          counts={s: len(arrays[f"{s}_xyz"]) for s in ("als", "mvs")},
          reference_accessed=False, scientific_verdict=None))
    evidence_root = root / camera_cfg["output_relative_root"]
    ep = evidence_root / "artifact_manifest.json"
    records.append(record(ep, region["evidence_manifest_sha256"]))
    ev = evidence_root / "evidence_views.json"
    records.append(record(ev, json.loads(ep.read_text())["outputs"][ev.name]["sha256"]))
    frozen = json.loads(ev.read_text())["views"]
    cc = camera_cfg["inputs"]["current_cameras"]
    camera_root = root / cc["camera_root_relative_path"]
    for key in ("cameras", "images"):
        records.append(record(camera_root / f"sparse/{key}.bin", cc[f"{key}_bin_sha256"]))
    crosswalk = Path(cc["exact_937_crosswalk_git_relative_path"])
    records.append(record(crosswalk, cc["exact_937_crosswalk_sha256"]))
    exact = {int(r["colmap_image_id"]): r for r in json.loads(crosswalk.read_text())["rows"]}
    cameras, images = read_cameras_bin(camera_root / "sparse/cameras.bin"), read_images_bin(camera_root / "sparse/images.bin")
    ordered = sorted(frozen, key=lambda r: hashlib.sha256((cfg["view_selection"]["seed"] + str(r["colmap_image_id"])).encode()).hexdigest())
    views = []
    for rank, row in enumerate(ordered):
        iid = int(row["colmap_image_id"])
        im, cam = images[iid], cameras[images[iid].camera_id]
        assert iid in exact and im.name == row["name"] and cam.model in ("PINHOLE", "SIMPLE_PINHOLE")
        image_path = camera_root / "images" / im.name
        records.append(record(image_path, row["image_sha256"]))
        path = camera_root / f"stereo/depth_maps/{im.name}.geometric.bin"
        rec = record(path)
        records.append(rec)
        header = depth_header(path)
        K = cam.K().copy()
        K[0] *= header["width"] / cam.width
        K[1] *= header["height"] / cam.height
        views.append(dict(image_id=iid, camera_id=im.camera_id, role="decision" if rank < cfg["view_selection"]["decision_count"] else "reserve",
                          hash_rank=rank, name=im.name, path=str(image_path), sha256=row["image_sha256"],
                          K=cam.K().tolist(), R=im.R().tolist(), t=im.tvec.tolist(), width=cam.width, height=cam.height,
                          camera_model=cam.model, maps={"depth": dict(**rec, **header, K=K.tolist(), frame="CAMERA_Z")}))
    write(common / "views.json", dict(views=views, split=cfg["view_selection"], coordinate_frame="SCENE_LOCAL_XYZ", scientific_verdict=None))
    coverage, selected, selected_cells = [], None, -1
    selection_mode = cfg["view_selection"].get("mode", "first_eligible")
    if selection_mode not in ("first_eligible", "max_native_xy_cells"):
        raise ValueError("Unsupported declared master selection mode")
    cell_size = cfg["view_selection"].get("xy_cell_size_m", .5)
    if not np.isfinite(cell_size) or cell_size <= 0:
        raise ValueError("Master support cell size must be positive")
    for view in views:
        if view["role"] != "decision":
            continue
        spec = view["maps"]["depth"]
        depth = read_depth(spec)
        K, R, t = np.asarray(spec["K"]), np.asarray(view["R"]), np.asarray(view["t"])
        yy, xx = np.indices(depth.shape)
        rays = np.stack((xx, yy, np.ones_like(xx)), axis=-1) @ np.linalg.inv(K).T
        xyz = (rays * depth[..., None] - t) @ R
        valid = np.isfinite(depth) & (depth > 0)
        prism = valid & inside(xyz, region["domain"])
        result = image_depth_to_sensor_mesh(np.where(prism, depth, 0.), K, R, t,
                   ImageMeshConfig(**cfg["image_mesh"]), image_id=str(view["image_id"]))
        eligible = len(result["mesh"].triangles) >= cfg["view_selection"]["minimum_faces"]
        native_xy = result["mesh"].vertices[:, :2]
        cells = np.floor((native_xy - [region["domain"]["x"][0], region["domain"]["y"][0]]) / cell_size).astype(np.int64)
        occupied_cells = len(np.unique(cells, axis=0))
        coverage.append(dict(image_id=view["image_id"], hash_rank=view["hash_rank"], valid_depth_pixels=int(valid.sum()),
                             prism_depth_pixels=int(prism.sum()), prism_vertices=len(result["mesh"].vertices),
                             prism_faces=len(result["mesh"].triangles), native_xy_occupied_cells=occupied_cells,
                             xy_cell_size_m=cell_size, eligible=eligible))
        if eligible and (selected is None or (selection_mode == "max_native_xy_cells" and occupied_cells > selected_cells)):
            selected = view
            selected_cells = occupied_cells
    if selected is None:
        write(output / "coverage_audit.json", dict(views=coverage, selected=None, reference_accessed=False))
        raise ValueError("No master passes the frozen P3 geometric eligibility rule")
    write(output / "coverage_audit.json", dict(views=coverage, selected_image_id=selected["image_id"],
          selection=cfg["view_selection"], reference_accessed=False, scientific_verdict=None))
    write(common / "selected_master.json", dict(image_id=selected["image_id"], view=selected,
          coverage=next(r for r in coverage if r["image_id"] == selected["image_id"]),
          selection=cfg["view_selection"], reference_accessed=False, scientific_verdict=None))
    receipt = dict(status="REGIONAL_INPUTS_FROZEN", region_id=region_id, scientific_verdict=None,
                   reference_accessed=False, domain=region["domain"], frame=cfg["frame"], selected_image_id=selected["image_id"],
                   native_counts={s: len(arrays[f"{s}_xyz"]) for s in ("als", "mvs")}, membership=membership,
                   view_count=len(views), decision_view_count=len(coverage), input_records=records,
                   source_git_head=os.environ.get("JBGS_SOURCE_GIT_HEAD"), container_image=os.environ.get("JBGS_CONTAINER_IMAGE_ID"),
                   source_snapshot_manifest=os.environ.get("JBGS_SOURCE_SNAPSHOT_MANIFEST"), elapsed_seconds=time.monotonic() - started,
                   outputs={str(p.relative_to(output)): sha(p) for p in output.rglob("*") if p.is_file()})
    write(output / "receipt.json", receipt)
    print(json.dumps({"phase": "inputs_complete", "region": region_id, "image_id": selected["image_id"], "counts": receipt["native_counts"]}), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--region", choices=("P1", "P2"), required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    run(args.config, args.region, args.output)
