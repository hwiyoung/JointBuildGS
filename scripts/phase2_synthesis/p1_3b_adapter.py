"""P1-3b — backend fix + support-plane adapter (1st round).

Two backend patches + two adapter steps applied to v4 envelopes for the five
representative buildings. Goal: recover P1-3's height/coverage collapse.

Backend patches (always applied for C1+):
  Patch 1 — face-vertex projection onto assigned plane + global snap merge.
            After ConvexHull's `_merge_coplanar_triangles`, vertices have
            up to ~5 cm residual to the plane (hs_tol). Patch 1 projects
            them exactly onto the plane (`v - (n·v − d)·n`), then merges
            globally close vertices (snap_tol = 1 mm) to restore shell
            topology.
  Patch 2 — class-agnostic support-d. `support_d(n_outward, support_centers)
            = max(n · c)` (q=1.0; robust q < 1 deferred to round 2).

Adapter steps (toggled by condition):
  Step 1   — centroid-inside orientation on ALL planes (walls, roofs,
             ground, bbox). Replaces `orient_normals_outward`. The centroid
             is the 10%-trimmed mean of building primitive centres.
  Step 2.5 — apply `support_d` to each non-virtual plane group (skip
             ground/bbox; their d's are already constructed for shell
             closure).

Conditions (per building):
  C0  ×  ×  ×  ×    P1-3 baseline (reproduce)
  C1  P1 ×  ×  ×    backend patch only
  C2  P1 ×  ✓  ×    + centroid-inside orientation
  C3  P1 ×  ✓  ✓    + d_support  (full adapter)

Targets: B0 (reference, NOT in Hard GO), B1 / B6 / B21 (clean cases),
B2 (regression watch).

Output:
  results/stage3_v4_validation/P1_3b_REPORT.md
  results/stage3_v4_validation/p1_3b/p1_3b_metrics.json
  results/stage3_v4_validation/p1_3b/<cond>/building_NN/{building.city.json,
                                                          val3dity.json}
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Dict, List, Tuple

import numpy as np
from scipy.spatial import ConvexHull, cKDTree
from scipy.stats import trim_mean

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from scripts.phase2_synthesis.run_stage3 import (  # noqa: E402
    _load_model, _assign_primitives_to_buildings,
    _run_val3dity, _summarize_val3dity)
from scripts.phase2_synthesis.obj_gt import parse_scene_obj  # noqa: E402
from src.stage3.clustering import cluster_primitives_v4  # noqa: E402
from src.stage3.ground_surface import (  # noqa: E402
    orient_normals_outward, add_ground_surface, add_bbox_planes)
from src.stage3.plane_intersection import (  # noqa: E402
    intersect_three_planes, _merge_coplanar_triangles)
from src.stage3.citygml_export import build_cityjson  # noqa: E402

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

GRAVITY = np.array([0.0, 1.0, 0.0])
SCENE = ROOT / "results/phase2_synthesis/scene.obj"
CKPT_MUTUAL = ROOT / "results/phase2_ablation_citygml/mutual/ckpt/final.pt"
TARGET_BIDS = [0, 1, 2, 6, 21]
CLEAN_BIDS = [1, 6, 21]   # Hard/Strong GO buildings
REGRESSION_BID = 2
REFERENCE_BID = 0

OUT_DIR = ROOT / "results/stage3_v4_validation"
WORK_DIR = OUT_DIR / "p1_3b"
WORK_DIR.mkdir(parents=True, exist_ok=True)

CONDITIONS = [
    ("C0", {"patch1": False, "step1": False, "step2_5": False}),
    ("C1", {"patch1": True,  "step1": False, "step2_5": False}),
    ("C2", {"patch1": True,  "step1": True,  "step2_5": False}),
    ("C3", {"patch1": True,  "step1": True,  "step2_5": True}),
]


def _assert_gravity():
    assert np.allclose(GRAVITY, [0.0, 1.0, 0.0]), \
        f"gravity != [0, 1, 0]: {GRAVITY}"


# ---------------------------------------------------------------------------
# v4 → groups list
# ---------------------------------------------------------------------------


def v4_to_groups(prims, pids) -> Tuple[List[Dict], np.ndarray, np.ndarray]:
    """Run v4 cluster on this building → groups list (compatible with
    process_building's downstream)."""
    _assert_gravity()
    centers = prims["centers"][pids]
    normals = prims["normals"][pids]
    areas = prims["areas"][pids]
    opacities = prims["opacities"][pids]
    labels = prims["sem_probs"][pids].argmax(axis=1)

    gids, rep_n, rep_off, rep_cls = cluster_primitives_v4(
        centers, normals, areas, labels,
        gravity=GRAVITY, opacities=opacities)

    groups: List[Dict] = []
    for k in range(len(rep_n)):
        m = gids == k
        if int(m.sum()) < 3:
            continue
        cs = centers[m]
        as_ = areas[m]
        w = as_ / (as_.sum() + 1e-12)
        c_mean = (cs * w[:, None]).sum(0)
        n = rep_n[k].astype(np.float64)
        n /= np.linalg.norm(n) + 1e-12
        groups.append({
            "plane_normal": n,
            "plane_d": float(np.dot(n, c_mean)),
            "class": int(rep_cls[k]),
            "prim_ids": np.where(m)[0].tolist(),
            "center": c_mean.copy(),
            "area": float(as_.sum()),
        })
    return groups, centers, labels


# ---------------------------------------------------------------------------
# Step 1 — centroid-inside orientation (all planes)
# ---------------------------------------------------------------------------


def centroid_inside_orient_all(groups: List[Dict],
                                centers: np.ndarray) -> np.ndarray:
    """Apply canonical centroid-inside flip to every plane in `groups`.
    Mutates in place. Returns the trimmed centroid (for logging)."""
    _assert_gravity()
    centroid = trim_mean(centers, 0.1, axis=0)
    for g in groups:
        n = g["plane_normal"]
        d = g["plane_d"]
        if (np.dot(n, centroid) - d) > 0:
            g["plane_normal"] = -n
            g["plane_d"] = -d
    return centroid


# ---------------------------------------------------------------------------
# Step 2.5 — support-d (Patch 2 applied)
# ---------------------------------------------------------------------------


def apply_support_d(groups: List[Dict], centers: np.ndarray) -> List[Dict]:
    """For non-virtual plane groups, replace plane_d with max(n · c) over the
    member primitive centres. Records `plane_d_initial` and `delta_d`."""
    _assert_gravity()
    for g in groups:
        if g.get("is_ground") or g.get("is_bbox"):
            continue
        pids = g.get("prim_ids", [])
        if len(pids) == 0:
            continue
        c_sub = centers[np.asarray(pids, dtype=np.int64)]
        n = g["plane_normal"]
        d_init = g["plane_d"]
        d_sup = float((c_sub @ n).max())
        g["plane_d_initial"] = d_init
        g["plane_d"] = d_sup
        g["delta_d"] = abs(d_sup - d_init)
    return groups


# ---------------------------------------------------------------------------
# Polytope build (with optional Patch 1)
# ---------------------------------------------------------------------------


def _build_polytope_raw(groups: List[Dict], prim_centers: np.ndarray,
                        hs_tol: float = 0.05, plane_tol: float = 0.1):
    """Replicates `build_convex_polytope` but returns valid_verts + per-face
    triangle list (unmerged) so we can inspect/patch."""
    N = len(groups)
    if N < 4:
        return None, None, None
    plane_n = np.array([g["plane_normal"] for g in groups])
    plane_d = np.array([g["plane_d"] for g in groups])

    extent = float((prim_centers.max(axis=0) - prim_centers.min(axis=0)).max())
    bbox_margin = max(5.0, 0.5 * extent)
    bbox_min = prim_centers.min(axis=0) - bbox_margin
    bbox_max = prim_centers.max(axis=0) + bbox_margin

    valid = []
    for i in range(N):
        for j in range(i + 1, N):
            for k in range(j + 1, N):
                pt = intersect_three_planes(
                    plane_n[i], plane_d[i],
                    plane_n[j], plane_d[j],
                    plane_n[k], plane_d[k])
                if pt is None:
                    continue
                if np.any(plane_n @ pt - plane_d > hs_tol):
                    continue
                if np.any(pt < bbox_min) or np.any(pt > bbox_max):
                    continue
                valid.append(pt)
    if len(valid) < 4:
        return None, None, None
    valid = np.array(valid)
    keep = [0]
    for vi in range(1, len(valid)):
        if all(np.linalg.norm(valid[vi] - valid[u]) > 0.001 for u in keep):
            keep.append(vi)
    valid = valid[keep]
    if len(valid) < 4:
        return None, None, None

    try:
        hull = ConvexHull(valid)
    except Exception:
        return None, None, None

    # Match each hull triangle to its closest plane
    from collections import defaultdict
    group_tris = defaultdict(list)
    for fi, simplex in enumerate(hull.simplices):
        face_verts = valid[simplex]
        best_gi, best_res = -1, float("inf")
        for gi in range(N):
            res = float(np.abs(plane_n[gi] @ face_verts.T - plane_d[gi]).max())
            if res < best_res:
                best_res = res
                best_gi = gi
        if best_res < plane_tol:
            group_tris[best_gi].append(simplex.tolist())
        else:
            eq = hull.equations[fi][:3]
            eq_len = np.linalg.norm(eq)
            if eq_len > 1e-10:
                fn = eq / eq_len
                cos_sims = plane_n @ fn
                best = int(np.argmax(cos_sims))
                if cos_sims[best] > 0.3:
                    group_tris[best].append(simplex.tolist())
    return valid, dict(group_tris), hull


def build_polytope_with_patches(groups: List[Dict], prim_centers: np.ndarray,
                                 patch1: bool,
                                 snap_tol: float = 0.001
                                 ) -> Tuple[Dict, Dict]:
    """Build polygons dict, optionally applying Patch 1 (project + snap).

    Returns (polygons, info) where info has:
      - max_d2p_before / max_d2p_after  (max |n·v − d| across face vertices)
      - max_displacement (max |v_proj − v_orig|)
      - snap_pairs_merged
    """
    valid, group_tris, _hull = _build_polytope_raw(groups, prim_centers)
    if valid is None:
        return None, {"error": "polytope_build_None"}

    # Coplanar merge → polygons (using existing helper)
    polygons_raw: Dict[int, np.ndarray] = {}
    for gi, tris in group_tris.items():
        pts = _merge_coplanar_triangles(valid, tris, groups[gi]["plane_normal"])
        if pts is not None and len(pts) >= 3:
            polygons_raw[gi] = pts

    # max_d2p before Patch 1
    def _max_d2p(polys: Dict[int, np.ndarray]) -> float:
        m = 0.0
        for gi, verts in polys.items():
            n = groups[gi]["plane_normal"]
            d = groups[gi]["plane_d"]
            res = np.abs(np.asarray(verts) @ n - d)
            m = max(m, float(res.max()))
        return m

    info: Dict = {
        "n_valid_verts": len(valid),
        "n_polygons_before": len(polygons_raw),
        "max_d2p_before": _max_d2p(polygons_raw),
        "max_d2p_after": float("nan"),
        "max_displacement": 0.0,
        "snap_pairs_merged": 0,
    }

    if not patch1:
        info["max_d2p_after"] = info["max_d2p_before"]
        return polygons_raw, info

    # ---- Patch 1: project face vertices onto plane, then snap ----
    proj_polys: Dict[int, np.ndarray] = {}
    max_disp = 0.0
    for gi, verts in polygons_raw.items():
        n = groups[gi]["plane_normal"]
        d = groups[gi]["plane_d"]
        v_arr = np.asarray(verts, dtype=np.float64)
        res = v_arr @ n - d
        v_proj = v_arr - res[:, None] * n[None, :]
        max_disp = max(max_disp, float(np.linalg.norm(v_arr - v_proj, axis=1).max()))
        proj_polys[gi] = v_proj

    # Global vertex pool + face indices
    all_v: List[np.ndarray] = []
    face_idx: Dict[int, List[int]] = {}
    for gi, verts in proj_polys.items():
        idx_list = []
        for v in verts:
            idx_list.append(len(all_v))
            all_v.append(v)
        face_idx[gi] = idx_list
    pool = np.array(all_v)

    # Union-find merge for vertex pairs within snap_tol
    parent = list(range(len(pool)))

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    snap_count = 0
    if len(pool) > 1:
        tree = cKDTree(pool)
        pairs = tree.query_pairs(snap_tol, output_type="ndarray")
        for a, b in pairs:
            ra, rb = find(int(a)), find(int(b))
            if ra != rb:
                parent[rb] = ra
                snap_count += 1

    # Coalesce: each cluster → mean vertex (so nearby projected points become
    # a single shared vertex). Then rebuild polygons with new indices.
    clusters: Dict[int, List[int]] = {}
    for i in range(len(pool)):
        clusters.setdefault(find(i), []).append(i)
    new_v: List[np.ndarray] = []
    root_to_new: Dict[int, int] = {}
    for r, idxs in clusters.items():
        root_to_new[r] = len(new_v)
        new_v.append(pool[idxs].mean(axis=0))
    new_v = np.array(new_v)

    new_polys: Dict[int, np.ndarray] = {}
    for gi, idx_list in face_idx.items():
        cleaned = []
        for i in idx_list:
            ni = root_to_new[find(i)]
            if not cleaned or cleaned[-1] != ni:
                cleaned.append(ni)
        if len(cleaned) > 1 and cleaned[-1] == cleaned[0]:
            cleaned = cleaned[:-1]
        if len(cleaned) >= 3:
            new_polys[gi] = new_v[cleaned]

    info["n_polygons_after"] = len(new_polys)
    info["max_d2p_after"] = _max_d2p(new_polys)
    info["max_displacement"] = max_disp
    info["snap_pairs_merged"] = snap_count

    return new_polys, info


# ---------------------------------------------------------------------------
# Pipeline orchestration
# ---------------------------------------------------------------------------


def run_one(prims, pids, gt_b, cond_name: str, cond: Dict, bid: int):
    """Run a single (building, condition) pipeline. Returns metrics."""
    _assert_gravity()
    groups, centers, labels = v4_to_groups(prims, pids)
    n_v4_groups = len(groups)
    if n_v4_groups < 4:
        return {"skipped": True, "reason": f"only {n_v4_groups} v4 groups"}

    # --- Step 1: orientation ---
    if cond["step1"]:
        centroid_inside_orient_all(groups, centers)
    else:
        orient_normals_outward(groups, centers.mean(axis=0))

    # --- Add ground + bbox ---
    wall_centers = centers[labels == 2]
    add_ground_surface(groups, wall_centers, centers.mean(axis=0))
    n_bbox = add_bbox_planes(groups, centers)

    # If Step 1 enabled: also re-apply centroid-inside to the freshly added
    # ground/bbox planes (their construction is canonical so they're already
    # outward, but we keep the contract uniform).
    if cond["step1"]:
        centroid_inside_orient_all(groups, centers)

    # --- Step 2.5: support_d ---
    apply_step2_5 = cond["step2_5"]
    if apply_step2_5:
        apply_support_d(groups, centers)

    # --- Inside ratio (post-orient) ---
    inside_ratios = []
    for g in groups:
        n = g["plane_normal"]
        d = g["plane_d"]
        ir = float((centers @ n - d < 0).mean())
        inside_ratios.append(ir)
    inside_ratios = np.array(inside_ratios)

    # --- Polytope build ---
    polygons, info = build_polytope_with_patches(groups, centers,
                                                  patch1=cond["patch1"])
    if polygons is None or len(polygons) < 4:
        return {
            "skipped": True,
            "reason": (info.get("error") if info else "polytope_None"),
            "n_v4_groups": n_v4_groups,
            "n_planes": len(groups),
            "mean_inside_ratio": float(inside_ratios.mean()),
            "n_planes_low_inside": int((inside_ratios < 0.85).sum()),
        }

    # --- CityJSON + val3dity ---
    bdir = WORK_DIR / cond_name / f"building_{bid:02d}"
    bdir.mkdir(parents=True, exist_ok=True)
    cj_result = build_cityjson(bid, groups, polygons, bdir)
    if cj_result is None:
        return {"skipped": True, "reason": "build_cityjson_None"}

    cj_path = bdir / "building.city.json"
    rp_path = bdir / "val3dity.json"
    v3d_raw = _run_val3dity(cj_path, rp_path)
    v3d = _summarize_val3dity(v3d_raw)

    # --- Geometry metrics ---
    cj = json.loads(cj_path.read_text())
    s = np.asarray(cj["transform"]["scale"])
    t = np.asarray(cj["transform"]["translate"])
    v_pred = np.asarray(cj["vertices"]) * s + t
    h_pred = float(v_pred[:, 1].max() - v_pred[:, 1].min())
    pred_vol = float(abs(cj_result.get("signed_volume", 0.0)))

    # GT
    gt_v = np.concatenate([f["vertices"] for f in gt_b["faces"]], axis=0)
    h_gt = float(gt_v[:, 1].max() - gt_v[:, 1].min())
    gt_bbox = float(np.prod(gt_v.max(axis=0) - gt_v.min(axis=0)))

    # GT solid volume (anchored fan; from Phase 0a logic)
    gt_centroid = gt_v.mean(axis=0)
    vol_gt = 0.0
    for f in gt_b["faces"]:
        verts = np.asarray(f["vertices"], dtype=np.float64).copy()
        nf = np.asarray(f["normal"], dtype=np.float64)
        nf /= np.linalg.norm(nf) + 1e-12
        cf = np.asarray(f["centroid"], dtype=np.float64)
        if np.dot(nf, cf - gt_centroid) < 0:
            verts = verts[::-1]
        v0 = verts[0] - gt_centroid
        for i in range(1, len(verts) - 1):
            v1 = verts[i] - gt_centroid
            v2 = verts[i + 1] - gt_centroid
            vol_gt += float(np.dot(v0, np.cross(v1, v2))) / 6.0
    vol_gt = abs(vol_gt)

    return {
        "type": gt_b["type"],
        "n_v4_groups": n_v4_groups,
        "n_planes": int(len(groups)),
        "n_bbox_added": int(n_bbox),
        "n_polygons": int(len(polygons)),
        "n_vertices": int(cj_result.get("n_vertices", 0)),
        "n_surfaces": int(cj_result.get("n_surfaces", 0)),
        "output_h": h_pred,
        "GT_h": h_gt,
        "abs_h": abs(h_pred - h_gt),
        "output_vol": pred_vol,
        "GT_vol": vol_gt,
        "GT_bbox_vol": gt_bbox,
        "vol_ratio": pred_vol / max(vol_gt, 1e-9),
        "coverage": pred_vol / max(gt_bbox, 1e-9),
        "val3dity_valid": bool(v3d["valid"]),
        "val3dity_errors": list(v3d.get("error_codes", [])),
        "S4_max_d2p_before": info.get("max_d2p_before", float("nan")),
        "S4_max_d2p": info.get("max_d2p_after", float("nan")),
        "S4_max_displacement": info.get("max_displacement", 0.0),
        "S4_snap_pairs": info.get("snap_pairs_merged", 0),
        "mean_inside_ratio": float(inside_ratios.mean()),
        "n_planes_low_inside": int((inside_ratios < 0.85).sum()),
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

    # results[bid][cond_name] = metrics
    results: Dict[int, Dict[str, Dict]] = {}
    for bid in TARGET_BIDS:
        if bid not in asg or len(asg[bid]) < 100:
            continue
        gt_b = next(b for b in gt["buildings"] if b["building_id"] == bid)
        results[bid] = {"type": gt_b["type"]}
        for cond_name, cond in CONDITIONS:
            print(f"\n=== B{bid} {gt_b['type']} {cond_name} ===")
            try:
                m = run_one(prims, asg[bid], gt_b, cond_name, cond, bid)
            except Exception as e:
                m = {"skipped": True,
                     "reason": f"{type(e).__name__}: {e}"}
            results[bid][cond_name] = m
            if m.get("skipped"):
                print(f"  → SKIP ({m.get('reason')})")
            else:
                print(f"  → h={m['output_h']:.2f}/{m['GT_h']:.2f} "
                      f"|Δh|={m['abs_h']:.2f} cov={m['coverage']*100:.1f}% "
                      f"v3d={'✓' if m['val3dity_valid'] else '✗'+str(m['val3dity_errors'])} "
                      f"S4_max_d2p={m['S4_max_d2p']*1000:.2f}mm")

    (WORK_DIR / "p1_3b_metrics.json").write_text(
        json.dumps(results, default=lambda o: float(o) if isinstance(
            o, np.generic) else str(o), indent=2))

    # ====================================================================
    # Build report
    # ====================================================================
    L: List[str] = []
    L.append("# P1-3b — backend fix + support-plane adapter (1st round)\n")
    L.append("**Mutual ckpt, 5 buildings × 4 conditions = 20 runs.** "
             "GT for evaluation only. v4 parameters P1-2-fixed.\n")
    L.append("`gravity = [0, 1, 0]` asserted in every entry.\n")
    L.append(f"Clean cases (Hard/Strong GO): **B{', B'.join(map(str, CLEAN_BIDS))}**. "
             f"Regression watch: B{REGRESSION_BID}. Reference (not in GO): "
             f"B{REFERENCE_BID}.\n")

    L.append("Conditions:\n")
    L.append("```")
    L.append("        Patch 1   Step 1     Step 2.5")
    L.append("C0        ×          ×           ×       (P1-3 baseline)")
    L.append("C1        ✓          ×           ×       (backend only)")
    L.append("C2        ✓          ✓           ×       (+ orientation)")
    L.append("C3        ✓          ✓           ✓       (+ d_support)")
    L.append("```\n")

    # ----- Table 1 -----
    L.append("## Table 1 — per-(building, condition)\n")
    L.append("| bid | cond | n_planes | output_h | GT_h | \\|Δh\\| | "
             "output_vol | vol_ratio | coverage | val3dity | "
             "S4_max_d2p | mean_inside_ratio |")
    L.append("|---|---|---|---|---|---|---|---|---|---|---|---|")
    for bid in TARGET_BIDS:
        if bid not in results:
            continue
        for cond_name, _ in CONDITIONS:
            m = results[bid][cond_name]
            if m.get("skipped"):
                L.append(f"| {bid} | {cond_name} | - | SKIP | - | - | "
                         f"- | - | - | {m.get('reason')} | - | - |")
                continue
            v3d_str = ("✓" if m["val3dity_valid"]
                        else f"✗{m['val3dity_errors']}")
            L.append(f"| {bid} | {cond_name} | {m['n_planes']} | "
                     f"{m['output_h']:.2f}m | {m['GT_h']:.2f}m | "
                     f"**{m['abs_h']:.2f}m** | "
                     f"{m['output_vol']:.0f} | "
                     f"{m['vol_ratio']:.2f} | "
                     f"{m['coverage']*100:.1f}% | "
                     f"{v3d_str} | "
                     f"{m['S4_max_d2p']*1000:.2f}mm | "
                     f"{m['mean_inside_ratio']:.3f} |")
    L.append("")

    # ----- dominant_fix attribution -----
    def _quality(m: Dict) -> float:
        """Lower is better — combines |Δh|, val3dity, vol_ratio."""
        if m.get("skipped"):
            return 1e9
        # Distance from "perfect": Δh + 5×(1-vol_ratio in [0,1]) + 10·(¬val3dity)
        dh = m["abs_h"]
        vr_pen = 5.0 * max(0.0, 1.0 - min(m["vol_ratio"], 1.0))
        v3_pen = 0.0 if m["val3dity_valid"] else 10.0
        return dh + vr_pen + v3_pen

    def _dominant_fix(per_cond: Dict[str, Dict]) -> Tuple[str, str]:
        """Find the single transition (C0→C1, C1→C2, C2→C3) with the largest
        quality improvement."""
        if any(per_cond[c].get("skipped") for c in ("C0", "C1", "C2", "C3")):
            return ("n/a", "skip")
        q0 = _quality(per_cond["C0"])
        q1 = _quality(per_cond["C1"])
        q2 = _quality(per_cond["C2"])
        q3 = _quality(per_cond["C3"])
        d_b = q0 - q1
        d_o = q1 - q2
        d_d = q2 - q3
        deltas = [("backend", d_b), ("orientation", d_o), ("d_support", d_d)]
        deltas.sort(key=lambda t: -t[1])
        # If top two are within 10% of each other → "combo"
        top = deltas[0]
        second = deltas[1]
        if top[1] > 0 and second[1] > 0 and (top[1] - second[1]) < 0.1 * abs(top[1]):
            return ("combo", "n/a")
        # If everything is non-positive → no fix dominates
        if top[1] <= 0:
            return ("none", "no improvement")
        return (top[0], "n/a")

    # ----- Table 2 — best condition per building -----
    L.append("## Table 2 — best condition + dominant_fix\n")
    L.append("| bid | role | best_cond | output_h | \\|Δh\\| | coverage | "
             "val3dity | dominant_fix |")
    L.append("|---|---|---|---|---|---|---|---|")
    role_of = {bid: ("clean" if bid in CLEAN_BIDS
                     else ("regression" if bid == REGRESSION_BID
                           else "reference")) for bid in TARGET_BIDS}
    dominants: Dict[int, str] = {}
    for bid in TARGET_BIDS:
        if bid not in results:
            continue
        per_cond = {cn: results[bid][cn] for cn, _ in CONDITIONS}
        # best by quality
        best_cn = min((cn for cn, _ in CONDITIONS),
                      key=lambda c: _quality(per_cond[c]))
        bm = per_cond[best_cn]
        dom, _why = _dominant_fix(per_cond)
        dominants[bid] = dom
        if bm.get("skipped"):
            L.append(f"| {bid} | {role_of[bid]} | {best_cn} | SKIP | - | - "
                     f"| - | {dom} |")
        else:
            v3d_str = ("✓" if bm["val3dity_valid"]
                        else f"✗{bm['val3dity_errors']}")
            L.append(f"| {bid} | {role_of[bid]} | **{best_cn}** | "
                     f"{bm['output_h']:.2f}m | {bm['abs_h']:.2f}m | "
                     f"{bm['coverage']*100:.1f}% | {v3d_str} | "
                     f"**{dom}** |")
    L.append("")

    # ----- Table 3 — B2 regression check -----
    L.append("## Table 3 — B2 regression watch\n")
    if REGRESSION_BID in results:
        c0 = results[REGRESSION_BID]["C0"]
        c3 = results[REGRESSION_BID]["C3"]
        L.append("| bid | C0 height | C3 height | Δ | C0 v3d | C3 v3d | "
                 "regression? |")
        L.append("|---|---|---|---|---|---|---|")
        if c0.get("skipped") or c3.get("skipped"):
            L.append(f"| 2 | - | - | - | skip | skip | n/a |")
        else:
            dh = c3["output_h"] - c0["output_h"]
            v3d_kept = (c0["val3dity_valid"] == c3["val3dity_valid"]) or c3["val3dity_valid"]
            regression = (abs(dh) > 1.0) or (c0["val3dity_valid"] and not c3["val3dity_valid"])
            L.append(f"| 2 | {c0['output_h']:.2f}m | {c3['output_h']:.2f}m | "
                     f"{dh:+.2f}m | "
                     f"{'✓' if c0['val3dity_valid'] else '✗'} | "
                     f"{'✓' if c3['val3dity_valid'] else '✗'} | "
                     f"{'**YES**' if regression else 'no'} |")
    L.append("")

    # ----- Table 4 — B0 reference -----
    L.append("## Table 4 — B0 reference (backend ablation)\n")
    if REFERENCE_BID in results:
        L.append("| cond | output_h | vol_ratio | val3dity | "
                 "S4_max_d2p_before | S4_max_d2p_after |")
        L.append("|---|---|---|---|---|---|")
        for cond_name, _ in CONDITIONS:
            m = results[REFERENCE_BID][cond_name]
            if m.get("skipped"):
                L.append(f"| {cond_name} | SKIP | - | - | - | - |"); continue
            v3d_str = ("✓" if m["val3dity_valid"]
                        else f"✗{m['val3dity_errors']}")
            L.append(f"| {cond_name} | {m['output_h']:.2f}m | "
                     f"{m['vol_ratio']:.2f} | {v3d_str} | "
                     f"{m['S4_max_d2p_before']*1000:.2f}mm | "
                     f"{m['S4_max_d2p']*1000:.2f}mm |")
    L.append("")

    # ----- GO/NG verdict -----
    L.append("## Hard / Strong GO verdict (clean cases B1/B6/B21, C3)\n")
    hard_pass = []
    strong_pass = []
    for bid in CLEAN_BIDS:
        m = results.get(bid, {}).get("C3", {})
        if m.get("skipped"):
            continue
        h_ok = m["abs_h"] < 2.0
        v3d_ok = m["val3dity_valid"]
        cov_ok = m["coverage"] * 100 >= 50.0
        if h_ok and v3d_ok:
            hard_pass.append(bid)
            if cov_ok:
                strong_pass.append(bid)

    # B2 regression
    b2c0 = results.get(REGRESSION_BID, {}).get("C0", {})
    b2c3 = results.get(REGRESSION_BID, {}).get("C3", {})
    b2_dh = (abs(b2c3.get("output_h", 0) - b2c0.get("output_h", 0))
             if not b2c0.get("skipped") and not b2c3.get("skipped")
             else float("inf"))
    b2_v3d_kept = (not b2c0.get("val3dity_valid", False)
                   or b2c3.get("val3dity_valid", False))
    b2_regression_ok = (b2_dh < 1.0 and b2_v3d_kept)

    n_hard = len(hard_pass)
    n_strong = len(strong_pass)
    L.append(f"- B1/B6/B21 hard pass (\\|Δh\\|<2m AND val3dity ✓): "
             f"**{n_hard}/3** ({hard_pass})")
    L.append(f"- B2 regression: \\|Δh\\|={b2_dh:.2f}m, "
             f"val3dity kept={b2_v3d_kept} → "
             f"{'OK' if b2_regression_ok else '**REGRESSION**'}")
    hard_go = (n_hard == 3 and b2_regression_ok)
    strong_go = (hard_go and n_strong == 3)
    L.append(f"- **Hard GO** (3/3 + B2 OK): {'✓' if hard_go else '✗'}")
    L.append(f"- **Strong GO** (Hard + 3/3 coverage ≥50%): "
             f"{'✓' if strong_go else '✗'} ({n_strong}/3 cov ≥50%)\n")

    # ----- Branch decision -----
    L.append("## Round 2 branch decision\n")
    if hard_go and strong_go:
        L.append("All clean cases pass Hard + Strong GO. **P1-4 진행.**")
    elif hard_go:
        L.append("Hard GO 통과 / Strong GO 일부 미달. coverage gap 분석 후 "
                 "round 2에서 robust q (q<1.0) 또는 wall envelope adapter 검토.")
    else:
        # Per-building diagnosis
        ng_b1 = 1 in CLEAN_BIDS and 1 not in hard_pass
        ng_b6 = 6 in CLEAN_BIDS and 6 not in hard_pass
        ng_b21 = 21 in CLEAN_BIDS and 21 not in hard_pass
        msgs = []
        if ng_b1 and not ng_b6 and not ng_b21:
            msgs.append("B1만 NG → wall envelope adapter / inside_ratio filter (round 2)")
        if ng_b6 and not ng_b1 and not ng_b21:
            msgs.append("B6만 NG → hip-roof multi-plane → roof candidate "
                         "reduction (round 2)")
        if ng_b21 and not ng_b1 and not ng_b6:
            msgs.append("B21만 NG → roof selection 또는 coverage 단독 분기 검토")
        if ng_b1 and ng_b6 and ng_b21:
            msgs.append("**전건물 NG** → adapter 설계 자체 재검토 필요")
        if not msgs and (n_hard < 3):
            msgs.append("일부 NG — 위 표 1·2 참조하여 각 건물 root cause 결정")
        # Check d_support side-effect
        for bid in CLEAN_BIDS:
            c2 = results.get(bid, {}).get("C2", {})
            c3 = results.get(bid, {}).get("C3", {})
            if c2.get("skipped") or c3.get("skipped"):
                continue
            if (c2["abs_h"] < c3["abs_h"] - 0.5
                or (c2["val3dity_valid"] and not c3["val3dity_valid"])):
                msgs.append(f"B{bid} C2 > C3 → d_support 역효과, q<1.0 도입 필요")
        # val3dity + S4 issues
        for bid in CLEAN_BIDS:
            c3 = results.get(bid, {}).get("C3", {})
            if c3.get("skipped"):
                continue
            if (not c3["val3dity_valid"]
                    and c3["S4_max_d2p"] > 0.010):
                msgs.append(f"B{bid} val3dity NG + S4_max_d2p>10mm → "
                             "Patch 1 미작동 또는 추가 backend 버그")
        for m in (msgs if msgs else ["세부 분기는 표 1·2 참조"]):
            L.append(f"- {m}")
    L.append("")

    # ----- Self-verification -----
    L.append("## Self-verification\n")
    n_runs = sum(1 for bid in TARGET_BIDS for cn, _ in CONDITIONS
                  if bid in results and cn in results[bid])
    n_assigned = sum(1 for bid in TARGET_BIDS
                     if bid in results and dominants.get(bid))
    # C0 reproduces P1-3?
    p1_3_path = OUT_DIR / "p1_3/p1_3_metrics.json"
    p1_3 = (json.loads(p1_3_path.read_text()) if p1_3_path.exists() else {})
    c0_match = []
    for bid in TARGET_BIDS:
        if bid not in results:
            continue
        c0m = results[bid]["C0"]
        ref = p1_3.get("v4", {}).get(str(bid)) or p1_3.get("v4", {}).get(bid)
        if c0m.get("skipped") or not ref:
            continue
        # Compare height (within 0.1m)
        if abs(c0m["output_h"] - ref.get("height_pred", float("nan"))) < 0.1:
            c0_match.append(bid)
    L.append(f"- gravity = [0, 1, 0] asserted: ✓")
    L.append(f"- 5 buildings × 4 conditions = 20 runs: "
             f"{'✓' if n_runs == 20 else f'✗ ({n_runs}/20)'}")
    L.append(f"- C0 reproduces P1-3 v4 height: "
             f"{len(c0_match)}/{len(TARGET_BIDS)} "
             f"({'✓' if len(c0_match) == 5 else 'partial'})")
    L.append(f"- dominant_fix assigned to all buildings: "
             f"{'✓' if n_assigned == len(results) else 'partial'}")
    L.append(f"- Patch 1 shell closure (C1+ S4_max_d2p < 1mm): "
             + ", ".join(f"B{bid}={results[bid]['C1']['S4_max_d2p']*1000:.2f}mm"
                         for bid in TARGET_BIDS
                         if bid in results
                         and not results[bid]["C1"].get("skipped")))
    L.append("")

    out_md = OUT_DIR / "P1_3b_REPORT.md"
    out_md.write_text("\n".join(L))
    print(f"\nReport → {out_md}")
    return results


if __name__ == "__main__":
    main()
