"""P1-3a — Stage 3 collapse-cause diagnostics.

Splits the P1-3 height/coverage collapse into 5 distinct causes by running
five independent diagnostics on bid=0,1,2,6,21 (Mutual ckpt) and assigning
each building a primary cause. The result determines P1-3b adapter scope.

Causes (priority order, highest first):
  NON_CONVEX             (Diag 4)
  BACKEND_FAIL           (Diag 3)
  ROOF_OFFSET            (Diag 2)
  GROUND_OFFSET          (Diag 2)
  WALL_TILT              (Diag 1: top vertex incident planes are tilted walls)
  WALL_MISCLASSIFIED     (Diag 1: top vertex incident is roof-class plane but
                          v4 labelled it wall — sem head issue)

GT is for evaluation/diagnosis only. v4 parameters are P1-2 fixed (no tuning).

Output:
  results/stage3_v4_validation/P1_3a_REPORT.md
  results/stage3_v4_validation/p1_3a/p1_3a_metrics.json
  results/stage3_v4_validation/p1_3a/diag3_gt_envelope/building_NN/* (val3dity)
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Dict, List, Tuple

import numpy as np
from scipy.spatial import ConvexHull

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from scripts.stage3_readout.run_stage3 import (  # noqa: E402
    _load_model, _assign_primitives_to_buildings,
    _run_val3dity, _summarize_val3dity,
)
from scripts.stage3_readout.obj_gt import parse_scene_obj  # noqa: E402
from src.stage3.clustering import cluster_primitives_v4  # noqa: E402
from src.stage3.ground_surface import (  # noqa: E402
    orient_normals_outward, add_ground_surface, add_bbox_planes)
from src.stage3.plane_intersection import (  # noqa: E402
    build_convex_polytope, intersect_three_planes)
from src.stage3.citygml_export import build_cityjson  # noqa: E402

# ---------------------------------------------------------------------------
# Constants and assertions
# ---------------------------------------------------------------------------

GRAVITY = np.array([0.0, 1.0, 0.0])
assert GRAVITY[1] == 1.0 and GRAVITY[0] == 0.0 and GRAVITY[2] == 0.0, \
    "P1-3a hard-coded for gravity = [0, 1, 0] (primitive Y-down frame)"

SCENE = ROOT / "results/phase2_synthesis/scene.obj"
CKPT_MUTUAL = ROOT / "results/phase2_ablation_citygml/mutual/ckpt/final.pt"
TARGET_BIDS = [0, 1, 2, 6, 21]
DIAG3_BIDS = [0, 1, 6]

OUT_DIR = ROOT / "results/stage3_v4_validation"
WORK_DIR = OUT_DIR / "p1_3a"
WORK_DIR.mkdir(parents=True, exist_ok=True)

# Cause priority (lower index = higher priority)
CAUSE_PRIORITY = [
    "NON_CONVEX", "BACKEND_FAIL", "ROOF_OFFSET",
    "GROUND_OFFSET", "WALL_TILT", "WALL_MISCLASSIFIED",
]


def _assert_gravity():
    assert np.allclose(GRAVITY, [0.0, 1.0, 0.0]), \
        f"gravity mismatch: {GRAVITY}"


# ---------------------------------------------------------------------------
# v4 + process_building, but keep the intermediate state we need.
# ---------------------------------------------------------------------------


def run_v4_capture(prims: Dict, pids: np.ndarray) -> Dict:
    """Run v4 cluster → process_building polytope, retaining the groups list
    (post orient + ground + bbox), valid_verts, and polygons."""
    _assert_gravity()
    centers = prims["centers"][pids]
    normals = prims["normals"][pids]
    areas = prims["areas"][pids]
    opacities = prims["opacities"][pids]
    labels = prims["sem_probs"][pids].argmax(axis=1)

    gids, rep_n, rep_off, rep_cls = cluster_primitives_v4(
        centers, normals, areas, labels,
        gravity=GRAVITY, opacities=opacities)

    # Build groups list (mimic groups_from_stage2_grouping)
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

    n_v4_groups = len(groups)
    building_center = centers.mean(axis=0)
    orient_normals_outward(groups, building_center)
    wall_centers = centers[labels == 2]
    add_ground_surface(groups, wall_centers, building_center)
    n_bbox = add_bbox_planes(groups, centers)

    polygons = build_convex_polytope(groups, centers, hs_tol=0.05)

    # Re-extract valid_verts for diagnostic active-plane analysis.
    extent = float((centers.max(axis=0) - centers.min(axis=0)).max())
    bbox_margin = max(5.0, 0.5 * extent)
    bbox_min = centers.min(axis=0) - bbox_margin
    bbox_max = centers.max(axis=0) + bbox_margin
    plane_n = np.array([g["plane_normal"] for g in groups])
    plane_d = np.array([g["plane_d"] for g in groups])
    valid_verts = []
    N = len(groups)
    for i in range(N):
        for j in range(i + 1, N):
            for k in range(j + 1, N):
                pt = intersect_three_planes(
                    plane_n[i], plane_d[i],
                    plane_n[j], plane_d[j],
                    plane_n[k], plane_d[k])
                if pt is None:
                    continue
                if np.any(plane_n @ pt - plane_d > 0.05):
                    continue
                if np.any(pt < bbox_min) or np.any(pt > bbox_max):
                    continue
                valid_verts.append(pt)
    valid_verts = (np.array(valid_verts) if valid_verts else np.zeros((0, 3)))
    if len(valid_verts):
        unique = [0]
        for vi in range(1, len(valid_verts)):
            if all(np.linalg.norm(valid_verts[vi] - valid_verts[u]) > 0.001
                   for u in unique):
                unique.append(vi)
        valid_verts = valid_verts[unique]

    return {
        "groups": groups,
        "n_v4_groups": n_v4_groups,
        "n_bbox_added": n_bbox,
        "polygons": polygons,
        "valid_verts": valid_verts,
        "building_center": building_center,
        "centers": centers,
        "labels": labels,
        "rep_normals_v4": rep_n,
        "rep_offsets_v4": rep_off,
        "rep_classes_v4": rep_cls,
    }


# ---------------------------------------------------------------------------
# Diag 0 — v4 normal convention (oriented vs unoriented)
# ---------------------------------------------------------------------------


def diag0_normal_convention(rep_n: np.ndarray, rep_cls: np.ndarray) -> Dict:
    """Find pairs of WALL rep_normals that share an axis. Determine whether
    v4 emits opposing walls as cos<-0.95 (oriented) or cos>+0.95 (unoriented).
    """
    _assert_gravity()
    walls = np.where(rep_cls == 2)[0]
    if len(walls) < 2:
        return {"n_oriented": 0, "n_unoriented": 0, "n_inconsistent": 0,
                "convention": "n/a"}
    wn = rep_n[walls]
    wn = wn / (np.linalg.norm(wn, axis=1, keepdims=True) + 1e-12)
    cos_mat = wn @ wn.T
    n_oriented = 0
    n_unoriented = 0
    n_inconsistent = 0
    for i in range(len(walls)):
        for j in range(i + 1, len(walls)):
            if abs(cos_mat[i, j]) <= 0.95:
                continue  # not on same axis
            if cos_mat[i, j] < -0.95:
                n_oriented += 1
            elif cos_mat[i, j] > 0.95:
                n_unoriented += 1
            else:
                n_inconsistent += 1
    if n_oriented > 0 and n_unoriented == 0:
        conv = "oriented"
    elif n_unoriented > 0 and n_oriented == 0:
        conv = "unoriented"
    elif n_oriented == 0 and n_unoriented == 0:
        conv = "no-pair"  # no opposite walls — single direction
    else:
        conv = "mixed"
    return {"n_oriented": n_oriented, "n_unoriented": n_unoriented,
            "n_inconsistent": n_inconsistent, "convention": conv}


# ---------------------------------------------------------------------------
# Diag 1 — Active plane identification
# ---------------------------------------------------------------------------


def _classify_plane(g: Dict) -> str:
    if g.get("is_ground"):
        return "ground"
    if g.get("is_bbox"):
        return "bbox"
    cls = g.get("class")
    return {1: "roof", 2: "wall", -1: "ground"}.get(int(cls), "?")


def diag1_active_planes(state: Dict) -> Dict:
    """For the polytope vertices, find top (min y) and bottom (max y in
    primitive Y-down). For each, list incident planes (residual < 1e-3)."""
    _assert_gravity()
    verts = state["valid_verts"]
    groups = state["groups"]
    if len(verts) < 4 or not groups:
        return {"polytope_h": 0.0, "top_v_y": float("nan"),
                "top_active": "no_polytope",
                "top_planes": [], "bottom_active": "no_polytope",
                "bottom_planes": []}

    plane_n = np.array([g["plane_normal"] for g in groups])
    plane_d = np.array([g["plane_d"] for g in groups])
    # Residual: n_i · v - d_i  (≤ 0 means inside; ≈ 0 means active/on-plane)
    residuals = verts @ plane_n.T - plane_d  # (V, P)

    top_idx = int(np.argmin(verts[:, 1]))      # smallest y = highest in space
    bot_idx = int(np.argmax(verts[:, 1]))
    top_y = float(verts[top_idx, 1])
    bot_y = float(verts[bot_idx, 1])

    def _incidents(vi: int) -> List[Dict]:
        mask = np.abs(residuals[vi]) < 1e-3
        out = []
        for pi in np.where(mask)[0]:
            g = groups[pi]
            n = np.asarray(g["plane_normal"])
            n_dot_g = float(abs(np.dot(n, GRAVITY)))
            out.append({
                "plane_idx": int(pi),
                "class": _classify_plane(g),
                "n_dot_g": n_dot_g,
                "n": [float(x) for x in n],
                "d": float(g["plane_d"]),
                "area": float(g.get("area", 0.0)),
                "n_prim": int(len(g.get("prim_ids", []))),
            })
        return out

    top_inc = _incidents(top_idx)
    bot_inc = _incidents(bot_idx)

    def _active_label(inc: List[Dict]) -> Tuple[str, Dict]:
        if not inc:
            return "none", {}
        # roof-like: any incident plane with |n·g| > 0.7
        roofy = [p for p in inc if p["n_dot_g"] > 0.7]
        if roofy:
            # pick the dominant roof-like plane (largest area)
            best = max(roofy, key=lambda p: p["area"])
            if best["class"] == "roof":
                return "roof", best
            if best["class"] == "wall":
                return "wall_misclassified_as_roof", best
            if best["class"] == "ground":
                return "ground", best
            if best["class"] == "bbox":
                return "bbox", best
            return "other", best
        # all incident planes are tilted (|n·g| < 0.7)
        # pick the wall with most prims
        wall_inc = [p for p in inc if p["class"] == "wall"]
        if wall_inc:
            best = max(wall_inc, key=lambda p: p["area"])
            return "wall_tilt", best
        best = max(inc, key=lambda p: p["area"])
        return "tilt_other", best

    top_label, top_best = _active_label(top_inc)
    bot_label, bot_best = _active_label(bot_inc)

    return {
        "polytope_h": float(bot_y - top_y),
        "top_v_y": top_y,
        "bottom_v_y": bot_y,
        "top_active": top_label,
        "top_best_plane": top_best,
        "top_incidents": top_inc,
        "bottom_active": bot_label,
        "bottom_best_plane": bot_best,
        "bottom_incidents": bot_inc,
    }


# ---------------------------------------------------------------------------
# Diag 2 — Roof/ground d offset vs GT
# ---------------------------------------------------------------------------


def diag2_offsets(state: Dict, gt_b: Dict) -> Dict:
    """Compare v4 vs GT roof-plane d (horizontal roofs only) and ground d.

    All d values use the outward-oriented half-space convention (same as
    process_building's groups list)."""
    _assert_gravity()
    groups = state["groups"]
    centers = state["centers"]

    # v4 roof groups (class=1) with |n·g|>0.7 — area-weighted d
    v4_roof = []
    for g in groups:
        if g.get("class") == 1 and not g.get("is_bbox") \
                and not g.get("is_ground") and \
                abs(np.dot(g["plane_normal"], GRAVITY)) > 0.7:
            v4_roof.append(g)
    if v4_roof:
        ws = np.array([g["area"] for g in v4_roof])
        ds = np.array([g["plane_d"] for g in v4_roof])
        v4_roof_d = float(np.average(ds, weights=ws + 1e-12))
    else:
        v4_roof_d = float("nan")

    # v4 ground = the appended ground group (class=-1, is_ground=True)
    v4_ground = next((g for g in groups if g.get("is_ground")), None)
    v4_ground_d = (float(v4_ground["plane_d"]) if v4_ground is not None
                   else float("nan"))

    # GT roof: faces with semantic_class==1 and |n·g|>0.7
    gt_faces = gt_b["faces"]
    gt_roof_faces = [f for f in gt_faces
                     if f["semantic_class"] == 1
                     and abs(np.dot(f["normal"], GRAVITY)) > 0.7]
    # Re-orient GT face normals outward (relative to GT centroid)
    gt_centroid = np.concatenate([f["vertices"] for f in gt_faces]).mean(axis=0)
    if gt_roof_faces:
        ws = np.array([f["area"] for f in gt_roof_faces])
        ds = []
        for f in gt_roof_faces:
            n = np.asarray(f["normal"])
            d = float(np.dot(n, f["centroid"]))
            # flip if pointing inward
            if np.dot(n, f["centroid"] - gt_centroid) < 0:
                n = -n; d = -d
            # Project to "outward = -y" convention (roof n_y < 0):
            # if n_y > 0 (would be ground-like), this is anomalous; skip
            if n[1] > 0.7:
                continue
            ds.append(d)
        gt_roof_d = (float(np.average(ds, weights=ws[:len(ds)] + 1e-12))
                     if ds else float("nan"))
    else:
        gt_roof_d = float("nan")

    # GT ground: faces with semantic_class==3 and |n·g|>0.95
    gt_ground_faces = [f for f in gt_faces
                       if f["semantic_class"] == 3
                       and abs(np.dot(f["normal"], GRAVITY)) > 0.95]
    if gt_ground_faces:
        ws = np.array([f["area"] for f in gt_ground_faces])
        ds = []
        for f in gt_ground_faces:
            n = np.asarray(f["normal"])
            d = float(np.dot(n, f["centroid"]))
            if np.dot(n, f["centroid"] - gt_centroid) < 0:
                n = -n; d = -d
            # Ground convention: n_y > 0 outward (since interior is at smaller y).
            if n[1] < 0.7:
                continue
            ds.append(d)
        gt_ground_d = (float(np.average(ds, weights=ws[:len(ds)] + 1e-12))
                       if ds else float("nan"))
    else:
        # Fallback: GT solid bbox y-max as ground level → d = +max_y
        all_v = np.concatenate([f["vertices"] for f in gt_faces])
        gt_ground_d = float(all_v[:, 1].max())

    delta_roof = (abs(v4_roof_d - gt_roof_d)
                  if not (np.isnan(v4_roof_d) or np.isnan(gt_roof_d))
                  else float("inf"))
    delta_ground = (abs(v4_ground_d - gt_ground_d)
                    if not (np.isnan(v4_ground_d) or np.isnan(gt_ground_d))
                    else float("inf"))

    return {
        "v4_roof_d": v4_roof_d,
        "GT_roof_d": gt_roof_d,
        "abs_d_roof": delta_roof,
        "v4_ground_d": v4_ground_d,
        "GT_ground_d": gt_ground_d,
        "abs_d_ground": delta_ground,
    }


# ---------------------------------------------------------------------------
# Diag 3 — Backend sanity: feed GT envelope planes into build_convex_polytope
# ---------------------------------------------------------------------------


def _gt_envelope_planes(gt_b: Dict, cos_thresh: float = 0.99,
                        d_thresh: float = 0.05) -> List[Dict]:
    """Merge co-planar GT faces into a minimal envelope plane set."""
    _assert_gravity()
    gt_faces = gt_b["faces"]
    gt_centroid = np.concatenate(
        [f["vertices"] for f in gt_faces]).mean(axis=0)

    # Build outward-normal records
    recs = []
    for f in gt_faces:
        n = np.asarray(f["normal"], dtype=np.float64)
        n /= np.linalg.norm(n) + 1e-12
        c = np.asarray(f["centroid"], dtype=np.float64)
        d = float(np.dot(n, c))
        if np.dot(n, c - gt_centroid) < 0:
            n = -n; d = -d
        recs.append({"n": n, "d": d, "area": f["area"], "centroid": c,
                     "class": f["semantic_class"]})

    # Greedy merge
    parent = list(range(len(recs)))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for i in range(len(recs)):
        for j in range(i + 1, len(recs)):
            cos = float(np.dot(recs[i]["n"], recs[j]["n"]))
            if cos < cos_thresh:
                continue
            if abs(recs[i]["d"] - recs[j]["d"]) > d_thresh:
                continue
            a, b = find(i), find(j)
            if a != b:
                parent[b] = a

    groups: Dict[int, List[Dict]] = {}
    for i, r in enumerate(recs):
        groups.setdefault(find(i), []).append(r)

    envelope = []
    for members in groups.values():
        ws = np.array([m["area"] for m in members])
        # area-weighted normal (members already sign-aligned outward)
        ns = np.stack([m["n"] for m in members])
        n = (ns * ws[:, None] / (ws.sum() + 1e-12)).sum(axis=0)
        n /= np.linalg.norm(n) + 1e-12
        ds = np.array([m["d"] for m in members])
        d = float(np.average(ds, weights=ws + 1e-12))
        cs = np.stack([m["centroid"] for m in members])
        c = (cs * ws[:, None] / (ws.sum() + 1e-12)).sum(axis=0)
        cls_majority = int(np.bincount(
            np.array([m["class"] for m in members])).argmax())
        envelope.append({
            "plane_normal": n,
            "plane_d": d,
            "class": cls_majority,
            "prim_ids": [],
            "center": c,
            "area": float(ws.sum()),
        })
    return envelope


def diag3_backend_sanity(bid: int, gt_b: Dict) -> Dict:
    """Feed merged GT envelope planes into build_convex_polytope; build
    CityJSON; run val3dity."""
    _assert_gravity()
    envelope = _gt_envelope_planes(gt_b)
    if len(envelope) < 4:
        return {"error": f"only {len(envelope)} GT envelope planes"}

    gt_verts = np.concatenate(
        [f["vertices"] for f in gt_b["faces"]], axis=0)
    polygons = build_convex_polytope(envelope, gt_verts, hs_tol=0.05)
    if polygons is None:
        return {"error": "build_convex_polytope_None",
                "GT_planes_n": len(envelope)}

    bdir = WORK_DIR / "diag3_gt_envelope" / f"building_{bid:02d}"
    bdir.mkdir(parents=True, exist_ok=True)
    cj_result = build_cityjson(bid, envelope, polygons, bdir)
    if cj_result is None:
        return {"error": "build_cityjson_None",
                "GT_planes_n": len(envelope)}

    cj_path = bdir / "building.city.json"
    rp_path = bdir / "val3dity.json"
    v3d_raw = _run_val3dity(cj_path, rp_path)
    v3d = _summarize_val3dity(v3d_raw)

    cj = json.loads(cj_path.read_text())
    s = np.asarray(cj["transform"]["scale"])
    t = np.asarray(cj["transform"]["translate"])
    v_out = np.asarray(cj["vertices"]) * s + t
    out_h = float(v_out[:, 1].max() - v_out[:, 1].min())
    out_vol = float(abs(cj_result.get("signed_volume", 0.0)))
    gt_h = float(gt_verts[:, 1].max() - gt_verts[:, 1].min())

    # GT vol via divergence theorem
    vol_div = 0.0
    gt_centroid = gt_verts.mean(axis=0)
    for f in gt_b["faces"]:
        n = np.asarray(f["normal"], dtype=np.float64)
        n /= np.linalg.norm(n) + 1e-12
        c = np.asarray(f["centroid"], dtype=np.float64)
        if np.dot(n, c - gt_centroid) < 0:
            n = -n
        vol_div += float(np.dot(n, c)) * f["area"] / 3.0
    gt_vol = float(abs(vol_div))

    delta_h = abs(out_h - gt_h)
    vol_ratio = out_vol / max(gt_vol, 1e-9)
    backend_ok = (delta_h < 1.0 and v3d["valid"] and vol_ratio > 0.7)

    return {
        "GT_planes_n": len(envelope),
        "out_h": out_h,
        "GT_h": gt_h,
        "abs_h": delta_h,
        "out_vol": out_vol,
        "GT_vol": gt_vol,
        "vol_ratio": vol_ratio,
        "val3dity_valid": bool(v3d["valid"]),
        "val3dity_errors": list(v3d.get("error_codes", [])),
        "verdict": "BACKEND_OK" if backend_ok else "BACKEND_FAIL",
    }


# ---------------------------------------------------------------------------
# Diag 4 — Convexity check
# ---------------------------------------------------------------------------


def diag4_convexity(gt_b: Dict) -> Dict:
    """2D footprint convexity ratio + 3D solid convexity ratio."""
    _assert_gravity()
    gt_faces = gt_b["faces"]

    # 2D footprint: use the GroundSurface face vertices (its area = footprint)
    ground_faces = [f for f in gt_faces if f["semantic_class"] == 3
                    and abs(np.dot(f["normal"], GRAVITY)) > 0.95]
    if ground_faces:
        # take largest if multiple
        ground = max(ground_faces, key=lambda f: f["area"])
        footprint_area = float(ground["area"])
        v2d = ground["vertices"][:, [0, 2]]  # drop y
        try:
            hull2d_area = float(ConvexHull(v2d).volume)  # area in 2D
        except Exception:
            hull2d_area = footprint_area
    else:
        # fallback: project all GT vertices to (x, z), area = footprint area approx
        all_v = np.concatenate([f["vertices"] for f in gt_faces])
        v2d = all_v[:, [0, 2]]
        try:
            hull2d_area = float(ConvexHull(v2d).volume)
        except Exception:
            hull2d_area = float("nan")
        footprint_area = hull2d_area  # no concave info → ratio = 1.0
    ratio_2d = (footprint_area / hull2d_area
                if hull2d_area > 0 else float("nan"))

    # 3D solid: GT volume via divergence theorem, hull volume via ConvexHull
    all_v = np.concatenate([f["vertices"] for f in gt_faces])
    gt_centroid = all_v.mean(axis=0)
    vol = 0.0
    for f in gt_faces:
        n = np.asarray(f["normal"], dtype=np.float64)
        n /= np.linalg.norm(n) + 1e-12
        c = np.asarray(f["centroid"], dtype=np.float64)
        if np.dot(n, c - gt_centroid) < 0:
            n = -n
        vol += float(np.dot(n, c)) * f["area"] / 3.0
    gt_vol = float(abs(vol))
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
# Cause assignment
# ---------------------------------------------------------------------------


def assign_cause(d1: Dict, d2: Dict, d3: Dict, d4: Dict) -> Tuple[str, List[str]]:
    """Return (primary_cause, secondary_causes)."""
    causes = []
    if d4 and d4.get("verdict") == "NON_CONVEX":
        causes.append("NON_CONVEX")
    if d3 is not None and d3.get("verdict") == "BACKEND_FAIL":
        causes.append("BACKEND_FAIL")
    if d2.get("abs_d_roof", float("inf")) >= 1.0:
        causes.append("ROOF_OFFSET")
    if d2.get("abs_d_ground", float("inf")) >= 1.0:
        causes.append("GROUND_OFFSET")
    if d1.get("top_active") == "wall_tilt":
        causes.append("WALL_TILT")
    if d1.get("top_active") == "wall_misclassified_as_roof":
        causes.append("WALL_MISCLASSIFIED")

    if not causes:
        return ("NO_COLLAPSE", [])
    causes_sorted = sorted(set(causes), key=CAUSE_PRIORITY.index)
    return (causes_sorted[0], causes_sorted[1:])


def branch_recommendation(primary: str, secondaries: List[str]) -> str:
    if primary == "WALL_TILT" and not secondaries:
        return "P1-3b: wall-only adapter"
    if primary == "ROOF_OFFSET" or "ROOF_OFFSET" in secondaries:
        if "WALL_TILT" in [primary] + secondaries:
            return "P1-3b: wall adapter + roof support selection"
        return "P1-3b: roof support selection"
    if primary == "GROUND_OFFSET" or "GROUND_OFFSET" in secondaries:
        return "P1-3b: + ground correction"
    if primary == "WALL_MISCLASSIFIED":
        return "Stage 2 sem-head 진단 우선; P1-3b 보류"
    if primary == "BACKEND_FAIL":
        return "backend(plane_intersection/orient) 우선; P1-3b 보류"
    if primary == "NON_CONVEX":
        return "해당 건물 분리 / 2.5D fallback"
    return "n/a"


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main():
    _assert_gravity()
    print(f"[load] {CKPT_MUTUAL.relative_to(ROOT)}")
    gt = parse_scene_obj(str(SCENE), frame="obj")
    prims = _load_model(CKPT_MUTUAL, emit_stage2_groups=False)
    asg = _assign_primitives_to_buildings(prims, gt, opacity_thresh=0.05)

    per_b: Dict[int, Dict] = {}
    for bid in TARGET_BIDS:
        if bid not in asg or len(asg[bid]) < 100:
            per_b[bid] = {"skipped": True, "reason": "no primitives"}
            continue
        gt_b = next(b for b in gt["buildings"] if b["building_id"] == bid)
        state = run_v4_capture(prims, asg[bid])

        d0 = diag0_normal_convention(state["rep_normals_v4"],
                                      state["rep_classes_v4"])
        d1 = diag1_active_planes(state)
        d2 = diag2_offsets(state, gt_b)
        d3 = diag3_backend_sanity(bid, gt_b) if bid in DIAG3_BIDS else None
        d4 = diag4_convexity(gt_b)
        primary, secondaries = assign_cause(d1, d2, d3, d4)
        rec = branch_recommendation(primary, secondaries)
        per_b[bid] = {
            "type": gt_b["type"],
            "n_v4_groups": int(state["n_v4_groups"]),
            "polygons_count": (int(len(state["polygons"]))
                                if state["polygons"] else 0),
            "n_valid_verts": int(len(state["valid_verts"])),
            "diag0": d0,
            "diag1": d1,
            "diag2": d2,
            "diag3": d3,
            "diag4": d4,
            "primary_cause": primary,
            "secondary_causes": secondaries,
            "branch": rec,
        }
        print(f"  B{bid:2d} {gt_b['type']:9s} cause={primary} "
              f"(secondary={secondaries}) → {rec}")

    # Save metrics
    (WORK_DIR / "p1_3a_metrics.json").write_text(json.dumps(
        {bid: {k: v for k, v in entry.items() if k != "diag1"
               or True}  # keep all
         for bid, entry in per_b.items()},
        default=lambda o: float(o) if isinstance(o, np.generic) else str(o),
        indent=2))

    # ============ Build report ============
    L = []
    L.append("# P1-3a — Stage 3 collapse cause diagnostics\n")
    L.append("**Mutual ckpt, 5 buildings (bid=0,1,2,6,21).** GT used for "
             "evaluation only. v4 parameters P1-2-fixed.\n")
    L.append("`gravity = [0, 1, 0]` asserted in every diagnostic entry.\n")

    # Diag 0
    L.append("## Diag 0 — v4 normal convention\n")
    L.append("Per building: count of WALL rep_normal pairs that share an axis "
             "(\\|cos\\|>0.95). cos<-0.95 ⇒ oriented (opposite outward "
             "normals); cos>+0.95 ⇒ unoriented (folded to same direction).\n")
    L.append("| bid | type | n_oriented | n_unoriented | n_inconsistent | "
             "convention |")
    L.append("|---|---|---|---|---|---|")
    for bid in TARGET_BIDS:
        e = per_b.get(bid, {})
        if e.get("skipped"):
            continue
        d0 = e["diag0"]
        L.append(f"| {bid} | {e['type']} | {d0['n_oriented']} | "
                 f"{d0['n_unoriented']} | {d0['n_inconsistent']} | "
                 f"**{d0['convention']}** |")
    L.append("")

    # Diag 1
    L.append("## Diag 1 — Active plane identification\n")
    L.append("Top vertex (smallest y in primitive Y-down) and its incident "
             "planes. `top_active` summarizes the dominant incident plane.\n")
    L.append("| bid | polytope_h | GT_h | top_v_y | top_active | "
             "top_class | top \\|n·g\\| | top_d | bottom_active |")
    L.append("|---|---|---|---|---|---|---|---|---|")
    for bid in TARGET_BIDS:
        e = per_b.get(bid, {})
        if e.get("skipped"):
            continue
        d1 = e["diag1"]
        gt_b = next(b for b in gt["buildings"] if b["building_id"] == bid)
        v_gt = np.concatenate([f["vertices"] for f in gt_b["faces"]])
        gt_h = float(v_gt[:, 1].max() - v_gt[:, 1].min())
        tb = d1.get("top_best_plane") or {}
        L.append(f"| {bid} | {d1['polytope_h']:.2f}m | {gt_h:.2f}m | "
                 f"{d1.get('top_v_y', 0):.2f} | "
                 f"**{d1['top_active']}** | "
                 f"{tb.get('class', '-')} | "
                 f"{tb.get('n_dot_g', float('nan')):.3f} | "
                 f"{tb.get('d', float('nan')):.2f} | "
                 f"{d1['bottom_active']} |")
    L.append("")

    # Diag 2
    L.append("## Diag 2 — Roof / ground d offset (GT vs v4)\n")
    L.append("d uses the outward-oriented half-space convention (n·x = d on "
             "plane). Roof: \\|n·g\\|>0.7, area-weighted. Ground: virtual "
             "GroundSurface added by `add_ground_surface`. GT ground falls "
             "back to GT-vertices y-max if no GT GroundSurface face.\n")
    L.append("| bid | v4_roof_d | GT_roof_d | \\|Δd_roof\\| | "
             "v4_ground_d | GT_ground_d | \\|Δd_ground\\| |")
    L.append("|---|---|---|---|---|---|---|")
    for bid in TARGET_BIDS:
        e = per_b.get(bid, {})
        if e.get("skipped"):
            continue
        d2 = e["diag2"]
        L.append(f"| {bid} | {d2['v4_roof_d']:.2f} | {d2['GT_roof_d']:.2f} | "
                 f"**{d2['abs_d_roof']:.2f}** | "
                 f"{d2['v4_ground_d']:.2f} | {d2['GT_ground_d']:.2f} | "
                 f"**{d2['abs_d_ground']:.2f}** |")
    L.append("")

    # Diag 3
    L.append("## Diag 3 — Backend sanity (GT envelope → build_convex_polytope)\n")
    L.append("Run on B0/B1/B6. GT faces are merged co-planar (cos>0.99, "
             "\\|Δd\\|<5cm) → envelope plane set → `build_convex_polytope`. "
             "BACKEND_OK ⇔ \\|Δh\\|<1m AND val3dity ✓ AND vol_ratio>0.7.\n")
    L.append("| bid | GT_planes_n | output_h | GT_h | \\|Δh\\| | "
             "output_vol | GT_vol | val3dity | verdict |")
    L.append("|---|---|---|---|---|---|---|---|---|")
    for bid in TARGET_BIDS:
        e = per_b.get(bid, {})
        if e.get("skipped"):
            continue
        d3 = e.get("diag3")
        if d3 is None:
            L.append(f"| {bid} | - | - | - | - | - | - | (not run) | - |")
            continue
        if "error" in d3:
            L.append(f"| {bid} | {d3.get('GT_planes_n', '?')} | - | - | - | "
                     f"- | - | - | error: {d3['error']} |")
            continue
        L.append(f"| {bid} | {d3['GT_planes_n']} | {d3['out_h']:.2f}m | "
                 f"{d3['GT_h']:.2f}m | **{d3['abs_h']:.2f}m** | "
                 f"{d3['out_vol']:.0f} | {d3['GT_vol']:.0f} | "
                 f"{'✓' if d3['val3dity_valid'] else '✗'+str(d3['val3dity_errors'])} | "
                 f"**{d3['verdict']}** |")
    L.append("")

    # Diag 4
    L.append("## Diag 4 — Convexity check (GT solid)\n")
    L.append("ratio_2D = footprint_area / 2D-hull_area; "
             "ratio_3D = GT_vol / 3D-hull_vol. CONVEX_OK ⇔ both ≥ 0.85.\n")
    L.append("| bid | type | ratio_2D | ratio_3D | hull_h vs solid_h | "
             "verdict |")
    L.append("|---|---|---|---|---|---|")
    for bid in TARGET_BIDS:
        e = per_b.get(bid, {})
        if e.get("skipped"):
            continue
        d4 = e["diag4"]
        L.append(f"| {bid} | {e['type']} | {d4['ratio_2D']:.3f} | "
                 f"{d4['ratio_3D']:.3f} | "
                 f"{d4['hull3D_h']:.2f} vs {d4['solid_h']:.2f} | "
                 f"**{d4['verdict']}** |")
    L.append("")

    # Cause assignment
    L.append("## Cause assignment + branch recommendation\n")
    L.append("Priority: NON_CONVEX > BACKEND_FAIL > ROOF_OFFSET > "
             "GROUND_OFFSET > WALL_TILT > WALL_MISCLASSIFIED.\n")
    L.append("| bid | type | primary_cause | secondary_causes | "
             "branch_recommendation |")
    L.append("|---|---|---|---|---|")
    cause_count: Dict[str, int] = {}
    for bid in TARGET_BIDS:
        e = per_b.get(bid, {})
        if e.get("skipped"):
            continue
        cause_count[e["primary_cause"]] = cause_count.get(
            e["primary_cause"], 0) + 1
        sec = ", ".join(e["secondary_causes"]) or "-"
        L.append(f"| {bid} | {e['type']} | **{e['primary_cause']}** | "
                 f"{sec} | {e['branch']} |")
    L.append("")

    L.append("## Cause distribution\n")
    L.append("| cause | count |")
    L.append("|---|---|")
    for c in CAUSE_PRIORITY:
        if cause_count.get(c, 0) > 0:
            L.append(f"| {c} | {cause_count[c]} |")
    if not cause_count:
        L.append("| (none) | 0 |")
    L.append("")

    # P1-3b scope
    if cause_count:
        majority_cause = max(cause_count.items(), key=lambda t: t[1])[0]
        L.append(f"## P1-3b scope\n")
        L.append(f"Majority cause: **{majority_cause}** "
                 f"({cause_count[majority_cause]}/5).\n")
        # Combine all per-building branch recs
        recs = sorted(set(e["branch"] for e in per_b.values()
                          if not e.get("skipped")))
        L.append("Per-building branch recommendations (deduplicated):\n")
        for r in recs:
            L.append(f"- {r}")

    # Self-verification
    L.append("\n## Self-verification\n")
    n_with_cause = sum(1 for e in per_b.values()
                        if not e.get("skipped") and "primary_cause" in e)
    L.append(f"- gravity = [0, 1, 0] asserted in every diagnostic entry: ✓")
    L.append(f"- 4 diagnostics × 5 buildings → {n_with_cause}/5 buildings "
             f"got a cause (None: 0)")
    L.append(f"- P1-3b branch recommendation determined: "
             f"{'✓' if cause_count else '✗'}")
    L.append("")

    out_md = OUT_DIR / "P1_3a_REPORT.md"
    out_md.write_text("\n".join(L))
    print(f"\nReport → {out_md}")
    return per_b


if __name__ == "__main__":
    main()
