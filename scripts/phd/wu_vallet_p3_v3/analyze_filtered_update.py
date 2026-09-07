"""Audit frozen Wu v2 face decisions and repair small-region output bookkeeping.

This is an additive declared-choice reproduction correction, not an author-code
equivalence claim. Candidate generation never opens a reference input. Only after
all candidate point clouds and their receipt are sealed may evaluation read UAS.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import shutil
import time

import numpy as np
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components
from scipy.spatial import cKDTree


def sha(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for block in iter(lambda: f.read(8 << 20), b""):
            h.update(block)
    return h.hexdigest()


def write(path, value):
    with Path(path).open("x") as f:
        json.dump(value, f, ensure_ascii=False, indent=2, allow_nan=False)
        f.write("\n")


def components(vertices, triangles, raw_labels):
    """Join changed faces by full shared edges, on the full frozen context mesh."""
    ids = np.flatnonzero(raw_labels == "changed")
    face_component = np.full(len(triangles), -1, np.int64)
    if not len(ids):
        return dict(face_component_id=face_component, area_m2=np.zeros(0), face_count=np.zeros(0, np.int64))
    tri = triangles[ids]
    edges = np.concatenate((tri[:, [0, 1]], tri[:, [1, 2]], tri[:, [2, 0]]))
    owners = np.tile(np.arange(len(ids)), 3)
    edges.sort(axis=1)
    order = np.lexsort((edges[:, 1], edges[:, 0]))
    edges, owners = edges[order], owners[order]
    same = np.all(edges[1:] == edges[:-1], axis=1)
    left, right = owners[:-1][same], owners[1:][same]
    graph = coo_matrix((np.ones(len(left), np.uint8), (left, right)), shape=(len(ids), len(ids))).tocsr()
    count, membership = connected_components(graph, directed=False)
    face_component[ids] = membership
    points = vertices[tri]
    area = .5 * np.linalg.norm(np.cross(points[:, 1] - points[:, 0], points[:, 2] - points[:, 0]), axis=1)
    return dict(face_component_id=face_component,
                area_m2=np.bincount(membership, weights=area, minlength=count),
                face_count=np.bincount(membership, minlength=count))


def assemble_status(vertex_count, triangles, raw_labels, regions, area_threshold):
    """Keep original SINGLE distinct from filtered CHANGED at every step.

    Vertex precedence is consistent > accepted_changed > raw_single > filtered
    > unassessed. A vertex may legitimately be incident to several face classes;
    all incident masks are returned so that aggregation is independently auditable.
    """
    if not np.isfinite(area_threshold) or area_threshold < 0:
        raise ValueError("area threshold must be finite and nonnegative")
    if len(raw_labels) != len(triangles) or not np.isin(raw_labels, ["consistent", "changed", "single"]).all():
        raise ValueError("invalid raw face labels")
    changed = raw_labels == "changed"
    removed = np.zeros(len(raw_labels), bool)
    removed[changed] = regions["area_m2"][regions["face_component_id"][changed]] < area_threshold
    faces = {"consistent": raw_labels == "consistent", "accepted_changed": changed & ~removed,
             "raw_single": raw_labels == "single", "filtered": removed}
    incident = {}
    status = np.full(vertex_count, "unassessed", dtype="U18")
    for key in ("filtered", "raw_single", "accepted_changed", "consistent"):
        mask = np.zeros(vertex_count, bool)
        mask[triangles[faces[key]].ravel()] = True
        incident[key] = mask
        status[mask] = key
    return dict(status=status, incident=incident, removed_face_mask=removed,
                old_keep=status != "accepted_changed",
                new_keep=np.isin(status, ["accepted_changed", "raw_single"]))


def legacy_vertex_labels(vertex_count, triangles, labels):
    result = np.full(vertex_count, "single", dtype="U10")
    for key in ("changed", "consistent"):
        result[triangles[labels == key].ravel()] = key
    return result


def counts(labels):
    keys, values = np.unique(labels, return_counts=True)
    return {str(k): int(v) for k, v in zip(keys, values)}


def ply(path, xyz, source):
    data = np.empty(len(xyz), dtype=[("x", "<f8"), ("y", "<f8"), ("z", "<f8"), ("source", "u1")])
    for axis, key in enumerate(("x", "y", "z")):
        data[key] = xyz[:, axis]
    data["source"] = source
    with Path(path).open("xb") as f:
        f.write(("ply\nformat binary_little_endian 1.0\ncomment source 0 retained ALS 1 admitted image\n"
                 f"element vertex {len(xyz)}\nproperty double x\nproperty double y\nproperty double z\n"
                 "property uchar source\nend_header\n").encode())
        data.tofile(f)


def run_candidates(config_path, output):
    if not Path("/.dockerenv").exists():
        raise RuntimeError("Docker execution required")
    started = time.monotonic()
    cfg = json.loads(Path(config_path).read_text())
    output.mkdir(parents=True, exist_ok=False)
    write(output / "config.json", cfg)
    root = Path(cfg["update_root"])
    receipt = json.loads((root / "receipt.json").read_text())
    assert receipt["reference_accessed"] is False
    source_files = [root / "common.npz", root / "meshes.npz", root / "receipt.json", Path(config_path)]
    common = np.load(root / "common.npz")
    with np.load(root / "meshes.npz") as archive:
        mesh = {key: archive[key] for key in archive.files}
    raw_path = root / cfg["frozen_arms"]["v2_a0"] / "face_decisions.npz"
    raw = np.load(raw_path)
    source_files.append(raw_path)
    regions = {side: components(mesh[f"{side}_xyz"], mesh[f"{side}_triangles"], raw[f"raw_{side}_face_labels"])
               for side in ("old", "new")}
    old_lookup = mesh["old_p3_lookup"]
    pixels = mesh["new_pixel_id"]
    pixel_lookup = {int(pixel): i for i, pixel in enumerate(pixels)}
    new_lookup = np.asarray([pixel_lookup[int(pixel)] for pixel in common["new_pixel_id"]], dtype=np.int64)
    assert np.array_equal(mesh["old_xyz"][old_lookup], common["old_xyz"])
    assert np.array_equal(mesh["new_xyz"][new_lookup], common["new_xyz"])
    lookup = {"old": old_lookup, "new": new_lookup}
    shutil.copy2(root / "common.npz", output / "common.npz")
    np.savez_compressed(output / "components.npz", **{
        f"{side}_{key}": value for side in ("old", "new") for key, value in regions[side].items()},
        raw_old_face_labels=raw["raw_old_face_labels"], raw_new_face_labels=raw["raw_new_face_labels"],
        old_p3_lookup=old_lookup, new_p3_lookup=new_lookup)
    arms = []
    for name, frozen in cfg["frozen_arms"].items():
        dest = output / name
        dest.mkdir()
        for filename in ("updated_points.npz", "updated_points.ply", "face_decisions.npz"):
            source = root / frozen / filename
            source_files.append(source)
            shutil.copy2(source, dest / filename)
        original = json.loads((root / frozen / "result.json").read_text())
        source_files.append(root / frozen / "result.json")
        data = np.load(dest / "updated_points.npz")
        faces = np.load(dest / "face_decisions.npz")
        for side in ("old", "new"):
            assert np.array_equal(faces[f"raw_{side}_face_labels"], raw[f"raw_{side}_face_labels"])
            recomputed = legacy_vertex_labels(len(mesh[f"{side}_xyz"]), mesh[f"{side}_triangles"], faces[f"{side}_face_labels"])[lookup[side]]
            if side == "old":
                recomputed = recomputed.astype("U10")
                meshed = np.zeros(len(mesh["old_xyz"]), bool)
                meshed[mesh["old_triangles"].ravel()] = True
                recomputed[~meshed[old_lookup]] = "unassessed"
            assert np.array_equal(recomputed, data[f"{side}_labels"])
        row = dict(original, name=name, frozen_source_arm=frozen, frozen_copy=True)
        row["outputs"] = {p.name: sha(p) for p in dest.iterdir()}
        write(dest / "result.json", row)
        arms.append(row)
    frozen_a1 = np.load(output / "v2_a1" / "updated_points.npz")
    new_regions = regions["new"]
    reproduced = assemble_status(len(mesh["new_xyz"]), mesh["new_triangles"], raw["raw_new_face_labels"], new_regions, 1.)
    newstatus = reproduced["status"][new_lookup]
    filtered_only = newstatus == "filtered"
    leak = dict(area_threshold_m2=1.0,
                filtered_new_faces=int(reproduced["removed_face_mask"].sum()),
                p3_filtered_only_vertices=int(filtered_only.sum()),
                p3_filtered_only_vertices_still_admitted_v2=int((filtered_only & frozen_a1["new_keep_mask"]).sum()),
                p3_touches_filtered_face_vertices=int(reproduced["incident"]["filtered"][new_lookup].sum()),
                v2_a0_a1_new_keep_disagreements=int(np.count_nonzero(
                    np.load(output / "v2_a0" / "updated_points.npz")["new_keep_mask"] != frozen_a1["new_keep_mask"])),
                mechanism="v2 demotes changed face to single, then admits every new vertex not consistent")
    variant_specs = [(f"corrected_area{value:g}", value, True) for value in cfg["area_sensitivity_m2"]]
    if cfg.get("changed_only_sensitivity_area_m2") is not None:
        value = cfg["changed_only_sensitivity_area_m2"]
        variant_specs.append((f"changed_only_area{value:g}", value, False))
    for name, threshold, keep_raw_single in variant_specs:
        dest = output / name
        dest.mkdir()
        selected = {side: assemble_status(len(mesh[f"{side}_xyz"]), mesh[f"{side}_triangles"],
                                         raw[f"raw_{side}_face_labels"], regions[side], threshold)
                    for side in ("old", "new")}
        old_status = selected["old"]["status"][old_lookup]
        new_status = selected["new"]["status"][new_lookup]
        old_keep = selected["old"]["old_keep"][old_lookup]
        new_keep = selected["new"]["new_keep"][new_lookup]
        if not keep_raw_single:
            new_keep = new_status == "accepted_changed"
        xyz = np.concatenate((common["old_xyz"][old_keep], common["new_xyz"][new_keep]))
        source = np.r_[np.zeros(old_keep.sum(), np.uint8), np.ones(new_keep.sum(), np.uint8)]
        legacy = {"consistent": "consistent", "accepted_changed": "changed", "raw_single": "single",
                  "filtered": "filtered", "unassessed": "unassessed"}
        old_labels = np.asarray([legacy[x] for x in old_status], dtype="U10")
        new_labels = np.asarray([legacy[x] for x in new_status], dtype="U10")
        payload = dict(updated_points=xyz, updated_source=source, old_labels=old_labels, new_labels=new_labels,
                       old_vertex_status=old_status, new_vertex_status=new_status,
                       old_keep_mask=old_keep, new_keep_mask=new_keep,
                       old_original_row=common["old_original_row"], old_original_file_index=common["old_original_file_index"],
                       new_pixel_id=common["new_pixel_id"],
                       updated_original_row=np.r_[common["old_original_row"][old_keep], np.full(new_keep.sum(), -1, np.int64)],
                       updated_original_file_index=np.r_[common["old_original_file_index"][old_keep], np.full(new_keep.sum(), -1, np.int16)],
                       updated_pixel_id=np.r_[np.full(old_keep.sum(), -1, np.int64), common["new_pixel_id"][new_keep]])
        for side in ("old", "new"):
            for key, mask in selected[side]["incident"].items():
                payload[f"{side}_incident_{key}"] = mask[lookup[side]]
        np.savez_compressed(dest / "updated_points.npz", **payload)
        np.savez_compressed(dest / "face_decisions.npz",
                            raw_old_face_labels=raw["raw_old_face_labels"], raw_new_face_labels=raw["raw_new_face_labels"],
                            old_removed_small_changed_mask=selected["old"]["removed_face_mask"],
                            new_removed_small_changed_mask=selected["new"]["removed_face_mask"])
        ply(dest / "updated_points.ply", xyz, source)
        row = dict(name=name, direction_mode="BIDIRECTIONAL", tolerance_m=.3, small_region_area_m2=threshold,
                   frozen_copy=False, scientific_verdict=None, reference_accessed=False,
                   raw_single_retained=keep_raw_single,
                   raw_single_meaning="UNKNOWN_RAW_SINGLE: no detected crossing; can include self-occluded or unknown coverage, not certified new-only",
                   counts=dict(old_total=len(old_keep), new_total=len(new_keep), old_retained=int(old_keep.sum()),
                               old_removed=int((~old_keep).sum()), new_admitted=int(new_keep.sum()),
                               new_excluded_consistent=int((new_status == "consistent").sum()),
                               new_excluded_filtered=int((new_status == "filtered").sum()),
                               new_excluded_unassessed=int((new_status == "unassessed").sum()),
                               new_excluded_raw_single=int(((new_status == "raw_single") & ~new_keep).sum()),
                               updated_points=len(xyz), old_labels=counts(old_labels), new_labels=counts(new_labels),
                               old_status=counts(old_status), new_status=counts(new_status)),
                   outputs={p.name: sha(p) for p in dest.iterdir()})
        write(dest / "result.json", row)
        arms.append(row)
    result = dict(status="FILTER_BOOKKEEPING_CANDIDATES_COMPLETE", task_id=cfg["task_id"],
                  scientific_verdict=None, reference_accessed=False, arms=arms,
                  full_author_reproduction=False, source_receipt=str(root / "receipt.json"),
                  image_id=receipt["image_id"], domain=receipt["domain"], working_crs=receipt["working_crs"],
                  GS_executed=False, bookkeeping_audit=leak,
                  vertex_precedence="consistent > accepted_changed > raw_single > filtered > unassessed",
                  raw_single_policy="Main corrections retain UNKNOWN_RAW_SINGLE independently of removed changed faces. Additional changed-only sensitivity excludes it. Raw single can mean self-occlusion/unknown coverage, not certified single-source or currentness.",
                  area_parameter_basis=cfg["area_parameter_basis"],
                  coordinate_policy="Exact frozen native coordinates; no fitting, smoothing, registration, averaging, or reference-based filtering",
                  input_hashes={str(p): sha(p) for p in source_files},
                  source_snapshot_manifest=os.environ.get("JBGS_SOURCE_SNAPSHOT_MANIFEST"),
                  source_git_head=os.environ.get("JBGS_SOURCE_GIT_HEAD"),
                  container_image=os.environ.get("JBGS_CONTAINER_IMAGE_ID"),
                  versions={k: importlib.metadata.version(k) for k in ("numpy", "scipy")},
                  elapsed_seconds=time.monotonic() - started)
    write(output / "candidate_receipt.json", result)
    write(output / "receipt.json", result)
    print(json.dumps({"phase": "candidates_sealed", "bookkeeping_audit": leak,
                      "arms": [{"name": a["name"], "counts": a["counts"]} for a in arms]}), flush=True)


def summarize(values):
    values = np.asarray(values)
    if not len(values):
        return dict(n=0, mean_m=None, median_m=None, p90_m=None, max_m=None)
    return dict(n=len(values), mean_m=float(values.mean()), median_m=float(np.median(values)),
                p90_m=float(np.quantile(values, .9)), max_m=float(values.max()))


def evaluate(config_path, output):
    """Separate post-seal reference audit, never consulted by run_candidates."""
    cfg = json.loads(Path(config_path).read_text())
    receipt_path = output / "candidate_receipt.json"
    frozen_receipt_sha = sha(receipt_path)
    receipt = json.loads(receipt_path.read_text())
    assert receipt["reference_accessed"] is False and receipt["status"] == "FILTER_BOOKKEEPING_CANDIDATES_COMPLETE"
    for arm in receipt["arms"]:
        for filename, expected in arm["outputs"].items():
            assert sha(output / arm["name"] / filename) == expected
    ref_path = Path(cfg["reference_npz"])
    if sha(ref_path) != cfg["reference_sha256"]:
        raise ValueError("Frozen UAS reference crop hash mismatch")
    reference = np.load(ref_path)["uas_xyz"]
    tree = cKDTree(reference)
    common = np.load(output / "common.npz")
    distances = {side: tree.query(common[f"{side}_xyz"], workers=4)[0] for side in ("old", "new")}
    threshold = cfg["reference_large_discrepancy_m"]
    evaluations = {}
    diagnostic = dict(old_xyz=common["old_xyz"], new_xyz=common["new_xyz"],
                      old_reference_distance_m=distances["old"], new_reference_distance_m=distances["new"],
                      new_pixel_id=common["new_pixel_id"])
    for arm in receipt["arms"]:
        name = arm["name"]
        data = np.load(output / name / "updated_points.npz")
        entry = {}
        for side in ("old", "new"):
            keep = data[f"{side}_keep_mask"]
            distance = distances[side]
            entry[side] = dict(retained=summarize(distance[keep]), excluded=summarize(distance[~keep]),
                               large_discrepancy_retained=int((keep & (distance > threshold)).sum()),
                               large_discrepancy_excluded=int((~keep & (distance > threshold)).sum()),
                               source_total=len(keep), source_large_discrepancy_total=int((distance > threshold).sum()))
            status = data[f"{side}_vertex_status"] if f"{side}_vertex_status" in data else data[f"{side}_labels"]
            entry[side]["status_groups"] = {str(key): dict(discrepancy=summarize(distance[status == key]),
                                               retained=int((keep & (status == key)).sum()),
                                               large_discrepancy=int(((status == key) & (distance > threshold)).sum()))
                                             for key in np.unique(status)}
            diagnostic[f"{name}_{side}_keep"] = keep
            diagnostic[f"{name}_{side}_status"] = status
        original_new = np.load(output / "v2_a0" / "updated_points.npz")["new_keep_mask"]
        removed = original_new & ~data["new_keep_mask"]
        entry["removed_new_relative_to_v2_a0"] = dict(points=int(removed.sum()), discrepancy=summarize(distances["new"][removed]),
                  large_discrepancy_points=int((removed & (distances["new"] > threshold)).sum()))
        combined_distance = np.r_[distances["old"][data["old_keep_mask"]], distances["new"][data["new_keep_mask"]]]
        entry["updated_to_reference"] = summarize(combined_distance)
        # Reverse direction uses precisely the same fixed reference points for all variants.
        entry["reference_to_updated"] = summarize(cKDTree(data["updated_points"]).query(reference, workers=4)[0])
        evaluations[name] = entry
    with np.load(Path(cfg["update_root"]) / "meshes.npz") as archive:
        mesh = {key: archive[key] for key in archive.files}
    comps = np.load(output / "components.npz")
    ids, areas = comps["new_face_component_id"], comps["new_area_m2"]
    lookup = comps["new_p3_lookup"]
    inverse = np.full(len(mesh["new_xyz"]), -1, np.int64)
    inverse[lookup] = np.arange(len(lookup))
    # A vertex can touch several changed components. For display choose the
    # largest incident area; record incident count rather than pretending unique ownership.
    vertex_largest = np.full(len(mesh["new_xyz"]), -1, np.int64)
    vertex_area = np.full(len(mesh["new_xyz"]), -1., np.float64)
    component_rows = []
    changed_faces = np.flatnonzero(ids >= 0)
    changed_faces = changed_faces[np.argsort(ids[changed_faces], kind="stable")]
    face_counts = np.bincount(ids[changed_faces], minlength=len(areas))
    offsets = np.r_[0, np.cumsum(face_counts)]
    for cid in np.argsort(areas, kind="stable"):
        vertices = np.unique(mesh["new_triangles"][changed_faces[offsets[cid]:offsets[cid + 1]]])
        vertex_largest[vertices] = cid
        vertex_area[vertices] = areas[cid]
        p3 = inverse[vertices]
        p3 = p3[p3 >= 0]
        if not len(p3):
            continue
        xyz = mesh["new_xyz"][vertices]
        centered = xyz - xyz.mean(axis=0)
        eigenvalues = np.linalg.eigvalsh(centered.T @ centered / max(len(xyz) - 1, 1))
        component_rows.append(dict(component_id=int(cid), area_m2=float(areas[cid]),
                                   context_faces=int(face_counts[cid]), context_vertices=len(vertices),
                                   p3_vertices=len(p3), context_aabb_min=xyz.min(axis=0).tolist(),
                                   context_aabb_max=xyz.max(axis=0).tolist(),
                                   context_pca_std_m=np.sqrt(np.maximum(eigenvalues, 0)).tolist(),
                                   p3_reference_discrepancy=summarize(distances["new"][p3]),
                                   p3_large_discrepancy_vertices=int((distances["new"][p3] > threshold).sum()),
                                   v2_a0_admitted=int(diagnostic["v2_a0_new_keep"][p3].sum()),
                                   corrected_area1_admitted=int(diagnostic["corrected_area1_new_keep"][p3].sum())))
    diagnostic["new_largest_incident_changed_component_id"] = vertex_largest[lookup]
    diagnostic["new_largest_incident_changed_area_m2"] = vertex_area[lookup]
    np.savez_compressed(output / "diagnostic_points.npz", **diagnostic)
    write(output / "components.json", {"components": sorted(component_rows, key=lambda r: -r["area_m2"]),
          "scope": "Full context edge components; P3 per-component vertex counts may overlap at shared vertices. Geometry-only components frozen before UAS read.",
          "scientific_verdict": None})
    result = dict(status="FILTER_REFERENCE_DIAGNOSTICS_COMPLETE", scientific_verdict=None,
                  methods=evaluations, large_discrepancy_threshold_m=threshold,
                  threshold_role="Post-hoc diagnostic grouping only; not an update or parameter-selection input",
                  reference_points=len(reference), reference_crs_header="EPSG:32632", working_crs="EPSG:25832",
                  reprojection_or_registration_performed=False,
                  interpretation="Raw-shift numerical discrepancy; not proven outlier/change labels or calibrated accuracy",
                  candidate_receipt_sha256=frozen_receipt_sha,
                  evaluation_source_snapshot_manifest=os.environ.get("JBGS_SOURCE_SNAPSHOT_MANIFEST"),
                  evaluation_container_image=os.environ.get("JBGS_CONTAINER_IMAGE_ID"),
                  input_hashes={str(ref_path): sha(ref_path), str(receipt_path): frozen_receipt_sha},
                  outputs={name: sha(output / name) for name in ("diagnostic_points.npz", "components.json")})
    assert sha(receipt_path) == frozen_receipt_sha
    write(output / "evaluation.json", result)
    print(json.dumps({"phase": "evaluation_complete", "methods": {k: {"new": v["new"], "removed": v["removed_new_relative_to_v2_a0"]}
                      for k, v in evaluations.items()}}), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--stage", choices=("candidates", "evaluation"), required=True)
    args = parser.parse_args()
    if args.stage == "candidates":
        run_candidates(args.config, args.output)
    else:
        evaluate(args.config, args.output)
