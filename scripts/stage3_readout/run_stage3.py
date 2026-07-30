"""Stage 3 runner for Phase 2 Step 2-2.

Pipeline: 2DGS checkpoint -> primitives -> per-building CityJSON -> val3dity.

Usage (inside container):
    python scripts/stage3_readout/run_stage3.py \
        --ckpt  results/phase2_ablation_citygml/<cond>/ckpt/final.pt \
        --scene results/phase2_synthesis/scene.obj \
        --out   results/phase2_ablation_citygml/<cond>/stage3 \
        [--use-gt-assignment]   # for debugging: use GT bboxes to assign prims to buildings

Outputs:
    out/primitives.npz                         all primitives (centers, normals, areas, sem_probs, labels)
    out/building_NN/building.city.json         Stage 3 CityJSON per building
    out/building_NN/lod2.ply                   LOD2 colored PLY (viz)
    out/building_NN/val3dity.json              val3dity output
    out/stage3_summary.json                    per-building pass/fail + metrics
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Dict, List

import numpy as np
import torch

# allow src.* imports
_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from src.stage2.model import GaussianModel2D, quat_to_rotmat  # noqa: E402
from src.stage2.grouping import group_primitives  # noqa: E402
from src.stage3.building_instance import process_building  # noqa: E402
from scripts.stage3_readout.obj_gt import parse_scene_obj  # noqa: E402


# Stage 2 grouping voxel size (must match training; src/stage2/grouping.py default)
_STAGE2_VOXEL_SIZE = 0.05
_STAGE2_N_DIRECTIONS = 12
_STAGE2_MIN_GROUP_SIZE = 5


def _load_model(ckpt_path: Path,
                emit_stage2_groups: bool = True) -> Dict[str, np.ndarray]:
    """Load checkpoint state_dict -> derived primitive arrays (cpu numpy).

    If emit_stage2_groups: also compute Stage 2 group assignment (the same
    voxel-hash grouping used during L_structure training) on the final
    primitives and add 'group_ids', 'rep_normals', 'rep_d' to the dict. This
    closes the C2 interface gap (RESEARCH_CONTEXT §15): Stage 3 receives the
    group structure Stage 2 was trained against, instead of re-clustering
    from scratch with a different algorithm.

    Stage 2's voxel_size/n_directions/min_group_size match training defaults.
    Result is deterministic given the ckpt — no randomness, no learning.
    """
    sd = torch.load(ckpt_path, map_location="cpu")["state_dict"]
    means = sd["means"].float()
    quats = sd["quats"].float()
    log_scales = sd["log_scales"].float()
    opacities = torch.sigmoid(sd["opacities_raw"]).float()
    sem_logits = sd["sem_logits"].float()

    R = quat_to_rotmat(quats)
    normals = R[..., :, 2]                       # (N,3) per CLAUDE.md
    scales = torch.exp(log_scales)               # (N,3)
    sU, sV = scales[..., 0], scales[..., 1]
    areas = (np.pi * sU * sV).float()            # ellipse area
    sem_probs = torch.softmax(sem_logits, dim=-1).float()
    labels = sem_probs.argmax(dim=-1)

    out = {
        "centers": means.numpy(),
        "normals": normals.numpy(),
        "scales": scales.numpy(),
        "areas": areas.numpy(),
        "opacities": opacities.numpy(),
        "sem_probs": sem_probs.numpy(),
        "labels": labels.numpy(),
    }

    if emit_stage2_groups:
        # group_primitives runs in torch.no_grad. We use cpu — the only cost is
        # one global voxel hash on ~10^6 primitives, ~1-2 s.
        gid_t, rep_n_t, rep_d_t = group_primitives(
            centers=means, normals=normals, sem_logits=sem_logits, scales=scales,
            voxel_size=_STAGE2_VOXEL_SIZE, n_directions=_STAGE2_N_DIRECTIONS,
            min_group_size=_STAGE2_MIN_GROUP_SIZE, exclude_bg=True,
        )
        out["group_ids"] = gid_t.numpy()        # (N,) int64, -1 = ungrouped
        out["rep_normals"] = rep_n_t.numpy()    # (G, 3)
        out["rep_d"] = rep_d_t.numpy()          # (G,) — Stage 2 convention
        n_grouped = int((gid_t >= 0).sum())
        n_groups = int(rep_n_t.shape[0])
        print(f"[stage3] Stage 2 grouping: {n_groups} groups, "
              f"{n_grouped}/{means.shape[0]} primitives grouped")

    return out


def _assign_primitives_to_buildings(
    prims: Dict[str, np.ndarray],
    gt: Dict,
    pad: float = 2.0,
    opacity_thresh: float = 0.05,
) -> Dict[int, np.ndarray]:
    """Assign each primitive to the building whose padded bbox contains it,
    falling back to the nearest building center. Primitives with opacity below
    `opacity_thresh` are dropped.

    Returns {building_id: prim_indices_ndarray}.
    """
    centers = prims["centers"]
    opa = prims["opacities"]
    keep_mask = opa >= opacity_thresh

    bboxes = []
    bcenters = []
    ids = []
    for b in gt["buildings"]:
        vs = np.concatenate([f["vertices"] for f in b["faces"]], axis=0)
        mn = vs.min(axis=0) - pad
        mx = vs.max(axis=0) + pad
        bboxes.append((mn, mx))
        bcenters.append(vs.mean(axis=0))
        ids.append(b["building_id"])
    bcenters = np.asarray(bcenters)

    assignment: Dict[int, List[int]] = {bid: [] for bid in ids}
    for i in np.where(keep_mask)[0]:
        c = centers[i]
        # first pass: bbox containment
        placed = False
        for bid, (mn, mx) in zip(ids, bboxes):
            if np.all(c >= mn) and np.all(c <= mx):
                assignment[bid].append(int(i))
                placed = True
                break
        if not placed:
            # fallback: nearest building center (within 2x spacing to avoid scene edge)
            d = np.linalg.norm(bcenters - c[None, :], axis=1)
            j = int(np.argmin(d))
            if d[j] < 12.0:  # spacing=18m, 2/3 * spacing
                assignment[ids[j]].append(int(i))
    return {bid: np.array(v, dtype=np.int64) for bid, v in assignment.items()}


def _build_primitives_dict(prims: Dict[str, np.ndarray]) -> Dict[str, np.ndarray]:
    """Package for src.stage3.building_instance.process_building."""
    out = {
        "centers": prims["centers"],
        "normals": prims["normals"],
        "areas": prims["areas"],
        "semantic_probs": prims["sem_probs"],
    }
    # Pass Stage 2 group info if present (Track 1, RESEARCH_CONTEXT §15).
    for k in ("group_ids", "rep_normals", "rep_d"):
        if k in prims:
            out[k] = prims[k]
    return out


def _run_val3dity(cj_path: Path, report_path: Path) -> Dict:
    """Run val3dity on CityJSON; return parsed report JSON (or error dict)."""
    try:
        proc = subprocess.run(
            ["val3dity", "--report", str(report_path), str(cj_path)],
            capture_output=True, text=True, timeout=180,
        )
    except FileNotFoundError:
        return {"error": "val3dity_not_found"}
    except subprocess.TimeoutExpired:
        return {"error": "timeout"}

    out = {
        "returncode": proc.returncode,
        "stdout_tail": proc.stdout[-500:],
        "stderr_tail": proc.stderr[-500:],
    }
    if report_path.exists():
        try:
            out["report"] = json.loads(report_path.read_text())
        except Exception as e:
            out["report_parse_error"] = str(e)
    return out


def _summarize_val3dity(v3d_result: Dict) -> Dict:
    """Extract valid flag + error codes from val3dity report."""
    rep = v3d_result.get("report", {})
    # val3dity 2.x report JSON structure
    features = rep.get("features", [])
    valid = False
    errors: List[str] = []
    if features:
        feat = features[0]
        valid = feat.get("validity", False)
        for err in feat.get("errors", []):
            code = err.get("code") or err.get("error_code")
            if code is not None:
                errors.append(str(code))
        # include primitive-level errors too
        for prim in feat.get("primitives", []):
            for err in prim.get("errors", []):
                code = err.get("code") or err.get("error_code")
                if code is not None:
                    errors.append(str(code))
    return {"valid": bool(valid), "error_codes": errors}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ckpt", required=True)
    ap.add_argument("--scene", default="results/phase2_synthesis/scene.obj")
    ap.add_argument("--out", required=True)
    ap.add_argument("--opa-thresh", type=float, default=0.05)
    ap.add_argument("--cos-thresh", type=float, default=0.85)
    ap.add_argument("--hs-tol", type=float, default=0.10)
    args = ap.parse_args()

    ckpt = Path(args.ckpt)
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"[stage3] ckpt={ckpt}")
    prims = _load_model(ckpt)
    print(f"[stage3] primitives: {prims['centers'].shape[0]} total, "
          f"{(prims['opacities'] >= args.opa_thresh).sum()} above opa>={args.opa_thresh}")
    # label histogram
    lbls, cnts = np.unique(prims["labels"], return_counts=True)
    print(f"[stage3] labels: {dict(zip(lbls.tolist(), cnts.tolist()))}")
    np.savez_compressed(out_dir / "primitives.npz", **prims)

    gt = parse_scene_obj(args.scene)
    print(f"[stage3] GT: {len(gt['buildings'])} buildings")

    assignment = _assign_primitives_to_buildings(prims, gt, opacity_thresh=args.opa_thresh)
    total_assigned = sum(len(v) for v in assignment.values())
    print(f"[stage3] primitives assigned to buildings: {total_assigned}")

    prim_dict = _build_primitives_dict(prims)
    summary: List[Dict] = []
    n_total = 0
    n_processed = 0
    n_valid = 0
    for b in gt["buildings"]:
        bid = b["building_id"]
        prim_ids = assignment.get(bid, np.array([], dtype=np.int64))
        entry = {"building_id": bid, "building_name": b["name"], "type": b["type"],
                 "n_primitives_assigned": int(len(prim_ids)), "stage3_success": False,
                 "val3dity_valid": False, "val3dity_errors": []}
        n_total += 1
        if len(prim_ids) < 3:
            entry["reason"] = "too_few_primitives"
            summary.append(entry)
            continue

        bdir = out_dir / f"building_{bid:02d}"
        bdir.mkdir(parents=True, exist_ok=True)
        try:
            result = process_building(
                bid, prim_ids, prim_dict, str(bdir),
                cos_thresh=args.cos_thresh, hs_tol=args.hs_tol,
            )
        except Exception as e:
            entry["reason"] = f"process_building_exception: {type(e).__name__}: {e}"
            summary.append(entry)
            continue

        if result is None:
            entry["reason"] = "process_building_returned_none"
            summary.append(entry)
            continue

        entry["stage3_success"] = True
        n_processed += 1
        entry.update({
            "n_surfaces": result["n_surfaces"],
            "n_vertices": result["n_vertices"],
            "signed_volume": result["signed_volume"],
            "n_edges_shared": result["n_edges_shared"],
            "n_edges_boundary": result["n_edges_boundary"],
            "n_edges_nonmanifold": result["n_edges_nonmanifold"],
            "surface_types": result["surface_types"],
            "cityjson_path": result["cityjson_path"],
        })

        # val3dity
        cj_path = Path(result["cityjson_path"])
        rp_path = bdir / "val3dity.json"
        v3d = _run_val3dity(cj_path, rp_path)
        v3d_summary = _summarize_val3dity(v3d)
        entry["val3dity_valid"] = v3d_summary["valid"]
        entry["val3dity_errors"] = v3d_summary["error_codes"]
        if v3d_summary["valid"]:
            n_valid += 1
        summary.append(entry)
        print(f"  bid={bid:02d} type={b['type']:10s} prims={len(prim_ids):4d} "
              f"surfs={entry.get('n_surfaces','-')} vol={entry.get('signed_volume',0):.2f} "
              f"val3dity={'VALID' if v3d_summary['valid'] else 'INVALID'} "
              f"errs={v3d_summary['error_codes']}")

    result_obj = {
        "ckpt": str(ckpt),
        "scene": args.scene,
        "n_buildings_total": n_total,
        "n_buildings_stage3_success": n_processed,
        "n_buildings_val3dity_valid": n_valid,
        "val3dity_pass_rate": float(n_valid / n_total) if n_total else 0.0,
        "params": {
            "opa_thresh": args.opa_thresh,
            "cos_thresh": args.cos_thresh,
            "hs_tol": args.hs_tol,
        },
        "buildings": summary,
    }
    (out_dir / "stage3_summary.json").write_text(
        json.dumps(result_obj, indent=2, default=float))
    print(f"\n[stage3] summary: {n_processed}/{n_total} stage3 success, "
          f"{n_valid}/{n_total} val3dity VALID "
          f"({result_obj['val3dity_pass_rate']*100:.1f}%)")


if __name__ == "__main__":
    main()
