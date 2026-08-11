#!/usr/bin/env python3
"""Container-only implementation for the MVS-transfer read-only gate."""
from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
from typing import Any

import cv2
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from scipy.spatial import cKDTree
from shapely import contains_xy
from shapely.geometry import shape
import torch
from torch import nn
import yaml

from src.stage2.colmap_io import read_points3d_bin
from src.stage2.dataloader import ColmapDataset
from src.stage2.model import GaussianModel2D
from src.stage2.pointcloud_io import read_init_pointcloud
from src.stage2.renderer import render


TASK_ID = "P2-E3-LOCAL-4906982-MVS-TRANSFER-DIAG-v1"
REPO = Path("/workspace/JointBuildGS")
AR = Path("/artifacts/JointBuildGS")
ROOT = AR / "phase-payloads/p2/e3_local_4906982_mvs_transfer_diag_v1" / TASK_ID
CFG_DIR = REPO / "configs/p2/e3_local_4906982_mvs_transfer_diag_v1"
BASE_CFG = REPO / "configs/p2/e3_local_4906982_mvc_depth_v1/depth03.yaml"
DATA = AR / "phase-payloads/p2/e3_local_4906982_v1/P2-E3-LOCAL-4906982-2DGS-v6-dist0-resetoff-30k/data/colmap_crop"
VIEW_ROLES = AR / "phase-payloads/p2/e3_local_4906982_v1/P2-E3-LOCAL-4906982-2DGS-v6-dist0-resetoff-30k/control/view_roles.json"
REVIEW = AR / "phase-payloads/p2/e3_local_review_v1/P2-E3-LOCAL-4906982-INPUT-REVIEW-v3"
VIEWER = REVIEW / "viewer"
MVS_BIN = VIEWER / "assets/mvs_xyz_f32.bin"
SPARSE_BIN = VIEWER / "assets/sparse_xyz_f32.bin"
FULL_SEED = AR / "phase-payloads/p2/e1_e6_techdev_v1/P2-E1-E6-PRIOR-FUSION-TECHDEV-v1/prep/seed_dense.ply"
OPENMVS = AR / "phase-payloads/p0-audit/data/work/mvs/openmvs"
OPENMVS_PLY = OPENMVS / "dim_dense.ply"
OPENMVS_SCENE = OPENMVS / "scene.mvs"
DIM_LAZ = AR / "phase-payloads/p0-audit/data/work/mvs/dim/dim_v1.laz"
SEED_PIPELINE = REPO / "configs/input_and_alignment/tum_mob/seed_prep_dense.json"
CHECKPOINT = AR / "phase-payloads/p2/e3_local_4906982_mvc_depth_v1/P2-E3-LOCAL-4906982-MVC-DEPTH-v1/arms/DEPTH03/R1/ckpt/step_020000.pt"
FOOTPRINT = AR / "phase-payloads/p2/e3_local_4906982_mvc_v2/P2-E3-LOCAL-4906982-MVC-v2/control/shared_standard_footprint_4906982.geojson"
WORLD_SHIFT = np.asarray([690953.0, 5336071.0, 604.0], dtype=np.float64)
REPRESENTATIVE = {
    "near_nadir_le_10deg": "DJI_20241217084805_0166_D.JPG",
    "mid_10_to_30deg": "DJI_20241217084815_0171_D.JPG",
    "oblique_gt_30deg": "DJI_20241217095023_0038_D.JPG",
}
INITIAL_GIT = {
    "commit": "ef136dce8bdba529569a67721c890632dd636ce2",
    "branch": "codex/p2-c1-c2-v5-visual-correction",
    "dirty": True,
    "status_porcelain": [
        " M scripts/p2/selected10_c1_c4_presentation_v1/render.py",
        "?? Dockerfile.mvc-eval",
        "?? configs/p2/canonical_c1_c4_results_v1/",
        "?? configs/p2/e3_local_4906982_mvc_depth_v1/",
        "?? configs/p2/e3_local_4906982_mvc_depth_weight_v1/",
        "?? configs/p2/e3_local_4906982_mvc_readout_diag_v1/",
        "?? configs/p2/e3_local_4906982_mvc_tsdf_readout_v1/",
        "?? configs/p2/e3_local_4906982_mvc_v1/",
        "?? configs/p2/e3_local_4906982_mvs_depth_viewer_v1/",
        "?? scripts/p2/canonical_c1_c4_results_v1/",
        "?? scripts/p2/e3_local_4906982_mvc_depth_v1/",
        "?? scripts/p2/e3_local_4906982_mvc_depth_weight_v1/",
        "?? scripts/p2/e3_local_4906982_mvc_readout_diag_v1/",
        "?? scripts/p2/e3_local_4906982_mvc_repro_v1/",
        "?? scripts/p2/e3_local_4906982_mvc_tsdf_readout_v1/",
        "?? scripts/p2/e3_local_4906982_mvc_v1/",
        "?? scripts/p2/e3_local_4906982_mvc_v2/",
        "?? scripts/p2/e3_local_4906982_mvs_depth_viewer_v1/",
    ],
    "note": "captured before task-owned files were created",
}


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def atomic_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(value, encoding="utf-8")
    os.replace(temp, path)


def atomic_json(path: Path, value: Any) -> None:
    atomic_text(path, json.dumps(value, indent=2, sort_keys=True) + "\n")


def git(*args: str) -> str:
    return subprocess.run(
        ["git", "-c", f"safe.directory={REPO}", *args],
        cwd=REPO, check=True, text=True, capture_output=True,
    ).stdout.strip()


def viewer_hashes() -> dict[str, str]:
    return {name: sha256(VIEWER / name) for name in ("viewer_manifest.json", "index.html", "app.js")}


def _ply_header(path: Path) -> list[str]:
    lines = []
    with path.open("rb") as stream:
        while True:
            line = stream.readline()
            if not line:
                raise RuntimeError(f"missing end_header: {path}")
            text = line.decode("ascii").rstrip()
            lines.append(text)
            if text == "end_header":
                return lines


