"""PolyFit Phase 2 — methodology re-test with CGAL repair recipe.

Stage A: GT scene.obj input (방법론 검증).
Stage B: v4 envelope input (데이터 검증, A 통과 시).

Metrics (per building):
  val3dity_valid, output_h, GT_h, |Δh|, coverage, vol_ratio,
  Hausdorff, Chamfer

Both meshes (GT solid, PolyFit OFF) are converted to triangulated point clouds
sampled at 5000 surface points; mutual KDTree distances give symmetric
Hausdorff and Chamfer.

Outputs:
  results/stage3_polyfit_phase2/{stageA,stageB}/building_NN/{
      input.txt, output.off, building.city.json, val3dity.json}
  results/stage3_polyfit_phase2/figures/*.png
  results/stage3_polyfit_phase2/REPORT.md
  results/stage3_polyfit_phase2/metrics.json
"""
from __future__ import annotations

import json
import subprocess
import sys
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
from scipy.spatial import ConvexHull, cKDTree
from scipy.stats import trim_mean
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d.art3d import Poly3DCollection

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from scripts.stage3_readout.run_stage3 import (  # noqa: E402
    _load_model, _assign_primitives_to_buildings,
    _run_val3dity, _summarize_val3dity)
from scripts.stage3_readout.obj_gt import parse_scene_obj  # noqa: E402
from src.stage3.clustering import cluster_primitives_v4  # noqa: E402

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

GRAVITY = np.array([0.0, 1.0, 0.0])
SCENE = ROOT / "results/phase2_synthesis/scene.obj"
CKPT_MUTUAL = ROOT / "results/phase2_ablation_citygml/mutual/ckpt/final.pt"
POLYFIT_CLI = ROOT / "src/stage3/polyfit_cli"
OUT_DIR = ROOT / "results/stage3_polyfit_phase2"
OUT_DIR.mkdir(parents=True, exist_ok=True)
(OUT_DIR / "figures").mkdir(parents=True, exist_ok=True)

# Same set as P1-3a Phase 1 — direct comparison
STAGE_A_BIDS = [0, 1, 2, 3, 4, 5, 6, 7, 8, 9]   # +1 (bid 3 included for parser diagnosis)
STAGE_B_BIDS = [0, 1, 2, 6, 21]
N_SAMPLE = 5000


# ---------------------------------------------------------------------------
# cluster_planes (verbatim from gt_polyfit_test.py for reproducibility)
# ---------------------------------------------------------------------------


def cluster_planes(faces, cos_tol=0.98, dist_tol=0.2):
    planes = []
    for fi, f in enumerate(faces):
        n = np.array(f["normal"]); c = np.array(f["centroid"])
        matched = False
        for p in planes:
            cos = float(np.dot(n, p["normal"]))
            if abs(cos) < cos_tol:
                continue
            proj = float(np.dot(p["normal"], c)) - p["d"]
            if abs(proj) < dist_tol:
                p["faces"].append(fi); matched = True; break
        if not matched:
            d = float(np.dot(n, c))
            planes.append({"normal": n.copy(), "d": d, "faces": [fi]})
    return [(p["normal"], p["d"], p["faces"]) for p in planes]


def sample_points_on_face(face, n_samples):
    verts = np.array(face["vertices"])
    if verts.shape[0] < 3:
        return np.array([face["centroid"]])
    centroid = np.array(face["centroid"])
    pts = [centroid]
    for v in verts:
        pts.append(v)
    for i in range(len(verts)):
        pts.append((verts[i] + verts[(i + 1) % len(verts)]) / 2)
    pts = np.array(pts)
    if len(pts) > n_samples:
        idx = np.random.default_rng(42).choice(len(pts), n_samples, replace=False)
        pts = pts[idx]
    return pts


def build_polyfit_input_from_gt_faces(faces, target_n_points=500):
    planes = cluster_planes(faces)
    total_area = sum(f["area"] for f in faces)
    all_pts, all_normals, all_pids = [], [], []
    for pi, (pn, _pd, fis) in enumerate(planes):
        for fi in fis:
            f = faces[fi]
            n_per_face = max(8, int(round(target_n_points * f["area"] / total_area)))
            pts = sample_points_on_face(f, n_per_face)
            all_pts.append(pts)
            all_normals.append(np.tile(pn, (len(pts), 1)))
            all_pids.append(np.full(len(pts), pi))
    if not all_pts:
        return None, None, None, 0
    all_pts = np.concatenate(all_pts)
    all_normals = np.concatenate(all_normals)
    all_pids = np.concatenate(all_pids)
    return all_pts, all_normals, all_pids, len(planes)


