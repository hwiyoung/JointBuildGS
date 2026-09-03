#!/usr/bin/env python3
"""Build and validate the offline raw-relation versus surface-patch viewer."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
from typing import Any, Iterable

import numpy as np


REPO = Path(__file__).resolve().parents[3]
DEFAULT_CONFIG = REPO / "configs/phd/mvs_als_surface_patch_viewer_v1/viewer_v1.json"


def sha256(path: Path, chunk_bytes: int = 8 << 20) -> str:
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(chunk_bytes), b""):
            value.update(block)
    return value.hexdigest()


def atomic_bytes(path: Path, value: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_bytes(value)
    os.replace(temporary, path)


def atomic_json(path: Path, value: Any) -> None:
    atomic_bytes(path, (json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8"))


def atomic_copy(source: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(target.suffix + ".tmp")
    shutil.copyfile(source, temporary)
    os.replace(temporary, target)


def write_array(path: Path, value: np.ndarray) -> None:
    atomic_bytes(path, np.ascontiguousarray(value).tobytes())


def record(path: Path, relative_to: Path, **extra: Any) -> dict[str, Any]:
    return {
        "path": path.relative_to(relative_to).as_posix(),
        "bytes": path.stat().st_size,
        "sha256": sha256(path),
        **extra,
    }


def require_file(root: Path, item: dict[str, Any]) -> Path:
    path = root / item["path"]
    if not path.is_file() or path.is_symlink():
        raise RuntimeError(f"missing exact upstream file: {path}")
    if path.stat().st_size != int(item["bytes"]) or sha256(path) != item["sha256"]:
        raise RuntimeError(f"upstream file hash/size drift: {path}")
    return path


def load_config(path: Path = DEFAULT_CONFIG) -> dict[str, Any]:
    cfg = json.loads(path.read_text(encoding="utf-8"))
    if cfg.get("schema") != "jointbuildgs.phd.mvs_als_surface_patch_viewer.run.v1":
        raise ValueError("surface-patch viewer config schema drift")
    if cfg.get("status") != "USER_APPROVED_DEVELOPMENT_NON_CONFIRMATORY":
        raise ValueError("surface-patch viewer build is not user-approved")
    if cfg.get("scientific_verdict", "missing") is not None:
        raise ValueError("scientific_verdict must remain null")
    if cfg.get("default_port") != 8892:
        raise ValueError("surface-patch viewer must use its separate port 8892")
    if set(cfg.get("classes", {})) != {"1", "2", "3", "4", "5"}:
        raise ValueError("exactly five frozen source-relation classes are required")
    if len(cfg.get("source_relation_viewer_manifest_sha256", "")) != 64:
        raise ValueError("source relation viewer manifest hash is not frozen")
    if len(cfg.get("surface_patch_artifact_manifest_sha256", "")) != 64:
        raise ValueError("surface-patch artifact manifest hash is not frozen")
    if len(cfg.get("surface_patch_validation_receipt_sha256", "")) != 64:
        raise ValueError("surface-patch validation receipt hash is not frozen")
    prisms = cfg.get("prisms", [])
    if not prisms:
        raise ValueError("at least one prism (evidence bank + warp-ncc) is required")
    names = [item["name"] for item in prisms]
    if len(set(names)) != len(names) or any(not re.fullmatch(r"[a-z0-9_]+", n) for n in names):
        raise ValueError("prism names must be unique lowercase identifiers")
    for item in prisms:
        for key in ("evidence_bank_artifact_manifest_sha256", "evidence_bank_validation_receipt_sha256",
                    "warp_ncc_artifact_manifest_sha256", "warp_ncc_validation_receipt_sha256"):
            if len(item.get(key, "")) != 64:
                raise ValueError(f"prism {item['name']}: {key} is not frozen")
    hm = cfg.get("hm_zone_rule", {})
    if float(hm.get("min_height_above_ground_m", 0)) <= 0 or float(hm.get("min_area_m2", 0)) <= 0:
        raise ValueError("hm_zone_rule must give positive height and area thresholds")
    qz = cfg.get("quality_zone_rule", {})
    if float(qz.get("min_sigma_ratio", 0)) < 1 or float(qz.get("min_sigma_mvs_m", 0)) <= 0:
        raise ValueError("quality_zone_rule must give a sigma ratio >= 1 and a positive sigma floor")
    serialized = json.dumps({
        "relation": cfg["source_relation_viewer_relative_root"],
        "patch": cfg["surface_patch_relative_root"],
        "prisms": [[item["evidence_bank_relative_root"], item["warp_ncc_relative_root"]] for item in prisms],
        "viewer": cfg["viewer_output_relative_root"],
    }).lower()
    for token in ("uas", "lod2", "footprint", "stable_id", "journal1"):
        if token in serialized:
            raise ValueError(f"prohibited input token: {token}")
    return cfg


def _require_names(dtype: np.dtype, names: Iterable[str], label: str) -> None:
    available = set(dtype.names or ())
    missing = set(names) - available
    if missing:
        raise RuntimeError(f"{label} missing fields: {sorted(missing)}")


def verify_relation_upstream(cfg: dict[str, Any], root: Path) -> tuple[dict[str, Any], dict[str, Path]]:
    manifest_path = root / "viewer_manifest.json"
    if not manifest_path.is_file() or manifest_path.is_symlink():
        raise RuntimeError(f"missing frozen relation viewer manifest: {manifest_path}")
    actual = sha256(manifest_path)
    if actual != cfg["source_relation_viewer_manifest_sha256"]:
        raise RuntimeError(f"source relation viewer manifest drift: {actual}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("scientific_verdict", "missing") is not None:
        raise RuntimeError("upstream relation viewer scientific_verdict is not null")
    if manifest.get("prohibited_inputs_accessed") != []:
        raise RuntimeError("upstream relation viewer prohibited-input access is not empty")
    files = {
        "mvs": require_file(root, manifest["sources"]["mvs"]),
        "als": require_file(root, manifest["sources"]["als"]),
        "xyz": require_file(root, manifest["relations"]["xyz"]),
        "attributes": require_file(root, manifest["relations"]["attributes"]),
        "metrics": require_file(root, manifest["relations"]["metrics"]),
        "support_counts": require_file(root, manifest["relations"]["support_counts"]),
    }
    return manifest, files


def verify_patch_upstream(cfg: dict[str, Any], root: Path) -> tuple[dict[str, Any], dict[str, Any], dict[str, Path]]:
    manifest_path = root / "artifact_manifest.json"
    validation_path = root / "validation_receipt.json"
    if not manifest_path.is_file() or manifest_path.is_symlink():
        raise RuntimeError(f"missing patch artifact manifest: {manifest_path}")
    if not validation_path.is_file() or validation_path.is_symlink():
        raise RuntimeError(f"missing patch validation receipt: {validation_path}")
    if sha256(manifest_path) != cfg["surface_patch_artifact_manifest_sha256"]:
        raise RuntimeError("surface-patch artifact manifest hash drift")
    if sha256(validation_path) != cfg["surface_patch_validation_receipt_sha256"]:
        raise RuntimeError("surface-patch validation receipt hash drift")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    validation = json.loads(validation_path.read_text(encoding="utf-8"))
    if manifest.get("task_id") != cfg["surface_patch_task_id"]:
        raise RuntimeError("surface-patch task ID drift")
    if manifest.get("schema") != "jointbuildgs.phd.mvs_als_surface_patch.artifact_manifest.v1":
        raise RuntimeError("surface-patch artifact manifest schema drift")
    if manifest.get("scientific_verdict", "missing") is not None:
        raise RuntimeError("upstream patch scientific_verdict is not null")
    if validation.get("scientific_verdict", "missing") is not None:
        raise RuntimeError("upstream patch validation scientific_verdict is not null")
    if any(value != "PASS" for value in validation.get("checks", {}).values()):
        raise RuntimeError("upstream patch validation contains a non-PASS check")
    files = {}
    for name in ("patch_membership.npy", "surface_patch_summary.npy", "technical_return.json"):
        if name not in manifest.get("outputs", {}):
            raise RuntimeError(f"patch artifact manifest omits {name}")
        files[name] = require_file(root, manifest["outputs"][name])
    technical = json.loads(files["technical_return.json"].read_text(encoding="utf-8"))
    if technical.get("scientific_verdict", "missing") is not None:
        raise RuntimeError("upstream patch technical scientific_verdict is not null")
    if technical.get("prohibited_inputs_accessed") != []:
        raise RuntimeError("upstream patch prohibited-input access is not empty")
    if technical.get("interpretation", {}).get("candidate_evidence_is_never_smoothed_to_compatible") is not True:
        raise RuntimeError("upstream patch candidate-safe aggregation contract is not true")
    if technical.get("selected_metrics", {}).get("candidate_to_compatible_core_count") != 0:
        raise RuntimeError("upstream patch candidate evidence was smoothed to compatible")
    files["artifact_manifest.json"] = manifest_path
    files["validation_receipt.json"] = validation_path
    return manifest, technical, files


def _verify_receipt_bound_workstream(root: Path, manifest_sha: str, receipt_sha: str, task_id: str, schema: str, label: str,
                                     required_outputs: tuple[str, ...]) -> tuple[dict[str, Any], dict[str, Any], dict[str, Path]]:
    """Shared contract for a receipt-bound phd workstream: pinned manifest + receipt, receipt bound to the manifest, all checks PASS,
    every required output byte-verified, scientific_verdict null everywhere."""
    manifest_path = root / "artifact_manifest.json"
    validation_path = root / "validation_receipt.json"
    for path in (manifest_path, validation_path):
        if not path.is_file() or path.is_symlink():
            raise RuntimeError(f"missing {label} receipt: {path}")
    if sha256(manifest_path) != manifest_sha:
        raise RuntimeError(f"{label} artifact manifest hash drift")
    if sha256(validation_path) != receipt_sha:
        raise RuntimeError(f"{label} validation receipt hash drift")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    validation = json.loads(validation_path.read_text(encoding="utf-8"))
    if manifest.get("task_id") != task_id or manifest.get("schema") != schema:
        raise RuntimeError(f"{label} task ID / schema drift")
    for item in (manifest, validation):
        if item.get("scientific_verdict", "missing") is not None:
            raise RuntimeError(f"upstream {label} scientific_verdict is not null")
    if any(value != "PASS" for value in validation.get("checks", {}).values()):
        raise RuntimeError(f"upstream {label} validation contains a non-PASS check")
    if validation.get("artifact_manifest_sha256") != sha256(manifest_path):
        raise RuntimeError(f"{label} validation receipt is not bound to this artifact manifest")
    files = {}
    for name in required_outputs:
        if name not in manifest.get("outputs", {}):
            raise RuntimeError(f"{label} artifact manifest omits {name}")
        files[name] = require_file(root, dict(manifest["outputs"][name], path=name))
    technical = json.loads(files["technical_return.json"].read_text(encoding="utf-8"))
    if technical.get("scientific_verdict", "missing") is not None or technical.get("prohibited_inputs_accessed") != []:
        raise RuntimeError(f"upstream {label} technical return contract drift")
    files["artifact_manifest.json"] = manifest_path
    files["validation_receipt.json"] = validation_path
    return manifest, technical, files


def verify_evidence_bank_upstream(cfg: dict[str, Any], root: Path):
    return _verify_receipt_bound_workstream(
        root, cfg["evidence_bank_artifact_manifest_sha256"], cfg["evidence_bank_validation_receipt_sha256"], cfg["evidence_bank_task_id"],
        "jointbuildgs.phd.evidence_bank.artifact_manifest.v1", "evidence-bank",
        ("evidence_cells.npy", "evidence_pairs.npy", "evidence_views.json", "evaluation.json", "evidence_preview.png", "technical_return.json"))


def verify_warp_ncc_upstream(cfg: dict[str, Any], root: Path):
    manifest, technical, files = _verify_receipt_bound_workstream(
        root, cfg["warp_ncc_artifact_manifest_sha256"], cfg["warp_ncc_validation_receipt_sha256"], cfg["warp_ncc_task_id"],
        "jointbuildgs.phd.warp_ncc.artifact_manifest.v1", "warp-ncc",
        ("warp_ncc_cells.npy", "warp_ncc_pairs.npy", "warp_ncc_views.json", "chips_index.json", "evaluation.json",
         "warp_ncc_preview.png", "warp_ncc_on_image.png", "technical_return.json"))
    chips = manifest.get("chips", {})
    chip_dir = root / chips.get("directory", "chips")
    digest = hashlib.sha256(); count = 0
    for path in sorted(chip_dir.glob("cell_*.png")):
        digest.update(path.name.encode()); digest.update(path.read_bytes()); count += 1
    if digest.hexdigest() != chips.get("sha256") or count != int(chips.get("count", -1)):
        raise RuntimeError("warp-ncc chip digest drift")
    files["chips_dir"] = chip_dir
    return manifest, technical, files


T1_METRIC_NAMES = ("n_cores", "core_d_median_m", "core_lod_median_m", "n_agree", "n_penetrate", "n_block", "n_mvs_only", "n_no_landing",
                   "n_occluded", "f_agree", "f_penetrate", "f_block", "texture_median", "n_views_unoccluded", "incidence_best_deg")
T2_METRIC_NAMES = ("n_views_m", "n_views_p", "n_pairs_m", "n_pairs_p", "ncc_median_m", "ncc_median_p", "ncc_fisher_m", "ncc_fisher_p",
                   "f_good_m", "f_good_p", "angle_median_m", "angle_median_p", "n_pairs_common", "delta_median", "f_m_over_p", "f_p_over_m",
                   "n_pairs_wide_m", "n_pairs_wide_p", "ncc_median_wide_m", "ncc_median_wide_p", "n_pairs_common_wide", "delta_median_wide",
                   "ncc_median_ctrl_0", "ncc_median_ctrl_1", "ncc_median_ctrl_2", "ncc_median_ctrl_3",
                   "n_pairs_ctrl_0", "n_pairs_ctrl_1", "n_pairs_ctrl_2", "n_pairs_ctrl_3",
                   "n_edge_px_m", "edge_dist_median_px_m", "edge_dist_median_m_m", "n_edge_px_p", "edge_dist_median_px_p", "edge_dist_median_m_p",
                   "chip_view_a", "chip_view_b", "chip_angle_deg", "chip_ncc_m", "chip_ncc_p")


def validate_evidence_arrays(t1: np.ndarray, t2: np.ndarray, top: np.ndarray) -> None:
    _require_names(t1.dtype, ("ix", "iy", "state", "rough", "mvs_patch", "als_patch", "power_3da", "power_3db", "power_2da", "r") + T1_METRIC_NAMES, "T1 cells")
    _require_names(t2.dtype, ("ix", "iy", "state", "rough", "mvs_patch", "als_patch", "power_2da_m", "power_2da_p", "power_2da_any", "r_t1", "r_t2",
                              "n_pairs_ctrl", "ncc_median_ctrl") + tuple(n for n in T2_METRIC_NAMES if "ctrl" not in n), "T2 cells")
    _require_names(top.dtype, ("ix", "iy", "layer", "mvs_z", "als_z"), "pairing cells")
    if len(t1) != len(t2) or len(top) != len(t1):
        raise RuntimeError("T1 / T2 / pairing top-layer cell counts differ")
    for f in ("ix", "iy", "state", "rough", "mvs_patch", "als_patch"):
        if not np.array_equal(t1[f], t2[f]) or not np.array_equal(t1[f][:0], t1[f][:0]):
            raise RuntimeError(f"T1 / T2 cell field drift: {f}")
    if not np.array_equal(top["ix"], t1["ix"]) or not np.array_equal(top["iy"], t1["iy"]):
        raise RuntimeError("pairing top-layer cells are not the T1 cell set")
    if not np.array_equal(t2["r_t1"], t1["r"]):
        raise RuntimeError("T2 r_t1 does not reproduce the T1 r")
    if not set(np.unique(t1["state"])).issubset({1, 2, 3, 4, 5}):
        raise RuntimeError("unknown pairing state in the evidence cells")


def validate_patch_arrays(
    membership: np.ndarray,
    summaries: np.ndarray,
    relation_attributes: np.ndarray,
) -> None:
    _require_names(membership.dtype, (
        "core_index", "patch_id", "raw_relation_class", "patch_relation_class",
        "core_source", "patch_status", "unassigned_reason", "patch_core_count",
        "patch_purity", "patch_radius_m",
    ), "patch membership")
    _require_names(summaries.dtype, (
        "patch_id", "patch_uid", "core_source", "patch_relation_class",
        "patch_status", "dominant_raw_class", "core_count", "cx", "cy", "cz",
        "nx", "ny", "nz", "radius_m", "bbox_diagonal_m", "support_area_proxy_m2",
        "plane_rmse_m", "plane_p95_abs_residual_m", "plane_max_abs_residual_m",
        "normal_p95_deg", "normal_max_deg",
        "relation_purity", "robust_fraction", "median_surface_variation",
        "count_class_1", "count_class_2", "count_class_3", "count_class_4", "count_class_5",
    ), "patch summary")
    count = len(membership)
    if relation_attributes.shape != (count, 4):
        raise RuntimeError("relation attribute count/stride does not match membership")
    if not np.array_equal(membership["core_index"], np.arange(count, dtype=np.uint32)):
        raise RuntimeError("patch membership core order drift")
    if not np.array_equal(membership["raw_relation_class"], relation_attributes[:, 0]):
        raise RuntimeError("raw five-class provenance drift")
    if not np.array_equal(membership["core_source"], relation_attributes[:, 1]):
        raise RuntimeError("source-family provenance drift")
    if not set(np.unique(membership["raw_relation_class"])).issubset({1, 2, 3, 4, 5}):
        raise RuntimeError("unknown raw relation class")
    if not set(np.unique(membership["patch_relation_class"])).issubset({1, 2, 3, 4, 5}):
        raise RuntimeError("unknown patch relation class")
    if not set(np.unique(membership["unassigned_reason"])).issubset({0, 1, 2, 3}):
        raise RuntimeError("unknown unassigned reason")
    referenced = set(map(int, np.unique(membership["patch_id"]))) - {0}
    available = set(map(int, summaries["patch_id"]))
    if referenced != available or len(available) != len(summaries):
        raise RuntimeError("patch ID referential integrity failure")
    uids = [bytes(value).rstrip(b"\0") for value in summaries["patch_uid"]]
    if any(not uid for uid in uids) or len(set(uids)) != len(uids):
        raise RuntimeError("patch UID is empty or non-unique")


def _local_height(xyz: np.ndarray, gcell: float) -> np.ndarray:
    """Height of every core above the local ground (5th-percentile core z per gcell cell, min over the 3x3 neighbourhood)."""
    off = 1.0e5
    gx = np.floor((xyz[:, 0] + off) / gcell).astype(np.int64); gy = np.floor((xyz[:, 1] + off) / gcell).astype(np.int64)
    gkeys = gx * 10_000_000 + gy
    uniq, inv = np.unique(gkeys, return_inverse=True)
    order = np.argsort(inv, kind="stable"); sorted_inv = inv[order]; sorted_z = xyz[order, 2]
    starts = np.searchsorted(sorted_inv, np.arange(len(uniq))); ends = np.append(starts[1:], len(sorted_inv))
    ground = np.array([float(np.quantile(sorted_z[a:b], 0.05)) for a, b in zip(starts, ends)])
    lookup = {int(k): float(g) for k, g in zip(uniq, ground)}
    local = np.full(len(xyz), np.inf)
    for dx in (-1, 0, 1):
        for dy in (-1, 0, 1):
            keys = (gx + dx) * 10_000_000 + (gy + dy)
            local = np.minimum(local, np.array([lookup.get(int(k), np.inf) for k in keys]))
    return xyz[:, 2] - local


def _cluster_flagged(xyz: np.ndarray, flag: np.ndarray, height: np.ndarray, ccell: float, min_cores: int, min_area: float, margin: float,
                     bounds_min: np.ndarray, bounds_max: np.ndarray, mvs_xyz: np.ndarray | None, extra: dict[str, np.ndarray] | None = None
                     ) -> tuple[np.ndarray, list[dict[str, Any]]]:
    """Grid the flagged cores into ccell cells with >= min_cores cores, 8-connect, drop clusters below min_area, flag scene-boundary contact,
    and record the fraction of cluster columns holding any MVS point (display cloud).  ``extra`` = per-core arrays whose cluster medians are
    reported (e.g. sigma ratios).  Returns the per-core cluster id (u16, 0 = none) and the cluster table sorted by area."""
    off = 1.0e5
    cluster = np.zeros(len(xyz), dtype=np.uint16)
    idx = np.flatnonzero(flag)
    if not len(idx):
        return cluster, []
    cx = np.floor((xyz[idx, 0] + off) / ccell).astype(np.int64); cy = np.floor((xyz[idx, 1] + off) / ccell).astype(np.int64)
    ckeys = cx * 10_000_000 + cy
    cu, ccnt = np.unique(ckeys, return_counts=True)
    dense = set(int(k) for k, c in zip(cu, ccnt) if c >= min_cores)
    seen: set[int] = set(); comps: list[list[int]] = []
    for k in sorted(dense):
        if k in seen:
            continue
        stack = [k]; seen.add(k); comp = []
        while stack:
            c = stack.pop(); comp.append(c); qx, qy = divmod(c, 10_000_000)
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    n = (qx + dx) * 10_000_000 + (qy + dy)
                    if n in dense and n not in seen:
                        seen.add(n); stack.append(n)
        comps.append(comp)
    mvs_keys: set[int] = set()
    if mvs_xyz is not None and len(mvs_xyz):
        mx = np.floor((mvs_xyz[:, 0] + off) / ccell).astype(np.int64); my = np.floor((mvs_xyz[:, 1] + off) / ccell).astype(np.int64)
        mvs_keys = set(map(int, np.unique(mx * 10_000_000 + my)))
    table = []; key_to_cluster: dict[int, int] = {}
    for comp in comps:
        area = len(comp) * ccell * ccell
        if area < min_area:
            continue
        qx = np.array([divmod(c, 10_000_000)[0] for c in comp]); qy = np.array([divmod(c, 10_000_000)[1] for c in comp])
        x0, x1 = float(qx.min() * ccell - off), float((qx.max() + 1) * ccell - off); y0, y1 = float(qy.min() * ccell - off), float((qy.max() + 1) * ccell - off)
        member = np.isin(ckeys, comp)
        boundary = bool(x0 <= bounds_min[0] + margin or y0 <= bounds_min[1] + margin or x1 >= bounds_max[0] - margin or y1 >= bounds_max[1] - margin)
        item = {"comp": comp, "area_m2": area, "cores": int(member.sum()), "bbox": [x0, y0, x1, y1],
                "height_median_m": float(np.median(height[idx][member])), "z_median": float(np.median(xyz[idx, 2][member])),
                "touches_scene_boundary": boundary,
                "mvs_column_fraction": float(sum(1 for c in comp if c in mvs_keys) / len(comp)) if mvs_keys else None}
        for name, values in (extra or {}).items():
            item[name] = float(np.median(values[idx][member]))
        table.append(item)
    table.sort(key=lambda item: (-item["area_m2"], item["bbox"]))
    for cid, item in enumerate(table, start=1):
        item["id"] = cid
        for c in item.pop("comp"):
            key_to_cluster[c] = cid
    for j, k in enumerate(ckeys):
        cluster[idx[j]] = key_to_cluster.get(int(k), 0)
    return cluster, table


def hm_zones(xyz: np.ndarray, relation_class: np.ndarray, rule: dict[str, Any], bounds_min: np.ndarray, bounds_max: np.ndarray,
             mvs_xyz: np.ndarray | None = None) -> tuple[np.ndarray, np.ndarray, list[dict[str, Any]]]:
    """Scene-wide 'MVS empty, prior present' zones: class-4 (PRIOR_ONLY_SUPPORT) cores at least ``min_height_above_ground_m`` above the
    local ground, clustered (see _cluster_flagged).  Display-only candidate finder; not a method input."""
    height = _local_height(xyz, float(rule["ground_cell_m"]))
    flag = ((relation_class == 4) & (height >= float(rule["min_height_above_ground_m"]))).astype(np.uint8)
    cluster, table = _cluster_flagged(xyz, flag.astype(bool), height, float(rule["cluster_cell_m"]), int(rule["min_cores_per_cell"]),
                                      float(rule["min_area_m2"]), float(rule["boundary_margin_m"]), bounds_min, bounds_max, mvs_xyz)
    return flag, cluster, table


def quality_zones(xyz: np.ndarray, relation_class: np.ndarray, metrics: np.ndarray, rule: dict[str, Any], bounds_min: np.ndarray,
                  bounds_max: np.ndarray, mvs_xyz: np.ndarray | None = None) -> tuple[np.ndarray, np.ndarray, list[dict[str, Any]]]:
    """Scene-wide 'prior quality better' zones: cores where BOTH sources support the same surface (class 1 or 2) but the MVS local noise
    sigma_mvs is at least ``min_sigma_ratio`` times sigma_als and at least ``min_sigma_mvs_m``, elevated as in hm_zones, clustered.
    ``metrics`` = relation metrics (N, 6) with sigma_mvs at column 4 and sigma_als at column 5.  Display-only candidate finder."""
    height = _local_height(xyz, float(rule["ground_cell_m"]))
    sm = metrics[:, 4].astype(np.float64); sa = metrics[:, 5].astype(np.float64)
    ok = np.isin(relation_class, [1, 2]) & np.isfinite(sm) & np.isfinite(sa) & (sa > 0)
    ratio = np.where(ok, sm / np.maximum(sa, 1e-6), 0.0)
    flag = (ok & (ratio >= float(rule["min_sigma_ratio"])) & (sm >= float(rule["min_sigma_mvs_m"])) & (height >= float(rule["min_height_above_ground_m"]))).astype(np.uint8)
    cluster, table = _cluster_flagged(xyz, flag.astype(bool), height, float(rule["cluster_cell_m"]), int(rule["min_cores_per_cell"]),
                                      float(rule["min_area_m2"]), float(rule["boundary_margin_m"]), bounds_min, bounds_max, mvs_xyz,
                                      extra={"sigma_mvs_median_m": sm, "sigma_als_median_m": sa})
    return flag, cluster, table


def _class_counts(values: np.ndarray) -> dict[str, int]:
    return {str(class_id): int(np.count_nonzero(values == class_id)) for class_id in range(1, 6)}


def _status_counts(values: np.ndarray) -> dict[str, int]:
    return {str(status): int(np.count_nonzero(values == status)) for status in range(5)}


def build(cfg: dict[str, Any], config_path: Path) -> dict[str, Any]:
    artifact_root = Path(cfg["artifact_root"])
    relation_root = artifact_root / cfg["source_relation_viewer_relative_root"]
    patch_root = artifact_root / cfg["surface_patch_relative_root"]
    viewer = artifact_root / cfg["viewer_output_relative_root"]
    assets = viewer / "assets"
    libraries = viewer / "lib"
    viewer.mkdir(parents=True, exist_ok=True)
    assets.mkdir(parents=True, exist_ok=True)
    libraries.mkdir(parents=True, exist_ok=True)

    relation_manifest, relation_files = verify_relation_upstream(cfg, relation_root)
    patch_manifest, patch_technical, patch_files = verify_patch_upstream(cfg, patch_root)
    membership = np.load(patch_files["patch_membership.npy"], allow_pickle=False)
    summaries = np.load(patch_files["surface_patch_summary.npy"], allow_pickle=False)
    relation_attributes = np.fromfile(relation_files["attributes"], dtype=np.uint8).reshape(-1, 4)
    validate_patch_arrays(membership, summaries, relation_attributes)

    copied = {}
    for key, source in relation_files.items():
        suffix = source.name
        target = assets / suffix
        atomic_copy(source, target)
        copied[key] = target

    patch_arrays = {
        "ids": np.ascontiguousarray(membership["patch_id"], dtype="<u4"),
        "attributes": np.ascontiguousarray(np.column_stack((
            membership["patch_relation_class"], membership["core_source"],
            membership["patch_status"], membership["unassigned_reason"],
        )), dtype=np.uint8),
        "core_counts": np.ascontiguousarray(membership["patch_core_count"], dtype="<u4"),
        "metrics": np.ascontiguousarray(np.column_stack((
            membership["patch_purity"], membership["patch_radius_m"],
        )), dtype="<f4"),
        "summary_ids": np.ascontiguousarray(np.column_stack((
            summaries["patch_id"], summaries["core_count"],
            summaries["count_class_1"], summaries["count_class_2"], summaries["count_class_3"],
            summaries["count_class_4"], summaries["count_class_5"],
        )), dtype="<u4"),
        "summary_attributes": np.ascontiguousarray(np.column_stack((
            summaries["core_source"], summaries["patch_relation_class"],
            summaries["patch_status"], summaries["dominant_raw_class"],
        )), dtype=np.uint8),
        "summary_pose": np.ascontiguousarray(np.column_stack((
            summaries["cx"], summaries["cy"], summaries["cz"],
            summaries["nx"], summaries["ny"], summaries["nz"],
        )), dtype="<f4"),
        "summary_metrics": np.ascontiguousarray(np.column_stack((
            summaries["radius_m"], summaries["bbox_diagonal_m"],
            summaries["plane_rmse_m"], summaries["plane_p95_abs_residual_m"],
            summaries["plane_max_abs_residual_m"], summaries["normal_p95_deg"],
            summaries["normal_max_deg"], summaries["support_area_proxy_m2"],
            summaries["relation_purity"], summaries["robust_fraction"],
            summaries["median_surface_variation"],
        )), dtype="<f4"),
        "summary_uids": np.ascontiguousarray(summaries["patch_uid"].astype("S20", copy=False)),
    }
    patch_paths = {
        "ids": assets / "patch_ids_u32le.bin",
        "attributes": assets / "patch_attributes_u8.bin",
        "core_counts": assets / "patch_core_counts_u32le.bin",
        "metrics": assets / "patch_metrics_f32le.bin",
        "summary_ids": assets / "patch_summary_ids_u32le.bin",
        "summary_attributes": assets / "patch_summary_attributes_u8.bin",
        "summary_pose": assets / "patch_summary_pose_f32le.bin",
        "summary_metrics": assets / "patch_summary_metrics_f32le.bin",
        "summary_uids": assets / "patch_summary_uids_s20.bin",
    }
    for name, array in patch_arrays.items():
        write_array(patch_paths[name], array)

    # ---- scene-wide "MVS empty, prior present" zones from the frozen relation cores (display-only)
    core_xyz = np.fromfile(copied["xyz"], dtype="<f4").reshape(-1, 3).astype(np.float64)
    core_class = relation_attributes[:, 0]
    bmin = np.array(relation_manifest["bounds"]["scene_local"]["min"], dtype=np.float64); bmax = np.array(relation_manifest["bounds"]["scene_local"]["max"], dtype=np.float64)
    mvs_display_xyz = np.fromfile(copied["mvs"], dtype="<f4").reshape(-1, 3).astype(np.float64)
    hm_flag, hm_cluster, hm_table = hm_zones(core_xyz, core_class, cfg["hm_zone_rule"], bmin, bmax, mvs_display_xyz)
    hm_paths = {"flag": assets / "hm_flag_u8.bin", "cluster": assets / "hm_cluster_u16le.bin"}
    write_array(hm_paths["flag"], hm_flag); write_array(hm_paths["cluster"], hm_cluster.astype("<u2"))
    core_metrics = np.fromfile(copied["metrics"], dtype="<f4").reshape(-1, int(relation_manifest["relations"]["metrics_stride"]))
    q_flag, q_cluster, q_table = quality_zones(core_xyz, core_class, core_metrics, cfg["quality_zone_rule"], bmin, bmax, mvs_display_xyz)
    q_paths = {"flag": assets / "quality_flag_u8.bin", "cluster": assets / "quality_cluster_u16le.bin"}
    write_array(q_paths["flag"], q_flag); write_array(q_paths["cluster"], q_cluster.astype("<u2"))

    # ---- prisms: T1 evidence bank + T2 warp-NCC cells (display-only), one block per prism
    prism_blocks = []
    prism_upstreams = {}
    chip_total = 0
    for item in cfg["prisms"]:
        name = item["name"]
        evidence_root = artifact_root / item["evidence_bank_relative_root"]
        warp_root = artifact_root / item["warp_ncc_relative_root"]
        t1_manifest, t1_technical, t1_files = verify_evidence_bank_upstream(item, evidence_root)
        t2_manifest, t2_technical, t2_files = verify_warp_ncc_upstream(item, warp_root)
        t1_cells = np.load(t1_files["evidence_cells.npy"], allow_pickle=False)
        t2_cells = np.load(t2_files["warp_ncc_cells.npy"], allow_pickle=False)
        pairing_root = artifact_root / t1_manifest["inputs"]["pairing_root"].split("/artifacts/JointBuildGS/")[-1]
        pair_cells = np.load(pairing_root / "pair_cells.npy", allow_pickle=False)
        if sha256(pairing_root / "artifact_manifest.json") != t1_manifest["inputs"]["pairing_manifest_sha256"]:
            raise RuntimeError(f"prism {name}: pairing manifest drift versus the evidence bank lineage")
        top = pair_cells[pair_cells["layer"] == 0]
        validate_evidence_arrays(t1_cells, t2_cells, top)
        if t2_technical.get("domain") != t1_technical.get("domain"):
            raise RuntimeError(f"prism {name}: T1 / T2 domain drift")
        dom = t1_technical["domain"]; cell_m = float(t1_technical["algorithm"]["cell_size_m"])
        cx = dom["x"][0] + (t1_cells["ix"] + 0.5) * cell_m; cy = dom["y"][0] + (t1_cells["iy"] + 0.5) * cell_m
        z_auto = np.where(np.isfinite(top["mvs_z"]), top["mvs_z"], top["als_z"])
        t1_metrics = np.column_stack([t1_cells[n].astype(np.float32) for n in T1_METRIC_NAMES])
        t2_columns = []
        for n in T2_METRIC_NAMES:
            if n.startswith("ncc_median_ctrl_") or n.startswith("n_pairs_ctrl_"):
                base, k = n.rsplit("_", 1); t2_columns.append(t2_cells[base][:, int(k)].astype(np.float32))
            else:
                t2_columns.append(t2_cells[n].astype(np.float32))
        t2_metrics = np.column_stack(t2_columns)
        evidence_arrays = {
            "cells_xyz": np.ascontiguousarray(np.column_stack((cx, cy, z_auto)), dtype="<f4"),
            "cells_z": np.ascontiguousarray(np.column_stack((top["mvs_z"], top["als_z"])), dtype="<f4"),
            "cells_attributes": np.ascontiguousarray(np.column_stack((
                t1_cells["state"], t1_cells["rough"], t1_cells["power_3da"], t1_cells["power_3db"],
                t2_cells["power_2da_m"], t2_cells["power_2da_p"], t2_cells["r_t1"], t2_cells["r_t2"])), dtype=np.uint8),
            "cells_patches": np.ascontiguousarray(np.column_stack((t1_cells["mvs_patch"], t1_cells["als_patch"])), dtype="<i4"),
            "cells_t1_metrics": np.ascontiguousarray(t1_metrics, dtype="<f4"),
            "cells_t2_metrics": np.ascontiguousarray(t2_metrics, dtype="<f4"),
        }
        evidence_paths = {key: assets / f"t12_{name}_{key}.bin" for key in evidence_arrays}
        for key, array in evidence_arrays.items():
            write_array(evidence_paths[key], array)
        chip_target = assets / f"t2_chips_{name}"
        chip_target.mkdir(parents=True, exist_ok=True)
        for old in chip_target.glob("cell_*.png"):
            old.unlink()
        chip_index = json.loads(t2_files["chips_index.json"].read_text(encoding="utf-8"))
        for entry in chip_index["cells"].values():
            atomic_copy(warp_root / entry["file"], chip_target / Path(entry["file"]).name)
        chip_count = len(chip_index["cells"]); chip_total += chip_count
        image_assets = {}
        for key, source in (("t1_preview", t1_files["evidence_preview.png"]), ("t2_preview", t2_files["warp_ncc_preview.png"]),
                            ("t2_on_image", t2_files["warp_ncc_on_image.png"])):
            target = assets / f"{name}_{key}.png"
            atomic_copy(source, target)
            image_assets[key] = target
        t1_eval = json.loads(t1_files["evaluation.json"].read_text(encoding="utf-8"))
        t2_eval = json.loads(t2_files["evaluation.json"].read_text(encoding="utf-8"))
        t2_views = json.loads(t2_files["warp_ncc_views.json"].read_text(encoding="utf-8"))
        prism_blocks.append({
            "name": name, "label": item.get("label", name), "site_note": item.get("site_note", ""),
            "role": "T1_T2_EVIDENCE_CELLS_DISPLAY_ONLY",
            "t1_task_id": item["evidence_bank_task_id"], "t2_task_id": item["warp_ncc_task_id"],
            "domain": dom, "cell_size_m": cell_m, "cell_count": int(len(t1_cells)),
            "state_names": {"1": "COMPATIBLE", "2": "PRIOR_ABOVE", "3": "CURRENT_ABOVE", "4": "PRIOR_ONLY", "5": "CURRENT_ONLY"},
            "state_colors": cfg["evidence_cell_colors"]["state"],
            "t1_metric_names": list(T1_METRIC_NAMES), "t2_metric_names": list(T2_METRIC_NAMES),
            "t1_algorithm": t1_technical["algorithm"], "t2_algorithm": t2_technical["algorithm"],
            "t1_view_count": int(t1_technical["view_count"]), "t2_view_count": int(t2_technical["view_count"]), "t2_pair_count": int(t2_technical["pair_count"]),
            "t2_pair_angle_histogram": t2_technical.get("pair_angle_histogram"), "t2_angle_stratified": t2_technical.get("angle_stratified"),
            "t2_revision_r2": t2_technical.get("revision_r2"), "t2_expectations_before_run": t2_eval.get("expectations_before_run"),
            "t1_per_state_summary": t1_eval["per_state_summary"], "t1_expectation_checks": t1_eval["expectation_checks"],
            "t2_per_state_summary": t2_eval["per_state_summary"], "t2_controls": t2_eval["controls"], "t2_expectation_checks": t2_eval["expectation_checks"],
            "t2_overlay_view": t2_technical.get("overlay_view"), "t2_views": {str(v["colmap_image_id"]): v["name"] for v in t2_views["views"]},
            "chips": {"directory": f"assets/t2_chips_{name}", "count": chip_count, "tile_px": chip_index["tile_px"], "layout": chip_index["layout"],
                      "files": {key: f"assets/t2_chips_{name}/{Path(entry['file']).name}" for key, entry in chip_index["cells"].items()}},
            "images": {key: record(path, viewer) for key, path in image_assets.items()},
            "not_decided_here": t2_technical.get("not_decided_here"),
            "assets": {
                "cells_xyz": record(evidence_paths["cells_xyz"], viewer, stride_bytes=12),
                "cells_z": record(evidence_paths["cells_z"], viewer, stride_bytes=8, names=["mvs_z", "als_z"]),
                "cells_attributes": record(evidence_paths["cells_attributes"], viewer, stride_bytes=8,
                                           names=["state", "rough", "power_3da", "power_3db", "power_2da_m", "power_2da_p", "r_t1", "r_t2"]),
                "cells_patches": record(evidence_paths["cells_patches"], viewer, stride_bytes=8, names=["mvs_patch", "als_patch"]),
                "cells_t1_metrics": record(evidence_paths["cells_t1_metrics"], viewer, stride_bytes=4 * len(T1_METRIC_NAMES), names=list(T1_METRIC_NAMES)),
                "cells_t2_metrics": record(evidence_paths["cells_t2_metrics"], viewer, stride_bytes=4 * len(T2_METRIC_NAMES), names=list(T2_METRIC_NAMES)),
            },
        })
        prism_upstreams[f"{name}_evidence_bank_artifact_manifest"] = record(t1_files["artifact_manifest.json"], evidence_root)
        prism_upstreams[f"{name}_evidence_bank_validation_receipt"] = record(t1_files["validation_receipt.json"], evidence_root)
        prism_upstreams[f"{name}_warp_ncc_artifact_manifest"] = record(t2_files["artifact_manifest.json"], warp_root)
        prism_upstreams[f"{name}_warp_ncc_validation_receipt"] = record(t2_files["validation_receipt.json"], warp_root)

    app_source = REPO / cfg["app_source_relative_root"]
    for name in ("index.html", "app.js", "styles.css"):
        atomic_copy(app_source / name, viewer / name)
    for key, source in cfg["browser_dependencies"].items():
        target_name = "three.module.min.js" if key == "three" else "gaussian-splats-3d.module.min.js"
        atomic_copy(REPO / source, libraries / target_name)

    count = len(membership)
    patch_count = len(summaries)
    relations = {
        **relation_manifest["relations"],
        "xyz": record(copied["xyz"], viewer),
        "attributes": record(copied["attributes"], viewer),
        "metrics": record(copied["metrics"], viewer),
        "support_counts": record(copied["support_counts"], viewer),
        "raw_class_counts": _class_counts(membership["raw_relation_class"]),
    }
    sources = {}
    for key in ("mvs", "als"):
        upstream = relation_manifest["sources"][key]
        sources[key] = record(
            copied[key], viewer, count=int(upstream["count"]), color=cfg["source_colors"][key],
            voxel_m=upstream["voxel_m"], role=upstream["role"],
        )
    patch_assets = {
        "ids": record(patch_paths["ids"], viewer, stride_bytes=4),
        "attributes": record(patch_paths["attributes"], viewer, stride_bytes=4,
                             names=["patch_relation_class", "core_source", "patch_status", "unassigned_reason"]),
        "core_counts": record(patch_paths["core_counts"], viewer, stride_bytes=4),
        "metrics": record(patch_paths["metrics"], viewer, stride_bytes=8,
                          names=["patch_purity", "patch_radius_m"]),
        "summary_ids": record(patch_paths["summary_ids"], viewer, stride_bytes=28,
                              names=["patch_id", "core_count", "count_class_1", "count_class_2",
                                     "count_class_3", "count_class_4", "count_class_5"]),
        "summary_attributes": record(patch_paths["summary_attributes"], viewer, stride_bytes=4,
                                     names=["core_source", "patch_relation_class", "patch_status", "dominant_raw_class"]),
        "summary_pose": record(patch_paths["summary_pose"], viewer, stride_bytes=24,
                               names=["cx", "cy", "cz", "nx", "ny", "nz"]),
        "summary_metrics": record(patch_paths["summary_metrics"], viewer, stride_bytes=44,
                                  names=["radius_m", "bbox_diagonal_m", "plane_rmse_m",
                                         "plane_p95_abs_residual_m", "plane_max_abs_residual_m",
                                         "normal_p95_deg", "normal_max_deg", "support_area_proxy_m2",
                                         "relation_purity", "robust_fraction", "median_surface_variation"]),
        "summary_uids": record(patch_paths["summary_uids"], viewer, stride_bytes=20),
    }
    status_names = patch_technical.get("patch_status_names", {})
    statuses = {
        str(key): {
            "name": status_names.get(str(key), f"STATUS_{key}"),
            "color": cfg["patch_status_colors"][str(key)],
            "core_count": _status_counts(membership["patch_status"])[str(key)],
        }
        for key in range(5)
    }
    manifest = {
        "schema": "jointbuildgs.phd.mvs_als_surface_patch.viewer.v1",
        "task_id": cfg["task_id"],
        "status": "READY_FOR_QUALITATIVE_WEB_REVIEW",
        "purpose": "RAW_FIVE_CLASS_VERSUS_LOCALLY_CONNECTED_SOURCE_SURFACE_PATCH_COMPARISON",
        "comparison_contract": {
            "before": "FROZEN_ONE_PASS_M3C2_SUPPORT_RELATION_CORE_LABELS",
            "after": "GEOMETRY_CONNECTED_PATCH_AGGREGATED_RELATION_LABELS",
            "m3c2_recomputed": False,
            "candidate_evidence_never_smoothed_to_compatible": True,
            "display_only_no_method_feedback": True,
        },
        "not_interpretable_as": [
            "TEMPORAL_CHANGE_VERDICT", "SOURCE_CORRECTNESS_VERDICT",
            "SOURCE_AUTHORITY_DECISION", "SCIENTIFIC_PERFORMANCE_VERDICT",
        ],
        "upstreams": {
            "source_relation_viewer_manifest": record(relation_root / "viewer_manifest.json", relation_root),
            "surface_patch_artifact_manifest": record(patch_files["artifact_manifest.json"], patch_root),
            "surface_patch_validation_receipt": record(patch_files["validation_receipt.json"], patch_root),
            **prism_upstreams,
        },
        "prisms": prism_blocks,
        "hm_zones": {
            "role": "SCENE_WIDE_MVS_EMPTY_PRIOR_PRESENT_ZONES_DISPLAY_ONLY",
            "rule": cfg["hm_zone_rule"],
            "elevated_core_count": int(hm_flag.sum()),
            "clusters": hm_table,
            "assets": {"flag": record(hm_paths["flag"], viewer, stride_bytes=1), "cluster": record(hm_paths["cluster"], viewer, stride_bytes=2)},
        },
        "quality_zones": {
            "role": "SCENE_WIDE_PRIOR_QUALITY_BETTER_ZONES_DISPLAY_ONLY",
            "rule": cfg["quality_zone_rule"],
            "flagged_core_count": int(q_flag.sum()),
            "clusters": q_table,
            "assets": {"flag": record(q_paths["flag"], viewer, stride_bytes=1), "cluster": record(q_paths["cluster"], viewer, stride_bytes=2)},
        },
        "frame": relation_manifest["frame"],
        "bounds": relation_manifest["bounds"],
        "sources": sources,
        "relations": relations,
        "classes": cfg["classes"],
        "reasons": relation_manifest["reasons"],
        "render_queue_classes": cfg["render_queue_classes"],
        "patches": {
            "core_count": count,
            "patch_count": patch_count,
            "selected_profile": patch_technical["selected_profile"],
            "raw_class_counts": _class_counts(membership["raw_relation_class"]),
            "patch_class_counts": _class_counts(membership["patch_relation_class"]),
            "status_counts": _status_counts(membership["patch_status"]),
            "assigned_core_count": int(np.count_nonzero(membership["patch_id"])),
            "unassigned_core_count": int(np.count_nonzero(membership["patch_id"] == 0)),
            "assets": patch_assets,
        },
        "patch_statuses": statuses,
        "unassigned_reasons": patch_technical.get("unassigned_reason_names", cfg["unassigned_reason_names"]),
        "source_family_colors": {"0": cfg["source_colors"]["mvs"], "1": cfg["source_colors"]["als"]},
        "active_tiles": relation_manifest["active_tiles"],
        "display_sampling": cfg["display_sampling"],
        "prohibited_inputs_accessed": [],
        "scientific_verdict": None,
    }
    atomic_json(viewer / "viewer_manifest.json", manifest)
    outputs = {}
    excluded = {"viewer_build_receipt.json", "viewer_validation_receipt.json"}
    for path in sorted(item for item in viewer.rglob("*") if item.is_file() and item.name not in excluded):
        outputs[path.relative_to(viewer).as_posix()] = {
            "bytes": path.stat().st_size,
            "sha256": sha256(path),
        }
    receipt = {
        "schema": "jointbuildgs.phd.mvs_als_surface_patch.viewer_build.v1",
        "task_id": cfg["task_id"],
        "status": "COMPLETE_DEVELOPMENT_NON_CONFIRMATORY",
        "config": {"path": str(config_path), "sha256": sha256(config_path)},
        "builder": {"path": str(Path(__file__)), "sha256": sha256(Path(__file__))},
        "inputs": {
            "source_relation_viewer_manifest": record(relation_root / "viewer_manifest.json", relation_root),
            "surface_patch_artifact_manifest": record(patch_files["artifact_manifest.json"], patch_root),
            "surface_patch_validation_receipt": record(patch_files["validation_receipt.json"], patch_root),
            **prism_upstreams,
        },
        "prism_count": len(prism_blocks),
        "evidence_cell_count": int(sum(block["cell_count"] for block in prism_blocks)),
        "chip_count": chip_total,
        "hm_cluster_count": len(hm_table),
        "quality_cluster_count": len(q_table),
        "relation_core_count": count,
        "patch_count": patch_count,
        "outputs": outputs,
        "prohibited_inputs_accessed": [],
        "scientific_verdict": None,
    }
    atomic_json(viewer / "viewer_build_receipt.json", receipt)
    return receipt


def validate(cfg: dict[str, Any]) -> dict[str, Any]:
    artifact_root = Path(cfg["artifact_root"])
    viewer = artifact_root / cfg["viewer_output_relative_root"]
    manifest = json.loads((viewer / "viewer_manifest.json").read_text(encoding="utf-8"))
    build_receipt = json.loads((viewer / "viewer_build_receipt.json").read_text(encoding="utf-8"))
    if manifest.get("scientific_verdict", "missing") is not None:
        raise AssertionError("viewer scientific_verdict must remain null")
    # re-verify the upstream pins so a standalone validate detects stale T0/patch/relation assets
    verify_relation_upstream(cfg, artifact_root / cfg["source_relation_viewer_relative_root"])
    verify_patch_upstream(cfg, artifact_root / cfg["surface_patch_relative_root"])
    for item in cfg["prisms"]:
        evidence_root = artifact_root / item["evidence_bank_relative_root"]; warp_root = artifact_root / item["warp_ncc_relative_root"]
        verify_evidence_bank_upstream(item, evidence_root)
        verify_warp_ncc_upstream(item, warp_root)
        for key, path in ((f"{item['name']}_evidence_bank_artifact_manifest", evidence_root / "artifact_manifest.json"),
                          (f"{item['name']}_evidence_bank_validation_receipt", evidence_root / "validation_receipt.json"),
                          (f"{item['name']}_warp_ncc_artifact_manifest", warp_root / "artifact_manifest.json"),
                          (f"{item['name']}_warp_ncc_validation_receipt", warp_root / "validation_receipt.json")):
            if manifest["upstreams"][key]["sha256"] != sha256(path):
                raise AssertionError(f"viewer assets are stale relative to the current {key}")
    if manifest.get("prohibited_inputs_accessed") != []:
        raise AssertionError("prohibited viewer input access is not empty")
    if manifest.get("comparison_contract", {}).get("m3c2_recomputed") is not False:
        raise AssertionError("viewer contract must not recompute M3C2")
    if manifest.get("comparison_contract", {}).get("candidate_evidence_never_smoothed_to_compatible") is not True:
        raise AssertionError("viewer candidate-safe aggregation contract drift")
    count = int(manifest["relations"]["count"])
    if count != int(manifest["patches"]["core_count"]):
        raise AssertionError("relation/patch core count mismatch")
    checks = 0
    for item in manifest["sources"].values():
        path = viewer / item["path"]
        if path.stat().st_size != int(item["count"]) * 12 or sha256(path) != item["sha256"]:
            raise AssertionError(f"source asset mismatch: {item['path']}")
        checks += 1
    relation_widths = {"xyz": 12, "attributes": 4, "metrics": 24, "support_counts": 8}
    for name, width in relation_widths.items():
        item = manifest["relations"][name]
        path = viewer / item["path"]
        if path.stat().st_size != count * width or sha256(path) != item["sha256"]:
            raise AssertionError(f"relation asset mismatch: {name}")
        checks += 1
    patch_count = int(manifest["patches"]["patch_count"])
    for name, item in manifest["patches"]["assets"].items():
        rows = patch_count if name.startswith("summary_") else count
        path = viewer / item["path"]
        if path.stat().st_size != rows * int(item["stride_bytes"]) or sha256(path) != item["sha256"]:
            raise AssertionError(f"patch asset mismatch: {name}")
        checks += 1
    if len(manifest["prisms"]) != len(cfg["prisms"]):
        raise AssertionError("prism count drift between config and manifest")
    for ev_block in manifest["prisms"]:
        ev_rows = int(ev_block["cell_count"])
        for name, item in ev_block["assets"].items():
            path = viewer / item["path"]
            if path.stat().st_size != ev_rows * int(item["stride_bytes"]) or sha256(path) != item["sha256"]:
                raise AssertionError(f"evidence-cell asset mismatch: {ev_block['name']} {name}")
            checks += 1
        for key, item in ev_block["images"].items():
            path = viewer / item["path"]
            if path.stat().st_size != int(item["bytes"]) or sha256(path) != item["sha256"]:
                raise AssertionError(f"evidence image mismatch: {ev_block['name']} {key}")
        chip_files = sorted((viewer / ev_block["chips"]["directory"]).glob("cell_*.png"))
        if len(chip_files) != int(ev_block["chips"]["count"]) or len(ev_block["chips"]["files"]) != len(chip_files):
            raise AssertionError(f"chip count drift in viewer assets: {ev_block['name']}")
        states = np.fromfile(viewer / ev_block["assets"]["cells_attributes"]["path"], dtype=np.uint8).reshape(-1, 8)[:, 0]
        if not set(np.unique(states)).issubset({1, 2, 3, 4, 5}):
            raise AssertionError(f"evidence-cell state drift in viewer assets: {ev_block['name']}")
    hm_block = manifest["hm_zones"]
    for name, item in hm_block["assets"].items():
        path = viewer / item["path"]
        if path.stat().st_size != count * int(item["stride_bytes"]) or sha256(path) != item["sha256"]:
            raise AssertionError(f"hm-zone asset mismatch: {name}")
        checks += 1
    hm_flag = np.fromfile(viewer / hm_block["assets"]["flag"]["path"], dtype=np.uint8)
    if int(hm_flag.sum()) != int(hm_block["elevated_core_count"]):
        raise AssertionError("hm-zone elevated core count drift")
    q_block = manifest["quality_zones"]
    for name, item in q_block["assets"].items():
        path = viewer / item["path"]
        if path.stat().st_size != count * int(item["stride_bytes"]) or sha256(path) != item["sha256"]:
            raise AssertionError(f"quality-zone asset mismatch: {name}")
        checks += 1
    q_flag = np.fromfile(viewer / q_block["assets"]["flag"]["path"], dtype=np.uint8)
    if int(q_flag.sum()) != int(q_block["flagged_core_count"]):
        raise AssertionError("quality-zone flagged core count drift")
    raw = np.fromfile(viewer / manifest["relations"]["attributes"]["path"], dtype=np.uint8).reshape(-1, 4)[:, 0]
    patch = np.fromfile(viewer / manifest["patches"]["assets"]["attributes"]["path"], dtype=np.uint8).reshape(-1, 4)[:, 0]
    if _class_counts(raw) != manifest["patches"]["raw_class_counts"]:
        raise AssertionError("raw five-class count drift")
    if _class_counts(patch) != manifest["patches"]["patch_class_counts"]:
        raise AssertionError("patch five-class count drift")
    uids = np.fromfile(viewer / manifest["patches"]["assets"]["summary_uids"]["path"], dtype="S20")
    if len(set(map(bytes, uids))) != patch_count or np.any(uids == b""):
        raise AssertionError("patch UID integrity drift")
    for name, item in build_receipt["outputs"].items():
        path = viewer / name
        if not path.is_file() or path.stat().st_size != int(item["bytes"]) or sha256(path) != item["sha256"]:
            raise AssertionError(f"build output drift: {name}")
    for name in ("index.html", "app.js", "styles.css"):
        text = (viewer / name).read_text(encoding="utf-8")
        if "https://" in text or "http://" in text:
            raise AssertionError(f"viewer has an unpinned remote dependency: {name}")
    receipt = {
        "schema": "jointbuildgs.phd.mvs_als_surface_patch.viewer_validation.v1",
        "task_id": cfg["task_id"],
        "checks": {
            "upstream_hashes_and_validation": "PASS",
            "asset_hashes_and_strides": "PASS",
            "raw_five_class_preserved": "PASS",
            "patch_five_class_and_uid_integrity": "PASS",
            "both_source_layers": "PASS",
            "evidence_cell_assets_chips_and_images": "PASS",
            "hm_zone_assets": "PASS",
            "quality_zone_assets": "PASS",
            "offline_dependencies": "PASS",
            "m3c2_not_recomputed": "PASS",
            "candidate_evidence_never_smoothed_to_compatible": "PASS",
            "scientific_verdict_null": "PASS",
            "prohibited_inputs": "PASS"
        },
        "assets_checked": checks,
        "relation_core_count": count,
        "patch_count": patch_count,
        "prism_count": len(manifest["prisms"]),
        "evidence_cell_count": int(sum(block["cell_count"] for block in manifest["prisms"])),
        "chip_count": int(sum(block["chips"]["count"] for block in manifest["prisms"])),
        "hm_cluster_count": len(hm_block["clusters"]),
        "quality_cluster_count": len(q_block["clusters"]),
        "scientific_verdict": None,
    }
    atomic_json(viewer / "viewer_validation_receipt.json", receipt)
    return receipt


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("command", choices=("build", "validate", "build-and-validate"))
    args = parser.parse_args()
    config_path = args.config.resolve()
    cfg = load_config(config_path)
    if args.command in {"build", "build-and-validate"}:
        print(json.dumps(build(cfg, config_path), indent=2))
    if args.command in {"validate", "build-and-validate"}:
        print(json.dumps(validate(cfg), indent=2))


if __name__ == "__main__":
    main()
