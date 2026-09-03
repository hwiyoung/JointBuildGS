#!/usr/bin/env python3
"""Textbook surface patches on raw source points (all objects, no building prior).

Stage 1  Surface growing.  Two textbook criteria are implemented and selected per
         source in the config: 'planar_surface' (Vosselman et al. 2004 / Vosselman &
         Maas 2010: angle to the region plane + point-to-plane residual, guarded PCA
         refits) and 'smoothness' (Rabbani, van den Heuvel & Vosselman 2006 with the
         PCL RegionGrowing semantics: neighbour-vs-current-point angle + curvature gate).
         On dense-image MVS the pure smoothness criterion fragments or leaks, so the
         planar-surface criterion is the selected one.
Stage 2  PCL-style Euclidean clustering of the residual points; clusters below
         the minimum are explicit NOISE (label 0), nothing is deleted.
Typing   Weinmann et al. (2015) eigen-features per patch: PLANAR / LINEAR / SCATTERED.

Vectorised, deterministic: the k-NN graph is built once; regions are connected
components of the smooth sub-graph among low-curvature points; high-curvature
points attach to the region of their nearest smooth neighbour.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time
from typing import Any

import numpy as np
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components
from scipy.spatial import cKDTree


REPO = Path(__file__).resolve().parents[3]
DEFAULT_CONFIG = REPO / "configs/phd/surface_patch_rg_v1/run_v1.json"
SCHEMA = "jointbuildgs.phd.surface_patch_rg.run.v1"
KIND_NOISE, KIND_SMOOTH_REGION, KIND_EUCLIDEAN_CLUSTER = 0, 1, 2
KIND_NAMES = {0: "NOISE", 1: "SMOOTH_REGION", 2: "EUCLIDEAN_CLUSTER"}
TYPE_NONE, TYPE_PLANAR, TYPE_LINEAR, TYPE_SCATTERED = 0, 1, 2, 3
TYPE_NAMES = {0: "NONE", 1: "PLANAR", 2: "LINEAR", 3: "SCATTERED"}
PROHIBITED_TOKENS = ("uas", "lod2", "footprint", "stable_id", "journal1", "roster")

POINT_DTYPE = np.dtype([("patch_id", "<i4"), ("kind", "u1"), ("curvature", "<f4"),
                        ("nx", "<f4"), ("ny", "<f4"), ("nz", "<f4")])
PATCH_DTYPE = np.dtype([
    ("patch_id", "<i4"), ("kind", "u1"), ("type", "u1"), ("point_count", "<u4"),
    ("cx", "<f4"), ("cy", "<f4"), ("cz", "<f4"), ("nx", "<f4"), ("ny", "<f4"), ("nz", "<f4"),
    ("tilt_from_up_deg", "<f4"), ("area_proxy_m2", "<f4"), ("extent_max_m", "<f4"),
    ("linearity", "<f4"), ("planarity", "<f4"), ("sphericity", "<f4"),
    ("mean_curvature", "<f4"), ("plane_rmse_m", "<f4"),
    ("bbox_min_x", "<f4"), ("bbox_min_y", "<f4"), ("bbox_min_z", "<f4"),
    ("bbox_max_x", "<f4"), ("bbox_max_y", "<f4"), ("bbox_max_z", "<f4"),
])


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(8 << 20), b""):
            value.update(block)
    return value.hexdigest()


def array_digest(array: np.ndarray) -> str:
    return hashlib.sha256(np.ascontiguousarray(array).tobytes()).hexdigest()


def atomic_bytes(path: Path, value: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_bytes(value)
    os.replace(tmp, path)


def atomic_json(path: Path, value: Any) -> None:
    atomic_bytes(path, (json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8"))


def atomic_npy(path: Path, value: np.ndarray) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("wb") as stream:
        np.save(stream, value, allow_pickle=False)
    os.replace(tmp, path)


def git_head() -> str:
    env = os.environ.get("JBGS_SOURCE_GIT_HEAD")
    if env:
        return env
    try:
        return subprocess.run(["git", "-C", str(REPO), "rev-parse", "HEAD"], check=True, capture_output=True, text=True).stdout.strip()
    except Exception:  # noqa: BLE001
        return "UNKNOWN"


def load_config(path: Path = DEFAULT_CONFIG) -> dict[str, Any]:
    cfg = json.loads(path.read_text(encoding="utf-8"))
    if cfg.get("schema") != SCHEMA:
        raise ValueError("surface-patch config schema drift")
    if cfg.get("status") != "USER_APPROVED_DEVELOPMENT_NON_CONFIRMATORY":
        raise ValueError("run is not user-approved")
    if cfg.get("scientific_verdict", "missing") is not None:
        raise ValueError("scientific_verdict must remain null")
    serialized = json.dumps({"inputs": cfg["inputs"], "output": cfg["output_relative_root"]}).lower()
    for token in PROHIBITED_TOKENS:
        if token in serialized:
            raise ValueError(f"prohibited input token: {token}")
    for name, p in cfg["algorithm"]["per_source"].items():
        if int(p["k_neighbors"]) < 5 or float(p["smoothness_deg"]) <= 0 or float(p["euclidean_tolerance_m"]) <= 0:
            raise ValueError(f"{name}: invalid parameters")
    return cfg


# ----------------------------------------------------------------------------
# geometry
# ----------------------------------------------------------------------------

def read_xyz_bin(path: Path) -> np.ndarray:
    if path.stat().st_size % 12:
        raise ValueError(f"{path}: invalid xyz_f32le byte count")
    return np.fromfile(path, dtype="<f4").reshape(-1, 3)


def domain_mask(xyz: np.ndarray, domain: dict[str, Any]) -> np.ndarray:
    low = np.array([domain["x"][0], domain["y"][0], domain["z"][0]])
    high = np.array([domain["x"][1], domain["y"][1], domain["z"][1]])
    return np.all((xyz >= low) & (xyz < high), axis=1)


def knn_normals(points: np.ndarray, k: int) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """k-NN PCA normal (sign: n_z >= 0) and curvature = lambda_min / sum (PCL definition).
    Returns normals, curvature, neighbour index matrix (k columns, self excluded)."""
    pts = np.asarray(points, dtype=np.float64)
    n = len(pts)
    if n == 0:
        return np.zeros((0, 3)), np.zeros(0), np.zeros((0, k), dtype=np.int64)
    kk = min(k + 1, n)
    _, idx = cKDTree(pts).query(pts, k=kk)
    idx = np.atleast_2d(idx)
    neighbours = idx[:, 1:] if kk > 1 else np.zeros((n, 0), dtype=np.int64)
    normals = np.zeros((n, 3)); curvature = np.zeros(n)
    block = 200_000
    for start in range(0, n, block):
        sel = slice(start, min(n, start + block))
        nb = pts[idx[sel]]                                   # (b, kk, 3) including self
        mean = nb.mean(axis=1, keepdims=True)
        d = nb - mean
        cov = np.einsum("bki,bkj->bij", d, d) / nb.shape[1]
        values, vectors = np.linalg.eigh(cov)                # ascending
        normals[sel] = vectors[:, :, 0]
        total = values.sum(axis=1)
        curvature[sel] = np.where(total > 0, values[:, 0] / np.maximum(total, 1e-30), 0.0)
    flip = normals[:, 2] < 0
    normals[flip] *= -1
    return normals, curvature, neighbours


def region_growing(points: np.ndarray, normals: np.ndarray, curvature: np.ndarray, neighbours: np.ndarray,
                   smoothness_deg: float, curvature_threshold: float, min_cluster_points: int) -> np.ndarray:
    """Rabbani 2006 / PCL RegionGrowing, vectorised.  Returns region label per point (0 = not in a region)."""
    n = len(points)
    labels = np.zeros(n, dtype=np.int64)
    if n == 0 or neighbours.shape[1] == 0:
        return labels
    cos_min = float(np.cos(np.deg2rad(smoothness_deg)))
    smooth = curvature < curvature_threshold                       # points allowed to propagate growth
    rows = np.repeat(np.arange(n), neighbours.shape[1])
    cols = neighbours.ravel()
    cosine = np.abs(np.einsum("ij,ij->i", normals[rows], normals[cols]))
    ok = cosine >= cos_min
    # stage A: regions = connected components among smooth points over smooth edges
    core = ok & smooth[rows] & smooth[cols]
    graph = coo_matrix((np.ones(int(core.sum()), dtype=np.int8), (rows[core], cols[core])), shape=(n, n))
    _, comp = connected_components(graph, directed=False)
    labels[smooth] = comp[smooth] + 1
    # stage B: non-smooth points join the region of their nearest smooth neighbour that passes the angle test
    attach = ok & (~smooth[rows]) & smooth[cols]
    if np.any(attach):
        # neighbours are ordered by distance per row; keep the first qualifying column per row
        order = np.lexsort((np.tile(np.arange(neighbours.shape[1]), n)[attach], rows[attach]))
        a_rows = rows[attach][order]; a_cols = cols[attach][order]
        first = np.ones(len(a_rows), dtype=bool); first[1:] = a_rows[1:] != a_rows[:-1]
        labels[a_rows[first]] = labels[a_cols[first]]
    # relabel compactly, release small regions
    ids, counts = np.unique(labels[labels > 0], return_counts=True)
    keep = ids[counts >= int(min_cluster_points)]
    remap = np.zeros(int(labels.max()) + 1, dtype=np.int64)
    remap[keep] = np.arange(1, len(keep) + 1)
    return remap[labels]


def planar_surface_growing(points: np.ndarray, normals: np.ndarray, curvature: np.ndarray, neighbours: np.ndarray,
                           smoothness_deg: float, max_point_to_plane_m: float, min_cluster_points: int,
                           refit_condition_ratio: float = 0.05) -> np.ndarray:
    """Vosselman-style planar surface growing (Vosselman et al. 2004; Vosselman & Maas 2010, surface growing):
    seeds in ascending curvature; a neighbour joins if its normal is within smoothness_deg of the REGION plane
    normal (sign-invariant) and its distance to the region plane is below max_point_to_plane_m; the region
    plane is refit (PCA) at every doubling of the member count, accepting a refit only if it is conditioned
    and stays within smoothness_deg of the seed normal.  Sequential FIFO growth, deterministic.
    Returns region label per point (0 = not in a region)."""
    from collections import deque
    n = len(points)
    labels = np.zeros(n, dtype=np.int64)
    if n == 0 or neighbours.shape[1] == 0:
        return labels
    cos_min = float(np.cos(np.deg2rad(smoothness_deg)))
    order = np.lexsort((np.arange(n), curvature))
    next_id = 0
    for seed in order:
        if labels[seed] != 0:
            continue
        seed_normal = normals[seed]
        plane_n = seed_normal.copy(); plane_d = float(plane_n @ points[seed])
        members = [int(seed)]
        pending = next_id + 1
        labels[seed] = pending
        queue = deque([int(seed)])
        next_refit = 8
        while queue:
            current = queue.popleft()
            for other in neighbours[current]:
                if labels[other] != 0:
                    continue
                if abs(float(normals[other] @ plane_n)) < cos_min:
                    continue
                if abs(float(plane_n @ points[other] - plane_d)) > max_point_to_plane_m:
                    continue
                labels[other] = pending
                members.append(int(other))
                queue.append(int(other))
                if len(members) >= next_refit:
                    sub = points[members]
                    centre = sub.mean(axis=0)
                    values, vectors = np.linalg.eigh(np.cov((sub - centre).T, bias=True))
                    candidate = vectors[:, 0] * (1 if vectors[2, 0] >= 0 else -1)
                    if values[1] >= refit_condition_ratio * max(values[2], 1e-30) and abs(float(candidate @ seed_normal)) >= cos_min:
                        plane_n = candidate
                    plane_d = float(plane_n @ centre)
                    next_refit *= 2
        if len(members) >= int(min_cluster_points):
            next_id += 1
            labels[members] = next_id
        else:
            labels[members] = 0
    return labels


def euclidean_clusters(points: np.ndarray, tolerance: float, min_points: int) -> np.ndarray:
    """PCL EuclideanClusterExtraction: connected components under a radius; small ones -> 0 (noise)."""
    n = len(points)
    if n == 0:
        return np.zeros(0, dtype=np.int64)
    pairs = cKDTree(points).query_pairs(tolerance, output_type="ndarray")
    graph = coo_matrix((np.ones(len(pairs), dtype=np.int8), (pairs[:, 0], pairs[:, 1])), shape=(n, n))
    _, comp = connected_components(graph, directed=False)
    ids, counts = np.unique(comp, return_counts=True)
    keep = ids[counts >= int(min_points)]
    remap = np.zeros(int(comp.max()) + 1, dtype=np.int64)
    remap[keep] = np.arange(1, len(keep) + 1)
    return remap[comp]


def eigen_features(points: np.ndarray) -> tuple[float, float, float, np.ndarray, np.ndarray, float]:
    pts = np.asarray(points, dtype=np.float64)
    centre = pts.mean(axis=0)
    if len(pts) < 3:
        return 0.0, 0.0, 0.0, np.array([0.0, 0.0, 1.0]), centre, 0.0
    values, vectors = np.linalg.eigh(np.cov((pts - centre).T, bias=True))
    l3, l2, l1 = values  # ascending -> l1 largest
    l1 = max(l1, 1e-30)
    normal = vectors[:, 0] * (1 if vectors[2, 0] >= 0 else -1)
    rmse = float(np.sqrt(np.mean(((pts - centre) @ normal) ** 2)))
    return float((l1 - l2) / l1), float((l2 - l3) / l1), float(l3 / l1), normal, centre, rmse


def area_proxy(points: np.ndarray, normal: np.ndarray, centre: np.ndarray, cell: float = 0.25) -> tuple[float, float]:
    pts = np.asarray(points, dtype=np.float64) - centre
    base = np.array([1.0, 0.0, 0.0]) if abs(normal[0]) < 0.9 else np.array([0.0, 1.0, 0.0])
    e1 = base - normal * (normal @ base); e1 /= np.linalg.norm(e1); e2 = np.cross(normal, e1)
    uv = np.column_stack((pts @ e1, pts @ e2))
    cells = np.unique(np.floor(uv / cell).astype(np.int64), axis=0)
    extent = float(np.max(np.ptp(uv, axis=0))) if len(uv) else 0.0
    return float(cell * cell * len(cells)), extent


def summarise(points: np.ndarray, labels: np.ndarray, kinds: np.ndarray, curvature: np.ndarray,
              typing: dict[str, Any], up: np.ndarray) -> np.ndarray:
    ids = np.unique(labels[labels > 0])
    out = np.zeros(len(ids), dtype=PATCH_DTYPE)
    for row, pid in enumerate(ids):
        sel = np.flatnonzero(labels == pid)
        pts = points[sel]
        lin, pla, sph, normal, centre, rmse = eigen_features(pts)
        area, extent = area_proxy(pts, normal, centre)
        # patch-level typing on physical criteria (eigen-ratios alone mislabel elongated flat patches as LINEAR)
        if rmse <= float(typing["planar_max_rmse_m"]) and len(sel) >= 3:
            ptype = TYPE_PLANAR
        elif lin >= float(typing["linearity_min"]) and sph < 0.05:
            ptype = TYPE_LINEAR
        else:
            ptype = TYPE_SCATTERED
        r = out[row]
        r["patch_id"], r["kind"], r["type"], r["point_count"] = pid, kinds[sel[0]], ptype, len(sel)
        r["cx"], r["cy"], r["cz"] = centre; r["nx"], r["ny"], r["nz"] = normal
        r["tilt_from_up_deg"] = float(np.degrees(np.arccos(min(1.0, abs(float(normal @ up))))))
        r["area_proxy_m2"], r["extent_max_m"] = area, extent
        r["linearity"], r["planarity"], r["sphericity"] = lin, pla, sph
        r["mean_curvature"], r["plane_rmse_m"] = float(curvature[sel].mean()), rmse
        r["bbox_min_x"], r["bbox_min_y"], r["bbox_min_z"] = pts.min(axis=0)
        r["bbox_max_x"], r["bbox_max_y"], r["bbox_max_z"] = pts.max(axis=0)
    return out


def segment_source(points: np.ndarray, params: dict[str, Any], typing: dict[str, Any], up: np.ndarray) -> tuple[np.ndarray, np.ndarray, dict[str, Any]]:
    """Whole textbook pipeline for one source.  Returns per-point records, patch summaries, accounting."""
    t0 = time.perf_counter()
    normals, curvature, neighbours = knn_normals(points, int(params["k_neighbors"]))
    if params.get("growth_criterion", "smoothness") == "planar_surface":
        regions = planar_surface_growing(points, normals, curvature, neighbours, float(params["smoothness_deg"]),
                                         float(params["max_point_to_plane_m"]), int(params["min_cluster_points"]))
    else:
        regions = region_growing(points, normals, curvature, neighbours, float(params["smoothness_deg"]),
                                 float(params["curvature_threshold"]), int(params["min_cluster_points"]))
    labels = regions.copy()
    kinds = np.where(regions > 0, KIND_SMOOTH_REGION, KIND_NOISE).astype(np.uint8)
    residual = np.flatnonzero(regions == 0)
    n_regions = int(regions.max()) if len(regions) else 0
    if len(residual):
        clusters = euclidean_clusters(points[residual], float(params["euclidean_tolerance_m"]), int(params["euclidean_min_points"]))
        clustered = clusters > 0
        labels[residual[clustered]] = n_regions + clusters[clustered]
        kinds[residual[clustered]] = KIND_EUCLIDEAN_CLUSTER
    per_point = np.zeros(len(points), dtype=POINT_DTYPE)
    per_point["patch_id"] = labels; per_point["kind"] = kinds; per_point["curvature"] = curvature
    per_point["nx"], per_point["ny"], per_point["nz"] = normals.T
    patches = summarise(points, labels, kinds, curvature, typing, up)
    accounting = {
        "points": int(len(points)),
        "smooth_regions": n_regions, "euclidean_clusters": int(len(patches) - n_regions),
        "points_in_smooth_regions": int(np.count_nonzero(kinds == KIND_SMOOTH_REGION)),
        "points_in_euclidean_clusters": int(np.count_nonzero(kinds == KIND_EUCLIDEAN_CLUSTER)),
        "points_noise": int(np.count_nonzero(kinds == KIND_NOISE)),
        "type_counts": {TYPE_NAMES[t]: int(np.count_nonzero(patches["type"] == t)) for t in (1, 2, 3)},
        "type_point_counts": {TYPE_NAMES[t]: int(patches["point_count"][patches["type"] == t].sum()) for t in (1, 2, 3)},
        "largest_patch_points": int(patches["point_count"].max()) if len(patches) else 0,
        "elapsed_seconds": time.perf_counter() - t0,
    }
    return per_point, patches, accounting


# ----------------------------------------------------------------------------
# outputs
# ----------------------------------------------------------------------------

def resolve_inputs(cfg: dict[str, Any]) -> dict[str, Any]:
    root = Path(cfg["artifact_root"]) / cfg["inputs"]["source_relation_relative_root"]
    resolved = {}
    for key, item in [("partition_receipt", cfg["inputs"]["partition_receipt"])] + list(cfg["inputs"]["partitions"].items()):
        path = root / item["relative_path"]
        if not path.is_file() or path.stat().st_size != int(item["bytes"]) or sha256(path) != item["sha256"]:
            raise RuntimeError(f"input drift: {key}")
        resolved[key] = {"path": str(path), "bytes": int(item["bytes"]), "sha256": item["sha256"]}
    return resolved


def write_preview(path: Path, results: dict[str, tuple[np.ndarray, np.ndarray, np.ndarray]], domain: dict[str, Any]) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, axes = plt.subplots(2, 2, figsize=(16, 15), dpi=110)
    rng = np.random.default_rng(0)
    type_colors = {1: "#22c55e", 2: "#f59e0b", 3: "#94a3b8"}
    for col, (name, (pts, per_point, patches)) in enumerate(results.items()):
        labels = per_point["patch_id"]
        palette = rng.uniform(0.15, 0.95, size=(int(labels.max()) + 1, 3)); palette[0] = [0.1, 0.1, 0.1]
        ax = axes[0, col]; ax.set_title(f"{name}: patches (random colour per patch, black = noise) n={len(patches)}")
        ax.scatter(pts[:, 0], pts[:, 1], s=0.4, c=palette[labels], linewidths=0)
        ax = axes[1, col]; ax.set_title(f"{name}: patch type  green=PLANAR  orange=LINEAR  grey=SCATTERED  black=noise")
        ptype = np.zeros(int(labels.max()) + 1, dtype=np.int64); ptype[patches["patch_id"]] = patches["type"]
        colors = np.array([[0.1, 0.1, 0.1]] + [matplotlib.colors.to_rgb(type_colors[t]) for t in (1, 2, 3)])
        ax.scatter(pts[:, 0], pts[:, 1], s=0.4, c=colors[ptype[labels]], linewidths=0)
    for ax in axes.ravel():
        ax.set_aspect("equal"); ax.set_xlim(domain["x"]); ax.set_ylim(domain["y"]); ax.grid(alpha=0.2)
    fig.suptitle("Textbook surface patches on the pilot prism, per source: planar surface growing (Vosselman 2004; PCL-style region growing with a plane-residual test) + Euclidean clustering of the residual", fontsize=11)
    fig.tight_layout(); path.parent.mkdir(parents=True, exist_ok=True); fig.savefig(path); plt.close(fig)


def run(cfg: dict[str, Any], config_path: Path) -> dict[str, Any]:
    started = time.perf_counter()
    out = Path(cfg["artifact_root"]) / cfg["output_relative_root"]
    out.mkdir(parents=True, exist_ok=True)
    resolved = resolve_inputs(cfg)
    up = np.array([0.0, 0.0, 1.0])  # descriptive tilt only (scene-local z is gravity-aligned within the frame)
    results = {}
    accounting = {}
    outputs = {}
    for name in ("mvs", "als"):
        xyz = read_xyz_bin(Path(resolved[name]["path"]))
        keep = domain_mask(xyz, cfg["domain"])
        rows = np.flatnonzero(keep).astype(np.uint32)
        pts = xyz[keep].astype(np.float64)
        per_point, patches, acc = segment_source(pts, cfg["algorithm"]["per_source"][name], cfg["algorithm"]["typing"], up)
        results[name] = (pts, per_point, patches)
        accounting[name] = acc
        for fname, array in ((f"points_{name}.npy", per_point), (f"patches_{name}.npy", patches), (f"point_rows_{name}.npy", rows)):
            atomic_npy(out / fname, array); outputs[fname] = array
    write_preview(out / "surface_patch_preview.png", results, cfg["domain"])
    technical = {
        "schema": "jointbuildgs.phd.surface_patch_rg.technical_return.v1", "task_id": cfg["task_id"],
        "status": "COMPLETE_DEVELOPMENT_NON_CONFIRMATORY", "generated_utc": utc_now(), "git_commit": git_head(),
        "config": {"path": str(config_path), "sha256": sha256(config_path)},
        "driver": {"path": str(Path(__file__)), "sha256": sha256(Path(__file__))},
        "domain": cfg["domain"], "frame": cfg["frame"], "algorithm": cfg["algorithm"],
        "accounting": accounting, "kind_names": KIND_NAMES, "type_names": TYPE_NAMES,
        "not_decided_here": cfg["not_decided_here"], "elapsed_seconds": time.perf_counter() - started,
        "prohibited_inputs_accessed": [], "scientific_verdict": None,
    }
    atomic_json(out / "technical_return.json", technical)
    manifest_outputs = {}
    for fname in sorted(list(outputs) + ["surface_patch_preview.png", "technical_return.json"]):
        p = out / fname; manifest_outputs[fname] = {"path": fname, "bytes": p.stat().st_size, "sha256": sha256(p)}
    atomic_json(out / "artifact_manifest.json", {
        "schema": "jointbuildgs.phd.surface_patch_rg.artifact_manifest.v1", "task_id": cfg["task_id"],
        "status": "COMPLETE_DEVELOPMENT_NON_CONFIRMATORY", "generated_utc": utc_now(), "git_commit": technical["git_commit"],
        "config": technical["config"], "driver": technical["driver"], "inputs": resolved, "outputs": manifest_outputs,
        "prohibited_inputs_accessed": [], "scientific_verdict": None,
    })
    return technical


def validate(cfg: dict[str, Any], rerun: bool = True) -> dict[str, Any]:
    out = Path(cfg["artifact_root"]) / cfg["output_relative_root"]
    manifest = json.loads((out / "artifact_manifest.json").read_text(encoding="utf-8"))
    checks = {}
    for fname, item in manifest["outputs"].items():
        p = out / fname
        if p.stat().st_size != int(item["bytes"]) or sha256(p) != item["sha256"]:
            raise AssertionError(f"output hash drift: {fname}")
    checks["output_hashes"] = "PASS"
    resolved = resolve_inputs(cfg)
    checks["input_hashes"] = "PASS"
    for name in ("mvs", "als"):
        per_point = np.load(out / f"points_{name}.npy", allow_pickle=False)
        patches = np.load(out / f"patches_{name}.npy", allow_pickle=False)
        rows = np.load(out / f"point_rows_{name}.npy", allow_pickle=False)
        if len(rows) != len(per_point):
            raise AssertionError(f"{name}: point lineage drift")
        labelled = per_point["patch_id"] > 0
        if not np.array_equal(np.unique(per_point["patch_id"][labelled]), patches["patch_id"]):
            raise AssertionError(f"{name}: patch id integrity drift")
        counts = np.bincount(per_point["patch_id"][labelled], minlength=int(patches["patch_id"].max()) + 1)[patches["patch_id"]]
        if not np.array_equal(counts, patches["point_count"]):
            raise AssertionError(f"{name}: patch point counts drift")
        if np.any((per_point["kind"] == KIND_NOISE) != (per_point["patch_id"] == 0)):
            raise AssertionError(f"{name}: noise labelling drift")
        if rerun:
            xyz = read_xyz_bin(Path(resolved[name]["path"]))
            pts = xyz[domain_mask(xyz, cfg["domain"])].astype(np.float64)
            again, again_patches, _ = segment_source(pts, cfg["algorithm"]["per_source"][name], cfg["algorithm"]["typing"], np.array([0.0, 0.0, 1.0]))
            if array_digest(again) != array_digest(per_point) or array_digest(again_patches) != array_digest(patches):
                raise AssertionError(f"{name}: determinism drift on rerun")
    checks["coverage_every_point_labelled_or_explicit_noise"] = "PASS"
    checks["patch_integrity"] = "PASS"
    if rerun:
        checks["determinism_rerun"] = "PASS"
    checks["prohibited_inputs"] = "PASS"
    checks["scientific_verdict_null"] = "PASS"
    receipt = {"schema": "jointbuildgs.phd.surface_patch_rg.validation.v1", "task_id": cfg["task_id"], "generated_utc": utc_now(),
               "checks": checks, "artifact_manifest_sha256": sha256(out / "artifact_manifest.json"),
               "prohibited_inputs_accessed": [], "scientific_verdict": None}
    atomic_json(out / "validation_receipt.json", receipt)
    return receipt


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--no-rerun", action="store_true")
    parser.add_argument("command", choices=("run", "validate", "run-and-validate"))
    args = parser.parse_args()
    cfg = load_config(args.config.resolve())
    if args.command in {"run", "run-and-validate"}:
        technical = run(cfg, args.config.resolve())
        print(json.dumps(technical["accounting"], indent=2))
    if args.command in {"validate", "run-and-validate"}:
        print(json.dumps(validate(cfg, rerun=not args.no_rerun)["checks"], indent=2))


if __name__ == "__main__":
    main()