# ---------------------------------------------------------------------------
# v4 envelope → polyfit input (Stage B)
# ---------------------------------------------------------------------------


def build_polyfit_input_from_v4(prims, pids, target_n_points=500):
    """Use v4 cluster output as PolyFit input. Each v4 group = 1 plane.
    Sample its primitive centres + a small grid of nearby points for density.
    """
    centers = prims["centers"][pids]
    normals = prims["normals"][pids]
    areas = prims["areas"][pids]
    opacities = prims["opacities"][pids]
    labels = prims["sem_probs"][pids].argmax(axis=1)
    gids, rep_n, rep_off, rep_cls = cluster_primitives_v4(
        centers, normals, areas, labels,
        gravity=GRAVITY, opacities=opacities)
    K = len(rep_n)
    if K < 4:
        return None, None, None, 0

    # area per group (sum of primitive areas), allocate points proportionally
    group_areas = np.array([areas[gids == k].sum() for k in range(K)])
    total_a = group_areas.sum()
    all_pts, all_normals, all_pids = [], [], []
    for k in range(K):
        m = gids == k
        if int(m.sum()) == 0:
            continue
        n_per_group = max(8, int(round(target_n_points * group_areas[k]
                                       / max(total_a, 1e-12))))
        c_sub = centers[m]
        if len(c_sub) > n_per_group:
            idx = np.random.default_rng(42).choice(len(c_sub),
                                                    n_per_group, replace=False)
            c_sub = c_sub[idx]
        all_pts.append(c_sub)
        n_unit = rep_n[k] / (np.linalg.norm(rep_n[k]) + 1e-12)
        all_normals.append(np.tile(n_unit, (len(c_sub), 1)))
        all_pids.append(np.full(len(c_sub), k))
    if not all_pts:
        return None, None, None, 0
    return (np.concatenate(all_pts), np.concatenate(all_normals),
            np.concatenate(all_pids), K)


def write_polyfit_input(path: Path, pts, normals, pids, n_planes):
    with open(path, "w") as f:
        f.write(f"{len(pts)} {n_planes}\n")
        for i in range(len(pts)):
            f.write(f"{pts[i,0]:.4f} {pts[i,1]:.4f} {pts[i,2]:.4f} "
                    f"{normals[i,0]:.4f} {normals[i,1]:.4f} {normals[i,2]:.4f} "
                    f"{int(pids[i])}\n")


def run_polyfit_cli(input_path: Path, output_path: Path,
                    timeout: int = 300) -> Tuple[bool, str]:
    cmd = [str(POLYFIT_CLI), str(input_path), str(output_path)]
    import os
    env = os.environ.copy()
    env["LD_LIBRARY_PATH"] = (
        "/opt/conda/lib:" + env.get("LD_LIBRARY_PATH", ""))
    try:
        r = subprocess.run(cmd, capture_output=True, text=True,
                           timeout=timeout, env=env)
        ok = r.returncode == 0 and output_path.exists()
        msg = (r.stderr.strip().split("\n")[-1] if r.stderr else "")
        # Capture full stderr for diagnostics
        if not ok and r.stderr:
            (output_path.parent / "polyfit_stderr.log").write_text(r.stderr)
        return ok, msg
    except subprocess.TimeoutExpired:
        return False, "timeout"


# ---------------------------------------------------------------------------
# OFF → CityJSON (mostly verbatim from gt_polyfit_test.py)
# ---------------------------------------------------------------------------