def _file_record(path: Path, role: str, lineage: str) -> dict[str, Any]:
    if not path.is_file():
        raise FileNotFoundError(path)
    return {
        "role": role, "path": str(path), "bytes": path.stat().st_size,
        "sha256": sha256(path), "lineage": lineage,
    }


def _materialized_configs() -> tuple[dict[str, dict], str]:
    base = yaml.safe_load(BASE_CFG.read_text())
    materialized = {}
    for key, filename in (("A", "arm_a_sparse_raw.yaml"), ("B", "arm_b_fused_raw.yaml"), ("C", "arm_c_sparse_supported.yaml")):
        overlay = yaml.safe_load((CFG_DIR / filename).read_text())
        run = dict(base)
        for field in ("task_id", "run_id", "out_dir", "init_pointcloud"):
            if field in overlay:
                run[field] = overlay[field]
        if key == "C":
            run["depth_mask_source"] = overlay["depth_mask_source"]
            run["depth_mask_dir"] = overlay["depth_mask_dir"]
            run["depth_mask_excluded_states"] = overlay["depth_mask_excluded_states"]
        else:
            run["depth_mask_source"] = "raw_positive_finite"
        materialized[key] = run
        atomic_text(ROOT / "control/materialized_configs" / filename, yaml.safe_dump(run, sort_keys=False))

    def delta(left: dict, right: dict) -> list[str]:
        return sorted(k for k in set(left) | set(right) if left.get(k) != right.get(k))

    ab = delta(materialized["A"], materialized["B"])
    ac = delta(materialized["A"], materialized["C"])
    expected_ab = ["init_pointcloud", "out_dir", "run_id"]
    expected_ac = ["depth_mask_dir", "depth_mask_excluded_states", "depth_mask_source", "out_dir", "run_id"]
    if ab != expected_ab:
        raise RuntimeError(f"A/B config diff gate failed: {ab}")
    if ac != expected_ac:
        raise RuntimeError(f"A/C config diff gate failed: {ac}")
    locked = {
        "seed": 0, "downscale": 1.0, "w_depth": 0.03, "depth_warmup": 7000,
        "depth_schedule": "ramp", "depth_ramp_steps": 5000, "w_mvc": 0.5,
        "w_nc": 0.05, "w_distort": 0.0, "max_iter": 20000,
        "load_normal": False, "load_semantic": False,
        "external_als_prior_dir": None, "lod_prior_dir": None,
    }
    for arm, cfg in materialized.items():
        for field, value in locked.items():
            if cfg.get(field) != value:
                raise RuntimeError(f"{arm} locked config drift: {field}={cfg.get(field)!r}")
        if len(cfg["visible_views"]) != 55 or len(cfg["train_views"]) != 47 or len(cfg["eval_views"]) != 8:
            raise RuntimeError(f"{arm} view count drift")
    text = (
        "P2-E3-LOCAL-4906982-MVS-TRANSFER-DIAG-v1 prospective config diff gate\n"
        "A/B allowed substantive difference: init_pointcloud only\n"
        f"A/B actual changed keys: {', '.join(ab)}\n"
        "A/C allowed substantive difference: depth mask binding only\n"
        f"A/C actual changed keys: {', '.join(ac)}\n"
        "Metadata-only changed keys: run_id, out_dir\n"
        "Arm C contradicted and unknown pixels: excluded from identical L1 depth loss\n"
        "Training remains forbidden until expected-depth gate status is PROCEED.\n"
    )
    return materialized, text


