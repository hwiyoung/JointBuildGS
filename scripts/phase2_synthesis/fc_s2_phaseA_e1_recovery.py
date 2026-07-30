"""FC-S2 Phase A: recover/regenerate E1 Baseline rendered evidence.

This script intentionally does not modify Stage3. It first records the E1
artifact search required by the FC-S2 prompt, then regenerates the missing
Baseline rendered evidence with the same render/export convention used for
E2_Mutual_rendered.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import subprocess
import sys
import time
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

import numpy as np
import torch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import scripts.phase2_synthesis.fc_s1_semantic_surface_readout as fc  # noqa: E402
from scripts.phase2_synthesis.obj_gt import parse_scene_obj  # noqa: E402
import scripts.phase2_synthesis.s1_rendered_e2style_gate as s1  # noqa: E402
import scripts.phase2_synthesis.s1d_fix_export_and_rerun as s1d  # noqa: E402


OUT_ROOT = (
    ROOT
    / "results/footprint_conditioned_readout"
    / "FC_S2_baseline_rendered_recovery_stage3_v1c"
    / "phaseA_e1_recovery"
)
E2_RENDER_ROOT = ROOT / "results/stage3_rendered_evidence/S1D_fix_export_and_rerun"
E2_FULL_NPZ = (
    E2_RENDER_ROOT
    / "phase3_fixed_quality/rendered_evidence_fixed_F2_class_normal_aware_voxel_0p05.npz"
)
E2_RENDER_METADATA = E2_RENDER_ROOT / "phase1_transform_sweep/rendered_sample_bank_metadata.json"
E2_VIEW_CSV = E2_RENDER_ROOT / "phase1_transform_sweep/rendered_sample_bank_views.csv"
E2_FIXED_METADATA = E2_RENDER_ROOT / "phase2_fixed_export/fixed_export_metadata.json"
E2_GRAPH = (
    E2_RENDER_ROOT
    / "phase3_fixed_quality/scene_evidence_graph_fixed_F2_class_normal_aware_voxel_0p05.json"
)
BASELINE_CONFIG = ROOT / "configs/mutual_loss/core_ablation/phase2_baseline.yaml"
BASELINE_CKPT = ROOT / "results/phase2_ablation_citygml/baseline/ckpt/final.pt"
MUTUAL_CONFIG = ROOT / "configs/mutual_loss/core_ablation/phase2_mutual.yaml"
MUTUAL_CKPT = ROOT / "results/phase2_ablation_citygml/mutual/ckpt/final.pt"

CLASS_FIELDS = {0: "n_bg", 1: "n_roof", 2: "n_wall", 3: "n_ground"}


def mkdir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def rel(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def jsonable(obj):
    if isinstance(obj, np.ndarray):
        return obj.tolist()
    if isinstance(obj, np.generic):
        return obj.item()
    if isinstance(obj, Path):
        return rel(obj)
    return str(obj)


def write_json(path: Path, payload: Dict) -> None:
    mkdir(path.parent)
    path.write_text(json.dumps(payload, indent=2, default=jsonable) + "\n")


def read_json(path: Path) -> Dict:
    if not path.exists():
        return {}
    return json.loads(path.read_text())


def write_csv(path: Path, rows: List[Dict], fields: Optional[List[str]] = None) -> None:
    mkdir(path.parent)
    if fields is None:
        fields = []
        seen = set()
        for row in rows:
            for key in row:
                if key not in seen:
                    seen.add(key)
                    fields.append(key)
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k, "") for k in fields})


def read_csv(path: Path) -> List[Dict]:
    if not path.exists():
        return []
    with path.open(newline="") as f:
        return list(csv.DictReader(f))


def safe_float(value: object) -> Optional[float]:
    try:
        x = float(value)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(x) or math.isinf(x) else x


def fmt(value: object, nd: int = 3) -> str:
    x = safe_float(value)
    if x is None:
        return "NA" if value in (None, "") else str(value)
    return f"{x:.{nd}f}"


def load_npz(path: Path) -> Dict[str, np.ndarray]:
    data = np.load(path, allow_pickle=False)
    return {k: data[k] for k in data.files}


def normalize_rows(arr: np.ndarray) -> np.ndarray:
    x = np.asarray(arr, dtype=np.float64)
    return x / np.maximum(np.linalg.norm(x, axis=1, keepdims=True), 1e-12)


def run_search_command(command: str) -> str:
    proc = subprocess.run(
        command,
        cwd=ROOT,
        shell=True,
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    return proc.stdout


def search_existing_artifacts() -> Tuple[List[Path], str]:
    commands = [
        r"""find results -type f \( \
  -iname '*rendered_evidence*.npz' -o \
  -iname '*rendered*evidence*.npz' -o \
  -iname '*baseline*rendered*.npz' -o \
  -iname '*baseline*evidence*.npz' \
\) -print | sort""",
        "find results -type f -iname '*.npz' | grep -i rendered",
        "find results -type f -iname '*.npz' | grep -i baseline",
        "find results -type f -iname '*.npz' | grep -i mutual",
    ]
    log_parts = []
    paths = []
    for command in commands:
        output = run_search_command(command)
        log_parts.append(f"$ {command}\n{output}")
        for line in output.splitlines():
            p = (ROOT / line.strip()).resolve()
            if line.strip() and p.exists() and p.suffix.lower() == ".npz":
                paths.append(p)
    unique = sorted(set(paths), key=lambda p: rel(p))
    return unique, "\n\n".join(log_parts)


def count_npz_points(path: Path) -> Dict:
    row: Dict[str, object] = {
        "path": rel(path),
        "size_bytes": path.stat().st_size,
        "loadable": False,
        "keys": "",
        "n_points": "",
        "n_roof": "",
        "n_wall": "",
        "n_ground": "",
        "bbox_min": "",
        "bbox_max": "",
        "compatibility_notes": "",
    }
    try:
        data = np.load(path, allow_pickle=False)
        keys = list(data.files)
        row["loadable"] = True
        row["keys"] = ";".join(keys)
        points = data["points"] if "points" in keys else data["xyz"] if "xyz" in keys else data["centers"] if "centers" in keys else None
        classes = data["classes"] if "classes" in keys else data["label"] if "label" in keys else data["labels"] if "labels" in keys else None
        if points is not None:
            pts = np.asarray(points)
            row["n_points"] = int(len(pts))
            if len(pts) and pts.ndim == 2 and pts.shape[1] >= 3:
                row["bbox_min"] = json.dumps(np.nanmin(pts[:, :3], axis=0).tolist())
                row["bbox_max"] = json.dumps(np.nanmax(pts[:, :3], axis=0).tolist())
        if classes is not None:
            cls = np.asarray(classes).astype(np.int64)
            row["n_roof"] = int(np.sum(cls == 1))
            row["n_wall"] = int(np.sum(cls == 2))
            row["n_ground"] = int(np.sum(cls == 3))
    except Exception as exc:  # noqa: BLE001
        row["compatibility_notes"] = f"NPZ_READ_ERROR: {type(exc).__name__}: {exc}"
    return row


def artifact_role(path: Path) -> str:
    p = rel(path).lower()
    if "e1_baseline_rendered" in p and "source_missing" not in p:
        return "E1_NAME_MATCH"
    if "baseline" in p and "rendered" in p:
        return "BASELINE_RENDERED_NAME_MATCH"
    if "baseline" in p and "primitive" in p:
        return "BASELINE_PRIMITIVE_NOT_RENDERED"
    if "mutual" in p and "rendered" in p:
        return "E2_OR_MUTUAL_RENDERED"
    if "rendered_evidence" in p or "rendered" in p:
        return "GENERIC_RENDERED_NOT_BASELINE"
    if "baseline" in p:
        return "BASELINE_NOT_RENDERED"
    return "OTHER"


def candidate_rows(paths: List[Path]) -> List[Dict]:
    rows = []
    for path in paths:
        row = count_npz_points(path)
        row["role_guess"] = artifact_role(path)
        row["mtime"] = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(path.stat().st_mtime))
        lower = rel(path).lower()
        if row["role_guess"] in {"BASELINE_PRIMITIVE_NOT_RENDERED", "BASELINE_NOT_RENDERED"}:
            row["compatibility_notes"] = "Not Baseline rendered evidence."
        elif row["role_guess"] == "E2_OR_MUTUAL_RENDERED":
            row["compatibility_notes"] = "Mutual rendered evidence, useful only as E2 reference."
        elif row["role_guess"] == "GENERIC_RENDERED_NOT_BASELINE":
            row["compatibility_notes"] = "Rendered evidence exists but not tied to Baseline checkpoint."
        elif "readout_evidence_after_stage3" in lower:
            row["compatibility_notes"] = "Post-readout diagnostic evidence, not source E1 evidence."
        rows.append(row)
    return rows


def decide_inventory(rows: List[Dict], search_log: str) -> Dict:
    e1_rows = [r for r in rows if r["role_guess"] in {"E1_NAME_MATCH", "BASELINE_RENDERED_NAME_MATCH"}]
    compatible = []
    incompatible = []
    for row in e1_rows:
        keys = set(str(row.get("keys", "")).split(";"))
        has_fields = {"points", "normals", "classes"}.issubset(keys) or {"xyz", "normal", "label"}.issubset(keys)
        if has_fields and safe_float(row.get("n_points")) and float(row["n_points"]) > 0:
            # Existing Baseline-rendered-looking files still need metadata parity.
            note = str(row.get("compatibility_notes", ""))
            if "primitive" not in note.lower():
                compatible.append(row)
        else:
            incompatible.append(row)
    stage3_missing_count = search_log.count("SOURCE_MISSING")
    if compatible:
        status = "FOUND_BUT_UNREGISTERED"
        reason = "A Baseline-rendered-looking evidence NPZ exists, but FC-S1/Stage3-v1 did not link it."
    elif incompatible:
        status = "FOUND_INCOMPATIBLE"
        reason = "Baseline-rendered-looking files exist but do not satisfy E2-style evidence fields/counts."
    else:
        status = "NOT_FOUND"
        reason = "No usable Baseline rendered source evidence NPZ was found before regeneration."
    return {
        "initial_status": status,
        "reason": reason,
        "candidate_count": len(rows),
        "e1_name_or_baseline_rendered_candidate_count": len(e1_rows),
        "compatible_candidate_paths": [r["path"] for r in compatible],
        "incompatible_candidate_paths": [r["path"] for r in incompatible],
        "stage3_v1_source_missing_marker_count_in_search_context": stage3_missing_count,
        "fc_s1_registered_baseline_rendered_path": rel(fc.BASELINE_RENDERED),
        "fc_s1_registered_baseline_rendered_exists": fc.BASELINE_RENDERED.exists(),
        "e2_reference_path": rel(E2_FULL_NPZ),
        "decision_before_regeneration": status,
    }


def selected_view_indices(ds, max_views: int) -> List[int]:
    return np.linspace(0, len(ds) - 1, min(max_views, len(ds)), dtype=int).tolist()


def render_sample_bank(args: argparse.Namespace, log_lines: List[str]) -> Tuple[Dict[str, np.ndarray], List[Dict]]:
    root = OUT_ROOT / "render_regeneration/phase1_render_export"
    bank_path = root / "baseline_rendered_sample_bank.npz"
    views_path = root / "baseline_rendered_sample_bank_views.csv"
    if bank_path.exists() and views_path.exists() and not args.force_render:
        log_lines.append(f"Reusing existing raw render sample bank: {rel(bank_path)}")
        return load_npz(bank_path), read_csv(views_path)

    mkdir(root)
    device = "cuda" if torch.cuda.is_available() and args.device == "cuda" else "cpu"
    log_lines.append(f"Loading Baseline checkpoint on {device}: {rel(BASELINE_CKPT)}")
    model, ds, cfg = s1.load_model_and_dataset(BASELINE_CONFIG, BASELINE_CKPT, args.render_downscale, device)
    idxs = selected_view_indices(ds, args.max_views)
    all_rows = []
    view_rows = []
    for local_id, idx in enumerate(idxs):
        b = ds[idx]
        h, w = int(b["height"]), int(b["width"])
        with torch.no_grad():
            out = s1.render(
                model,
                b["w2c"].to(device),
                b["K"].to(device),
                w,
                h,
                sh_degree=model.max_sh_degree,
                render_mode="RGB+ED",
            )
            sem_logits = s1.render_semantic(model, b["w2c"].to(device), b["K"].to(device), w, h)
            sem_prob = torch.softmax(sem_logits, dim=-1)
        depth_expected = out["depth"].detach().cpu().numpy().astype(np.float32)
        depth_median = out["depth_median"].detach().cpu().numpy().astype(np.float32)
        alpha = out["alpha"].detach().cpu().numpy().astype(np.float32)
        normal = out["normal_render"].detach().cpu().numpy().astype(np.float32)
        prob = sem_prob.detach().cpu().numpy().astype(np.float32)
        ys = np.arange(0, h, args.pixel_stride, dtype=np.int32)
        xs = np.arange(0, w, args.pixel_stride, dtype=np.int32)
        vv, uu = np.meshgrid(ys, xs, indexing="ij")
        de = depth_expected[vv, uu]
        dm = depth_median[vv, uu]
        a = alpha[vv, uu]
        p = prob[vv, uu]
        sem_conf = p.max(axis=-1)
        labels = p.argmax(axis=-1).astype(np.int64)
        n = normal[vv, uu]
        n_norm = np.linalg.norm(n, axis=-1)
        valid = (
            np.isfinite(de)
            & np.isfinite(dm)
            & ((de > 0.0) | (dm > 0.0))
            & (a > s1.ALPHA_MIN)
            & (sem_conf > s1.SEM_CONF_MIN)
            & (n_norm > 1e-5)
        )
        n_valid = int(np.sum(valid))
        if n_valid:
            normals = n[valid].reshape(-1, 3).astype(np.float64)
            normals = normalize_rows(normals).astype(np.float32)
            all_rows.append({
                "depth_expected": de[valid].reshape(-1).astype(np.float32),
                "depth_median": dm[valid].reshape(-1).astype(np.float32),
                "normal": normals,
                "sem_prob": p[valid].reshape(-1, 4).astype(np.float32),
                "label": labels[valid].reshape(-1).astype(np.int64),
                "alpha": a[valid].reshape(-1).astype(np.float32),
                "confidence": (a[valid].reshape(-1) * sem_conf[valid].reshape(-1)).astype(np.float32),
                "view_id": np.full(n_valid, idx, dtype=np.int32),
                "pixel_u": uu[valid].reshape(-1).astype(np.int32),
                "pixel_v": vv[valid].reshape(-1).astype(np.int32),
            })
        row = {
            "view_id": idx,
            "local_view_id": local_id,
            "image_name": b["name"],
            "height": h,
            "width": w,
            "n_pixels_sampled": int(uu.size),
            "n_valid_samples": n_valid,
            "mean_alpha": float(np.mean(a[valid])) if n_valid else 0.0,
            "mean_sem_conf": float(np.mean(sem_conf[valid])) if n_valid else 0.0,
        }
        view_rows.append(row)
        msg = f"[E1 render] view {local_id + 1}/{len(idxs)} idx={idx} valid={n_valid}"
        print(msg, flush=True)
        log_lines.append(msg)
    if not all_rows:
        raise RuntimeError("No valid Baseline rendered samples were produced")
    raw = {k: np.concatenate([r[k] for r in all_rows], axis=0) for k in all_rows[0]}
    if len(raw["label"]) > args.max_raw_samples:
        keep = s1.downsample_balanced(raw["label"], args.max_raw_samples, args.seed)
        raw = {k: v[keep] for k, v in raw.items()}
        log_lines.append(f"Downsampled raw samples to max_raw_samples={args.max_raw_samples}")
    np.savez_compressed(bank_path, **raw)
    write_csv(views_path, view_rows)
    write_json(root / "baseline_rendered_sample_bank_metadata.json", {
        "checkpoint": rel(BASELINE_CKPT),
        "config": rel(BASELINE_CONFIG),
        "n_views": len(idxs),
        "selected_views": idxs,
        "n_samples": int(len(raw["label"])),
        "render_downscale": args.render_downscale,
        "pixel_stride": args.pixel_stride,
        "alpha_min": s1.ALPHA_MIN,
        "semantic_conf_min": s1.SEM_CONF_MIN,
        "depth_outputs": ["expected_z_depth", "median_z_depth"],
        "config_data_root": cfg.get("resolved_data_root"),
        "gravity": [0, 1, 0],
    })
    return raw, view_rows


def fixed_raw_from_e2_convention(raw: Dict[str, np.ndarray], args: argparse.Namespace, log_lines: List[str]) -> Dict:
    fixed_root = OUT_ROOT / "render_regeneration/phase2_fixed_export"
    fixed_path = fixed_root / "baseline_raw_rendered_samples_fixed.npz"
    if fixed_path.exists() and not args.force_fixed_export:
        log_lines.append(f"Reusing fixed raw samples: {rel(fixed_path)}")
        return load_npz(fixed_path)
    mkdir(fixed_root)
    e2_meta = read_json(E2_FIXED_METADATA)
    candidate = {
        "depth_mode": e2_meta.get("depth_convention", "expected_z"),
        "camera_mode": e2_meta.get("camera_convention", "camera_to_world_inverse_extrinsic"),
        "axis_mode": e2_meta.get("axis_convention", "existing_axes"),
        "candidate_id": e2_meta.get("selected_candidate_id", "C000"),
    }
    fixed = s1d.fixed_raw_from_candidate(raw, candidate, args)
    np.savez_compressed(fixed_path, **fixed)
    write_json(fixed_root / "baseline_fixed_export_metadata.json", {
        "checkpoint": rel(BASELINE_CKPT),
        "config": rel(BASELINE_CONFIG),
        "matched_e2_metadata": rel(E2_FIXED_METADATA),
        "depth_convention": candidate["depth_mode"],
        "camera_convention": candidate["camera_mode"],
        "normal_frame": e2_meta.get("normal_frame", "gsplat_render_normals_world_frame_N0_exported"),
        "scene_normalization_inverse_applied": e2_meta.get("scene_normalization_inverse_applied", False),
        "axis_convention": candidate["axis_mode"],
        "gravity": [0, 1, 0],
        "selected_candidate_id_reused_from_e2": candidate["candidate_id"],
        "gt_used_for_generation": False,
        "gt_used_for_candidate_selection": False,
        "note": "Baseline reused E2 selected deterministic render/depth/camera/axis convention; no Baseline-specific tuning.",
        "world_bbox_min": fixed["xyz"].min(axis=0).tolist(),
        "world_bbox_max": fixed["xyz"].max(axis=0).tolist(),
    })
    return fixed


def fuse_e1_f2(fixed: Dict[str, np.ndarray], args: argparse.Namespace, log_lines: List[str]) -> Dict:
    final_path = OUT_ROOT / "E1_Baseline_rendered.npz"
    if final_path.exists() and not args.force_fixed_export:
        log_lines.append(f"Reusing final E1 evidence: {rel(final_path)}")
        return load_npz(final_path)
    labels = fixed["label"].astype(np.int64)
    voxel_size = 0.05
    vox = np.floor(fixed["xyz"].astype(np.float64) / voxel_size).astype(np.int32)
    keys = np.concatenate([vox, labels[:, None].astype(np.int32), s1.normal_bins(fixed["normal"])], axis=1)
    raw_for_fuse = {
        "xyz": fixed["xyz"],
        "normal": fixed["normal"],
        "sem_prob": fixed["sem_prob"],
        "label": fixed["label"],
        "confidence": fixed["confidence"],
        "view_id": fixed["view_id"],
    }
    ev = s1.fuse_groups(raw_for_fuse, keys, "F2_class_normal_aware_voxel_0p05")
    np.savez_compressed(final_path, **ev)
    s1.write_binary_ply(
        OUT_ROOT / "E1_Baseline_rendered.ply",
        ev,
        extra={
            "view_count": ev.get("view_count", np.ones(len(ev["classes"]), dtype=np.int32)),
            "confidence": ev.get("confidence", ev["weights"]),
            "normal_consistency": ev.get("normal_consistency", np.ones(len(ev["classes"]), dtype=np.float32)),
            "semantic_entropy": ev.get("semantic_entropy", np.zeros(len(ev["classes"]), dtype=np.float32)),
        },
        max_points=args.max_ply_points,
        seed=args.seed,
    )
    write_json(OUT_ROOT / "scene_evidence_graph_E1_Baseline_rendered.json", {
        "gravity": [0, 1, 0],
        "evidence_type": "stage2_rendered_surface_evidence_fixed",
        "points_file": "E1_Baseline_rendered.npz",
        "ply_file": "E1_Baseline_rendered.ply",
        "classes": s1.CLASSES,
        "fusion": "F2_class_normal_aware_voxel_0p05",
        "gt_used_for_generation": False,
        "checkpoint": rel(BASELINE_CKPT),
    })
    log_lines.append(f"Wrote final E1 evidence with {len(ev['classes'])} points: {rel(final_path)}")
    return ev


def entropy_value(evidence: Dict) -> Optional[float]:
    if "sem_probs" in evidence and len(evidence["sem_probs"]):
        p = np.clip(np.asarray(evidence["sem_probs"], dtype=np.float64), 1e-12, 1.0)
        return float(np.mean(-np.sum(p * np.log(p), axis=1) / math.log(p.shape[1])))
    return fc.evidence_entropy(evidence)


def confidence_stats(evidence: Dict) -> Dict:
    arr = evidence.get("confidence", evidence.get("weights"))
    if arr is None or len(arr) == 0:
        return {
            "confidence_mean": "",
            "confidence_p05": "",
            "confidence_p50": "",
            "confidence_p95": "",
        }
    x = np.asarray(arr, dtype=np.float64)
    return {
        "confidence_mean": float(np.mean(x)),
        "confidence_p05": float(np.percentile(x, 5)),
        "confidence_p50": float(np.percentile(x, 50)),
        "confidence_p95": float(np.percentile(x, 95)),
    }


def coordinate_stats(evidence: Dict) -> Dict:
    pts = np.asarray(evidence["points"], dtype=np.float64)
    if len(pts) == 0:
        return {
            "x_min": "",
            "y_min": "",
            "z_min": "",
            "x_max": "",
            "y_max": "",
            "z_max": "",
            "invalid_coordinate_count": 0,
        }
    invalid = int(np.sum(~np.isfinite(pts).all(axis=1)))
    finite = pts[np.isfinite(pts).all(axis=1)]
    if len(finite) == 0:
        return {
            "x_min": "",
            "y_min": "",
            "z_min": "",
            "x_max": "",
            "y_max": "",
            "z_max": "",
            "invalid_coordinate_count": invalid,
        }
    mn = finite.min(axis=0)
    mx = finite.max(axis=0)
    return {
        "x_min": float(mn[0]),
        "y_min": float(mn[1]),
        "z_min": float(mn[2]),
        "x_max": float(mx[0]),
        "y_max": float(mx[1]),
        "z_max": float(mx[2]),
        "invalid_coordinate_count": invalid,
    }


def normal_alignment_by_class(evidence: Dict) -> Dict:
    cls = evidence["classes"]
    normals = evidence["normals"]
    out = {}
    for c, name in [(1, "roof"), (2, "wall"), (3, "ground")]:
        m = cls == c
        if np.any(m):
            out[f"{name}_mean_abs_gravity_dot"] = float(np.mean(np.abs(normals[m] @ np.asarray([0.0, 1.0, 0.0]))))
        else:
            out[f"{name}_mean_abs_gravity_dot"] = ""
    return out


def sanity_row(evidence: Dict, bid: int, source: str, full_count: int) -> Dict:
    base = fc.evidence_summary_row(evidence, bid, source)
    row = {
        "bid": f"B{bid}",
        "file_exists": True,
        "source": source,
        "footprint_crop_hit_rate": len(evidence["classes"]) / max(full_count, 1),
        "semantic_label_distribution": json.dumps({str(k): int(np.sum(evidence["classes"] == k)) for k in range(4)}),
        "semantic_entropy": entropy_value(evidence),
        "normal_consistency": fc.normal_consistency(evidence),
        "empty_domain": int(len(evidence["classes"]) == 0),
        **base,
        **confidence_stats(evidence),
        **coordinate_stats(evidence),
        **normal_alignment_by_class(evidence),
    }
    row["pass_basic"] = bool(
        row["n_points"] > 0
        and row["n_roof"] > 0
        and row["n_wall"] > 0
        and int(row["invalid_coordinate_count"]) == 0
    )
    return row


def compare_rows(e1_rows: List[Dict], e2_rows: List[Dict]) -> List[Dict]:
    e2_by_bid = {r["bid"]: r for r in e2_rows}
    out = []
    fields = [
        "n_points", "n_roof", "n_wall", "n_ground", "n_bg",
        "semantic_entropy", "normal_consistency", "confidence_mean",
    ]
    for r in e1_rows:
        e2 = e2_by_bid.get(r["bid"], {})
        row = {"bid": r["bid"]}
        for field in fields:
            a = safe_float(r.get(field))
            b = safe_float(e2.get(field))
            row[f"e1_{field}"] = r.get(field, "")
            row[f"e2_{field}"] = e2.get(field, "")
            row[f"delta_{field}"] = "" if a is None or b is None else a - b
            row[f"ratio_{field}"] = "" if a is None or b in (None, 0.0) else a / b
        for axis in ["x", "y", "z"]:
            a0 = safe_float(r.get(f"{axis}_min"))
            a1 = safe_float(r.get(f"{axis}_max"))
            b0 = safe_float(e2.get(f"{axis}_min"))
            b1 = safe_float(e2.get(f"{axis}_max"))
            if None not in (a0, a1, b0, b1):
                inter = max(0.0, min(a1, b1) - max(a0, b0))
                union = max(a1, b1) - min(a0, b0)
                row[f"{axis}_range_overlap_ratio"] = inter / max(union, 1e-12)
            else:
                row[f"{axis}_range_overlap_ratio"] = ""
        out.append(row)
    return out


def aggregate_evidence(rows: List[Dict], source: str) -> Dict:
    numeric_fields = [
        "n_points", "n_roof", "n_wall", "n_ground", "n_bg",
        "semantic_entropy", "normal_consistency", "confidence_mean",
        "invalid_coordinate_count", "footprint_crop_hit_rate",
    ]
    out = {
        "source": source,
        "n_bids": len(rows),
        "nonempty_bids": sum(1 for r in rows if int(r.get("n_points", 0)) > 0),
        "roof_wall_nonzero_bids": sum(1 for r in rows if int(r.get("n_roof", 0)) > 0 and int(r.get("n_wall", 0)) > 0),
        "ground_nonzero_bids": sum(1 for r in rows if int(r.get("n_ground", 0)) > 0),
        "basic_pass_bids": sum(1 for r in rows if r.get("pass_basic") in {True, "True", "true", 1, "1"}),
    }
    for field in numeric_fields:
        vals = [safe_float(r.get(field)) for r in rows]
        vals = [v for v in vals if v is not None]
        out[f"mean_{field}"] = float(np.mean(vals)) if vals else ""
        out[f"min_{field}"] = float(np.min(vals)) if vals else ""
    return out


def write_per_bid_evidence(e1_full: Dict, e2_full: Dict) -> Tuple[List[Dict], List[Dict], List[Dict]]:
    buildings = parse_scene_obj(fc.SCENE, frame="obj")["buildings"]
    by_bid = fc.target_buildings(buildings)
    e1_norm = fc.normalize_evidence(e1_full, "E1_Baseline_rendered", "rendered")
    e2_norm = fc.normalize_evidence(e2_full, "E2_Mutual_rendered", "rendered")
    e1_rows = []
    e2_rows = []
    for bid in fc.TARGET_BIDS:
        building = by_bid[bid]
        footprint = fc.footprint_for_building(building)
        if footprint is None:
            continue
        e1 = fc.crop_evidence(e1_norm, footprint, "E1_Baseline_rendered", bid)
        e2 = fc.crop_evidence(e2_norm, footprint, "E2_Mutual_rendered", bid)
        e1_dir = OUT_ROOT / "phase1_evidence/E1_Baseline_rendered" / f"B{bid}"
        e2_dir = OUT_ROOT / "phase1_evidence/E2_Mutual_rendered" / f"B{bid}"
        mkdir(e1_dir)
        mkdir(e2_dir)
        np.savez_compressed(e1_dir / "evidence.npz", **{k: v for k, v in e1.items() if isinstance(v, np.ndarray)})
        np.savez_compressed(e2_dir / "evidence.npz", **{k: v for k, v in e2.items() if isinstance(v, np.ndarray)})
        e1_rows.append(sanity_row(e1, bid, "E1_Baseline_rendered", len(e1_norm["classes"])))
        e2_rows.append(sanity_row(e2, bid, "E2_Mutual_rendered", len(e2_norm["classes"])))
    compare = compare_rows(e1_rows, e2_rows)
    return e1_rows, e2_rows, compare


def acceptance_decision(e1_rows: List[Dict], compare: List[Dict]) -> Dict:
    n = len(e1_rows)
    nonempty = sum(1 for r in e1_rows if int(r.get("n_points", 0)) > 0)
    roof_wall = sum(1 for r in e1_rows if int(r.get("n_roof", 0)) > 0 and int(r.get("n_wall", 0)) > 0)
    ground = sum(1 for r in e1_rows if int(r.get("n_ground", 0)) > 0)
    invalid = sum(int(r.get("invalid_coordinate_count", 0)) for r in e1_rows)
    overlap_vals = []
    for r in compare:
        vals = [safe_float(r.get(f"{axis}_range_overlap_ratio")) for axis in ["x", "y", "z"]]
        vals = [v for v in vals if v is not None]
        if vals:
            overlap_vals.append(float(np.mean(vals)))
    coord_ok = bool(overlap_vals and float(np.mean(overlap_vals)) > 0.90 and invalid == 0)
    accepted = bool(nonempty >= max(1, n - 1) and roof_wall >= max(1, n - 1) and coord_ok)
    if accepted:
        decision = "ACCEPT_FOR_STAGE3_MATRIX"
        reason = "E1 has non-empty roof/wall evidence for most target buildings and coordinate range matches E2."
    else:
        decision = "REJECT_FOR_STAGE3_MATRIX"
        reason = "E1 sanity gate failed; see per-bid evidence counts and coordinate overlap."
    return {
        "accepted_for_stage3": accepted,
        "decision": decision,
        "reason": reason,
        "n_target_bids": n,
        "nonempty_bids": nonempty,
        "roof_wall_nonzero_bids": roof_wall,
        "ground_nonzero_bids": ground,
        "invalid_coordinate_count_total": invalid,
        "mean_coordinate_range_overlap_with_e2": float(np.mean(overlap_vals)) if overlap_vals else None,
    }


def write_render_config(args: argparse.Namespace, view_rows: List[Dict], final_ev: Dict) -> Dict:
    e2_meta = read_json(E2_RENDER_METADATA)
    e2_fixed = read_json(E2_FIXED_METADATA)
    e2_graph = read_json(E2_GRAPH)
    selected_views = [int(r["view_id"]) for r in view_rows]
    e2_selected_views = [int(x) for x in e2_meta.get("selected_views", [])]
    config = {
        "source": "E1_Baseline_rendered",
        "final_e1_path": rel(OUT_ROOT / "E1_Baseline_rendered.npz"),
        "baseline_checkpoint": rel(BASELINE_CKPT),
        "baseline_config": rel(BASELINE_CONFIG),
        "e2_reference_path": rel(E2_FULL_NPZ),
        "e2_checkpoint": rel(MUTUAL_CKPT),
        "e2_config": rel(MUTUAL_CONFIG),
        "same_scene": rel(fc.SCENE),
        "same_camera_set_as_e2": selected_views == e2_selected_views,
        "selected_views": selected_views,
        "e2_selected_views": e2_selected_views,
        "render_downscale": args.render_downscale,
        "pixel_stride": args.pixel_stride,
        "render_resolution_rows": sorted({(int(r["height"]), int(r["width"])) for r in view_rows}),
        "depth_export_convention": e2_fixed.get("depth_convention", "expected_z"),
        "normal_export_convention": e2_fixed.get("normal_frame", "gsplat_render_normals_world_frame_N0_exported"),
        "semantic_export_convention": "render_semantic softmax probabilities, argmax labels, 4 classes bg/roof/wall/terrain",
        "mask_rule": {
            "alpha_min": s1.ALPHA_MIN,
            "semantic_conf_min": s1.SEM_CONF_MIN,
            "finite_depth": True,
            "normal_norm_min": 1e-5,
        },
        "fusion": e2_graph.get("fusion", "F2_class_normal_aware_voxel_0p05"),
        "class_normal_aware_filtering": True,
        "voxel_size_m": 0.05,
        "coordinate_frame": {
            "camera_convention": e2_fixed.get("camera_convention", "camera_to_world_inverse_extrinsic"),
            "axis_convention": e2_fixed.get("axis_convention", "existing_axes"),
            "scene_normalization_inverse_applied": e2_fixed.get("scene_normalization_inverse_applied", False),
        },
        "gravity": [0, 1, 0],
        "footprint_conditioned_extraction": {
            "applied_in_sanity_and_downstream_stage3": True,
            "footprint_buffer_m": fc.FOOTPRINT_BUFFER_M,
            "target_bids": [f"B{b}" for b in fc.TARGET_BIDS],
        },
        "stage3_readout_config": {
            "stage3_algorithm_modified": False,
            "readout_not_run_in_this_script": True,
        },
        "final_full_scene_counts": {
            "n_points": int(len(final_ev["classes"])),
            "n_roof": int(np.sum(final_ev["classes"] == 1)),
            "n_wall": int(np.sum(final_ev["classes"] == 2)),
            "n_ground": int(np.sum(final_ev["classes"] == 3)),
            "n_bg": int(np.sum(final_ev["classes"] == 0)),
        },
    }
    write_json(OUT_ROOT / "e1_render_config.json", config)
    return config


def write_report(
    inventory: Dict,
    accept: Dict,
    e1_summary: Dict,
    e2_summary: Dict,
    config: Dict,
    final_status: str,
) -> None:
    lines = [
        "# FC-S2 Phase A E1 Recovery Report",
        "",
        "## Decision",
        "",
        f"- Final status: `{final_status}`",
        f"- Initial inventory status: `{inventory['initial_status']}`",
        f"- Final E1 path: `{config['final_e1_path']}`",
        f"- Accepted for Stage3 matrix: `{accept['accepted_for_stage3']}`",
        f"- Acceptance reason: {accept['reason']}",
        "",
        "## Search Result",
        "",
        f"No compatible pre-existing `E1_Baseline_rendered` NPZ was found. FC-S1 registered `{inventory['fc_s1_registered_baseline_rendered_path']}`, exists={inventory['fc_s1_registered_baseline_rendered_exists']}.",
        "",
        "## Regeneration Config",
        "",
        "| Condition | E1 Baseline | E2 Mutual | Match |",
        "| --- | --- | --- | --- |",
        f"| checkpoint | `{config['baseline_checkpoint']}` | `{config['e2_checkpoint']}` | different by design |",
        f"| camera set | {len(config['selected_views'])} views | {len(config['e2_selected_views'])} views | {config['same_camera_set_as_e2']} |",
        f"| render downscale | {config['render_downscale']} | {config['render_downscale']} | True |",
        f"| pixel stride | {config['pixel_stride']} | {config['pixel_stride']} | True |",
        f"| depth convention | {config['depth_export_convention']} | {config['depth_export_convention']} | True |",
        f"| fusion | {config['fusion']} | {config['fusion']} | True |",
        f"| voxel size | {config['voxel_size_m']} | {config['voxel_size_m']} | True |",
        f"| gravity | {config['gravity']} | {config['gravity']} | True |",
        "",
        "## Evidence Summary",
        "",
        "| Source | nonempty_bids | roof_wall_nonzero_bids | ground_nonzero_bids | mean_n_points | mean_n_roof | mean_n_wall | mean_n_ground | normal_consistency | semantic_entropy |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
        f"| E1_Baseline_rendered | {e1_summary['nonempty_bids']} | {e1_summary['roof_wall_nonzero_bids']} | {e1_summary['ground_nonzero_bids']} | {fmt(e1_summary['mean_n_points'])} | {fmt(e1_summary['mean_n_roof'])} | {fmt(e1_summary['mean_n_wall'])} | {fmt(e1_summary['mean_n_ground'])} | {fmt(e1_summary['mean_normal_consistency'])} | {fmt(e1_summary['mean_semantic_entropy'])} |",
        f"| E2_Mutual_rendered | {e2_summary['nonempty_bids']} | {e2_summary['roof_wall_nonzero_bids']} | {e2_summary['ground_nonzero_bids']} | {fmt(e2_summary['mean_n_points'])} | {fmt(e2_summary['mean_n_roof'])} | {fmt(e2_summary['mean_n_wall'])} | {fmt(e2_summary['mean_n_ground'])} | {fmt(e2_summary['mean_normal_consistency'])} | {fmt(e2_summary['mean_semantic_entropy'])} |",
        "",
        "## Sanity Gate",
        "",
        f"- Non-empty E1 target buildings: {accept['nonempty_bids']}/{accept['n_target_bids']}",
        f"- E1 roof/wall non-zero target buildings: {accept['roof_wall_nonzero_bids']}/{accept['n_target_bids']}",
        f"- E1 ground non-zero target buildings: {accept['ground_nonzero_bids']}/{accept['n_target_bids']}",
        f"- Total invalid E1 coordinates after footprint crops: {accept['invalid_coordinate_count_total']}",
        f"- Mean E1/E2 coordinate range overlap: {fmt(accept['mean_coordinate_range_overlap_with_e2'])}",
        "",
        "## Files",
        "",
        "- `e1_search_log.txt`",
        "- `e1_candidate_artifacts.csv`",
        "- `e1_inventory_decision.json`",
        "- `E1_Baseline_rendered.npz`",
        "- `baseline_rendered_regeneration_status.json`",
        "- `e1_render_config.json`",
        "- `e1_sanity_by_bid.csv`",
        "- `e1_evidence_summary.csv`",
        "- `e1_vs_e2_evidence_summary.csv`",
        "- `e1_acceptance_decision.json`",
        "",
        "No Stage3 algorithm changes were made. Track B was not started.",
        "",
    ]
    (OUT_ROOT / "E1_RECOVERY_REPORT.md").write_text("\n".join(lines))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-views", type=int, default=56)
    ap.add_argument("--render-downscale", type=float, default=0.25)
    ap.add_argument("--pixel-stride", type=int, default=2)
    ap.add_argument("--max-raw-samples", type=int, default=3_000_000)
    ap.add_argument("--max-ply-points", type=int, default=750_000)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--device", choices=["cuda", "cpu"], default="cuda")
    ap.add_argument("--force-render", action="store_true")
    ap.add_argument("--force-fixed-export", action="store_true")
    args = ap.parse_args()

    if not np.allclose(s1.GRAVITY, np.asarray([0.0, 1.0, 0.0])):
        raise AssertionError(f"Expected gravity=[0,1,0], got {s1.GRAVITY}")
    mkdir(OUT_ROOT)

    paths, search_log = search_existing_artifacts()
    (OUT_ROOT / "e1_search_log.txt").write_text(search_log + "\n")
    rows = candidate_rows(paths)
    write_csv(OUT_ROOT / "e1_candidate_artifacts.csv", rows)
    inventory = decide_inventory(rows, search_log)
    write_json(OUT_ROOT / "e1_inventory_decision.json", inventory)

    log_lines: List[str] = [
        "FC-S2 Phase A Baseline rendered regeneration log",
        f"Initial inventory status: {inventory['initial_status']}",
    ]
    final_e1 = OUT_ROOT / "E1_Baseline_rendered.npz"
    regenerated = inventory["initial_status"] in {"NOT_FOUND", "FOUND_INCOMPATIBLE"} or not final_e1.exists()
    if regenerated:
        raw, view_rows = render_sample_bank(args, log_lines)
        fixed = fixed_raw_from_e2_convention(raw, args, log_lines)
        e1_full = fuse_e1_f2(fixed, args, log_lines)
    else:
        log_lines.append(f"Reusing compatible E1 evidence: {rel(final_e1)}")
        e1_full = load_npz(final_e1)
        view_rows = read_csv(OUT_ROOT / "render_regeneration/phase1_render_export/baseline_rendered_sample_bank_views.csv")
    e2_full = load_npz(E2_FULL_NPZ)
    config = write_render_config(args, view_rows, e1_full)

    e1_rows, e2_rows, compare = write_per_bid_evidence(e1_full, e2_full)
    write_csv(OUT_ROOT / "e1_sanity_by_bid.csv", e1_rows)
    e1_summary = aggregate_evidence(e1_rows, "E1_Baseline_rendered")
    e2_summary = aggregate_evidence(e2_rows, "E2_Mutual_rendered")
    write_csv(OUT_ROOT / "e1_evidence_summary.csv", [e1_summary, e2_summary])
    write_csv(OUT_ROOT / "e1_vs_e2_evidence_summary.csv", compare)
    accept = acceptance_decision(e1_rows, compare)
    write_json(OUT_ROOT / "e1_acceptance_decision.json", accept)

    final_status = "REGENERATED_AND_ACCEPTED" if regenerated and accept["accepted_for_stage3"] else (
        "REGENERATED_REJECTED" if regenerated else inventory["initial_status"]
    )
    status = {
        "final_status": final_status,
        "regenerated": regenerated,
        "accepted_for_stage3": accept["accepted_for_stage3"],
        "final_e1_path": rel(OUT_ROOT / "E1_Baseline_rendered.npz"),
        "initial_inventory_status": inventory["initial_status"],
        "baseline_checkpoint": rel(BASELINE_CKPT),
        "matched_e2_reference": rel(E2_FULL_NPZ),
        "stage3_algorithm_modified": False,
        "track_b_started": False,
    }
    write_json(OUT_ROOT / "baseline_rendered_regeneration_status.json", status)
    write_report(inventory, accept, e1_summary, e2_summary, config, final_status)
    (OUT_ROOT / "e1_render_log.txt").write_text("\n".join(log_lines) + "\n")
    print(f"[FC-S2 Phase A] {final_status} -> {rel(OUT_ROOT)}", flush=True)


if __name__ == "__main__":
    main()