def off_to_cityjson(off_path: Path, building_id: int,
                    out_dir: Path, scale: float = 0.001) -> Optional[Dict]:
    lines = off_path.read_text().splitlines()
    if not lines or not lines[0].strip().startswith("OFF"):
        return None

    def _skip(idx):
        while idx < len(lines) and (
            not lines[idx].strip() or lines[idx].strip().startswith("#")):
            idx += 1
        return idx

    i = _skip(1)
    counts = lines[i].split()
    n_v, n_f = int(counts[0]), int(counts[1])
    i = _skip(i + 1)
    verts = []
    read = 0
    while read < n_v and i < len(lines):
        if not lines[i].strip():
            i += 1; continue
        tok = lines[i].split()
        verts.append([float(tok[0]), float(tok[1]), float(tok[2])])
        i += 1; read += 1
    faces = []
    read = 0
    while read < n_f and i < len(lines):
        if not lines[i].strip():
            i += 1; continue
        tok = lines[i].split()
        k = int(tok[0])
        faces.append([int(tok[1 + j]) for j in range(k)])
        i += 1; read += 1
    if n_f < 4:
        return None

    translate = [min(v[j] for v in verts) for j in range(3)]
    t_ijk = [round(translate[j] / scale) for j in range(3)]
    qvert_map: Dict = {}
    int_verts: List = []
    remap = [0] * len(verts)
    for vi, v in enumerate(verts):
        key = tuple(round(v[j] / scale) for j in range(3))
        if key not in qvert_map:
            qvert_map[key] = len(int_verts)
            int_verts.append([key[j] - t_ijk[j] for j in range(3)])
        remap[vi] = qvert_map[key]
    boundaries = []
    for f in faces:
        ring = [remap[i] for i in f]
        cleaned = [ring[0]]
        for idx in ring[1:]:
            if idx != cleaned[-1]:
                cleaned.append(idx)
        if len(cleaned) > 1 and cleaned[-1] == cleaned[0]:
            cleaned = cleaned[:-1]
        if len(cleaned) >= 3:
            boundaries.append([cleaned])
    if len(boundaries) < 4:
        return None

    def _sv():
        vol = 0
        for bnd in boundaries:
            ring = bnd[0]
            if len(ring) < 3: continue
            pts = [np.array(int_verts[i]) * scale for i in ring]
            for k in range(1, len(pts) - 1):
                vol += float(np.dot(pts[0], np.cross(pts[k], pts[k + 1])))
        return vol / 6.0
    vol = _sv()
    if vol < 0:
        for b in boundaries:
            b[0] = b[0][::-1]
        vol = -vol

    sem_surfaces = [{"type": "RoofSurface"}]
    sem_values = [0] * len(boundaries)
    bname = f"building_{building_id:03d}"
    cityjson = {
        "type": "CityJSON", "version": "2.0",
        "transform": {"scale": [scale] * 3, "translate": translate},
        "CityObjects": {
            bname: {
                "type": "Building",
                "attributes": {"building_id": int(building_id),
                               "signed_volume": vol},
                "geometry": [{
                    "type": "Solid", "lod": "2",
                    "boundaries": [boundaries],
                    "semantics": {"surfaces": sem_surfaces,
                                  "values": [sem_values]},
                }],
            }
        },
        "vertices": int_verts,
    }
    out_path = out_dir / "building.city.json"
    out_path.write_text(json.dumps(cityjson, indent=2))
    return {"cityjson_path": str(out_path),
            "n_surfaces": len(boundaries),
            "n_vertices": len(int_verts),
            "signed_volume": vol}


# ---------------------------------------------------------------------------
# Mesh sampling + distance metrics
# ---------------------------------------------------------------------------


def _triangulate_polygon(verts: np.ndarray) -> np.ndarray:
    """Fan triangulate a planar polygon (V, 3) → (T, 3, 3) triangles."""
    V = len(verts)
    if V < 3:
        return np.empty((0, 3, 3))
    return np.stack([np.stack([verts[0], verts[i], verts[i + 1]])
                     for i in range(1, V - 1)], axis=0)


def _sample_triangles(triangles: np.ndarray, n: int,
                      seed: int = 0) -> np.ndarray:
    """Uniform sampling on union of triangles, area-weighted."""
    if len(triangles) == 0:
        return np.empty((0, 3))
    e1 = triangles[:, 1] - triangles[:, 0]
    e2 = triangles[:, 2] - triangles[:, 0]
    areas = 0.5 * np.linalg.norm(np.cross(e1, e2), axis=1)
    A = areas.sum()
    if A <= 0:
        return np.empty((0, 3))
    rng = np.random.default_rng(seed)
    tri_idx = rng.choice(len(triangles), n, p=areas / A)
    u = rng.random(n)
    v = rng.random(n)
    mask = u + v > 1
    u[mask] = 1 - u[mask]
    v[mask] = 1 - v[mask]
    pts = (triangles[tri_idx, 0]
           + u[:, None] * (triangles[tri_idx, 1] - triangles[tri_idx, 0])
           + v[:, None] * (triangles[tri_idx, 2] - triangles[tri_idx, 0]))
    return pts