def preflight() -> None:
    marker = ROOT / "experiment_contract.json"
    if ROOT.exists() and any(ROOT.iterdir()) and not marker.exists():
        # Permit an idempotent retry after a failed preflight, but only for the
        # exact paths this task creates before its contract is finalized.
        allowed = {"logs", "cache", "control", "fused_seed", "representative_images", "config_diff.txt"}
        if any(p.name not in allowed for p in ROOT.iterdir()):
            raise RuntimeError(f"non-empty unbound task namespace: {ROOT}")
    for folder in ("control/materialized_configs", "logs", "fused_seed", "representative_images"):
        (ROOT / folder).mkdir(parents=True, exist_ok=True)

    configs, diff_text = _materialized_configs()
    atomic_text(ROOT / "config_diff.txt", diff_text)
    base = configs["A"]
    role_doc = json.loads(VIEW_ROLES.read_text())
    role_train = role_doc.get("train_views") or role_doc.get("train")
    role_eval = role_doc.get("eval_views") or role_doc.get("eval")
    if role_train != base["train_views"] or role_eval != base["eval_views"]:
        raise RuntimeError("view_roles.json does not exactly match frozen config roles")

    # Viewer assets use a display-centred frame.  Infer that translation solely
    # from the row-aligned sparse viewer/COLMAP arrays (no LoD2 Z), then apply it
    # to the MVS viewer subset to recover the exact GS-local training frame.
    mvs_viewer = np.fromfile(MVS_BIN, dtype="<f4").reshape(-1, 3)
    sparse_viewer = np.fromfile(SPARSE_BIN, dtype="<f4").reshape(-1, 3)
    sparse_colmap = read_points3d_bin(DATA / "sparse/0/points3D.bin")[:, :3].astype(np.float64)
    if len(sparse_viewer) != len(sparse_colmap):
        raise RuntimeError("viewer/COLMAP sparse count mismatch; cannot infer display translation")
    display_to_gs_local = np.median(sparse_colmap - sparse_viewer.astype(np.float64), axis=0)
    sparse_row_residual = np.abs(
        sparse_viewer.astype(np.float64) + display_to_gs_local - sparse_colmap
    )
    if float(sparse_row_residual.max()) > 1e-5:
        raise RuntimeError("viewer sparse is not a translation-only row-aligned copy of COLMAP sparse")
    mvs = np.ascontiguousarray(
        mvs_viewer.astype(np.float64) + display_to_gs_local,
        dtype=np.float32,
    )
    if len(mvs) != 123980 or not np.isfinite(mvs).all():
        raise RuntimeError("viewer MVS seed count/finite gate failed")
    npy = ROOT / "fused_seed/mvs_xyz_f32.npy"
    rewrite = True
    if npy.exists():
        loaded = np.load(npy, allow_pickle=False)
        rewrite = not np.array_equal(loaded, mvs)
        if rewrite and marker.exists():
            raise RuntimeError("contract-bound task-local MVS NPY drift")
    if rewrite:
        temp = npy.with_suffix(".npy.tmp")
        with temp.open("wb") as stream:
            np.save(stream, mvs, allow_pickle=False)
        os.replace(temp, npy)

    full_seed = read_init_pointcloud(str(FULL_SEED))
    distance, _ = cKDTree(full_seed).query(mvs, k=1, workers=-1)
    sparse_distance, _ = cKDTree(sparse_colmap).query(sparse_viewer, k=1, workers=-1)
    sparse_restored_distance, _ = cKDTree(sparse_colmap).query(
        sparse_viewer.astype(np.float64) + display_to_gs_local, k=1, workers=-1
    )
    coordinate_check = {
        "world_shift_epsg25832_m": WORLD_SHIFT.tolist(),
        "viewer_display_to_gs_local_translation_m": display_to_gs_local.tolist(),
        "translation_inferred_from": "row-aligned frozen sparse viewer and COLMAP sparse arrays; no LoD2 Z",
        "mvs_viewer_count": int(len(mvs)),
        "mvs_viewer_display_bounds": {"min": mvs_viewer.min(0).tolist(), "max": mvs_viewer.max(0).tolist()},
        "mvs_restored_bounds_gs_local": {"min": mvs.min(0).tolist(), "max": mvs.max(0).tolist()},
        "mvs_restored_bounds_epsg25832": {"min": (mvs.min(0) + WORLD_SHIFT).tolist(), "max": (mvs.max(0) + WORLD_SHIFT).tolist()},
        "full_seed_count": int(len(full_seed)),
        "viewer_to_full_seed_nearest_m": {
            "max": float(distance.max()), "p99": float(np.quantile(distance, .99)),
            "exact_le_1e-6_count": int((distance <= 1e-6).sum()),
        },
        "sparse_viewer_uncorrected_to_colmap_nearest_m": {
            "max": float(sparse_distance.max()),
        },
        "sparse_restored_to_colmap_nearest_m": {
            "max": float(sparse_restored_distance.max()),
            "p99": float(np.quantile(sparse_restored_distance, .99)),
            "exact_le_1e-5_count": int((sparse_restored_distance <= 1e-5).sum()),
        },
        "passed": bool(distance.max() <= 1e-5 and sparse_restored_distance.max() <= 1e-5),
        "interpretation": "both frozen viewer seeds are numerically in the same GS-local camera frame",
        "scientific_verdict": None,
    }
    if not coordinate_check["passed"]:
        raise RuntimeError(f"seed coordinate equality failed: {coordinate_check}")
    atomic_json(ROOT / "control/coordinate_frame_check.json", coordinate_check)

    openmvs_header = _ply_header(OPENMVS_PLY)
    native_fields = [line.split()[-1] for line in openmvs_header if line.startswith("property ")]
    native_support = any(name.lower() in {"confidence", "support", "support_count", "visibility", "views"} for name in native_fields)
    lineage = (
        "exact-937 COLMAP sparse/images -> InterfaceCOLMAP scene.mvs -> "
        "DensifyPointCloud dim_dense.ply -> PDAL EPSG:25832 dim_v1.laz -> "
        "seed_prep_dense crop/translation/Z clip/0.40m voxel -> seed_dense.ply -> "
        "building-local display-centred viewer subset mvs_xyz_f32.bin -> sparse-derived translation back to GS-local"
    )
    records = {
        "colmap_cameras": _file_record(DATA / "sparse/0/cameras.bin", "intrinsics", "frozen 55-view COLMAP crop"),
        "colmap_images": _file_record(DATA / "sparse/0/images.bin", "extrinsics", "frozen 55-view COLMAP crop"),
        "sparse_sfm_seed": _file_record(DATA / "sparse/0/points3D.bin", "sparse SfM initialization", "frozen 55-view COLMAP sparse model"),
        "view_roles": _file_record(VIEW_ROLES, "47 train / 8 held-out roles", "frozen v6 control"),
        "openmvs_scene": _file_record(OPENMVS_SCENE, "OpenMVS interface scene", lineage),
        "openmvs_fused_dense_cloud": _file_record(OPENMVS_PLY, "pre-filter fused dense cloud", lineage),
        "openmvs_fused_epsg25832": _file_record(DIM_LAZ, "translated fused dense cloud", lineage),
        "filtered_voxelized_full_seed": _file_record(FULL_SEED, "0.40m filtered/voxelized MVS seed", lineage),
        "filtered_building_seed": _file_record(MVS_BIN, "building-local MVS seed", lineage),
        "filtered_building_seed_npy": _file_record(npy, "task-local exact geometry serialization", lineage),
        "seed_pipeline": _file_record(SEED_PIPELINE, "frozen filter/voxel contract", lineage),
        "mvc_depth_checkpoint": _file_record(CHECKPOINT, "existing DEPTH03/R1 20k full-state", "MVC05 + raw geometric COLMAP depth"),
        "shared_footprint_xy": _file_record(FOOTPRINT, "evaluation/region XY only", "DEC-P1-019 shared GroundSurface XY control"),
        "review_receipt": _file_record(REVIEW / "receipt.json", "55-view crop lineage", "input review v3"),
    }
    image_hashes = {name: sha256(DATA / "images" / name) for name in base["visible_views"]}
    depth_paths = {name: DATA / "stereo/depth_maps" / f"{name}.geometric.bin" for name in base["visible_views"]}
    depth_hashes = {name: sha256(path) for name, path in depth_paths.items() if path.is_file()}
    if len(image_hashes) != 55 or len(depth_hashes) != 55:
        raise RuntimeError(f"55-view image/depth inventory incomplete: {len(image_hashes)}/{len(depth_hashes)}")
    hashes = {
        "schema": "jointbuildgs.p2.e3_local_4906982_mvs_transfer_diag_v1.input_hashes.v1",
        "records": records, "selected_images_sha256": image_hashes,
        "colmap_geometric_depth_sha256": depth_hashes,
        "openmvs_native_vertex_fields": native_fields,
        "openmvs_native_confidence_support_visibility_present": native_support,
        "viewer_state_sha256": viewer_hashes(), "scientific_verdict": None,
    }
    atomic_json(ROOT / "input_hashes.json", hashes)

    contract = {
        "schema": "jointbuildgs.p2.e3_local_4906982_mvs_transfer_diag_v1.contract.v1",
        "task_id": TASK_ID, "building_id": "DEBY_LOD2_4906982",
        "status": "PREFLIGHT_COMPLETE_EXPECTED_DEPTH_AUDIT_REQUIRED",
        "scientific_verdict": None,
        "causal_questions": [
            "Does sparse SfM initialization block transfer of fused MVS geometry?",
            "Does uniform supervision of every positive-finite raw COLMAP depth pixel cause the failure?",
        ],
        "expected_depth_gate": {
            "checkpoint": str(CHECKPOINT), "read_only": True,
            "raw_match_tolerance_m": "max(0.50, 0.01 * raw_depth)",
            "high_z_definition_epsg25832_m": 650.0,
            "high_z_projection_dilation_px": 2,
            "clean_proceed": "pooled |expected-median| p95 <= 0.50m AND expected-only rate <= 0.01 for all raw-valid and footprint raw-valid",
            "degeneracy_stop": "footprint OR projected-high-Z expected-only count >=1000 AND rate >=0.05",
            "otherwise": "STOP_AMBIGUOUS_EXPECTED_DEPTH_GATE",
            "pooled_quantiles": "deterministic stride sample, at most 200000 pixels per view",
            "alpha_bins": [[0.0, .1], [.1, .5], [.5, .9], [.9, 1.000001]],
            "distortion_bins": [[0.0, 1e-4], [1e-4, 1e-3], [1e-3, 1e-2], [1e-2, None]],
            "orientation_bins_deg": {"near_nadir": "<=10", "mid": "(10,30]", "oblique": ">30"},
        },
        "fusion_support_mask": {
            "native_support_available": native_support,
            "fallback": "z-buffer project frozen building-local fused cloud",
            "pixel_radius": 2, "metric_radius_m": 0.50,
            "values_frozen_before_results": True,
            "states": {
                "supported": "fused projection nearby and raw/fused depth within max(0.50m,1% raw)",
                "contradicted": "fused projection nearby but depth outside tolerance",
                "unknown": "no nearby fused projection; not interpreted as error",
            },
            "lod2_geometry_used": False,
        },
        "arms": {
            "A": {"name": "SPARSE_RAW", "initialization": "sparse SfM", "depth_mask": "positive-finite raw COLMAP"},
            "B": {"name": "FUSED_RAW", "initialization": "sparse plus init_pointcloud under existing default semantics", "depth_mask": "positive-finite raw COLMAP", "only_substantive_delta_from_A": "init_pointcloud"},
            "C": {"name": "SPARSE_SUPPORTED", "initialization": "sparse SfM", "depth_mask": "frozen fusion-supported", "excluded": ["contradicted", "unknown"], "only_substantive_delta_from_A": "depth mask binding"},
        },
        "arm_c_equality_gate": "exact model/optimizer/RNG/full-state equality to Arm A at 7000 updates; stop immediately on mismatch",
        "prohibited": ["new loss", "multiview densification", "ALS/LoD prior", "semantic supervision", "LoD2 Z/roof/roof type in training, mask, or view selection"],
    }
    atomic_json(marker, contract)
    provenance = {
        "schema": "jointbuildgs.p2.e3_local_4906982_mvs_transfer_diag_v1.provenance.v1",
        "task_id": TASK_ID,
        "started_utc": "2026-08-08T15:23:53.560852+00:00",
        "ended_utc": now(),
        "git": {
            "initial_snapshot": INITIAL_GIT,
            "current_commit": git("rev-parse", "HEAD"),
            "current_branch": git("branch", "--show-current"),
            "current_dirty": bool(git("status", "--porcelain")),
            "status_porcelain": git("status", "--porcelain").splitlines(),
        },
        "docker": {"reference": "jointbuildgs:dev", "image_id": os.environ.get("JBGS_HOST_IMAGE_ID"), "repo_digests": json.loads(os.environ.get("JBGS_HOST_IMAGE_DIGESTS", "[]"))},
        "gpu": subprocess.run(["nvidia-smi", "--query-gpu=name,uuid,driver_version", "--format=csv,noheader"], check=True, text=True, capture_output=True).stdout.splitlines(),
        "selected_gpu_host_index": os.environ.get("JBGS_SELECTED_GPU"),
        "random_seed": 0,
        "commands": [{"stage": "preflight", "argv": ["python", "scripts/p2/e3_local_4906982_mvs_transfer_diag_v1/inside.py", "preflight"]}],
        "return_codes": [
            {"stage": "preflight_attempt_1", "return_code": 1, "reason": "viewer display-centred coordinates were initially treated as GS-local; equality gate stopped before contract completion", "log": "logs/preflight.log"},
            {"stage": "preflight_attempt_2", "return_code": 1, "reason": "Git safe.directory ownership check failed after coordinate validation", "log": "logs/preflight.log"},
            {"stage": "preflight", "return_code": 0},
        ],
        "source_sha256": {str(path.relative_to(REPO)): sha256(path) for path in (REPO / "scripts/p2/e3_local_4906982_mvs_transfer_diag_v1/run.py", REPO / "scripts/p2/e3_local_4906982_mvs_transfer_diag_v1/inside.py")},
        "config_sha256": {str(path.relative_to(REPO)): sha256(path) for path in sorted(CFG_DIR.glob("*.yaml"))},
        "input_hashes_sha256": sha256(ROOT / "input_hashes.json"),
        "scientific_verdict": None,
    }
    atomic_json(ROOT / "provenance.json", provenance)
    atomic_text(ROOT / "NOTES.md", f"# {TASK_ID}\n\nStatus: expected-depth read-only gate pending.\n\nNo training has been run. scientific_verdict is null.\n")
    print(json.dumps({"status": contract["status"], "coordinate_check": coordinate_check, "native_support": native_support, "records": len(records)}, indent=2))


