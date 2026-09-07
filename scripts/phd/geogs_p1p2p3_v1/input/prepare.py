"""Prepare explicit GeoGS scene inputs without accessing evaluation references.

This adapter changes the prior input from LoD2 to an ALS scan-layer surface.
It does not implement or modify GeoGS training, rendering, or extraction.
All destinations are new directories; existing input bytes remain read-only.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import struct
import time

import numpy as np


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(8 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def write_json(path, value):
    with Path(path).open("x") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")


def record(path, expected=None):
    path = Path(path)
    actual = sha(path)
    if expected and actual != expected:
        raise ValueError(f"Frozen input changed: {path}")
    return {"path": str(path), "bytes": path.stat().st_size, "sha256": actual}


def resolve(cfg, path):
    value = Path(path)
    return value if value.is_absolute() else Path(cfg["artifact_root"]) / value


def require_isolation():
    if not Path("/.dockerenv").exists():
        raise RuntimeError("Project execution requires Docker")
    blocked = [
        "/artifacts/JointBuildGS/phase-payloads/p0-audit/data/raw/tum2twin",
        "/artifacts/JointBuildGS/phase-payloads/phd/wu_vallet_regions_v4/PHD-WU-VALLET-REGIONS-EVALUATION-v4",
        "/artifacts/JointBuildGS/phase-payloads/phd/wu_vallet_p3_v1/PHD-WU-VALLET-P3-EVALUATION-v1-r2",
    ]
    if any(Path(p).exists() for p in blocked):
        raise RuntimeError("Raw and cropped UAS references must not be mounted")
    return {p: False for p in blocked}


def unpack(stream, fmt):
    size = struct.calcsize("<" + fmt)
    data = stream.read(size)
    if len(data) != size:
        raise ValueError("Truncated COLMAP metadata")
    return struct.unpack("<" + fmt, data)


def read_pose_metadata(camera_root):
    """Retain original COLMAP quaternion/translation double values exactly."""
    sparse = Path(camera_root) / "sparse"
    if (sparse / "0/cameras.bin").exists():
        sparse = sparse / "0"
    cameras, images = {}, {}
    with (sparse / "cameras.bin").open("rb") as stream:
        for _ in range(unpack(stream, "Q")[0]):
            cid, model, width, height = unpack(stream, "iiQQ")
            if model not in (0, 1):
                raise ValueError("Only frozen undistorted pinhole cameras are permitted")
            params = unpack(stream, "d" * (3 if model == 0 else 4))
            cameras[cid] = dict(id=cid, model=model, width=width, height=height, params=params)
    with (sparse / "images.bin").open("rb") as stream:
        for _ in range(unpack(stream, "Q")[0]):
            row = unpack(stream, "idddddddi")
            name = bytearray()
            while True:
                byte = stream.read(1)
                if not byte:
                    raise ValueError("Truncated COLMAP image name")
                if byte == b"\0":
                    break
                name.extend(byte)
            observations = unpack(stream, "Q")[0]
            stream.seek(observations * 24, 1)
            images[row[0]] = dict(id=row[0], qvec=row[1:5], tvec=row[5:8],
                                  camera_id=row[8], name=name.decode("utf-8"))
    return cameras, images


def qvec_rotation(q):
    w, x, y, z = q
    return np.array([[1 - 2*y*y - 2*z*z, 2*x*y - 2*w*z, 2*x*z + 2*w*y],
                     [2*x*y + 2*w*z, 1 - 2*x*x - 2*z*z, 2*y*z - 2*w*x],
                     [2*x*z - 2*w*y, 2*y*z + 2*w*x, 1 - 2*x*x - 2*y*y]])


def camera_K(camera):
    params = camera["params"]
    fx, fy, cx, cy = (params[0], params[0], params[1], params[2]) if camera["model"] == 0 else params
    return np.array([[fx, 0., cx], [0., fy, cy], [0., 0., 1.]])


def write_colmap(directory, cameras, images, empty_points=False):
    directory.mkdir(parents=True, exist_ok=False)
    camera_ids = sorted({image["camera_id"] for image in images})
    with (directory / "cameras.bin").open("xb") as binary, (directory / "cameras.txt").open("x") as text:
        binary.write(struct.pack("<Q", len(camera_ids)))
        for cid in camera_ids:
            cam = cameras[cid]
            binary.write(struct.pack("<iiQQ", cid, cam["model"], cam["width"], cam["height"]))
            binary.write(struct.pack("<" + "d"*len(cam["params"]), *cam["params"]))
            model = "SIMPLE_PINHOLE" if cam["model"] == 0 else "PINHOLE"
            text.write(f"{cid} {model} {cam['width']} {cam['height']} " + " ".join(map(repr, cam["params"])) + "\n")
    with (directory / "images.bin").open("xb") as binary, (directory / "images.txt").open("x") as text:
        binary.write(struct.pack("<Q", len(images)))
        for image in images:
            binary.write(struct.pack("<idddddddi", image["id"], *image["qvec"], *image["tvec"], image["camera_id"]))
            binary.write(image["name"].encode() + b"\0" + struct.pack("<Q", 0))
            text.write(f"{image['id']} " + " ".join(map(repr, (*image["qvec"], *image["tvec"]))) +
                       f" {image['camera_id']} {image['name']}\n\n")
    if empty_points:
        (directory / "points3D.bin").write_bytes(struct.pack("<Q", 0))
        (directory / "points3D.txt").write_text("# No image-derived initialization; official LoD initialization required.\n")


def partition_views(views, hold=8, batch_size=16):
    if hold < 2 or batch_size < 2:
        raise ValueError("Split hold and DA3 maximum batch size must be >=2")
    ordered = sorted(views, key=lambda view: Path(view["name"]).name.split(".")[0])
    names = [view["name"] for view in ordered]
    if len(names) != len(set(names)):
        raise ValueError("Duplicate image filename")
    train = [v for i, v in enumerate(ordered) if i % hold]
    evaluation = [v for i, v in enumerate(ordered) if not i % hold]
    batches = [train[start:start+batch_size] for start in range(0, len(train), batch_size)]
    if batches and len(batches[-1]) == 1:
        if len(batches) == 1 or len(batches[-2]) < 3:
            raise ValueError("Not enough views for pose-conditioned DA3 batching")
        batches[-1].insert(0, batches[-2].pop())
    return ordered, train, evaluation, batches


def prepare_cameras(config_path, region, output):
    started = time.monotonic()
    isolation = require_isolation()
    cfg = json.loads(Path(config_path).read_text())
    spec = cfg["regions"][region]
    views_path = resolve(cfg, spec["views_json"])
    inputs = [record(config_path), record(views_path, spec["views_sha256"])]
    views = json.loads(views_path.read_text())["views"]
    camera_root = resolve(cfg, cfg["camera_root"])
    for key in ("cameras", "images"):
        inputs.append(record(camera_root / f"sparse/{key}.bin", cfg["camera_hashes"][key]))
    cameras, original = read_pose_metadata(camera_root)
    ordered, train, evaluation, batches = partition_views(views, cfg["split"]["llffhold"], cfg["da3"]["max_batch_views"])
    if len(views) != spec["expected_views"] or len(train) != spec["expected_train"] or len(evaluation) != spec["expected_test"]:
        raise ValueError("Regional view membership changed")
    for view in ordered:
        pose, cam = original[view["image_id"]], cameras[view["camera_id"]]
        if pose["name"] != view["name"] or pose["camera_id"] != view["camera_id"]:
            raise ValueError("Pose identity differs from frozen view manifest")
        if not np.array_equal(np.asarray(pose["tvec"]), view["t"]) or not np.allclose(qvec_rotation(pose["qvec"]), view["R"], rtol=0, atol=1e-14):
            raise ValueError("Pose values differ from frozen view manifest")
        if (cam["width"], cam["height"]) != (view["width"], view["height"]) or not np.array_equal(camera_K(cam), view["K"]):
            raise ValueError("Camera calibration differs from frozen view manifest")
        if Path(view["name"]).name != view["name"]:
            raise ValueError("Input filenames must be simple basenames")
        inputs.append(record(view["path"], view["sha256"]))
    output.mkdir(parents=True, exist_ok=False)
    images_dir = output / "images"
    images_dir.mkdir()
    for view in ordered:
        shutil.copyfile(view["path"], images_dir / view["name"])
        if sha(images_dir / view["name"]) != view["sha256"]:
            raise ValueError("Copied image failed integrity check")
    full_poses = [original[v["image_id"]] for v in ordered]
    write_colmap(output / "sparse/0", cameras, full_poses, empty_points=True)
    write_colmap(output / "sparse_lod/0", cameras, full_poses)
    write_colmap(output / "sparse_txt", cameras, full_poses)
    write_colmap(output / "train_sparse_txt", cameras, [original[v["image_id"]] for v in train])
    batch_records = []
    for number, batch in enumerate(batches):
        batch_root = output / "da3_batches" / f"batch_{number:03d}"
        write_colmap(batch_root / "sparse/0", cameras, [original[v["image_id"]] for v in batch], empty_points=True)
        batch_images = batch_root / "images"
        batch_images.mkdir()
        for view in batch:
            target = images_dir / view["name"]
            os.link(target, batch_images / view["name"])
        batch_records.append(dict(batch_id=number, scene=str(batch_root), count=len(batch),
                                  image_ids=[v["image_id"] for v in batch], names=[v["name"] for v in batch]))
    split = dict(schema="jointbuildgs.geogs.region_split.v1", region=region,
                 rule="filename stem ascending; zero-based index modulo llffhold ==0 is evaluation",
                 llffhold=cfg["split"]["llffhold"], all=ordered, train=train, evaluation=evaluation,
                 da3_batches=batch_records, da3_policy="Disjoint filename-ordered train-only batches; original inference within each batch; explicit input adaptation from whole-scene DA3.",
                 independent_confirmatory=False, historical_pose_preprocessing="Shared full-source SfM/poses; all regional images historically used in development.",
                 current_mvs_use="Input-context comparator only; never the initialization in this ALS arm.", scientific_verdict=None)
    write_json(output / "split_manifest.json", split)
    projection_audit = {}
    for cid in sorted({v["camera_id"] for v in ordered}):
        cam = cameras[cid]
        K = camera_K(cam)
        projection_audit[str(cid)] = dict(width=cam["width"], height=cam["height"], K=K.tolist(),
            delta_principal_from_half_image_px=[float(K[0, 2]-cam["width"]*.5), float(K[1, 2]-cam["height"]*.5)],
            status="SOURCE_K_RETAINED_OFF_AXIS_RENDERER_PARITY_REQUIRES_VALIDATION")
    write_json(output / "projection_audit.json", projection_audit)
    write_json(output / "scene_reference_frame.json", {"base_to_canonical": {"scale": 1., "shift": [0., 0., 0.], "swap_xy": False},
                 "note": "ALS mesh is already in scene-local metric coordinates; upstream --z_offset must be 0."})
    outputs = {str(p.relative_to(output)): record(p) for p in output.rglob("*") if p.is_file() and not p.is_symlink()}
    receipt = dict(status="CAMERAS_AND_SPLITS_PREPARED_NO_PRIOR_GENERATION", region=region, scientific_verdict=None,
                   counts=dict(all=len(ordered), train=len(train), evaluation=len(evaluation), da3_batches=len(batches)),
                   source_camera_projection=projection_audit,
                   inputs=inputs, outputs=outputs, reference_paths_absent=isolation,
                   prior_generated=False, trained=False, elapsed_seconds=time.monotonic()-started,
                   command=__import__("sys").argv, source_sha256=sha(__file__),
                   git_commit=os.environ.get("JBGS_SOURCE_GIT_HEAD"), image_id=os.environ.get("JBGS_CONTAINER_IMAGE_ID"))
    write_json(output / "camera_receipt.json", receipt)
    print(json.dumps({"status": receipt["status"], "region": region, "counts": receipt["counts"]}), flush=True)


def prepare_surface(config_path, region, output):
    """Scan-layer triangulation with exactly recorded membership and omissions."""
    from scripts.phd.wu_vallet_p3_v2.update_points import build_old, inside
    from plyfile import PlyData, PlyElement

    started = time.monotonic()
    isolation = require_isolation()
    cfg = json.loads(Path(config_path).read_text())
    spec = cfg["regions"][region]
    acquisition_path = resolve(cfg, spec["acquisition_npz"])
    inputs = [record(config_path), record(acquisition_path, spec["acquisition_sha256"]),
              record("scripts/phd/wu_vallet_p3_v2/update_points.py")]
    with np.load(acquisition_path) as source:
        indices = np.flatnonzero(inside(source["context_xyz"], spec["context_domain"]))
        xyz, faces, mesh_audit = build_old(source, indices, cfg["als_surface"])
        original_row = source["context_original_row"][indices]
        original_file = source["context_original_file_index"][indices]
    if not len(faces):
        raise RuntimeError("Declared ALS surface conversion yielded no faces")
    if not np.isfinite(xyz).all():
        raise ValueError("Nonfinite ALS coordinates")
    represented = np.zeros(len(xyz), dtype=bool)
    represented[np.unique(faces)] = True
    core = inside(xyz, spec["domain"])
    output.mkdir(parents=True, exist_ok=False)
    with (output / "als_surface.obj").open("x") as stream:
        stream.write("# ALS scan-layer surface adaptation; scene-local meters; no reference input\n")
        for point in xyz:
            stream.write("v " + " ".join(format(v, ".17g") for v in point) + "\n")
        for triangle in faces:
            stream.write("f " + " ".join(str(int(v)+1) for v in triangle) + "\n")
    vertices = np.empty(len(xyz), dtype=[("x", "<f8"), ("y", "<f8"), ("z", "<f8")])
    for axis, name in enumerate(("x", "y", "z")):
        vertices[name] = xyz[:, axis]
    triangles = np.empty(len(faces), dtype=[("vertex_indices", "<i4", (3,))])
    triangles["vertex_indices"] = faces
    PlyData([PlyElement.describe(vertices, "vertex"), PlyElement.describe(triangles, "face")],
            text=False, byte_order="<").write(str(output / "als_surface.ply"))
    np.savez_compressed(output / "vertex_membership.npz", acquisition_context_row=indices,
                        original_file_index=original_file, original_row=original_row,
                        represented_in_surface=represented, inside_evaluation_prism=core)
    area = np.linalg.norm(np.cross(xyz[faces[:, 1]]-xyz[faces[:, 0]], xyz[faces[:, 2]]-xyz[faces[:, 0]]), axis=1)*.5
    receipt = dict(status="ALS_SURFACE_ADAPTATION_PREPARED", region=region, scientific_verdict=None,
                   inputs=inputs, reference_paths_absent=isolation, context_domain=spec["context_domain"], domain=spec["domain"],
                   method="Independent strip/return layers triangulated in scan/beam coordinates; incomplete scans excluded from faces.",
                   parameters=cfg["als_surface"], mesh_audit=mesh_audit,
                   counts=dict(context_points=len(xyz), faces=len(faces), represented_points=int(represented.sum()),
                               omitted_context_points=int((~represented).sum()), core_points=int(core.sum()),
                               omitted_core_points=int((core & ~represented).sum())), area_m2=float(area.sum()),
                   limitations=["ALS interpolation is an input adaptation; surface currentness and accuracy are not assumed.",
                                "Separate strips/returns may overlap; no UAS-guided registration, fusion, smoothing or gap filling.",
                                "Unrepresented ALS points are retained in membership and must count as conversion loss.",
                                "Context is finite and may not cover full RGB backgrounds; image metrics need a fixed scene-independent crop/mask."],
                   frame=cfg["crs"], additional_transform_applied=False, upstream_z_offset_required=0.,
                   outputs={str(p.relative_to(output)): record(p) for p in output.rglob("*") if p.is_file()},
                   command=__import__("sys").argv, source_sha256=sha(__file__), elapsed_seconds=time.monotonic()-started,
                   git_commit=os.environ.get("JBGS_SOURCE_GIT_HEAD"), image_id=os.environ.get("JBGS_CONTAINER_IMAGE_ID"))
    write_json(output / "surface_receipt.json", receipt)
    print(json.dumps({"status": receipt["status"], "region": region, "counts": receipt["counts"]}), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--region", choices=("P1", "P2", "P3"), required=True)
    parser.add_argument("--stage", choices=("cameras", "surface"), required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    function = prepare_cameras if args.stage == "cameras" else prepare_surface
    function(args.config, args.region, args.output)