def gt_mesh_triangles(gt_b: Dict) -> np.ndarray:
    tris = []
    for f in gt_b["faces"]:
        verts = np.asarray(f["vertices"], dtype=np.float64)
        tris.append(_triangulate_polygon(verts))
    return np.concatenate(tris, axis=0) if tris else np.empty((0, 3, 3))


def cj_mesh_triangles(cj_path: Path) -> np.ndarray:
    cj = json.loads(cj_path.read_text())
    s = np.asarray(cj["transform"]["scale"])
    t = np.asarray(cj["transform"]["translate"])
    V = np.asarray(cj["vertices"], dtype=np.float64) * s + t
    tris = []
    for cobj in cj["CityObjects"].values():
        for geom in cobj.get("geometry", []):
            for shell in geom["boundaries"]:
                for face in shell:
                    ring = face[0] if isinstance(face[0], list) else face
                    poly = V[ring]
                    tris.append(_triangulate_polygon(poly))
    return np.concatenate(tris, axis=0) if tris else np.empty((0, 3, 3))


def hausdorff_chamfer(P: np.ndarray, Q: np.ndarray) -> Tuple[float, float]:
    if len(P) == 0 or len(Q) == 0:
        return float("nan"), float("nan")
    tP = cKDTree(P); tQ = cKDTree(Q)
    dPQ, _ = tQ.query(P)  # P → Q
    dQP, _ = tP.query(Q)  # Q → P
    hausdorff = float(max(dPQ.max(), dQP.max()))
    chamfer = float(0.5 * (dPQ.mean() + dQP.mean()))
    return hausdorff, chamfer


def gt_volume_anchored(gt_b: Dict) -> float:
    faces = gt_b["faces"]
    all_v = np.concatenate([f["vertices"] for f in faces])
    c0 = all_v.mean(axis=0)
    vol = 0.0
    for f in faces:
        verts = np.asarray(f["vertices"], dtype=np.float64).copy()
        n = np.asarray(f["normal"]); n /= np.linalg.norm(n) + 1e-12
        cf = np.asarray(f["centroid"])
        if np.dot(n, cf - c0) < 0:
            verts = verts[::-1]
        v0 = verts[0] - c0
        for i in range(1, len(verts) - 1):
            vol += float(np.dot(v0, np.cross(verts[i] - c0,
                                              verts[i + 1] - c0))) / 6.0
    return abs(vol)


# ---------------------------------------------------------------------------
# Pipeline: input → polyfit → cityjson → val3dity → metrics
# ---------------------------------------------------------------------------


