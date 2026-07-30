"""P1-3 Phase 0 — prereq diagnostics for P1-3b adapter design.

Three independent diagnostics on bid=0,1,2,6,21 (Mutual ckpt):
  Phase 0a — Fix Diag 4 ratio_3D (B2=1.949 was impossible; the GT volume
             estimator using vp.mean(axis=0) as face centroid is wrong for
             non-rectangular polygons. Replace with fan-triangulation + signed
             tetrahedra w.r.t. the world origin).
  Phase 0b — Roof primitive y-distribution diagnosis. Classify each
             building's roof failure mode: SPURIOUS_ROOF, WEIGHT_BUG,
             SLOPE_D_ARTIFACT, or SELECTION.
  Phase 0d — Centroid-inside plane orientation prereq. Apply the canonical
             centroid-based flip to RAW v4 planes (before process_building's
             orient_normals_outward) and measure inside_ratio change.

Phase 0c (manual trace) is run separately.

Output:
  results/stage3_v4_validation/P1_3_phase0_REPORT.md
  results/stage3_v4_validation/p1_3_phase0/p1_3_phase0_metrics.json
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Dict, List, Tuple

import numpy as np
from scipy.spatial import ConvexHull
from scipy.stats import trim_mean

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from scripts.stage3_readout.run_stage3 import (  # noqa: E402
    _load_model, _assign_primitives_to_buildings)
from scripts.stage3_readout.obj_gt import parse_scene_obj  # noqa: E402
from src.stage3.clustering import cluster_primitives_v4  # noqa: E402

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

GRAVITY = np.array([0.0, 1.0, 0.0])
SCENE = ROOT / "results/phase2_synthesis/scene.obj"
CKPT_MUTUAL = ROOT / "results/phase2_ablation_citygml/mutual/ckpt/final.pt"
TARGET_BIDS = [0, 1, 2, 6, 21]
OUT_DIR = ROOT / "results/stage3_v4_validation"
WORK_DIR = OUT_DIR / "p1_3_phase0"
WORK_DIR.mkdir(parents=True, exist_ok=True)


def _assert_gravity():
    assert np.allclose(GRAVITY, [0.0, 1.0, 0.0]), \
        f"gravity != [0, 1, 0]: {GRAVITY}"


# ---------------------------------------------------------------------------
# Phase 0a — corrected GT volume (fan triangulation + signed tetrahedra)
# ---------------------------------------------------------------------------


def gt_volume_via_fan(gt_b: Dict) -> float:
    """Robust closed-mesh volume via signed tetrahedra anchored at the
    building centroid.

    For a water-tight CCW-outward mesh, V = (1/6) Σ v_a · (v_b × v_c) is
    origin-invariant. scene.obj's CityGML LOD2 meshes are NOT exactly
    water-tight (verified empirically — origin-anchored, centroid-formula,
    and trimesh.volume disagree wildly on B2/B6). Anchoring the apex at the
    building centroid makes the integrand small near defects so they cancel.

    Per-face: fan-triangulate from v[0]; for each triangle (v0, vi, v_{i+1}),
    the tetrahedron with apex at gt_centroid has signed volume
    (1/6) (v0-c) · ((vi-c) × (v_{i+1}-c)). Vertices are reversed when the
    Newell normal is inward, so the winding stays CCW outward.
    """
    _assert_gravity()
    faces = gt_b["faces"]
    all_v = np.concatenate([f["vertices"] for f in faces], axis=0)
    gt_centroid = all_v.mean(axis=0)
    vol = 0.0
    for f in faces:
        verts = np.asarray(f["vertices"], dtype=np.float64).copy()
        n = np.asarray(f["normal"], dtype=np.float64)
        n /= np.linalg.norm(n) + 1e-12
        c = np.asarray(f["centroid"], dtype=np.float64)
        if np.dot(n, c - gt_centroid) < 0:
            verts = verts[::-1]
        v0 = verts[0] - gt_centroid
        for i in range(1, len(verts) - 1):
            v1 = verts[i] - gt_centroid
            v2 = verts[i + 1] - gt_centroid
            vol += float(np.dot(v0, np.cross(v1, v2))) / 6.0
    return abs(vol)


def diag4_phase0a(gt_b: Dict) -> Dict:
    """Recompute ratio_2D and ratio_3D with corrected GT volume."""
    _assert_gravity()
    faces = gt_b["faces"]
    all_v = np.concatenate([f["vertices"] for f in faces], axis=0)

    # 2D footprint via GroundSurface face (semantic_class==3, |n·g|>0.95)
    ground_faces = [f for f in faces if f["semantic_class"] == 3
                    and abs(np.dot(f["normal"], GRAVITY)) > 0.95]
    if ground_faces:
        ground = max(ground_faces, key=lambda f: f["area"])
        footprint_area = float(ground["area"])
        v2d = ground["vertices"][:, [0, 2]]
        try:
            hull2d_area = float(ConvexHull(v2d).volume)  # area in 2D
        except Exception:
            hull2d_area = footprint_area
    else:
        v2d = all_v[:, [0, 2]]
        try:
            hull2d_area = float(ConvexHull(v2d).volume)
        except Exception:
            hull2d_area = float("nan")
        footprint_area = hull2d_area
    ratio_2d = (footprint_area / hull2d_area
                if hull2d_area > 0 else float("nan"))

    # 3D corrected
    gt_vol = gt_volume_via_fan(gt_b)
    try:
        hull3d = ConvexHull(all_v)
        hull3d_vol = float(hull3d.volume)
        hull3d_h = float(all_v[hull3d.vertices][:, 1].max()
                         - all_v[hull3d.vertices][:, 1].min())
    except Exception:
        hull3d_vol = float("nan")
        hull3d_h = float("nan")
    ratio_3d = (gt_vol / hull3d_vol if hull3d_vol > 0 else float("nan"))
    solid_h = float(all_v[:, 1].max() - all_v[:, 1].min())

    convex_ok = (ratio_2d >= 0.85 and ratio_3d >= 0.85)

    return {
        "ratio_2D": ratio_2d,
        "ratio_3D": ratio_3d,
        "footprint_area": footprint_area,
        "hull2D_area": hull2d_area,
        "GT_vol": gt_vol,
        "hull3D_vol": hull3d_vol,
        "hull3D_h": hull3d_h,
        "solid_h": solid_h,
        "verdict": "CONVEX_OK" if convex_ok else "NON_CONVEX",
    }


# ---------------------------------------------------------------------------
# Phase 0b — roof primitive y-distribution per v4 group
# ---------------------------------------------------------------------------


def diag_phase0b_roof(prims, pids, gt_b) -> Dict:
    _assert_gravity()
    centers = prims["centers"][pids]
    normals = prims["normals"][pids]
    areas = prims["areas"][pids]
    opacities = prims["opacities"][pids]
    labels = prims["sem_probs"][pids].argmax(axis=1)

    gids, rep_n, rep_off, rep_cls = cluster_primitives_v4(
        centers, normals, areas, labels,
        gravity=GRAVITY, opacities=opacities)

    # GT roof y range (vertices of all GT roof faces)
    gt_roof_verts = np.concatenate(
        [f["vertices"] for f in gt_b["faces"] if f["semantic_class"] == 1],
        axis=0) if any(f["semantic_class"] == 1 for f in gt_b["faces"]) else None
    if gt_roof_verts is None:
        gt_y_min, gt_y_max = -np.inf, np.inf
    else:
        gt_y_min = float(gt_roof_verts[:, 1].min())  # most negative = highest
        gt_y_max = float(gt_roof_verts[:, 1].max())
    gt_pad = 1.0  # ±1 m tolerance

    # Pad: a primitive whose y is within [gt_y_min - pad, gt_y_max + pad] is
    # plausibly on the GT roof; outside this range is "spurious".
    roof_mask = labels == 1

    # Roof groups (rep_cls==1)
    roof_group_ids = np.where(rep_cls == 1)[0]
    group_records: List[Dict] = []
    for k in roof_group_ids:
        m = gids == k
        if int(m.sum()) == 0:
            continue
        cs = centers[m]
        as_ = areas[m]
        n_k = rep_n[k].astype(np.float64)
        n_k /= np.linalg.norm(n_k) + 1e-12
        d_k = float(rep_off[k])
        ys = cs[:, 1]

        # Predicted y at the primitive centroid (cx, cz) using the plane
        # equation n·x = d. y = (d − n_x·cx − n_z·cz) / n_y. Skip if n_y ~ 0.
        bld_centroid = centers.mean(axis=0)
        if abs(n_k[1]) > 1e-3:
            pred_y = float((d_k - n_k[0] * bld_centroid[0]
                            - n_k[2] * bld_centroid[2]) / n_k[1])
        else:
            pred_y = float("nan")

        # spurious: primitives in this group with y outside GT roof range±pad
        spurious_count = int(((ys < gt_y_min - gt_pad)
                              | (ys > gt_y_max + gt_pad)).sum())
        spurious_pct = 100.0 * spurious_count / max(int(m.sum()), 1)

        group_records.append({
            "gid": int(k),
            "n_prim": int(m.sum()),
            "support_area": float(as_.sum()),
            "y_mean": float(ys.mean()),
            "y_std": float(ys.std()),
            "y_min": float(ys.min()),
            "y_max": float(ys.max()),
            "rep_n": [float(x) for x in n_k],
            "rep_d": d_k,
            "predicted_y_at_centroid": pred_y,
            "spurious_pct": spurious_pct,
        })

    # Compute the v4 roof_d as in P1-3a (area-weighted, |n·g|>0.7)
    horiz_groups = [g for g in group_records
                    if abs(g["rep_n"][1]) > 0.7]
    if horiz_groups:
        ws = np.array([g["support_area"] for g in horiz_groups])
        ds = np.array([g["rep_d"] for g in horiz_groups])
        # outward orientation will be applied later in process_building, but
        # for d-mean we need consistent sign. Since v4 returns rep_n in the
        # convention rep_n·x = rep_off, mean of d's is meaningful only when
        # rep_n's are aligned (same sign of n_y). Sign-align all to n_y < 0
        # (roof outward in primitive Y-down frame).
        signs = np.where(np.array([g["rep_n"][1] for g in horiz_groups]) > 0,
                         -1.0, 1.0)
        ds = ds * signs
        v4_roof_d_mean = float(np.average(ds, weights=ws + 1e-12))
        # weight contribution per group
        for g, w in zip(horiz_groups, ws):
            g["weight_contrib_pct"] = float(100.0 * w / (ws.sum() + 1e-12))
    else:
        v4_roof_d_mean = float("nan")

    # GT roof_d (sign-aligned to n_y < 0 outward, area-weighted)
    gt_roof_faces = [f for f in gt_b["faces"]
                     if f["semantic_class"] == 1
                     and abs(np.dot(f["normal"], GRAVITY)) > 0.7]
    if gt_roof_faces:
        gt_centroid = np.concatenate(
            [f["vertices"] for f in gt_b["faces"]]).mean(axis=0)
        ws = np.array([f["area"] for f in gt_roof_faces])
        ds = []
        for f in gt_roof_faces:
            n = np.asarray(f["normal"]).astype(np.float64)
            n /= np.linalg.norm(n) + 1e-12
            d = float(np.dot(n, f["centroid"]))
            if np.dot(n, f["centroid"] - gt_centroid) < 0:
                n = -n
                d = -d
            # sign-align to n_y < 0
            if n[1] > 0:
                n = -n
                d = -d
            ds.append(d)
        gt_roof_d = float(np.average(ds, weights=ws + 1e-12))
    else:
        gt_roof_d = float("nan")

    # Top group identification (largest weight contribution)
    if horiz_groups:
        top_group = max(horiz_groups, key=lambda g: g["weight_contrib_pct"])
        top_gid = top_group["gid"]
        top_y_mean = top_group["y_mean"]
        top_area = top_group["support_area"]
        top_weight = top_group["weight_contrib_pct"]
        top_pred_y = top_group["predicted_y_at_centroid"]
        top_d = top_group["rep_d"]
        top_spurious = top_group["spurious_pct"]
    else:
        top_gid = -1
        top_y_mean = top_area = top_weight = top_pred_y = top_d = float("nan")
        top_spurious = float("nan")

    # Group-level dominant_cause
    median_area = (float(np.median([g["support_area"] for g in horiz_groups]))
                   if horiz_groups else 0.0)
    delta_d = abs(v4_roof_d_mean - gt_roof_d) if (
        not np.isnan(v4_roof_d_mean) and not np.isnan(gt_roof_d)) else float(
            "inf")

    if not horiz_groups:
        dominant_cause = "NO_ROOF_GROUPS"
    elif top_spurious > 30.0:
        dominant_cause = "SPURIOUS_ROOF"
    elif top_weight > 70.0 and top_area < median_area:
        dominant_cause = "WEIGHT_BUG"
    elif (gt_y_min - gt_pad) <= top_pred_y <= (gt_y_max + gt_pad) and delta_d >= 1.0:
        dominant_cause = "SLOPE_D_ARTIFACT"
    elif delta_d < 1.0:
        dominant_cause = "OK"
    else:
        dominant_cause = "SELECTION"

    return {
        "n_roof_groups": len(roof_group_ids),
        "n_horiz_roof_groups": len(horiz_groups),
        "v4_roof_d_mean": v4_roof_d_mean,
        "GT_roof_d": gt_roof_d,
        "abs_d_roof": delta_d,
        "GT_roof_y_range": [gt_y_min, gt_y_max],
        "top_gid": int(top_gid),
        "top_y_mean": top_y_mean,
        "top_area": top_area,
        "top_weight_contrib": top_weight,
        "top_predicted_y_at_centroid": top_pred_y,
        "top_d": top_d,
        "top_spurious_pct": top_spurious,
        "median_horiz_area": median_area,
        "dominant_cause": dominant_cause,
        "all_horiz_groups": horiz_groups,
    }


# ---------------------------------------------------------------------------
# Phase 0d — centroid-inside orientation prereq
# ---------------------------------------------------------------------------


def centroid_inside_orient(rep_n: np.ndarray, rep_off: np.ndarray,
                            centers: np.ndarray) -> Dict:
    """Apply canonical orientation: flip plane if its (n, d) places the
    building centroid OUTSIDE (n·c > d). After flipping, both halves of the
    plane are evaluated and `inside_ratio` is reported.

    centroid is computed via 10% trimmed mean per axis (robust to outliers).
    """
    _assert_gravity()
    centroid = trim_mean(centers, 0.1, axis=0)  # (3,)
    K = len(rep_n)
    n_out = rep_n.copy().astype(np.float64)
    d_out = rep_off.copy().astype(np.float64)
    flipped = np.zeros(K, dtype=bool)

    inside_before = np.zeros(K)
    inside_after = np.zeros(K)

    for k in range(K):
        n = n_out[k] / (np.linalg.norm(n_out[k]) + 1e-12)
        d = d_out[k]
        # Inside (before): fraction of primitive centers satisfying n·c < d
        ib = float((centers @ n - d < 0).mean())
        inside_before[k] = ib
        # Flip if centroid is on the wrong side (outside the half-space)
        if (np.dot(n, centroid) - d) > 0:
            n_out[k] = -n
            d_out[k] = -d
            flipped[k] = True
        else:
            n_out[k] = n
        # Inside (after)
        ia = float((centers @ n_out[k] - d_out[k] < 0).mean())
        inside_after[k] = ia

    return {
        "n_planes": int(K),
        "centroid": [float(x) for x in centroid],
        "inside_before": inside_before,
        "inside_after": inside_after,
        "flipped": flipped,
        "rep_n_out": n_out,
        "rep_d_out": d_out,
    }


def diag_phase0d(prims, pids) -> Dict:
    _assert_gravity()
    centers = prims["centers"][pids]
    normals = prims["normals"][pids]
    areas = prims["areas"][pids]
    opacities = prims["opacities"][pids]
    labels = prims["sem_probs"][pids].argmax(axis=1)

    gids, rep_n, rep_off, rep_cls = cluster_primitives_v4(
        centers, normals, areas, labels,
        gravity=GRAVITY, opacities=opacities)

    out = centroid_inside_orient(rep_n, rep_off, centers)

    n_walls = int((rep_cls == 2).sum())
    n_roofs = int((rep_cls == 1).sum())
    n_walls_flipped = int(out["flipped"][rep_cls == 2].sum()) if n_walls else 0
    n_roofs_flipped = int(out["flipped"][rep_cls == 1].sum()) if n_roofs else 0

    return {
        "n_planes": out["n_planes"],
        "n_walls": n_walls,
        "n_roofs": n_roofs,
        "centroid": out["centroid"],
        "mean_inside_before": float(out["inside_before"].mean()),
        "mean_inside_after": float(out["inside_after"].mean()),
        "n_low_inside_after": int((out["inside_after"] < 0.85).sum()),
        "n_walls_flipped": n_walls_flipped,
        "n_roofs_flipped": n_roofs_flipped,
        "rep_classes": [int(c) for c in rep_cls],
        "inside_before": [float(x) for x in out["inside_before"]],
        "inside_after": [float(x) for x in out["inside_after"]],
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main():
    _assert_gravity()
    print(f"[load] {CKPT_MUTUAL.relative_to(ROOT)}")
    gt = parse_scene_obj(str(SCENE), frame="obj")
    prims = _load_model(CKPT_MUTUAL, emit_stage2_groups=False)
    asg = _assign_primitives_to_buildings(prims, gt, opacity_thresh=0.05)

    # Load prior P1-3a metrics (for "old" ratio_3D / ratio_2D in 0a comparison)
    prior_path = OUT_DIR / "p1_3a/p1_3a_metrics.json"
    prior = (json.loads(prior_path.read_text()) if prior_path.exists() else {})

    per_b: Dict[int, Dict] = {}
    for bid in TARGET_BIDS:
        if bid not in asg or len(asg[bid]) < 100:
            per_b[bid] = {"skipped": True, "reason": "no_primitives"}
            continue
        gt_b = next(b for b in gt["buildings"] if b["building_id"] == bid)

        d4 = diag4_phase0a(gt_b)
        d_b = diag_phase0b_roof(prims, asg[bid], gt_b)
        d_d = diag_phase0d(prims, asg[bid])
        old = prior.get(str(bid), prior.get(bid, {})).get("diag4", {})
        per_b[bid] = {
            "type": gt_b["type"],
            "phase0a": {
                "old_ratio_2D": float(old.get("ratio_2D", float("nan"))),
                "old_ratio_3D": float(old.get("ratio_3D", float("nan"))),
                **d4,
            },
            "phase0b": d_b,
            "phase0d": d_d,
        }
        print(f"  B{bid:2d} {gt_b['type']:9s} "
              f"r3D: {old.get('ratio_3D', '?'):>5} → {d4['ratio_3D']:.3f} "
              f"({d4['verdict']})  roof: {d_b['dominant_cause']:18s} "
              f"flip W={d_d['n_walls_flipped']}/{d_d['n_walls']}")

    # ============ Build report ============
    L: List[str] = []
    L.append("# P1-3 Phase 0 — prereq diagnostics (0a + 0b + 0d)\n")
    L.append("**Mutual ckpt, bid=0,1,2,6,21.** GT for evaluation only. "
             "v4 parameters P1-2-fixed.\n")
    L.append("`gravity = [0, 1, 0]` asserted in every diagnostic entry.\n")
    L.append("Phase 0c (manual trace) is run separately.\n")

    # ----- Phase 0a -----
    L.append("## Phase 0a — Diag 4 ratio_3D fix\n")
    L.append("**Bug**: P1-3a used `vp.mean(axis=0)` as face centroid in the "
             "divergence formula `V = (1/3) Σ A·(n·c)`, which is incorrect "
             "for non-rectangular planar polygons (vertex mean ≠ true "
             "area-weighted centroid). For B2 this produced "
             "ratio_3D = 1.949 (impossible: convex hull contains the "
             "solid, so ratio ≤ 1).\n")
    L.append("**Fix**: switch to fan triangulation + signed tetrahedra. "
             "Each face is fan-triangulated from v[0]; each triangle "
             "(v0, vi, vi+1) contributes `(1/6) · v0 · (v1 × v2)` to the "
             "signed volume. Vertices are reversed if the face normal "
             "(Newell) is inward, ensuring CCW-outward winding.\n")
    L.append("| bid | type | old ratio_3D | new ratio_3D | "
             "old ratio_2D | new ratio_2D | new verdict |")
    L.append("|---|---|---|---|---|---|---|")
    new_3d_ok = 0
    new_2d_ok = 0
    for bid in TARGET_BIDS:
        e = per_b.get(bid, {})
        if e.get("skipped"):
            continue
        a = e["phase0a"]
        new3 = a["ratio_3D"]
        new2 = a["ratio_2D"]
        if new3 <= 1.0 + 1e-6:
            new_3d_ok += 1
        if new2 <= 1.0 + 1e-6:
            new_2d_ok += 1
        L.append(f"| {bid} | {e['type']} | "
                 f"{a['old_ratio_3D']:.3f} | **{new3:.3f}** | "
                 f"{a['old_ratio_2D']:.3f} | {new2:.3f} | "
                 f"**{a['verdict']}** |")
    L.append("")
    L.append(f"- Phase 0a verdict: 5/5 ratio_3D ≤ 1: "
             f"**{'OK' if new_3d_ok == 5 else 'NG'}** ({new_3d_ok}/5)")
    L.append(f"- 5/5 ratio_2D ≤ 1: "
             f"**{'OK' if new_2d_ok == 5 else 'NG'}** ({new_2d_ok}/5)")
    # B6 verdict
    b6 = per_b.get(6, {}).get("phase0a")
    if b6:
        L.append(f"- B6 new ratio_3D = {b6['ratio_3D']:.3f} → "
                 f"**{b6['verdict']}**")

    # ----- Phase 0b -----
    L.append("\n## Phase 0b — Roof primitive y-distribution\n")
    L.append("Per building, identify the v4 roof group with the largest "
             "weight contribution to the area-weighted v4_roof_d, and "
             "classify the failure mode:\n")
    L.append("- `SPURIOUS_ROOF`: top group has > 30% primitives outside GT "
             "roof y-range (Stage 2 sem-head misclassification — out of "
             "P1-3b scope).")
    L.append("- `WEIGHT_BUG`: top group dominates the mean (>70%) AND has "
             "below-median area — a small outlier biases the mean.")
    L.append("- `SLOPE_D_ARTIFACT`: predicted_y_at_centroid is in the GT "
             "roof y-range AND \\|Δd\\| ≥ 1m (sloped roof; the d-comparison "
             "metric is just inappropriate, selection is OK).")
    L.append("- `SELECTION`: \\|Δd\\| ≥ 1m and none of the above apply.")
    L.append("- `OK`: \\|Δd\\| < 1m.\n")
    L.append("| bid | n_horiz_roof_groups | top_gid | top_y_mean | "
             "top_area | weight_contrib | GT_roof_y_range | "
             "spurious% | predicted_y@centroid | GT_roof_d | "
             "v4_roof_d | \\|Δd\\| | dominant_cause |")
    L.append("|---|---|---|---|---|---|---|---|---|---|---|---|---|")
    for bid in TARGET_BIDS:
        e = per_b.get(bid, {})
        if e.get("skipped"):
            continue
        b = e["phase0b"]
        gt_range = b["GT_roof_y_range"]
        L.append(f"| {bid} | {b['n_horiz_roof_groups']} | "
                 f"{b['top_gid']} | {b['top_y_mean']:.2f} | "
                 f"{b['top_area']:.2f} | {b['top_weight_contrib']:.1f}% | "
                 f"[{gt_range[0]:.2f}, {gt_range[1]:.2f}] | "
                 f"{b['top_spurious_pct']:.1f}% | "
                 f"{b['top_predicted_y_at_centroid']:.2f} | "
                 f"{b['GT_roof_d']:.2f} | {b['v4_roof_d_mean']:.2f} | "
                 f"**{b['abs_d_roof']:.2f}** | "
                 f"**{b['dominant_cause']}** |")
    L.append("")

    # ----- Phase 0d -----
    L.append("## Phase 0d — Centroid-inside orientation prereq\n")
    L.append("Apply canonical orientation to RAW v4 planes (rep_n, rep_off) "
             "BEFORE process_building's `orient_normals_outward`. Centroid "
             "is the 10%-trimmed mean of building primitive centres (robust "
             "to outliers). For each plane, flip if `n · centroid > d` "
             "(centroid is outside the half-space). `inside_ratio` is the "
             "fraction of primitive centres satisfying `n·c < d`.\n")
    L.append("| bid | n_planes | n_walls | n_roofs | mean inside (before) | "
             "mean inside (after) | n_planes ratio<0.85 (after) | "
             "n_walls_flipped |")
    L.append("|---|---|---|---|---|---|---|---|")
    for bid in TARGET_BIDS:
        e = per_b.get(bid, {})
        if e.get("skipped"):
            continue
        d = e["phase0d"]
        L.append(f"| {bid} | {d['n_planes']} | {d['n_walls']} | "
                 f"{d['n_roofs']} | "
                 f"{d['mean_inside_before']:.3f} | "
                 f"{d['mean_inside_after']:.3f} | "
                 f"{d['n_low_inside_after']} | "
                 f"{d['n_walls_flipped']} |")
    L.append("")

    # ----- Decide P1-3b clean cases -----
    L.append("## P1-3b clean case decision\n")
    clean_cases: List[int] = []
    skip_reasons: Dict[int, str] = {}
    for bid in TARGET_BIDS:
        e = per_b.get(bid, {})
        if e.get("skipped"):
            skip_reasons[bid] = "no_primitives"; continue
        cause = e["phase0b"]["dominant_cause"]
        ratio_3d = e["phase0a"]["ratio_3D"]
        if cause == "SPURIOUS_ROOF":
            skip_reasons[bid] = "SPURIOUS_ROOF (Stage 2 task)"; continue
        if bid == 0:
            skip_reasons[bid] = "B0 backend-fragile (parallel with Phase 0c)"
            continue
        if bid == 6:
            if ratio_3d < 0.85:
                skip_reasons[bid] = (f"NON_CONVEX confirmed "
                                      f"(ratio_3D={ratio_3d:.3f}); 2.5D fallback")
                continue
        clean_cases.append(bid)

    L.append(f"**clean_cases = {clean_cases}** (length {len(clean_cases)}).\n")
    if skip_reasons:
        L.append("Excluded:")
        for bid, why in skip_reasons.items():
            L.append(f"- B{bid}: {why}")

    if len(clean_cases) < 3:
        L.append("\n**WARN**: clean_cases < 3 — P1-3b 보류, 더 근본적 진단 "
                 "필요.\n")
    else:
        L.append("\nP1-3b 진행 가능.\n")

    # ----- Self-verification -----
    L.append("## Self-verification\n")
    L.append(f"- gravity = [0, 1, 0] asserted in every entry: ✓")
    L.append(f"- Phase 0a 5건물 ratio_3D ≤ 1: "
             f"{'✓' if new_3d_ok == 5 else f'✗ ({new_3d_ok}/5)'}")
    n_with_cause = sum(1 for e in per_b.values()
                       if not e.get("skipped")
                       and "dominant_cause" in e["phase0b"])
    L.append(f"- Phase 0b 5건물 dominant_cause 할당: "
             f"{'✓' if n_with_cause == 5 else f'✗ ({n_with_cause}/5)'}")
    L.append(f"- Phase 0d before/after 표 출력: ✓")
    L.append(f"- P1-3b clean_cases 결정: ✓ ({clean_cases})")

    # Save metrics
    def jsonable(o):
        if isinstance(o, (np.ndarray,)):
            return o.tolist()
        if isinstance(o, (np.generic,)):
            return o.item()
        return str(o)
    (WORK_DIR / "p1_3_phase0_metrics.json").write_text(
        json.dumps(per_b, default=jsonable, indent=2))

    out_md = OUT_DIR / "P1_3_phase0_REPORT.md"
    out_md.write_text("\n".join(L))
    print(f"\nReport → {out_md}")
    return per_b


if __name__ == "__main__":
    main()
