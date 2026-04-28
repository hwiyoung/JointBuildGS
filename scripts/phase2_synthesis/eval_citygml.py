"""Phase 2 Step 2-2 — CityGML quality evaluation per condition.

For each condition directory (stage3_summary + per-building CityJSON) compute:
    - val3dity pass rate + error code distribution
    - face IoU (predicted face polygons vs GT scene.obj per-building faces)
    - Hausdorff distance (predicted mesh vs GT mesh)
    - semantic accuracy (face class confusion vs GT)
    - sigma_normal (stdev of primitive normals per GT face, per condition)

Usage:
    python scripts/phase2_synthesis/eval_citygml.py \
        --stage3-dir results/phase2_ablation_citygml/<cond>/stage3 \
        --scene      results/phase2_synthesis/scene.obj \
        --out        results/phase2_ablation_citygml/<cond>/eval

Output: <out>/eval_summary.json with per-building + aggregate metrics.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np
import trimesh

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from scripts.phase2_synthesis.obj_gt import parse_scene_obj  # noqa: E402


# ---------- CityJSON reading ----------

def load_cityjson_building(cj_path: Path):
    """Return dict {faces: [{vertices (Nv,3), type: str}], vertices: (V,3)}."""
    cj = json.loads(cj_path.read_text())
    sc = cj["transform"]["scale"]
    tr = cj["transform"]["translate"]
    V = np.array(cj["vertices"], dtype=np.float64)
    V = V * np.array(sc)[None, :] + np.array(tr)[None, :]
    # CityJSON 2.0 Solid structure: boundaries[0] = outer shell = list of surfaces
    # Each surface = [ring0, ring1, ...], ring = list of vertex indices
    bname = next(iter(cj["CityObjects"]))
    geom = cj["CityObjects"][bname]["geometry"][0]
    sem_surfaces = geom.get("semantics", {}).get("surfaces", [])
    sem_values = geom.get("semantics", {}).get("values", [[]])[0]
    shells = geom["boundaries"][0]  # outer shell
    faces = []
    for i, surf in enumerate(shells):
        ring = surf[0]  # outer ring
        if len(ring) < 3:
            continue
        vp = V[np.array(ring)]
        stype = sem_surfaces[sem_values[i]]["type"] if i < len(sem_values) else "Unknown"
        faces.append({"vertices": vp, "type": stype})
    return {"name": bname, "faces": faces, "vertices": V}


SEMTYPE_TO_CLASS = {"RoofSurface": 1, "WallSurface": 2, "GroundSurface": 3}


def _face_geom_from_vertices(verts: np.ndarray):
    """Return (normal_unit, centroid, area). None if degenerate."""
    n_unnorm = np.zeros(3)
    N = len(verts)
    for i in range(N):
        a, b = verts[i], verts[(i + 1) % N]
        n_unnorm[0] += (a[1] - b[1]) * (a[2] + b[2])
        n_unnorm[1] += (a[2] - b[2]) * (a[0] + b[0])
        n_unnorm[2] += (a[0] - b[0]) * (a[1] + b[1])
    nrm = float(np.linalg.norm(n_unnorm))
    if nrm < 1e-12:
        return None
    return n_unnorm / nrm, verts.mean(axis=0), nrm * 0.5


def load_gt_from_convex_dir(convex_dir: Path, scene_obj_path: str) -> Dict:
    """Load 'GT' from convex polytope reconstructions of GT mesh.

    For apples-to-apples comparison: both pred and 'GT' have been through the
    same convex simplification, so face-count discrepancy (~22 vs ~7 per
    building) is removed. Building 'type' (flat/gable/...) is copied from the
    original scene.obj since CityJSON does not preserve that metadata.
    """
    scene_gt = parse_scene_obj(scene_obj_path)
    types_by_id = {b["building_id"]: b["type"] for b in scene_gt["buildings"]}

    buildings = []
    for cj_path in sorted(convex_dir.glob("building_*/building.city.json")):
        bid_str = cj_path.parent.name.replace("building_", "")
        try:
            bid = int(bid_str)
        except ValueError:
            continue
        cjb = load_cityjson_building(cj_path)
        faces = []
        for f in cjb["faces"]:
            verts = np.asarray(f["vertices"], dtype=np.float64)
            geom = _face_geom_from_vertices(verts)
            if geom is None:
                continue
            normal, centroid, area = geom
            faces.append({
                "vertices": verts,
                "normal": normal,
                "area": area,
                "centroid": centroid,
                "semantic_class": SEMTYPE_TO_CLASS.get(f["type"], 0),
            })
        if not faces:
            continue
        buildings.append({
            "building_id": bid,
            "type": types_by_id.get(bid, "unknown"),
            "name": cjb["name"],
            "faces": faces,
        })
    return {"buildings": buildings}


def faces_to_mesh(faces: List[Dict]) -> trimesh.Trimesh:
    """Triangulate per-face polygons and build a single trimesh."""
    verts = []
    tris = []
    for f in faces:
        poly = f["vertices"]
        n = len(poly)
        base = len(verts)
        verts.extend(poly.tolist())
        for i in range(1, n - 1):
            tris.append([base, base + i, base + i + 1])
    if not tris:
        return trimesh.Trimesh()
    V = np.array(verts, dtype=np.float64)
    F = np.array(tris, dtype=np.int64)
    return trimesh.Trimesh(vertices=V, faces=F, process=False)


# ---------- face matching ----------

def _polygon_2d(poly3d: np.ndarray, n: np.ndarray):
    """Project polygon onto plane with normal n. Returns 2D polygon in plane-local coords."""
    u = np.array([1.0, 0.0, 0.0])
    if abs(np.dot(u, n)) > 0.9:
        u = np.array([0.0, 1.0, 0.0])
    u = u - np.dot(u, n) * n
    u /= np.linalg.norm(u) + 1e-12
    v = np.cross(n, u)
    c = poly3d.mean(axis=0)
    p2 = np.stack([(poly3d - c) @ u, (poly3d - c) @ v], axis=-1)
    return p2, c, u, v


def _polygon_area_2d(p2: np.ndarray) -> float:
    n = len(p2)
    s = 0.0
    for i in range(n):
        a, b = p2[i], p2[(i + 1) % n]
        s += a[0] * b[1] - a[1] * b[0]
    return abs(s) * 0.5


def face_iou_2d(poly_a: np.ndarray, poly_b: np.ndarray) -> Optional[float]:
    """2D IoU of two (approximately coplanar) polygons after projecting to shared plane."""
    try:
        from shapely.geometry import Polygon
        from shapely.validation import make_valid
    except ImportError:
        return None

    # use normal of poly_a's plane
    n = _newell(poly_a)
    if np.linalg.norm(n) < 1e-8:
        return None
    n /= np.linalg.norm(n)
    p2a, c, u, v = _polygon_2d(poly_a, n)
    p2b = np.stack([(poly_b - c) @ u, (poly_b - c) @ v], axis=-1)

    try:
        pa = make_valid(Polygon(p2a))
        pb = make_valid(Polygon(p2b))
        inter = pa.intersection(pb).area
        union = pa.union(pb).area
    except Exception:
        return None
    if union < 1e-8:
        return None
    return inter / union


def _newell(poly: np.ndarray) -> np.ndarray:
    n = np.zeros(3)
    N = len(poly)
    for i in range(N):
        a, b = poly[i], poly[(i + 1) % N]
        n[0] += (a[1] - b[1]) * (a[2] + b[2])
        n[1] += (a[2] - b[2]) * (a[0] + b[0])
        n[2] += (a[0] - b[0]) * (a[1] + b[1])
    return n


def match_faces(pred_faces: List[Dict], gt_faces: List[Dict],
                cos_thresh: float = 0.6):
    """Match predicted faces to GT faces: greedy by (class match, normal dot, IoU).

    Returns matches [{pred_idx, gt_idx, iou, normal_cos, class_match}].
    """
    pred_n = []
    for pf in pred_faces:
        n = _newell(pf["vertices"])
        nr = np.linalg.norm(n)
        pred_n.append(n / nr if nr > 1e-8 else np.zeros(3))
    gt_n = [f["normal"] for f in gt_faces]

    class_map = {"RoofSurface": 1, "WallSurface": 2, "GroundSurface": 3}
    pred_cls = [class_map.get(pf["type"], 0) for pf in pred_faces]
    gt_cls = [f["semantic_class"] for f in gt_faces]

    used_gt = set()
    matches = []
    # rank pred faces by area descending (bigger first)
    pred_areas = []
    for pf in pred_faces:
        n = _newell(pf["vertices"])
        nr = np.linalg.norm(n)
        pred_areas.append(nr * 0.5 if nr > 0 else 0.0)
    order = np.argsort(-np.array(pred_areas))

    for pi in order:
        best_j, best_iou = -1, -1.0
        for gj in range(len(gt_faces)):
            if gj in used_gt:
                continue
            # require normal alignment (absolute cos)
            cos = abs(float(np.dot(pred_n[pi], gt_n[gj])))
            if cos < cos_thresh:
                continue
            iou = face_iou_2d(pred_faces[pi]["vertices"], gt_faces[gj]["vertices"])
            if iou is None:
                continue
            if iou > best_iou:
                best_iou = iou
                best_j = gj
        if best_j >= 0:
            used_gt.add(best_j)
            matches.append({
                "pred_idx": int(pi),
                "gt_idx": int(best_j),
                "iou": float(best_iou),
                "normal_cos": float(abs(np.dot(pred_n[pi], gt_n[best_j]))),
                "class_match": bool(pred_cls[pi] == gt_cls[best_j]),
                "pred_class": int(pred_cls[pi]),
                "gt_class": int(gt_cls[best_j]),
            })
        else:
            matches.append({
                "pred_idx": int(pi), "gt_idx": -1, "iou": 0.0,
                "normal_cos": 0.0, "class_match": False,
                "pred_class": int(pred_cls[pi]), "gt_class": -1,
            })
    # unmatched GT faces
    for gj in range(len(gt_faces)):
        if gj not in used_gt:
            matches.append({
                "pred_idx": -1, "gt_idx": int(gj), "iou": 0.0,
                "normal_cos": 0.0, "class_match": False,
                "pred_class": -1, "gt_class": int(gt_cls[gj]),
            })
    return matches


# ---------- Hausdorff ----------

def hausdorff_sym(mesh_a: trimesh.Trimesh, mesh_b: trimesh.Trimesh,
                  n_sample: int = 4000) -> Dict[str, float]:
    """Symmetric Hausdorff & mean surface-to-surface distance between two meshes."""
    if mesh_a.faces is None or len(mesh_a.faces) == 0 or \
       mesh_b.faces is None or len(mesh_b.faces) == 0:
        return {"hausdorff": float("nan"), "mean_a_to_b": float("nan"),
                "mean_b_to_a": float("nan")}
    sa, _ = trimesh.sample.sample_surface(mesh_a, n_sample)
    sb, _ = trimesh.sample.sample_surface(mesh_b, n_sample)
    _, dab, _ = trimesh.proximity.closest_point(mesh_b, sa)
    _, dba, _ = trimesh.proximity.closest_point(mesh_a, sb)
    return {
        "hausdorff": float(max(dab.max(), dba.max())),
        "mean_a_to_b": float(dab.mean()),
        "mean_b_to_a": float(dba.mean()),
    }


# ---------- sigma_normal ----------

def compute_sigma_normal(prims_file: Path, gt: Dict,
                         building_assignment: Dict[int, np.ndarray],
                         cos_gate: float = 0.8) -> Dict[int, float]:
    """sigma_normal per building = mean over GT faces of angular std of primitive
    normals that (i) belong to that building, (ii) have class matching the face,
    (iii) have |<n_prim, n_face>| > cos_gate.
    """
    if not prims_file.exists():
        return {}
    d = np.load(prims_file)
    centers = d["centers"]
    normals = d["normals"]
    labels = d["labels"]
    out = {}
    for b in gt["buildings"]:
        bid = b["building_id"]
        idxs = building_assignment.get(bid, np.array([], dtype=np.int64))
        if len(idxs) == 0:
            out[bid] = float("nan"); continue
        face_sigmas = []
        for f in b["faces"]:
            if f["semantic_class"] == 0:
                continue
            n_face = f["normal"]
            # primitives in this building with matching class
            mask = labels[idxs] == f["semantic_class"]
            if not mask.any():
                continue
            cand = idxs[mask]
            # gate by proximity to face plane (normal alignment)
            n_prim = normals[cand]
            cos = np.abs(n_prim @ n_face)
            sel = cand[cos > cos_gate]
            if len(sel) < 3:
                continue
            np_sel = normals[sel]
            # angular std from mean normal
            mean_n = np_sel.mean(axis=0)
            mean_n /= (np.linalg.norm(mean_n) + 1e-12)
            ang = np.degrees(np.arccos(np.clip(np.abs(np_sel @ mean_n), 0, 1)))
            face_sigmas.append(float(ang.std()))
        out[bid] = float(np.mean(face_sigmas)) if face_sigmas else float("nan")
    return out


def _assignment_from_summary(stage3_summary: Dict, prims_file: Path, gt: Dict,
                             opa_thresh: float = 0.05) -> Dict[int, np.ndarray]:
    """Recompute primitive->building assignment the same way run_stage3.py did."""
    if not prims_file.exists():
        return {}
    d = np.load(prims_file)
    centers = d["centers"]
    opa = d["opacities"]
    keep = opa >= opa_thresh
    bboxes = []
    ids = []
    for b in gt["buildings"]:
        vs = np.concatenate([f["vertices"] for f in b["faces"]], axis=0)
        bboxes.append((vs.min(0) - 2.0, vs.max(0) + 2.0))
        ids.append(b["building_id"])
    assignment = {bid: [] for bid in ids}
    bcent = np.array([(bb[0] + bb[1]) / 2 for bb in bboxes])
    for i in np.where(keep)[0]:
        c = centers[i]
        placed = False
        for bid, (mn, mx) in zip(ids, bboxes):
            if np.all(c >= mn) and np.all(c <= mx):
                assignment[bid].append(int(i))
                placed = True
                break
        if not placed:
            dist = np.linalg.norm(bcent - c, axis=1)
            j = int(np.argmin(dist))
            if dist[j] < 12.0:
                assignment[ids[j]].append(int(i))
    return {k: np.array(v, dtype=np.int64) for k, v in assignment.items()}


# ---------- main ----------

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage3-dir", required=True)
    ap.add_argument("--scene", default="results/phase2_synthesis/scene.obj")
    ap.add_argument("--gt-cityjson-dir", default=None,
                    help="If set, use convex GT CityJSON from this dir instead "
                         "of scene.obj GT. Apples-to-apples comparison "
                         "(both pred and GT convex-simplified).")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    stage3_dir = Path(args.stage3_dir)
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    if args.gt_cityjson_dir:
        gt = load_gt_from_convex_dir(Path(args.gt_cityjson_dir), args.scene)
        print(f"[eval] GT source: convex CityJSON dir ({len(gt['buildings'])} buildings)")
    else:
        gt = parse_scene_obj(args.scene)
        print(f"[eval] GT source: scene.obj ({len(gt['buildings'])} buildings)")
    stage3_summary = json.loads((stage3_dir / "stage3_summary.json").read_text())
    prims_file = stage3_dir / "primitives.npz"

    assignment = _assignment_from_summary(stage3_summary, prims_file, gt)
    sigma_map = compute_sigma_normal(prims_file, gt, assignment)

    per_building = []
    face_ious = []
    hausdorffs = []
    cls_confusion = np.zeros((4, 4), dtype=np.int64)  # [pred_cls, gt_cls]
    n_val = 0
    n_total = len(gt["buildings"])
    err_code_counts: Dict[str, int] = {}

    for b in gt["buildings"]:
        bid = b["building_id"]
        bdir = stage3_dir / f"building_{bid:02d}"
        entry = next((e for e in stage3_summary["buildings"]
                      if e["building_id"] == bid), None) or {}
        rec = {
            "building_id": bid,
            "type": b["type"],
            "stage3_success": bool(entry.get("stage3_success")),
            "val3dity_valid": bool(entry.get("val3dity_valid")),
            "val3dity_errors": list(entry.get("val3dity_errors", [])),
            "sigma_normal_deg": sigma_map.get(bid, float("nan")),
        }
        for code in rec["val3dity_errors"]:
            err_code_counts[code] = err_code_counts.get(code, 0) + 1
        if rec["val3dity_valid"]:
            n_val += 1

        cj_path = bdir / "building.city.json"
        if cj_path.exists():
            pred = load_cityjson_building(cj_path)
            # face-level matching
            matches = match_faces(pred["faces"], b["faces"])
            ious_this = [m["iou"] for m in matches
                         if m["pred_idx"] >= 0 and m["gt_idx"] >= 0]
            face_ious.extend(ious_this)
            rec["n_pred_faces"] = len(pred["faces"])
            rec["n_gt_faces"] = len(b["faces"])
            rec["mean_matched_iou"] = float(np.mean(ious_this)) if ious_this else 0.0
            rec["n_matched"] = sum(1 for m in matches
                                   if m["pred_idx"] >= 0 and m["gt_idx"] >= 0)
            # confusion
            for m in matches:
                pc = m["pred_class"] if m["pred_class"] in (0, 1, 2, 3) else 0
                gc = m["gt_class"] if m["gt_class"] in (0, 1, 2, 3) else 0
                if pc == 0 and gc == 0:
                    continue
                cls_confusion[pc][gc] += 1

            # Hausdorff
            try:
                pred_mesh = faces_to_mesh(pred["faces"])
                gt_mesh = faces_to_mesh(b["faces"])
                hh = hausdorff_sym(pred_mesh, gt_mesh)
                rec.update(hh)
                if not np.isnan(hh["hausdorff"]):
                    hausdorffs.append(hh["hausdorff"])
            except Exception as e:
                rec["hausdorff_error"] = f"{type(e).__name__}: {e}"
        else:
            rec["n_pred_faces"] = 0
            rec["mean_matched_iou"] = 0.0

        per_building.append(rec)

    # aggregate
    diag = cls_confusion.diagonal().sum()
    off = cls_confusion.sum() - diag
    sem_acc = float(diag / (diag + off)) if (diag + off) > 0 else 0.0

    aggregate = {
        "n_buildings": n_total,
        "val3dity_pass_rate": float(n_val / n_total),
        "val3dity_error_codes": err_code_counts,
        "mean_face_iou_matched": float(np.mean(face_ious)) if face_ious else 0.0,
        "median_face_iou_matched": float(np.median(face_ious)) if face_ious else 0.0,
        "mean_hausdorff_m": float(np.mean(hausdorffs)) if hausdorffs else float("nan"),
        "median_hausdorff_m": float(np.median(hausdorffs)) if hausdorffs else float("nan"),
        "semantic_accuracy": sem_acc,
        "confusion_matrix_4x4_pred_gt": cls_confusion.tolist(),
        "mean_sigma_normal_deg": float(np.nanmean(
            [r["sigma_normal_deg"] for r in per_building
             if not np.isnan(r["sigma_normal_deg"])]))
            if any(not np.isnan(r["sigma_normal_deg"]) for r in per_building) else float("nan"),
    }

    out = {"aggregate": aggregate, "per_building": per_building}
    (out_dir / "eval_summary.json").write_text(
        json.dumps(out, indent=2, default=float))
    print(f"[eval] val3dity_pass={aggregate['val3dity_pass_rate']*100:.1f}% "
          f"face_iou={aggregate['mean_face_iou_matched']:.3f} "
          f"hausdorff={aggregate['mean_hausdorff_m']:.2f}m "
          f"sem_acc={sem_acc*100:.1f}% "
          f"sigma_n={aggregate['mean_sigma_normal_deg']:.2f}deg")


if __name__ == "__main__":
    main()