def run_one(stage: str, bid: int, gt_b: Dict, work_dir: Path,
            input_builder, *args, **kwargs) -> Dict:
    work_dir.mkdir(parents=True, exist_ok=True)
    pts, normals, pids, n_planes = input_builder(*args, **kwargs)
    if pts is None or n_planes < 4:
        return {"stage": stage, "bid": bid, "skipped": True,
                "reason": f"input_builder returned n_planes={n_planes}"}

    in_path = work_dir / "polyfit_input.txt"
    off_path = work_dir / "polyfit_output.off"
    write_polyfit_input(in_path, pts, normals, pids, n_planes)

    ok, msg = run_polyfit_cli(in_path, off_path)
    if not ok:
        return {"stage": stage, "bid": bid, "skipped": True,
                "reason": f"polyfit_fail: {msg}",
                "n_planes": int(n_planes), "n_pts": int(len(pts))}

    cj_result = off_to_cityjson(off_path, bid, work_dir)
    if cj_result is None:
        return {"stage": stage, "bid": bid, "skipped": True,
                "reason": "off_to_cityjson_None",
                "n_planes": int(n_planes), "n_pts": int(len(pts))}

    cj_path = Path(cj_result["cityjson_path"])
    rp_path = work_dir / "val3dity.json"
    v3d_raw = _run_val3dity(cj_path, rp_path)
    v3d = _summarize_val3dity(v3d_raw)

    # Heights
    cj = json.loads(cj_path.read_text())
    s = np.asarray(cj["transform"]["scale"])
    t = np.asarray(cj["transform"]["translate"])
    V_pred = np.asarray(cj["vertices"]) * s + t
    h_pred = float(V_pred[:, 1].max() - V_pred[:, 1].min())
    pred_vol = float(abs(cj_result["signed_volume"]))

    gt_v = np.concatenate([f["vertices"] for f in gt_b["faces"]])
    h_gt = float(gt_v[:, 1].max() - gt_v[:, 1].min())
    gt_bbox_vol = float(np.prod(gt_v.max(axis=0) - gt_v.min(axis=0)))
    gt_vol = gt_volume_anchored(gt_b)

    # Hausdorff / Chamfer (sampled point clouds)
    pred_tris = cj_mesh_triangles(cj_path)
    gt_tris = gt_mesh_triangles(gt_b)
    P = _sample_triangles(pred_tris, N_SAMPLE, seed=0)
    Q = _sample_triangles(gt_tris, N_SAMPLE, seed=1)
    hausdorff, chamfer = hausdorff_chamfer(P, Q)

    return {
        "stage": stage,
        "bid": bid,
        "type": gt_b["type"],
        "skipped": False,
        "n_planes": int(n_planes),
        "n_pts": int(len(pts)),
        "n_surfaces": int(cj_result["n_surfaces"]),
        "n_vertices": int(cj_result["n_vertices"]),
        "output_h": h_pred,
        "GT_h": h_gt,
        "abs_h": abs(h_pred - h_gt),
        "output_vol": pred_vol,
        "GT_vol": gt_vol,
        "GT_bbox_vol": gt_bbox_vol,
        "vol_ratio": pred_vol / max(gt_vol, 1e-9),
        "coverage": pred_vol / max(gt_bbox_vol, 1e-9),
        "hausdorff": hausdorff,
        "chamfer": chamfer,
        "val3dity_valid": bool(v3d["valid"]),
        "val3dity_errors": list(v3d.get("error_codes", [])),
    }


# ---------------------------------------------------------------------------
# Visualization
# ---------------------------------------------------------------------------


def _plot_triangles(ax, tris: np.ndarray, color: str, alpha: float = 0.4):
    if len(tris) == 0:
        return
    coll = Poly3DCollection(tris, facecolors=color, edgecolors="k",
                             linewidth=0.2, alpha=alpha)
    ax.add_collection3d(coll)
    pts = tris.reshape(-1, 3)
    ax.set_xlim(pts[:, 0].min(), pts[:, 0].max())
    ax.set_ylim(pts[:, 1].min(), pts[:, 1].max())
    ax.set_zlim(pts[:, 2].min(), pts[:, 2].max())


def make_side_by_side_figure(stage: str, bid: int, gt_b: Dict,
                              cj_path: Optional[Path], out_png: Path):
    fig = plt.figure(figsize=(10, 5))
    ax1 = fig.add_subplot(1, 2, 1, projection="3d")
    ax2 = fig.add_subplot(1, 2, 2, projection="3d")
    gt_tris = gt_mesh_triangles(gt_b)
    _plot_triangles(ax1, gt_tris, "steelblue", alpha=0.45)
    ax1.set_title(f"GT  (B{bid} {gt_b['type']})")
    if cj_path and cj_path.exists():
        pred_tris = cj_mesh_triangles(cj_path)
        _plot_triangles(ax2, pred_tris, "darkorange", alpha=0.45)
        ax2.set_title(f"PolyFit  ({stage})")
    else:
        ax2.set_title("(no PolyFit output)")
    for ax in (ax1, ax2):
        ax.set_xlabel("x"); ax.set_ylabel("y"); ax.set_zlabel("z")
    plt.tight_layout()
    plt.savefig(out_png, dpi=110, bbox_inches="tight")
    plt.close()


# ---------------------------------------------------------------------------
# bid 3 parser diagnostic
# ---------------------------------------------------------------------------