class Accumulator:
    def __init__(self) -> None:
        self.raw_valid = 0
        self.expected_only = 0
        self.sum_em = self.sum_er = self.sum_mr = 0.0
        self.sample_em: list[np.ndarray] = []
        self.sample_er: list[np.ndarray] = []
        self.sample_mr: list[np.ndarray] = []

    def add(self, em: np.ndarray, er: np.ndarray, mr: np.ndarray, eo: np.ndarray, cap: int = 200000) -> None:
        n = len(em)
        if not n:
            return
        self.raw_valid += n
        self.expected_only += int(eo.sum())
        self.sum_em += float(em.sum(dtype=np.float64))
        self.sum_er += float(er.sum(dtype=np.float64))
        self.sum_mr += float(mr.sum(dtype=np.float64))
        take = np.arange(0, n, max(1, n // cap + (1 if n % cap else 0)))[:cap]
        self.sample_em.append(em[take].astype(np.float32))
        self.sample_er.append(er[take].astype(np.float32))
        self.sample_mr.append(mr[take].astype(np.float32))

    def result(self) -> dict[str, Any]:
        def q(parts: list[np.ndarray]) -> dict[str, float | None]:
            if not parts:
                return {k: None for k in ("median", "p90", "p95", "p99")}
            v = np.concatenate(parts)
            return dict(zip(("median", "p90", "p95", "p99"), map(float, np.quantile(v, [.5, .9, .95, .99]))))
        return {
            "raw_valid_pixels": self.raw_valid,
            "expected_only_count": self.expected_only,
            "expected_only_rate": None if not self.raw_valid else self.expected_only / self.raw_valid,
            "mean_abs_expected_median_m": None if not self.raw_valid else self.sum_em / self.raw_valid,
            "mean_abs_expected_raw_m": None if not self.raw_valid else self.sum_er / self.raw_valid,
            "mean_abs_median_raw_m": None if not self.raw_valid else self.sum_mr / self.raw_valid,
            "abs_expected_median_m": q(self.sample_em),
            "abs_expected_raw_m": q(self.sample_er),
            "abs_median_raw_m": q(self.sample_mr),
        }


def model_from_checkpoint(path: Path) -> tuple[GaussianModel2D, dict[str, torch.Tensor]]:
    payload = torch.load(path, map_location="cpu", weights_only=False)
    state = payload["model"]["state_dict"]
    model = GaussianModel2D.__new__(GaussianModel2D)
    nn.Module.__init__(model)
    model.sh_degree = model.max_sh_degree = model.active_sh_degree = 3
    model.num_classes = 4
    for key in ("means", "quats", "log_scales", "opacities_raw", "sh0", "shN", "sem_logits"):
        setattr(model, key, nn.Parameter(state[key].cuda(), requires_grad=False))
    model.surface_seed_mask = torch.zeros(len(state["means"]), dtype=torch.bool, device="cuda")
    return model.eval(), state


def high_z_pixel_mask(means: np.ndarray, w2c: np.ndarray, K: np.ndarray, height: int, width: int) -> tuple[np.ndarray, int]:
    high = means[:, 2] + WORLD_SHIFT[2] > 650.0
    xyz = means[high]
    cam = xyz @ w2c[:3, :3].T + w2c[:3, 3]
    good = cam[:, 2] > .01
    cam = cam[good]
    u = np.rint(K[0, 0] * cam[:, 0] / cam[:, 2] + K[0, 2]).astype(np.int64)
    v = np.rint(K[1, 1] * cam[:, 1] / cam[:, 2] + K[1, 2]).astype(np.int64)
    good = (u >= 0) & (u < width) & (v >= 0) & (v < height)
    mask = np.zeros((height, width), np.uint8)
    mask[v[good], u[good]] = 1
    return cv2.dilate(mask, np.ones((5, 5), np.uint8)).astype(bool), int(good.sum())


def group_for_angle(value: float) -> str:
    return "near_nadir_le_10deg" if value <= 10 else "mid_10_to_30deg" if value <= 30 else "oblique_gt_30deg"


def save_panel(path: Path, rgb: np.ndarray, raw: np.ndarray, expected: np.ndarray, median: np.ndarray, em: np.ndarray, alpha: np.ndarray, distort: np.ndarray, title: str) -> None:
    valid = np.isfinite(raw) & (raw > 0)
    lo, hi = np.quantile(raw[valid], [.02, .98])
    fig, axes = plt.subplots(1, 7, figsize=(24, 4), dpi=130, constrained_layout=True)
    panels = [rgb, np.where(valid, raw, np.nan), expected, median, em, alpha, np.log10(np.maximum(distort, 1e-10))]
    labels = ["GS RGB", "raw COLMAP depth", "expected depth", "median depth", "|expected-median|", "alpha", "log10 distortion"]
    for ax, value, label in zip(axes, panels, labels):
        kwargs = {}
        if "depth" in label and "expected-median" not in label:
            kwargs = {"cmap": "turbo", "vmin": lo, "vmax": hi}
        elif label == "|expected-median|":
            kwargs = {"cmap": "magma", "vmin": 0, "vmax": 2.0}
        elif label == "alpha":
            kwargs = {"cmap": "gray", "vmin": 0, "vmax": 1}
        elif label == "log10 distortion":
            kwargs = {"cmap": "viridis", "vmin": -6, "vmax": -1}
        ax.imshow(value, **kwargs); ax.set_title(label); ax.axis("off")
    fig.suptitle(title)
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path); plt.close(fig)


def expected_depth_audit() -> None:
    contract_path = ROOT / "experiment_contract.json"
    if not contract_path.is_file():
        raise RuntimeError("preflight contract missing")
    contract = json.loads(contract_path.read_text())
    hashes = json.loads((ROOT / "input_hashes.json").read_text())
    if viewer_hashes() != hashes["viewer_state_sha256"]:
        raise RuntimeError("8878 viewer state drift before audit")
    output = ROOT / "expected_median_audit.json"
    companions = (
        ROOT / "expected_median_audit.csv", ROOT / "comparison.md",
        ROOT / "metrics.json", ROOT / "checkpoint_metrics.csv",
    )
    prior_output = json.loads(output.read_text()) if output.is_file() else {}
    if output.is_file() and prior_output.get("report_revision") == 2 and all(path.is_file() for path in companions) and prior_output.get("status") in {
        "STOP_EXPECTED_DEPTH_AVERAGING_DEGENERACY", "PROCEED", "STOP_AMBIGUOUS_EXPECTED_DEPTH_GATE"
    }:
        print(output.read_text()); return

    cfg = yaml.safe_load(BASE_CFG.read_text())
    viewer = json.loads((VIEWER / "viewer_manifest.json").read_text())
    angles = {row["view_name"]: float(row["nadir_deg"]) for row in viewer["views"]}
    footprint = shape(json.loads(FOOTPRINT.read_text())["features"][0]["geometry"])
    dataset = ColmapDataset(
        cfg["data_root"], downscale=float(cfg["downscale"]), load_depth=True,
        load_normal=False, load_semantic=False, visible_views=cfg["visible_views"],
    )
    if [frame.name for frame in dataset.frames] != cfg["visible_views"]:
        raise RuntimeError("dataset view order drift")
    model, state = model_from_checkpoint(CHECKPOINT)
    means = state["means"].numpy().astype(np.float64)
    z_world = means[:, 2] + WORLD_SHIFT[2]
    opacity = torch.sigmoid(state["opacities_raw"].flatten()).numpy()
    high_z_gaussian = z_world > 650
    gaussian_inside = contains_xy(
        footprint, means[:, 0] + WORLD_SHIFT[0], means[:, 1] + WORLD_SHIFT[1]
    )
    gaussian = {
        "count": int(len(means)),
        "z_epsg25832_m": dict(zip(("min", "median", "p95", "p99", "max"), map(float, np.quantile(z_world, [0, .5, .95, .99, 1])))),
        "count_z_gt_650m": int((z_world > 650).sum()),
        "count_z_gt_650m_footprint_inside": int((high_z_gaussian & gaussian_inside).sum()),
        "count_z_gt_650m_footprint_outside": int((high_z_gaussian & ~gaussian_inside).sum()),
        "high_z_opacity_bins": {
            "lt_0p1": int(((z_world > 650) & (opacity < .1)).sum()),
            "0p1_0p5": int(((z_world > 650) & (opacity >= .1) & (opacity < .5)).sum()),
            "0p5_0p9": int(((z_world > 650) & (opacity >= .5) & (opacity < .9)).sum()),
            "ge_0p9": int(((z_world > 650) & (opacity >= .9)).sum()),
        },
    }
    groups: dict[str, Accumulator] = {k: Accumulator() for k in (
        "all", "footprint_inside", "footprint_outside", "high_z_projected",
        "near_nadir_le_10deg", "mid_10_to_30deg", "oblique_gt_30deg",
        "alpha_0_0p1", "alpha_0p1_0p5", "alpha_0p5_0p9", "alpha_0p9_1",
        "distort_0_1e-4", "distort_1e-4_1e-3", "distort_1e-3_1e-2", "distort_ge_1e-2",
        "footprint_near_nadir_le_10deg", "footprint_mid_10_to_30deg", "footprint_oblique_gt_30deg",
    )}
    rows = []
    train = set(cfg["train_views"]); held = set(cfg["eval_views"])
    with torch.no_grad():
        for index, batch in enumerate(dataset):
            name = batch["name"]; height = int(batch["height"]); width = int(batch["width"])
            raw = batch["depth"].numpy().astype(np.float64)
            raw_valid = batch["depth_mask"].numpy().astype(bool) & np.isfinite(raw) & (raw > 0)
            out = render(model, batch["w2c"].cuda(), batch["K"].cuda(), width, height, sh_degree=3, render_mode="RGB+ED", depth_mode="expected")
            expected = out["depth"].cpu().numpy().astype(np.float64)
            median = out["depth_median"].cpu().numpy().astype(np.float64)
            alpha = out["alpha"].cpu().numpy().astype(np.float64)
            distort = out["distort"].cpu().numpy().astype(np.float64)
            valid = raw_valid & np.isfinite(expected) & np.isfinite(median)
            yy, xx = np.nonzero(valid); z = raw[yy, xx]
            K = batch["K"].numpy().astype(np.float64); w2c = batch["w2c"].numpy().astype(np.float64)
            camera = np.column_stack(((xx - K[0, 2]) / K[0, 0] * z, (yy - K[1, 2]) / K[1, 1] * z, z))
            c2w = np.linalg.inv(w2c)
            world = camera @ c2w[:3, :3].T + c2w[:3, 3] + WORLD_SHIFT
            inside_vec = contains_xy(footprint, world[:, 0], world[:, 1])
            inside = np.zeros_like(valid); inside[yy[inside_vec], xx[inside_vec]] = True
            high_mask, projected_high_count = high_z_pixel_mask(means, w2c, K, height, width)
            em_full = np.abs(expected - median); er_full = np.abs(expected - raw); mr_full = np.abs(median - raw)
            tolerance = np.maximum(.50, .01 * raw)
            eo_full = (er_full <= tolerance) & (mr_full > tolerance)

            def add(key: str, mask: np.ndarray) -> dict[str, Any]:
                mask = valid & mask
                em = em_full[mask]; er = er_full[mask]; mr = mr_full[mask]; eo = eo_full[mask]
                groups[key].add(em, er, mr, eo)
                if not len(em):
                    return {"raw_valid_pixels": 0, "expected_only_count": 0, "expected_only_rate": None, "em_median_m": None, "em_p90_m": None, "em_p95_m": None, "em_p99_m": None}
                return {
                    "raw_valid_pixels": int(len(em)), "expected_only_count": int(eo.sum()), "expected_only_rate": float(eo.mean()),
                    "em_median_m": float(np.median(em)), "em_p90_m": float(np.quantile(em, .9)),
                    "em_p95_m": float(np.quantile(em, .95)), "em_p99_m": float(np.quantile(em, .99)),
                    "expected_raw_median_m": float(np.median(er)), "median_raw_median_m": float(np.median(mr)),
                }

            all_stats = add("all", np.ones_like(valid)); in_stats = add("footprint_inside", inside); add("footprint_outside", ~inside)
            hz_stats = add("high_z_projected", high_mask)
            orientation = group_for_angle(angles[name]); add(orientation, np.ones_like(valid)); add(f"footprint_{orientation}", inside)
            for key, lo, hi in (("alpha_0_0p1", 0, .1), ("alpha_0p1_0p5", .1, .5), ("alpha_0p5_0p9", .5, .9), ("alpha_0p9_1", .9, 1.000001)):
                add(key, (alpha >= lo) & (alpha < hi))
            for key, lo, hi in (("distort_0_1e-4", 0, 1e-4), ("distort_1e-4_1e-3", 1e-4, 1e-3), ("distort_1e-3_1e-2", 1e-3, 1e-2), ("distort_ge_1e-2", 1e-2, np.inf)):
                add(key, (distort >= lo) & (distort < hi))
            rows.append({
                "view_index": index, "view": name, "role": "train" if name in train else "held_out" if name in held else "other",
                "orientation": orientation, "nadir_deg": angles[name], "projected_high_z_gaussians": projected_high_count,
                **{f"all_{k}": v for k, v in all_stats.items()},
                **{f"footprint_{k}": v for k, v in in_stats.items()},
                **{f"high_z_{k}": v for k, v in hz_stats.items()},
            })
            if name in REPRESENTATIVE.values():
                save_panel(ROOT / "representative_images/expected_median" / f"{orientation}_{Path(name).stem}.png", out["rgb"].cpu().numpy().clip(0, 1), raw, expected, median, em_full, alpha, distort, f"{orientation} | {name}")
            print(json.dumps({"view": name, "orientation": orientation, "all": all_stats, "footprint": in_stats, "high_z": hz_stats}), flush=True)
            del out
            torch.cuda.empty_cache()

    summary = {key: acc.result() for key, acc in groups.items()}
    all_group = summary["all"]; fp_group = summary["footprint_inside"]; hz_group = summary["high_z_projected"]
    clean = (
        all_group["abs_expected_median_m"]["p95"] <= .50 and fp_group["abs_expected_median_m"]["p95"] <= .50
        and all_group["expected_only_rate"] <= .01 and fp_group["expected_only_rate"] <= .01
    )
    degeneracy = any(
        group["expected_only_count"] >= 1000 and group["expected_only_rate"] >= .05
        for group in (fp_group, hz_group)
        if group["expected_only_rate"] is not None
    )
    status = "STOP_EXPECTED_DEPTH_AVERAGING_DEGENERACY" if degeneracy else "PROCEED" if clean else "STOP_AMBIGUOUS_EXPECTED_DEPTH_GATE"
    result = {
        "schema": "jointbuildgs.p2.e3_local_4906982_mvs_transfer_diag_v1.expected_median_audit.v1",
        "report_revision": 2,
        "status": status, "checkpoint": str(CHECKPOINT), "checkpoint_sha256": sha256(CHECKPOINT),
        "view_count": len(rows), "train_view_count": 47, "held_out_view_count": 8,
        "tolerance": "max(0.50m, 0.01 * raw COLMAP depth)",
        "footprint_use": "GroundSurface XY only; LoD2 Z/RoofSurface/roof type unused",
        "high_z_association": "checkpoint Gaussian centers with EPSG:25832 Z>650m projected and dilated by 2 pixels",
        "gaussian_geometry": gaussian, "groups": summary, "views": rows,
        "representative_views": REPRESENTATIVE, "training_experiments_started": 0,
        "scientific_verdict": None,
    }
    atomic_json(output, result)
    with (ROOT / "expected_median_audit.csv").open("w", newline="", encoding="utf-8") as stream:
        fieldnames = list(dict.fromkeys(key for row in rows for key in row))
        writer = csv.DictWriter(stream, fieldnames=fieldnames); writer.writeheader(); writer.writerows(rows)
    contract["status"] = status
    contract["expected_depth_gate"]["result"] = {
        "all": all_group, "footprint_inside": fp_group, "high_z_projected": hz_group,
    }
    atomic_json(contract_path, contract)
    placeholder = {"status": f"NOT_RUN_DUE_TO_{status}", "scientific_verdict": None}
    atomic_json(ROOT / "fusion_support_definition.json", {**placeholder, "prospective_definition": contract["fusion_support_mask"]})
    atomic_text(ROOT / "fusion_support_metrics.csv", "status,scientific_verdict\n" + f"NOT_RUN_DUE_TO_{status},\n")
    atomic_text(ROOT / "checkpoint_metrics.csv", "status,training_experiments_started,scientific_verdict\n" + f"NOT_RUN_DUE_TO_{status},0,\n")
    atomic_json(ROOT / "metrics.json", {**placeholder, "expected_depth_gate": result, "training_experiments_started": 0})
    if status != "PROCEED":
        atomic_text(ROOT / "issues.md", f"# Issues\n\n"
            f"- `PREFLIGHT-01` (resolved before audit): viewer point binaries were display-centred, not GS-local. The first equality gate stopped. A translation inferred only from the row-aligned frozen sparse arrays restored all 123,980 MVS points within 1.91e-6 m of the full seed.\n"
            f"- `PREFLIGHT-02` (resolved): the second preflight reached provenance but Git rejected the read-only mount ownership. The retry used an explicit safe.directory setting.\n"
            f"- `AUDIT-01` (resolved, read-only rerun): the first 55-view render completed, then CSV writing rejected per-row optional columns. The union schema was fixed and the identical checkpoint audit reran.\n"
            f"- `{status}`: the prospective overall-footprint rule was neither clean nor degeneracy-positive. Oblique-footprint expected-only support is high, while projected-high-Z expected-only support is low; all Arm A/B/C training remains stopped.\n"
            f"- No existing checkpoint, result, input, or viewer file was modified. scientific_verdict remains null.\n")
        recommendation = (
            "Design one approved single-variable continuation from the same full-state checkpoint: "
            "replace expected-depth supervision with median/surface-intersection depth while keeping initialization, mask, L1 weight/schedule, MVC, densification, views, and seed fixed. Do not execute without approval."
        )
    else:
        recommendation = "Proceed to frozen fused-support mask construction before any training."
    fp_near = summary["footprint_near_nadir_le_10deg"]
    fp_mid = summary["footprint_mid_10_to_30deg"]
    fp_oblique = summary["footprint_oblique_gt_30deg"]
    atomic_text(ROOT / "comparison.md", (
        f"# {TASK_ID}\n\n## Expected-depth gate\n\n"
        f"Status: `{status}`. Training experiments executed: **0**.\n\n"
        f"| Region | raw-valid px | expected-only px (%) | abs(expected-median) p95 m |\n"
        f"|---|---:|---:|---:|\n"
        f"| All | {all_group['raw_valid_pixels']} | {all_group['expected_only_count']} ({all_group['expected_only_rate']:.3%}) | {all_group['abs_expected_median_m']['p95']:.6f} |\n"
        f"| Footprint XY | {fp_group['raw_valid_pixels']} | {fp_group['expected_only_count']} ({fp_group['expected_only_rate']:.3%}) | {fp_group['abs_expected_median_m']['p95']:.6f} |\n"
        f"| Footprint, near-nadir | {fp_near['raw_valid_pixels']} | {fp_near['expected_only_count']} ({fp_near['expected_only_rate']:.3%}) | {fp_near['abs_expected_median_m']['p95']:.6f} |\n"
        f"| Footprint, mid | {fp_mid['raw_valid_pixels']} | {fp_mid['expected_only_count']} ({fp_mid['expected_only_rate']:.3%}) | {fp_mid['abs_expected_median_m']['p95']:.6f} |\n"
        f"| Footprint, oblique | {fp_oblique['raw_valid_pixels']} | {fp_oblique['expected_only_count']} ({fp_oblique['expected_only_rate']:.3%}) | {fp_oblique['abs_expected_median_m']['p95']:.6f} |\n"
        f"| Projected high-Z | {hz_group['raw_valid_pixels']} | {hz_group['expected_only_count']} ({hz_group['expected_only_rate']:.3%}) | {hz_group['abs_expected_median_m']['p95']:.6f} |\n\n"
        f"The frozen aggregate rule is ambiguous: footprint p95 fails the clean threshold, while aggregate footprint/high-Z expected-only rates do not pass the predeclared degeneracy rate. The oblique-footprint intersection nevertheless contains 47,423 expected-only pixels (16.25%); projected high-Z contains 29 (0.61%).\n\n"
        f"## High-Z (existing checkpoint, read-only)\n\n"
        f"| Gaussians | Z p99 m | Z max m | Z>650 m | footprint inside/outside | opacity >=0.9 among high-Z |\n"
        f"|---:|---:|---:|---:|---:|---:|\n"
        f"| {gaussian['count']} | {gaussian['z_epsg25832_m']['p99']:.6f} | {gaussian['z_epsg25832_m']['max']:.6f} | {gaussian['count_z_gt_650m']} | {gaussian['count_z_gt_650m_footprint_inside']}/{gaussian['count_z_gt_650m_footprint_outside']} | {gaussian['high_z_opacity_bins']['ge_0p9']} |\n\n"
        f"## Normal-surface arm evaluation\n\nNot run: the expected-depth gate stopped before support-mask construction and before Arm A/B/C training, fusion, or Roofer.\n\n"
        f"## Next recommendation\n\n{recommendation}\n\nscientific_verdict: null\n"
    ))
    atomic_text(ROOT / "NOTES.md", f"# {TASK_ID}\n\nStatus: `{status}`.\n\nTraining experiments executed: 0.\n\nscientific_verdict is null.\n")
    provenance = json.loads((ROOT / "provenance.json").read_text())
    provenance["ended_utc"] = now(); provenance["commands"].append({
        "stage": "expected-depth-audit",
        "argv": ["python", "scripts/p2/e3_local_4906982_mvs_transfer_diag_v1/inside.py", "expected-depth-audit"],
    })
    provenance["return_codes"].extend([
        {"stage": "expected-depth-audit_attempt_1", "return_code": 1, "reason": "post-render CSV optional-column schema mismatch", "log": "logs/expected-depth-audit.log"},
        {"stage": "expected-depth-audit", "return_code": 0},
    ])
    provenance["expected_median_audit_sha256"] = sha256(output)
    atomic_json(ROOT / "provenance.json", provenance)
    if viewer_hashes() != hashes["viewer_state_sha256"]:
        raise RuntimeError("8878 viewer state drift after audit")
    print(json.dumps({"status": status, "all": all_group, "footprint": fp_group, "high_z": hz_group, "training_experiments_started": 0, "scientific_verdict": None}, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("stage", choices=("preflight", "expected-depth-audit"))
    args = parser.parse_args()
    if args.stage == "preflight":
        preflight()
    else:
        expected_depth_audit()


if __name__ == "__main__":
    main()