def diagnose_bid3(gt_b: Dict, work_dir: Path) -> Dict:
    work_dir.mkdir(parents=True, exist_ok=True)
    pts, normals, pids, n_planes = build_polyfit_input_from_gt_faces(
        gt_b["faces"])
    in_path = work_dir / "polyfit_input.txt"
    if pts is None:
        return {"error": "input_builder None"}
    write_polyfit_input(in_path, pts, normals, pids, n_planes)
    lines = in_path.read_text().splitlines()
    line55 = lines[54] if len(lines) > 54 else ""
    issues = []
    expected_max_pid = n_planes - 1
    out_of_range_pids = 0
    for li, line in enumerate(lines[1:], start=2):
        tok = line.split()
        if len(tok) != 7:
            issues.append((li, "bad_fields", line[:120]))
            if len(issues) >= 5: break
        else:
            try:
                pid = int(tok[6])
                if pid < 0 or pid > expected_max_pid:
                    out_of_range_pids += 1
            except ValueError:
                issues.append((li, "non_int_pid", line[:120]))
                if len(issues) >= 5: break
    return {
        "n_planes": int(n_planes),
        "n_lines_input": int(len(lines)),
        "line_55_raw": line55,
        "n_issues_first_5": issues,
        "out_of_range_pids": int(out_of_range_pids),
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main():
    print(f"[load] {CKPT_MUTUAL.relative_to(ROOT)}")
    gt = parse_scene_obj(str(SCENE), frame="obj")

    # ====================================================================
    # Stage A — GT input
    # ====================================================================
    stageA_dir = OUT_DIR / "stageA"
    stageA_results: Dict[int, Dict] = {}
    print("\n=== Stage A — GT input ===")
    for bid in STAGE_A_BIDS:
        gt_b = next(b for b in gt["buildings"] if b["building_id"] == bid)
        bdir = stageA_dir / f"building_{bid:02d}"
        m = run_one("A", bid, gt_b, bdir,
                    input_builder=build_polyfit_input_from_gt_faces,
                    faces=gt_b["faces"])
        stageA_results[bid] = m
        if m.get("skipped"):
            print(f"  B{bid:2d} {gt_b['type']:9s} SKIP — {m['reason']}")
        else:
            print(f"  B{bid:2d} {gt_b['type']:9s} h={m['output_h']:.2f}/{m['GT_h']:.2f} "
                  f"|Δh|={m['abs_h']:.2f} cov={m['coverage']*100:.1f}% "
                  f"vol_ratio={m['vol_ratio']:.2f} "
                  f"v3d={'✓' if m['val3dity_valid'] else '✗'+str(m['val3dity_errors'])} "
                  f"H={m['hausdorff']:.2f} C={m['chamfer']:.3f}")

    # bid 3 diagnostic
    bid3_diag = diagnose_bid3(
        next(b for b in gt["buildings"] if b["building_id"] == 3),
        OUT_DIR / "bid3_diag")

    # Stage A pass criteria
    n_v3d_pass = sum(1 for m in stageA_results.values()
                     if not m.get("skipped") and m["val3dity_valid"])
    valid_metrics = [m for m in stageA_results.values()
                     if not m.get("skipped") and m["val3dity_valid"]]
    mean_dh = (np.mean([m["abs_h"] for m in valid_metrics])
               if valid_metrics else float("nan"))
    mean_cov = (np.mean([m["coverage"] for m in valid_metrics])
                if valid_metrics else 0.0)
    mean_haus = (np.mean([m["hausdorff"] for m in valid_metrics])
                 if valid_metrics else float("nan"))
    A_methodology_pass = (n_v3d_pass >= 8 and mean_dh < 2.0
                          and mean_cov >= 0.50)
    A_valid_only = (n_v3d_pass >= 1)

    print(f"\nStage A summary: v3d {n_v3d_pass}/{len(STAGE_A_BIDS)} "
          f"| mean|Δh|={mean_dh:.2f}m mean cov={mean_cov*100:.1f}% "
          f"mean H={mean_haus:.2f}m")
    print(f"  → methodology_pass={A_methodology_pass}, "
          f"any_valid={A_valid_only}")

    # ====================================================================
    # Per-type figures (Stage A) — pick 1 building per type if available
    # ====================================================================
    by_type: Dict[str, List[int]] = defaultdict(list)
    for bid, m in stageA_results.items():
        if not m.get("skipped"):
            by_type[m["type"]].append(bid)
    for t, bids in by_type.items():
        if not bids: continue
        # prefer valid; else first
        valid_bids = [b for b in bids if stageA_results[b]["val3dity_valid"]]
        pick = (valid_bids[0] if valid_bids else bids[0])
        gt_b = next(b for b in gt["buildings"] if b["building_id"] == pick)
        cj_path = stageA_dir / f"building_{pick:02d}/building.city.json"
        out_png = OUT_DIR / "figures" / f"stageA_{t}_b{pick}.png"
        make_side_by_side_figure("Stage A", pick, gt_b,
                                  cj_path if cj_path.exists() else None,
                                  out_png)

    # ====================================================================
    # Stage B — v4 envelope (only if Stage A produces any valid)
    # ====================================================================
    stageB_results: Dict[int, Dict] = {}
    if A_valid_only:
        print("\n=== Stage B — v4 envelope ===")
        prims = _load_model(CKPT_MUTUAL, emit_stage2_groups=False)
        asg = _assign_primitives_to_buildings(prims, gt, opacity_thresh=0.05)
        stageB_dir = OUT_DIR / "stageB"
        for bid in STAGE_B_BIDS:
            if bid not in asg or len(asg[bid]) < 100:
                stageB_results[bid] = {"skipped": True, "reason": "no_primitives"}
                continue
            gt_b = next(b for b in gt["buildings"] if b["building_id"] == bid)
            bdir = stageB_dir / f"building_{bid:02d}"
            m = run_one("B", bid, gt_b, bdir,
                        input_builder=build_polyfit_input_from_v4,
                        prims=prims, pids=asg[bid])
            stageB_results[bid] = m
            if m.get("skipped"):
                print(f"  B{bid:2d} {gt_b['type']:9s} SKIP — {m['reason']}")
            else:
                print(f"  B{bid:2d} {gt_b['type']:9s} h={m['output_h']:.2f}/{m['GT_h']:.2f} "
                      f"|Δh|={m['abs_h']:.2f} cov={m['coverage']*100:.1f}% "
                      f"vol_ratio={m['vol_ratio']:.2f} "
                      f"v3d={'✓' if m['val3dity_valid'] else '✗'+str(m['val3dity_errors'])} "
                      f"H={m['hausdorff']:.2f} C={m['chamfer']:.3f}")
        # Stage B figures (clean cases)
        for bid in STAGE_B_BIDS:
            m = stageB_results.get(bid, {})
            if m.get("skipped"): continue
            gt_b = next(b for b in gt["buildings"] if b["building_id"] == bid)
            cj_path = stageB_dir / f"building_{bid:02d}/building.city.json"
            out_png = OUT_DIR / "figures" / f"stageB_b{bid}.png"
            make_side_by_side_figure("Stage B", bid, gt_b,
                                      cj_path if cj_path.exists() else None,
                                      out_png)
    else:
        print("\nStage B skipped — no Stage A valid (A 가설 약화 보고)")

    # ====================================================================
    # Save metrics JSON
    # ====================================================================
    metrics = {
        "stageA": {str(b): m for b, m in stageA_results.items()},
        "stageB": {str(b): m for b, m in stageB_results.items()},
        "stageA_n_v3d_pass": n_v3d_pass,
        "stageA_mean_abs_h": float(mean_dh) if not np.isnan(mean_dh) else None,
        "stageA_mean_coverage": float(mean_cov),
        "stageA_mean_hausdorff": float(mean_haus) if not np.isnan(mean_haus) else None,
        "stageA_methodology_pass": A_methodology_pass,
        "stageA_any_valid": A_valid_only,
        "bid3_parser_diagnostic": bid3_diag,
    }

    def _jsonable(o):
        if isinstance(o, (np.ndarray,)): return o.tolist()
        if isinstance(o, (np.generic,)): return o.item()
        return str(o)

    (OUT_DIR / "metrics.json").write_text(
        json.dumps(metrics, default=_jsonable, indent=2))
    print(f"\nSaved → {OUT_DIR/'metrics.json'}")
    return metrics


if __name__ == "__main__":
    main()
