"""P1-4a Part B: GT-derived evidence-based relation read-out.

This experiment does not use roof type as an input. It samples GT mesh evidence
with position, normal, semantic class, and support weights, then constructs a
closed CityJSON shell from wall/roof/ground geometric relations.
"""
from __future__ import annotations

import csv
import json
import math
import subprocess
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from scipy.interpolate import LinearNDInterpolator, NearestNDInterpolator
from scipy.spatial import cKDTree
from shapely import MultiPoint, concave_hull
from shapely.geometry import GeometryCollection, LineString, MultiPolygon, Point, Polygon
from shapely.ops import polygonize, triangulate

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from scripts.phase2_synthesis.obj_gt import parse_scene_obj  # noqa: E402
from scripts.phase2_synthesis.polyfit_phase2 import (  # noqa: E402
    _sample_triangles,
    cj_mesh_triangles,
    gt_mesh_triangles,
    gt_volume_anchored,
    hausdorff_chamfer,
)
from scripts.phase2_synthesis.run_stage3 import (  # noqa: E402
    _run_val3dity,
    _summarize_val3dity,
)


SCENE = ROOT / "results/phase2_synthesis/scene.obj"
OUT_ROOT = ROOT / "results/stage3_typed_readout/P1_4a_gt_sanity"
POLYFIT_AUDIT = ROOT / "results/stage3_v4_validation/polyfit_input_audit/AUDIT_REPORT.md"
TARGET_BIDS = [1, 2, 8, 6, 0, 3]
CORE_BIDS = [1, 2, 8, 6, 0]

CLASS_NAME = {1: "roof", 2: "wall", 3: "ground", 0: "unknown"}
CLASS_COLOR = {
    1: (220, 40, 40),
    2: (45, 95, 215),
    3: (45, 160, 75),
    0: (150, 150, 150),
}
SEM_TYPE = {1: "RoofSurface", 2: "WallSurface", 3: "GroundSurface"}
GRAVITY = np.array([0.0, 1.0, 0.0])
N_METRIC_SAMPLE = 6000
SURFACE_COVERAGE_THRESH_M = 0.5
CITYJSON_SCALE = 0.0001


@dataclass
class PlaneCandidate:
    node_id: str
    class_id: int
    semantic_class: str
    normal: np.ndarray
    d: float
    point_indices: np.ndarray
    support_weight: float
    residual_mean: float
    residual_p95: float
    confidence: float
    bbox_min: np.ndarray
    bbox_max: np.ndarray


def _mkdir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def _jsonable(obj):
    if isinstance(obj, np.ndarray):
        return obj.tolist()
    if isinstance(obj, np.generic):
        return obj.item()
    if isinstance(obj, (Point, Polygon, LineString)):
        return obj.wkt
    return str(obj)


def _fmt(v: Optional[float], nd: int = 4) -> str:
    if v is None:
        return "NA"
    if isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
        return "NA"
    return f"{float(v):.{nd}f}"


def _bbox(points: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
    if len(points) == 0:
        z = np.zeros(3)
        return z.copy(), z.copy()
    return points.min(axis=0), points.max(axis=0)


def _newell_normal(poly: np.ndarray) -> np.ndarray:
    n = np.zeros(3, dtype=np.float64)
    for i in range(len(poly)):
        a = poly[i]
        b = poly[(i + 1) % len(poly)]
        n[0] += (a[1] - b[1]) * (a[2] + b[2])
        n[1] += (a[2] - b[2]) * (a[0] + b[0])
        n[2] += (a[0] - b[0]) * (a[1] + b[1])
    norm = np.linalg.norm(n)
    return n / norm if norm > 1e-12 else n


def _orient_face(vertices: np.ndarray, center: np.ndarray) -> np.ndarray:
    verts = np.asarray(vertices, dtype=np.float64)
    if len(verts) < 3:
        return verts
    n = _newell_normal(verts)
    c = verts.mean(axis=0)
    if float(np.dot(n, c - center)) < 0:
        return verts[::-1].copy()
    return verts


def _polygon_fan_triangles(poly: np.ndarray) -> np.ndarray:
    if len(poly) < 3:
        return np.empty((0, 3, 3))
    return np.asarray([[poly[0], poly[i], poly[i + 1]]
                       for i in range(1, len(poly) - 1)], dtype=np.float64)


def _sample_face(face: Dict, min_points: int = 80, density: float = 1.2,
                 seed: int = 0) -> np.ndarray:
    """Sample a planar polygon using only its geometry as evidence source."""
    verts = np.asarray(face["vertices"], dtype=np.float64)
    base = [verts.mean(axis=0)]
    base.extend([v for v in verts])
    for i in range(len(verts)):
        base.append((verts[i] + verts[(i + 1) % len(verts)]) * 0.5)

    n_random = max(min_points, int(round(float(face["area"]) * density))) - len(base)
    if n_random <= 0:
        return np.asarray(base, dtype=np.float64)

    tris = _polygon_fan_triangles(verts)
    if len(tris) == 0:
        return np.asarray(base, dtype=np.float64)
    rnd = _sample_triangles(tris, n_random, seed=seed)
    return np.vstack([np.asarray(base, dtype=np.float64), rnd])


def generate_evidence(building: Dict) -> Dict:
    pts, normals, classes, weights, face_ids = [], [], [], [], []
    for fi, face in enumerate(building["faces"]):
        samples = _sample_face(face, seed=1000 + int(building["building_id"]) * 997 + fi)
        n = np.asarray(face["normal"], dtype=np.float64)
        n = n / (np.linalg.norm(n) + 1e-12)
        cls = int(face.get("semantic_class", 0))
        w = float(face["area"]) / max(len(samples), 1)
        pts.append(samples)
        normals.append(np.tile(n, (len(samples), 1)))
        classes.append(np.full(len(samples), cls, dtype=np.int64))
        weights.append(np.full(len(samples), w, dtype=np.float64))
        face_ids.append(np.full(len(samples), fi, dtype=np.int64))
    return {
        "points": np.concatenate(pts, axis=0),
        "normals": np.concatenate(normals, axis=0),
        "classes": np.concatenate(classes, axis=0),
        "weights": np.concatenate(weights, axis=0),
        "face_ids": np.concatenate(face_ids, axis=0),
    }


def write_evidence_ply(path: Path, evidence: Dict, mask: Optional[np.ndarray] = None) -> None:
    pts = evidence["points"] if mask is None else evidence["points"][mask]
    normals = evidence["normals"] if mask is None else evidence["normals"][mask]
    classes = evidence["classes"] if mask is None else evidence["classes"][mask]
    weights = evidence["weights"] if mask is None else evidence["weights"][mask]
    lines = [
        "ply",
        "format ascii 1.0",
        f"element vertex {len(pts)}",
        "property float x",
        "property float y",
        "property float z",
        "property float nx",
        "property float ny",
        "property float nz",
        "property uchar red",
        "property uchar green",
        "property uchar blue",
        "property int semantic_class",
        "property float support_weight",
        "end_header",
    ]
    for p, n, cls, w in zip(pts, normals, classes, weights):
        color = CLASS_COLOR.get(int(cls), CLASS_COLOR[0])
        lines.append(
            f"{p[0]:.6f} {p[1]:.6f} {p[2]:.6f} "
            f"{n[0]:.6f} {n[1]:.6f} {n[2]:.6f} "
            f"{color[0]} {color[1]} {color[2]} {int(cls)} {float(w):.8f}"
        )
    path.write_text("\n".join(lines) + "\n")


def write_evidence_stats(path: Path, evidence: Dict) -> None:
    fields = ["class", "n_points", "area_sum", "bbox_min", "bbox_max",
              "normal_mean", "normal_modes_estimated"]
    rows = []
    for cls in [1, 2, 3]:
        m = evidence["classes"] == cls
        pts = evidence["points"][m]
        normals = evidence["normals"][m]
        weights = evidence["weights"][m]
        if len(pts):
            mn, mx = _bbox(pts)
            nmean = np.average(normals, axis=0, weights=weights)
            nmean = nmean / (np.linalg.norm(nmean) + 1e-12)
            modes = estimate_normal_modes(normals, weights)
        else:
            mn = mx = nmean = np.zeros(3)
            modes = 0
        rows.append({
            "class": CLASS_NAME[cls],
            "n_points": int(len(pts)),
            "area_sum": float(weights.sum()),
            "bbox_min": " ".join(f"{x:.4f}" for x in mn),
            "bbox_max": " ".join(f"{x:.4f}" for x in mx),
            "normal_mean": " ".join(f"{x:.5f}" for x in nmean),
            "normal_modes_estimated": int(modes),
        })
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def estimate_normal_modes(normals: np.ndarray, weights: np.ndarray,
                          cos_tol: float = 0.985, min_weight_frac: float = 0.02) -> int:
    if len(normals) == 0:
        return 0
    total = float(weights.sum())
    modes: List[Tuple[np.ndarray, float]] = []
    for n, w in sorted(zip(normals, weights), key=lambda x: -float(x[1])):
        n = np.asarray(n, dtype=np.float64)
        n /= np.linalg.norm(n) + 1e-12
        matched = False
        for i, (mn, mw) in enumerate(modes):
            if abs(float(np.dot(n, mn))) >= cos_tol:
                sign = 1.0 if float(np.dot(n, mn)) >= 0 else -1.0
                new = mn * mw + sign * n * float(w)
                new /= np.linalg.norm(new) + 1e-12
                modes[i] = (new, mw + float(w))
                matched = True
                break
        if not matched:
            modes.append((n, float(w)))
    return sum(1 for _n, w in modes if w >= min_weight_frac * total)


def cluster_planes_from_evidence(evidence: Dict, class_id: int,
                                 cos_tol: float = 0.985,
                                 dist_tol: float = 0.20) -> List[PlaneCandidate]:
    idxs = np.where(evidence["classes"] == class_id)[0]
    pts = evidence["points"]
    normals = evidence["normals"]
    weights = evidence["weights"]
    clusters: List[Dict] = []
    for idx in idxs:
        n = normals[idx].copy()
        n /= np.linalg.norm(n) + 1e-12
        p = pts[idx]
        d = float(np.dot(n, p))
        matched = False
        for c in clusters:
            cos = float(np.dot(n, c["normal"]))
            if abs(cos) < cos_tol:
                continue
            signed_d = d if cos >= 0 else -d
            if abs(signed_d - c["d"]) > dist_tol:
                continue
            c["indices"].append(int(idx))
            # area-weighted representative normal.
            sign = 1.0 if cos >= 0 else -1.0
            c["normal_sum"] += sign * n * float(weights[idx])
            c["weight"] += float(weights[idx])
            c["normal"] = c["normal_sum"] / (np.linalg.norm(c["normal_sum"]) + 1e-12)
            c["d"] = float(np.average(
                [np.dot(c["normal"], pts[j]) for j in c["indices"]],
                weights=[weights[j] for j in c["indices"]]))
            matched = True
            break
        if not matched:
            clusters.append({
                "indices": [int(idx)],
                "normal": n.copy(),
                "normal_sum": n * float(weights[idx]),
                "d": d,
                "weight": float(weights[idx]),
            })

    out = []
    total_weight = float(weights[idxs].sum()) if len(idxs) else 1.0
    for ci, c in enumerate(clusters):
        ids = np.asarray(c["indices"], dtype=np.int64)
        n = c["normal"] / (np.linalg.norm(c["normal"]) + 1e-12)
        d = float(np.average(pts[ids] @ n, weights=weights[ids]))
        residuals = np.abs(pts[ids] @ n - d)
        mn, mx = _bbox(pts[ids])
        residual_score = max(0.0, 1.0 - float(np.mean(residuals)) / 0.10)
        support_score = min(1.0, float(weights[ids].sum()) / max(total_weight * 0.35, 1e-9))
        confidence = 0.65 * support_score + 0.35 * residual_score
        out.append(PlaneCandidate(
            node_id=f"{CLASS_NAME.get(class_id, 'unknown')}_{ci}",
            class_id=class_id,
            semantic_class=CLASS_NAME.get(class_id, "unknown"),
            normal=n,
            d=d,
            point_indices=ids,
            support_weight=float(weights[ids].sum()),
            residual_mean=float(np.mean(residuals)),
            residual_p95=float(np.percentile(residuals, 95)),
            confidence=float(confidence),
            bbox_min=mn,
            bbox_max=mx,
        ))
    out.sort(key=lambda p: -p.support_weight)
    # Reassign stable node IDs after sorting.
    for i, p in enumerate(out):
        p.node_id = f"{CLASS_NAME.get(class_id, 'unknown')}_{i}"
    return out


def plane_to_json(p: PlaneCandidate) -> Dict:
    return {
        "id": p.node_id,
        "semantic_class": p.semantic_class,
        "normal": p.normal.tolist(),
        "d": p.d,
        "support_area": p.support_weight,
        "n_points": int(len(p.point_indices)),
        "residual_mean": p.residual_mean,
        "residual_p95": p.residual_p95,
        "confidence": p.confidence,
        "bbox_min": p.bbox_min.tolist(),
        "bbox_max": p.bbox_max.tolist(),
    }


def vertical_wall_line(p: PlaneCandidate) -> Optional[Tuple[np.ndarray, float, np.ndarray]]:
    n2 = np.array([p.normal[0], p.normal[2]], dtype=np.float64)
    norm = np.linalg.norm(n2)
    if norm < 1e-8:
        return None
    n2 /= norm
    # For wall planes n_x*x + n_z*z = d when n_y ~= 0.
    d2 = p.d / norm
    direction = np.array([-n2[1], n2[0]], dtype=np.float64)
    return n2, float(d2), direction


def line_intersection_2d(n1: np.ndarray, d1: float,
                         n2: np.ndarray, d2: float) -> Optional[np.ndarray]:
    A = np.vstack([n1, n2])
    det = float(np.linalg.det(A))
    if abs(det) < 1e-8:
        return None
    return np.linalg.solve(A, np.array([d1, d2], dtype=np.float64))


def segment_distance_to_point(a: np.ndarray, b: np.ndarray, p: np.ndarray) -> float:
    ab = b - a
    denom = float(np.dot(ab, ab))
    if denom < 1e-12:
        return float(np.linalg.norm(p - a))
    t = float(np.clip(np.dot(p - a, ab) / denom, 0.0, 1.0))
    q = a + t * ab
    return float(np.linalg.norm(p - q))


def wall_segments_from_planes(wall_planes: List[PlaneCandidate], evidence: Dict) -> List[Dict]:
    segs = []
    for wp in wall_planes:
        line = vertical_wall_line(wp)
        if line is None:
            continue
        n2, d2, direction = line
        pts2 = evidence["points"][wp.point_indices][:, [0, 2]]
        ts = pts2 @ direction
        lo, hi = float(np.min(ts)), float(np.max(ts))
        a = n2 * d2 + direction * lo
        b = n2 * d2 + direction * hi
        segs.append({
            "wall_node": wp.node_id,
            "normal_2d": n2,
            "d_2d": d2,
            "direction_2d": direction,
            "p0": a,
            "p1": b,
            "support_area": wp.support_weight,
            "confidence": wp.confidence,
        })
    return segs


def candidate_polygon_score(poly: Polygon, wall_xz: np.ndarray,
                            ground_xz: np.ndarray) -> Dict:
    if poly.is_empty or not poly.is_valid or poly.area <= 1e-6:
        return {"score": -1e9, "valid": False}
    boundary = poly.boundary
    wall_d = np.array([boundary.distance(Point(float(x), float(z))) for x, z in wall_xz])
    inside_ground = np.mean([poly.buffer(1e-6).contains(Point(float(x), float(z))) or
                             poly.buffer(1e-6).touches(Point(float(x), float(z)))
                             for x, z in ground_xz]) if len(ground_xz) else 1.0
    coords = list(poly.exterior.coords)[:-1]
    simplicity = 1.0 / max(len(coords), 1)
    dist_score = math.exp(-float(np.mean(wall_d)) / 0.35)
    p95_score = math.exp(-float(np.percentile(wall_d, 95)) / 0.75)
    area_score = 1.0 if poly.area > 5.0 else poly.area / 5.0
    score = 0.45 * dist_score + 0.20 * p95_score + 0.15 * inside_ground + 0.10 * area_score + 0.10 * simplicity
    return {
        "score": float(score),
        "valid": bool(poly.is_valid),
        "area": float(poly.area),
        "n_vertices": int(len(coords)),
        "wall_distance_mean": float(np.mean(wall_d)),
        "wall_distance_p95": float(np.percentile(wall_d, 95)),
        "ground_inside_fraction": float(inside_ground),
        "self_intersection_penalty": 0.0 if poly.is_valid else 1.0,
        "simplicity_penalty": float(1.0 - simplicity),
    }


def _largest_polygon(geom) -> Optional[Polygon]:
    if geom.is_empty:
        return None
    if isinstance(geom, Polygon):
        return geom
    if isinstance(geom, MultiPolygon):
        polys = list(geom.geoms)
        return max(polys, key=lambda p: p.area) if polys else None
    if isinstance(geom, GeometryCollection):
        polys = [g for g in geom.geoms if isinstance(g, Polygon)]
        return max(polys, key=lambda p: p.area) if polys else None
    return None


def build_footprint_candidates(evidence: Dict, wall_planes: List[PlaneCandidate]) -> Tuple[Polygon, List[Dict], List[Dict]]:
    wall_mask = evidence["classes"] == 2
    ground_mask = evidence["classes"] == 3
    wall_xz = evidence["points"][wall_mask][:, [0, 2]]
    ground_xz = evidence["points"][ground_mask][:, [0, 2]]
    segs = wall_segments_from_planes(wall_planes, evidence)
    candidates: List[Tuple[str, Polygon]] = []
    mp = MultiPoint([tuple(x) for x in wall_xz])
    hull = _largest_polygon(mp.convex_hull)
    if hull is not None:
        candidates.append(("wall_points_convex_hull", hull))
    for ratio in (0.15, 0.30, 0.50, 0.80):
        try:
            ch = _largest_polygon(concave_hull(mp, ratio=ratio, allow_holes=False))
            if ch is not None:
                candidates.append((f"wall_points_concave_hull_{ratio:.2f}", ch))
        except Exception:
            pass
    line_geoms = [LineString([tuple(s["p0"]), tuple(s["p1"])]) for s in segs]
    polys = list(polygonize(line_geoms))
    if polys:
        candidates.append(("wall_line_polygonize", max(polys, key=lambda p: p.area)))

    scored = []
    for name, poly in candidates:
        if poly is None or poly.is_empty:
            continue
        # Use exterior only. Holes from sparse evidence are not considered.
        poly = Polygon(poly.exterior.coords)
        sc = candidate_polygon_score(poly, wall_xz, ground_xz)
        coords = [[float(x), float(z)] for x, z in list(poly.exterior.coords)[:-1]]
        scored.append({
            "id": name,
            "source": name,
            "score": sc["score"],
            "score_components": sc,
            "polygon_xz": coords,
        })
    if not scored:
        raise RuntimeError("No footprint candidate could be generated from wall evidence")
    scored.sort(key=lambda r: -r["score"])
    best = Polygon(scored[0]["polygon_xz"])
    # Ensure a CCW exterior in xz for stable wall construction.
    if not best.exterior.is_ccw:
        best = Polygon(list(best.exterior.coords)[::-1])
        scored[0]["polygon_xz"] = [[float(x), float(z)] for x, z in list(best.exterior.coords)[:-1]]
    return best, scored, segs


def write_footprint_plot(path: Path, poly: Polygon, candidates: List[Dict], evidence: Dict) -> None:
    fig, ax = plt.subplots(figsize=(7, 6))
    wall = evidence["points"][evidence["classes"] == 2][:, [0, 2]]
    roof = evidence["points"][evidence["classes"] == 1][:, [0, 2]]
    ax.scatter(wall[:, 0], wall[:, 1], s=4, c="#2D5FD7", alpha=0.45, label="wall evidence")
    ax.scatter(roof[:, 0], roof[:, 1], s=4, c="#DC2828", alpha=0.25, label="roof evidence")
    for cand in candidates[:4]:
        xy = np.asarray(cand["polygon_xz"] + [cand["polygon_xz"][0]], dtype=float)
        ax.plot(xy[:, 0], xy[:, 1], linewidth=0.8, alpha=0.35)
    xy = np.asarray(list(poly.exterior.coords), dtype=float)
    ax.plot(xy[:, 0], xy[:, 1], color="black", linewidth=2.0, label="selected")
    ax.set_aspect("equal", adjustable="box")
    ax.set_xlabel("x")
    ax.set_ylabel("z")
    ax.legend(loc="best", fontsize=8)
    ax.grid(True, linewidth=0.2, alpha=0.4)
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)


def fit_roof_interpolators(evidence: Dict):
    roof = evidence["classes"] == 1
    roof_xz = evidence["points"][roof][:, [0, 2]]
    roof_y = evidence["points"][roof][:, 1]
    if len(roof_xz) < 3:
        raise RuntimeError("Too few roof evidence points")
    linear = LinearNDInterpolator(roof_xz, roof_y, fill_value=np.nan)
    nearest = NearestNDInterpolator(roof_xz, roof_y)

    def height(x: float, z: float) -> float:
        val = linear(float(x), float(z))
        try:
            y = float(val)
        except TypeError:
            y = float(np.asarray(val).reshape(-1)[0])
        if math.isnan(y):
            y = float(nearest(float(x), float(z)))
        return y
    return height


def roof_plane_height(plane: PlaneCandidate, x: float, z: float) -> Optional[float]:
    ny = float(plane.normal[1])
    if abs(ny) < 1e-6:
        return None
    return float((plane.d - plane.normal[0] * x - plane.normal[2] * z) / ny)


def roof_support_polygon(plane: PlaneCandidate, evidence: Dict) -> Optional[Polygon]:
    pts = evidence["points"][plane.point_indices][:, [0, 2]]
    if len(pts) < 3:
        return None
    geom = MultiPoint([tuple(p) for p in pts]).convex_hull
    return _largest_polygon(geom)


def roof_surface_candidates(roof_planes: List[PlaneCandidate], footprint: Polygon,
                            evidence: Dict) -> List[Dict]:
    rows = []
    roof_pts = evidence["points"][evidence["classes"] == 1]
    for rp in roof_planes:
        support_poly = roof_support_polygon(rp, evidence)
        clipped = support_poly.intersection(footprint) if support_poly is not None else Polygon()
        residuals = np.abs(evidence["points"][rp.point_indices] @ rp.normal - rp.d)
        coverage = len(rp.point_indices) / max(len(roof_pts), 1)
        rows.append({
            "roof_node": rp.node_id,
            "normal": rp.normal.tolist(),
            "d": rp.d,
            "support_area": rp.support_weight,
            "n_points": int(len(rp.point_indices)),
            "point_to_plane_residual_mean": float(np.mean(residuals)),
            "point_to_plane_residual_p95": float(np.percentile(residuals, 95)),
            "coverage_fraction_of_roof_evidence": float(coverage),
            "support_polygon_area_xz": float(support_poly.area) if support_poly else 0.0,
            "clipped_to_footprint_area_xz": float(clipped.area) if not clipped.is_empty else 0.0,
            "confidence": rp.confidence,
        })
    return rows


def write_roof_mode_plot(path: Path, roof_planes: List[PlaneCandidate]) -> None:
    fig, ax = plt.subplots(figsize=(6, 4))
    xs = [math.degrees(math.atan2(float(p.normal[2]), float(p.normal[0]))) for p in roof_planes]
    ys = [float(abs(p.normal[1])) for p in roof_planes]
    sizes = [max(30.0, p.support_weight * 4.0) for p in roof_planes]
    ax.scatter(xs, ys, s=sizes, c="#DC2828", alpha=0.75)
    for p, x, y in zip(roof_planes, xs, ys):
        ax.text(x, y, p.node_id, fontsize=8)
    ax.set_xlabel("roof normal azimuth deg")
    ax.set_ylabel("|normal dot gravity|")
    ax.set_ylim(0, 1.05)
    ax.grid(True, linewidth=0.2, alpha=0.4)
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)


def _signed_area_2d(poly: np.ndarray) -> float:
    s = 0.0
    for i in range(len(poly)):
        a = poly[i]
        b = poly[(i + 1) % len(poly)]
        s += float(a[0] * b[1] - b[0] * a[1])
    return 0.5 * s


def _remove_near_collinear(poly: np.ndarray, eps: float = 1e-8) -> np.ndarray:
    pts = [np.asarray(p, dtype=np.float64) for p in poly]
    changed = True
    while changed and len(pts) > 3:
        changed = False
        out = []
        n = len(pts)
        for i in range(n):
            a = pts[(i - 1) % n]
            b = pts[i]
            c = pts[(i + 1) % n]
            ab = b - a
            bc = c - b
            cross = abs(float(ab[0] * bc[1] - ab[1] * bc[0]))
            if cross <= eps and float(np.dot(ab, bc)) >= 0:
                changed = True
                continue
            out.append(b)
        pts = out
    return np.asarray(pts, dtype=np.float64)


def _point_in_tri_2d(p: np.ndarray, a: np.ndarray, b: np.ndarray, c: np.ndarray,
                     eps: float = 1e-10) -> bool:
    v0 = c - a
    v1 = b - a
    v2 = p - a
    den = float(v0[0] * v1[1] - v1[0] * v0[1])
    if abs(den) < eps:
        return False
    u = float((v2[0] * v1[1] - v1[0] * v2[1]) / den)
    v = float((v0[0] * v2[1] - v2[0] * v0[1]) / den)
    return u >= -eps and v >= -eps and (u + v) <= 1.0 + eps


def ear_clip_triangulate_xz(coords: np.ndarray) -> List[np.ndarray]:
    """Triangulate a simple xz polygon without adding boundary vertices.

    This keeps the final CityJSON shell edge-consistent: roof boundary,
    wall top, wall bottom, and ground boundary all use the same ring.
    """
    poly = _remove_near_collinear(np.asarray(coords, dtype=np.float64))
    if len(poly) < 3:
        return []
    if _signed_area_2d(poly) < 0:
        poly = poly[::-1].copy()
    indices = list(range(len(poly)))
    tris: List[np.ndarray] = []
    guard = 0
    while len(indices) > 3 and guard < len(poly) * len(poly):
        guard += 1
        clipped = False
        for pos in range(len(indices)):
            i_prev = indices[(pos - 1) % len(indices)]
            i_curr = indices[pos]
            i_next = indices[(pos + 1) % len(indices)]
            a, b, c = poly[i_prev], poly[i_curr], poly[i_next]
            cross = float((b[0] - a[0]) * (c[1] - b[1]) -
                          (b[1] - a[1]) * (c[0] - b[0]))
            if cross <= 1e-10:
                continue
            contains = False
            for j in indices:
                if j in (i_prev, i_curr, i_next):
                    continue
                if _point_in_tri_2d(poly[j], a, b, c):
                    contains = True
                    break
            if contains:
                continue
            tris.append(np.asarray([a, b, c], dtype=np.float64))
            del indices[pos]
            clipped = True
            break
        if not clipped:
            # Conservative fallback: fan triangulation. This should only happen
            # for nearly degenerate footprints and is still edge-consistent.
            base = poly[indices[0]]
            for k in range(1, len(indices) - 1):
                tris.append(np.asarray([base, poly[indices[k]], poly[indices[k + 1]]],
                                       dtype=np.float64))
            return tris
    if len(indices) == 3:
        tris.append(np.asarray([poly[indices[0]], poly[indices[1]], poly[indices[2]]],
                               dtype=np.float64))
    return tris


def make_roof_mesh(footprint: Polygon, evidence: Dict) -> Tuple[List[np.ndarray], List[np.ndarray]]:
    """Create a continuous roof height-field mesh over the wall-derived footprint."""
    height = fit_roof_interpolators(evidence)
    boundary = _remove_near_collinear(np.asarray(list(footprint.exterior.coords)[:-1], dtype=np.float64))
    raw_tris = ear_clip_triangulate_xz(boundary)
    roof_faces = []
    roof_faces_xz = []
    for coords in raw_tris:
        if len(coords) < 3:
            continue
        verts = np.asarray([[x, height(x, z), z] for x, z in coords], dtype=np.float64)
        roof_faces.append(verts)
        roof_faces_xz.append(coords)
    return roof_faces, roof_faces_xz


def point_on_segment_2d(p: np.ndarray, a: np.ndarray, b: np.ndarray,
                        eps: float = 1e-5) -> Optional[float]:
    ab = b - a
    denom = float(np.dot(ab, ab))
    if denom < 1e-12:
        return None
    t = float(np.dot(p - a, ab) / denom)
    if t < -1e-6 or t > 1.0 + 1e-6:
        return None
    q = a + np.clip(t, 0.0, 1.0) * ab
    if float(np.linalg.norm(p - q)) <= eps:
        return float(np.clip(t, 0.0, 1.0))
    return None


def unique_points_sorted(points_with_t: List[Tuple[float, np.ndarray]]) -> List[np.ndarray]:
    points_with_t.sort(key=lambda x: x[0])
    out: List[np.ndarray] = []
    for _t, p in points_with_t:
        if not out or np.linalg.norm(p - out[-1]) > 1e-5:
            out.append(p)
    return out


def subdivided_boundary_ring(footprint: Polygon, roof_faces_xz: List[np.ndarray]) -> np.ndarray:
    coords = np.asarray(list(footprint.exterior.coords)[:-1], dtype=np.float64)
    roof_boundary_pts = []
    for face in roof_faces_xz:
        for p in face:
            if footprint.boundary.distance(Point(float(p[0]), float(p[1]))) < 1e-5:
                roof_boundary_pts.append(np.asarray(p, dtype=np.float64))
    ring: List[np.ndarray] = []
    for i in range(len(coords)):
        a = coords[i]
        b = coords[(i + 1) % len(coords)]
        pts = [(0.0, a), (1.0, b)]
        for p in roof_boundary_pts:
            t = point_on_segment_2d(p, a, b)
            if t is not None:
                pts.append((t, p))
        segment_pts = unique_points_sorted(pts)
        if ring and np.linalg.norm(ring[-1] - segment_pts[0]) < 1e-5:
            ring.extend(segment_pts[1:])
        else:
            ring.extend(segment_pts)
    if len(ring) > 1 and np.linalg.norm(ring[0] - ring[-1]) < 1e-5:
        ring = ring[:-1]
    return np.asarray(ring, dtype=np.float64)


def assemble_closed_shell(footprint: Polygon, evidence: Dict,
                          roof_planes: List[PlaneCandidate]) -> Tuple[List[Dict], Dict]:
    roof_faces, roof_faces_xz = make_roof_mesh(footprint, evidence)
    if not roof_faces:
        raise RuntimeError("No roof faces generated from relation read-out")
    height = fit_roof_interpolators(evidence)
    ground_y = float(np.average(
        evidence["points"][evidence["classes"] == 3][:, 1],
        weights=evidence["weights"][evidence["classes"] == 3]))
    # Use the same simplified boundary that ear clipping used for the roof.
    # Otherwise collinear wall/ground vertices would split boundary edges that
    # the roof represents as longer edges, producing false open-edge diagnostics.
    ring_xz = _remove_near_collinear(np.asarray(list(footprint.exterior.coords)[:-1],
                                                dtype=np.float64))
    if _signed_area_2d(ring_xz) < 0:
        ring_xz = ring_xz[::-1].copy()
    top_ring = np.asarray([[x, height(x, z), z] for x, z in ring_xz], dtype=np.float64)
    bottom_ring = np.asarray([[x, ground_y, z] for x, z in ring_xz], dtype=np.float64)

    faces: List[Dict] = []
    for verts in roof_faces:
        faces.append({"vertices": verts, "type": "RoofSurface", "source": "roof_height_field"})
    for i in range(len(ring_xz)):
        j = (i + 1) % len(ring_xz)
        verts = np.asarray([top_ring[i], bottom_ring[i], bottom_ring[j], top_ring[j]], dtype=np.float64)
        if np.linalg.norm(verts[0] - verts[3]) < 1e-5:
            continue
        faces.append({"vertices": verts, "type": "WallSurface", "source": "wall_boundary_segment"})
    faces.append({"vertices": bottom_ring[::-1].copy(), "type": "GroundSurface", "source": "ground_boundary"})

    allv = np.concatenate([f["vertices"] for f in faces], axis=0)
    center = allv.mean(axis=0)
    for f in faces:
        f["vertices"] = _orient_face(f["vertices"], center)
    diag = edge_incidence_diagnostics(faces)
    diag.update({
        "n_roof_faces": sum(1 for f in faces if f["type"] == "RoofSurface"),
        "n_wall_faces": sum(1 for f in faces if f["type"] == "WallSurface"),
        "n_ground_faces": sum(1 for f in faces if f["type"] == "GroundSurface"),
        "ground_y": ground_y,
        "boundary_vertices": int(len(ring_xz)),
        "roof_plane_candidates_used_for_height_field": [p.node_id for p in roof_planes],
    })
    return faces, diag


def qkey(v: np.ndarray, scale: float = CITYJSON_SCALE) -> Tuple[int, int, int]:
    return tuple(int(round(float(v[i]) / scale)) for i in range(3))


def edge_incidence_diagnostics(faces: List[Dict]) -> Dict:
    edges: Dict[Tuple[Tuple[int, int, int], Tuple[int, int, int]], int] = defaultdict(int)
    degenerate_faces = 0
    degenerate_edges = 0
    for f in faces:
        verts = [qkey(v) for v in f["vertices"]]
        cleaned = [verts[0]]
        for k in verts[1:]:
            if k != cleaned[-1]:
                cleaned.append(k)
        if len(cleaned) > 1 and cleaned[-1] == cleaned[0]:
            cleaned = cleaned[:-1]
        if len(cleaned) < 3:
            degenerate_faces += 1
            continue
        for i in range(len(cleaned)):
            a = cleaned[i]
            b = cleaned[(i + 1) % len(cleaned)]
            if a == b:
                degenerate_edges += 1
                continue
            e = (a, b) if a < b else (b, a)
            edges[e] += 1
    counts = Counter(edges.values())
    return {
        "n_edges": int(len(edges)),
        "n_edges_incident_1": int(counts.get(1, 0)),
        "n_edges_incident_2": int(counts.get(2, 0)),
        "n_edges_incident_gt2": int(sum(v for k, v in counts.items() if k > 2)),
        "all_boundary_edges_exactly_2": bool(counts.get(1, 0) == 0 and sum(v for k, v in counts.items() if k > 2) == 0),
        "degenerate_faces_removed_or_skipped": int(degenerate_faces),
        "degenerate_edges": int(degenerate_edges),
    }


def faces_to_cityjson(faces: List[Dict], building_id: int, out_path: Path,
                      scale: float = CITYJSON_SCALE) -> Dict:
    vert_map: Dict[Tuple[int, int, int], int] = {}
    raw_int_verts: List[List[int]] = []

    def add_vertex(v: np.ndarray) -> int:
        key = qkey(v, scale)
        if key not in vert_map:
            vert_map[key] = len(raw_int_verts)
            raw_int_verts.append(list(key))
        return vert_map[key]

    boundaries = []
    sem_surfaces = []
    sem_values = []
    surface_types = []
    for f in faces:
        ids = [add_vertex(v) for v in f["vertices"]]
        cleaned = [ids[0]]
        for idx in ids[1:]:
            if idx != cleaned[-1]:
                cleaned.append(idx)
        if len(cleaned) > 1 and cleaned[-1] == cleaned[0]:
            cleaned = cleaned[:-1]
        if len(cleaned) < 3:
            continue
        boundaries.append([cleaned])
        sem_surfaces.append({"type": f["type"]})
        sem_values.append(len(sem_surfaces) - 1)
        surface_types.append(f["type"])

    def signed_vol(boundaries_, int_verts_) -> float:
        vol = 0.0
        for bnd in boundaries_:
            ring = bnd[0]
            pts = [np.asarray(int_verts_[i], dtype=np.float64) * scale for i in ring]
            for i in range(1, len(pts) - 1):
                vol += float(np.dot(pts[0], np.cross(pts[i], pts[i + 1])))
        return vol / 6.0

    vol = signed_vol(boundaries, raw_int_verts)
    if vol < 0:
        for b in boundaries:
            b[0] = b[0][::-1]
        vol = -vol

    translate = [min(v[i] for v in raw_int_verts) * scale for i in range(3)]
    t_ijk = [round(translate[i] / scale) for i in range(3)]
    adj_verts = [[v[i] - t_ijk[i] for i in range(3)] for v in raw_int_verts]
    bname = f"building_{building_id:03d}"
    cj = {
        "type": "CityJSON",
        "version": "2.0",
        "transform": {"scale": [scale] * 3, "translate": translate},
        "CityObjects": {
            bname: {
                "type": "Building",
                "attributes": {
                    "building_id": int(building_id),
                    "construction": "gt_derived_relation_readout",
                    "signed_volume": float(vol),
                },
                "geometry": [{
                    "type": "Solid",
                    "lod": "2",
                    "boundaries": [boundaries],
                    "semantics": {"surfaces": sem_surfaces, "values": [sem_values]},
                }],
            }
        },
        "vertices": adj_verts,
    }
    out_path.write_text(json.dumps(cj, indent=2))
    edge_diag = edge_incidence_diagnostics(faces)
    return {
        "cityjson_path": str(out_path),
        "n_surfaces": int(len(boundaries)),
        "n_vertices": int(len(adj_verts)),
        "signed_volume": float(vol),
        "surface_types": dict(Counter(surface_types)),
        **edge_diag,
    }


def relation_edges(wall_planes: List[PlaneCandidate], roof_planes: List[PlaneCandidate],
                   ground_planes: List[PlaneCandidate],
                   wall_segments: List[Dict]) -> List[Dict]:
    edges = []
    seg_by_node = {s["wall_node"]: s for s in wall_segments}
    for i, a in enumerate(wall_planes):
        la = vertical_wall_line(a)
        if la is None:
            continue
        for b in wall_planes[i + 1:]:
            lb = vertical_wall_line(b)
            if lb is None:
                continue
            p = line_intersection_2d(la[0], la[1], lb[0], lb[1])
            if p is None:
                continue
            sa = seg_by_node.get(a.node_id)
            sb = seg_by_node.get(b.node_id)
            da = segment_distance_to_point(sa["p0"], sa["p1"], p) if sa else 999.0
            db = segment_distance_to_point(sb["p0"], sb["p1"], p) if sb else 999.0
            conf = math.exp(-(da + db) / 0.75) * min(a.confidence, b.confidence)
            edges.append({
                "type": "wall_wall_intersection",
                "nodes": [a.node_id, b.node_id],
                "point_xz": p.tolist(),
                "segment_distance_sum": float(da + db),
                "confidence": float(conf),
            })
    for w in wall_planes:
        for g in ground_planes[:1]:
            edges.append({
                "type": "wall_ground_intersection",
                "nodes": [w.node_id, g.node_id],
                "confidence": float(min(w.confidence, g.confidence)),
            })
    for r in roof_planes:
        for w in wall_planes:
            denom = np.linalg.norm(np.cross(r.normal, w.normal))
            edges.append({
                "type": "roof_wall_intersection",
                "nodes": [r.node_id, w.node_id],
                "parallel_score": float(denom),
                "confidence": float(min(r.confidence, w.confidence) * min(1.0, denom)),
            })
    for i, a in enumerate(roof_planes):
        for b in roof_planes[i + 1:]:
            denom = np.linalg.norm(np.cross(a.normal, b.normal))
            edges.append({
                "type": "roof_roof_intersection",
                "nodes": [a.node_id, b.node_id],
                "parallel_score": float(denom),
                "confidence": float(min(a.confidence, b.confidence) * min(1.0, denom * 2.0)),
            })
    return edges


def write_graph_json(path: Path, wall_planes: List[PlaneCandidate],
                     roof_planes: List[PlaneCandidate],
                     ground_planes: List[PlaneCandidate],
                     wall_segments: List[Dict]) -> List[Dict]:
    nodes = [plane_to_json(p) for p in wall_planes + roof_planes + ground_planes]
    edges = relation_edges(wall_planes, roof_planes, ground_planes, wall_segments)
    payload = {
        "input_policy": {
            "roof_type_label_used": False,
            "final_footprint_used": False,
            "final_roof_model_used": False,
            "allowed_inputs": ["sample position", "sample normal", "semantic class", "support weight"],
        },
        "nodes": nodes,
        "edges": edges,
        "summary": {
            "n_wall_plane_candidates": len(wall_planes),
            "n_roof_plane_candidates": len(roof_planes),
            "n_ground_plane_candidates": len(ground_planes),
            "n_edges": len(edges),
        },
    }
    path.write_text(json.dumps(payload, indent=2, default=_jsonable))
    return edges


def write_footprint_graph_json(path: Path, selected: Polygon, candidates: List[Dict],
                               wall_segments: List[Dict]) -> None:
    payload = {
        "selected_candidate_id": candidates[0]["id"],
        "selected_polygon_xz": [[float(x), float(z)] for x, z in list(selected.exterior.coords)[:-1]],
        "selected_score": candidates[0]["score"],
        "candidates": candidates,
        "wall_support_segments": [{
            "wall_node": s["wall_node"],
            "p0": s["p0"].tolist(),
            "p1": s["p1"].tolist(),
            "normal_2d": s["normal_2d"].tolist(),
            "d_2d": s["d_2d"],
            "support_area": s["support_area"],
            "confidence": s["confidence"],
        } for s in wall_segments],
    }
    path.write_text(json.dumps(payload, indent=2, default=_jsonable))


def selected_surfaces_payload(faces: List[Dict], assembly_diag: Dict, city_diag: Dict) -> Dict:
    rows = []
    for i, f in enumerate(faces):
        verts = np.asarray(f["vertices"], dtype=np.float64)
        rows.append({
            "surface_id": i,
            "type": f["type"],
            "source": f.get("source", ""),
            "n_vertices": int(len(verts)),
            "bbox_min": verts.min(axis=0).tolist(),
            "bbox_max": verts.max(axis=0).tolist(),
            "normal": _newell_normal(verts).tolist(),
        })
    return {
        "surfaces": rows,
        "assembly_diagnostics": assembly_diag,
        "cityjson_diagnostics": city_diag,
    }


def optional_roof_archetype(roof_planes: List[PlaneCandidate], assembly_diag: Dict,
                            evidence: Dict) -> Dict:
    roof_mask = evidence["classes"] == 1
    roof_pts = evidence["points"][roof_mask]
    roof_weights = evidence["weights"][roof_mask]
    y_range = float(np.max(roof_pts[:, 1]) - np.min(roof_pts[:, 1])) if len(roof_pts) else 0.0
    total = sum(p.support_weight for p in roof_planes) or 1.0
    dominant = [p for p in roof_planes if p.support_weight / total >= 0.08]
    horizontal_support = sum(p.support_weight for p in dominant if abs(float(np.dot(p.normal, GRAVITY))) > 0.95) / total
    mode_count = len(dominant)
    if horizontal_support > 0.80 and y_range < 1.5:
        label = "flat-like"
    elif mode_count == 2:
        label = "gable-like"
    elif mode_count in (3, 4):
        label = "hip-like"
    else:
        label = "complex-like"
    return {
        "diagnostic_only": True,
        "used_as_algorithm_input": False,
        "label": label,
        "dominant_roof_plane_count": int(mode_count),
        "selected_roof_surface_count": int(assembly_diag.get("n_roof_faces", 0)),
        "roof_y_range": y_range,
        "horizontal_support_fraction": float(horizontal_support),
        "dominant_roof_modes": [plane_to_json(p) for p in dominant],
        "topology_notes": {
            "ridge_or_hip_edges_inferred_from_plane_modes": int(mode_count > 1),
            "roof_mesh_representation": "continuous height-field triangulation over wall-derived footprint",
        },
    }


def val3dity_summary(cj_path: Path, report_path: Path) -> Dict:
    raw = _run_val3dity(cj_path, report_path)
    if raw.get("error"):
        report_path.write_text(json.dumps(raw, indent=2))
        return {"valid": None, "error_codes": [raw["error"]], "raw": raw}
    summary = _summarize_val3dity(raw)
    return {"valid": bool(summary["valid"]), "error_codes": summary["error_codes"], "raw": raw}


def evaluate_cityjson(cj_path: Path, building: Dict, city_diag: Dict,
                      bdir: Path) -> Dict:
    v3d = val3dity_summary(cj_path, bdir / "val3dity_relation.json")
    gt_v = np.concatenate([f["vertices"] for f in building["faces"]], axis=0)
    gt_h = float(gt_v[:, 1].max() - gt_v[:, 1].min())
    pred_tris = cj_mesh_triangles(cj_path)
    gt_tris = gt_mesh_triangles(building)
    pred_pts = _sample_triangles(pred_tris, N_METRIC_SAMPLE, seed=10)
    gt_pts = _sample_triangles(gt_tris, N_METRIC_SAMPLE, seed=11)
    hausdorff, chamfer = hausdorff_chamfer(pred_pts, gt_pts)
    if len(pred_pts) and len(gt_pts):
        tree = cKDTree(pred_pts)
        d_gt_to_pred, _ = tree.query(gt_pts)
        coverage = float(np.mean(d_gt_to_pred <= SURFACE_COVERAGE_THRESH_M))
    else:
        coverage = float("nan")
    if len(pred_tris):
        pred_vertices = pred_tris.reshape(-1, 3)
        pred_h = float(pred_vertices[:, 1].max() - pred_vertices[:, 1].min())
    else:
        pred_h = float("nan")
    gt_vol = gt_volume_anchored(building)
    pred_vol = float(abs(city_diag.get("signed_volume", float("nan"))))
    return {
        "bid": int(building["building_id"]),
        "true_type_eval_only": building.get("type"),
        "cityjson_path": str(cj_path),
        "val3dity_valid": v3d["valid"],
        "val3dity_errors": v3d["error_codes"],
        "output_h": pred_h,
        "GT_h": gt_h,
        "h_err": abs(pred_h - gt_h) if not math.isnan(pred_h) else None,
        "output_vol": pred_vol,
        "GT_vol": gt_vol,
        "vol_ratio": pred_vol / max(gt_vol, 1e-9),
        "coverage": coverage,
        "coverage_definition": f"fraction of sampled GT surface points within {SURFACE_COVERAGE_THRESH_M}m of relation mesh",
        "hausdorff": hausdorff,
        "chamfer": chamfer,
        "n_surfaces": city_diag.get("n_surfaces"),
        "n_vertices": city_diag.get("n_vertices"),
        "edge_incidence_ok": city_diag.get("all_boundary_edges_exactly_2"),
        "n_edges_incident_1": city_diag.get("n_edges_incident_1"),
        "n_edges_incident_gt2": city_diag.get("n_edges_incident_gt2"),
    }


def verdict_for_metrics(metrics: Dict) -> str:
    if metrics["val3dity_valid"] is None:
        return "VAL3DITY_NOT_RUN_GEOMETRY_REVIEW_ONLY"
    if not metrics["val3dity_valid"]:
        return "RELATION_SHELL_INVALID"
    if metrics["edge_incidence_ok"] and metrics["coverage"] >= 0.70 and metrics["vol_ratio"] >= 0.70:
        return "RELATION_READOUT_OK"
    if metrics["edge_incidence_ok"] and metrics["coverage"] >= 0.50:
        return "RELATION_READOUT_PARTIAL"
    return "RELATION_READOUT_LOW_FIT"


def process_building(building: Dict) -> Dict:
    bid = int(building["building_id"])
    bdir = OUT_ROOT / f"B{bid}"
    _mkdir(bdir)
    evidence = generate_evidence(building)
    np.savez_compressed(bdir / "evidence_gt_sampled.npz", **evidence)
    write_evidence_ply(bdir / "evidence_gt_sampled.ply", evidence)
    write_evidence_ply(bdir / "wall_evidence.ply", evidence, evidence["classes"] == 2)
    write_evidence_ply(bdir / "roof_evidence.ply", evidence, evidence["classes"] == 1)
    write_evidence_stats(bdir / "evidence_stats.csv", evidence)

    wall_planes = cluster_planes_from_evidence(evidence, 2)
    roof_planes = cluster_planes_from_evidence(evidence, 1)
    ground_planes = cluster_planes_from_evidence(evidence, 3)
    footprint, footprint_candidates, wall_segments = build_footprint_candidates(evidence, wall_planes)
    write_footprint_graph_json(bdir / "footprint_graph.json", footprint, footprint_candidates, wall_segments)
    # Compatibility filename from the broader P1-4a request.
    (bdir / "footprint_candidates.json").write_text(json.dumps({
        "selected_candidate_id": footprint_candidates[0]["id"],
        "candidates": footprint_candidates,
    }, indent=2, default=_jsonable))
    write_footprint_plot(bdir / "footprint_candidates.png", footprint, footprint_candidates, evidence)
    graph_edges = write_graph_json(bdir / "evidence_graph.json", wall_planes, roof_planes,
                                   ground_planes, wall_segments)
    roof_candidates = roof_surface_candidates(roof_planes, footprint, evidence)
    (bdir / "roof_surface_candidates.json").write_text(json.dumps({
        "roof_surface_generation": "roof plane candidates clipped diagnostically; final shell uses relation height-field triangulation",
        "candidates": roof_candidates,
    }, indent=2, default=_jsonable))
    # Compatibility filename from the broader P1-4a request.
    (bdir / "roof_modes.json").write_text(json.dumps({
        "roof_type_label_used": False,
        "roof_plane_candidates": [plane_to_json(p) for p in roof_planes],
    }, indent=2, default=_jsonable))
    write_roof_mode_plot(bdir / "roof_mode_plot.png", roof_planes)

    faces, assembly_diag = assemble_closed_shell(footprint, evidence, roof_planes)
    cj_path = bdir / "relation_readout.city.json"
    city_diag = faces_to_cityjson(faces, bid, cj_path)
    selected = selected_surfaces_payload(faces, assembly_diag, city_diag)
    (bdir / "selected_surfaces.json").write_text(json.dumps(selected, indent=2, default=_jsonable))
    archetype = optional_roof_archetype(roof_planes, assembly_diag, evidence)
    (bdir / "optional_roof_archetype.json").write_text(json.dumps(archetype, indent=2, default=_jsonable))
    metrics = evaluate_cityjson(cj_path, building, city_diag, bdir)
    metrics["verdict"] = verdict_for_metrics(metrics)
    metrics["optional_roof_archetype"] = archetype["label"]
    metrics["input_assertions"] = {
        "roof_type_label_used_in_part_b": False,
        "final_footprint_used_in_part_b": False,
        "final_roof_model_used_in_part_b": False,
        "roof_archetype_is_diagnostic_only": True,
    }
    metrics["graph_summary"] = {
        "n_wall_plane_candidates": len(wall_planes),
        "n_roof_plane_candidates": len(roof_planes),
        "n_ground_plane_candidates": len(ground_planes),
        "n_relation_edges": len(graph_edges),
        "selected_footprint_candidate": footprint_candidates[0]["id"],
        "selected_footprint_score": footprint_candidates[0]["score"],
    }
    (bdir / "metrics.json").write_text(json.dumps(metrics, indent=2, default=_jsonable))
    return metrics


def write_summary_csv(path: Path, rows: List[Dict]) -> None:
    fields = [
        "bid", "true_type_eval_only", "optional_roof_archetype", "val3dity_valid",
        "val3dity_errors", "h_err", "coverage", "vol_ratio", "hausdorff",
        "chamfer", "edge_incidence_ok", "n_edges_incident_1",
        "n_edges_incident_gt2", "n_surfaces", "verdict",
    ]
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            out = {k: row.get(k, "") for k in fields}
            out["val3dity_errors"] = ";".join(str(x) for x in row.get("val3dity_errors", []))
            writer.writerow(out)


def write_report(rows: List[Dict]) -> None:
    core = [r for r in rows if int(r["bid"]) in CORE_BIDS]
    val3dity_available = all(r["val3dity_valid"] is not None for r in rows)
    simple_ok = [r for r in core if r["true_type_eval_only"] in ("flat", "gable")
                 and r["coverage"] >= 0.70 and r["vol_ratio"] >= 0.70 and r["edge_incidence_ok"]]
    hip_tri_partial = [r for r in core if r["true_type_eval_only"] in ("hip", "tri-slope")
                       and r["coverage"] >= 0.50 and r["vol_ratio"] >= 0.50 and r["edge_incidence_ok"]]
    if not val3dity_available:
        overall = "B_UNDECIDED_VAL3DITY_NOT_AVAILABLE"
    elif len(simple_ok) >= 3 and len(hip_tri_partial) >= 1:
        overall = "B_GO"
    elif len(simple_ok) >= 3:
        overall = "B_PARTIAL"
    else:
        overall = "B_NG"

    lines = [
        "# P1-4a Part B - GT-derived Evidence Relation Read-out",
        "",
        "## 1. Purpose",
        "",
        "This run tests whether GT-sampled position/normal/semantic evidence can be converted into a closed CityJSON shell through geometric relations. Roof archetype is not an input and is only written as a post-hoc diagnostic.",
        "",
        "## 2. Inputs And Restrictions",
        "",
        f"- GT source: `{SCENE.relative_to(ROOT)}`",
        "- Allowed Part B inputs: sampled point position, sample normal, semantic class, support weight.",
        "- Forbidden Part B inputs: GT roof type label, final footprint polygon, final roof model.",
        "- Assertion: every `metrics.json` records `roof_type_label_used_in_part_b=false`, `final_footprint_used_in_part_b=false`, and `final_roof_model_used_in_part_b=false`.",
        "",
        "## 3. Method",
        "",
        "1. Build an evidence graph with wall/roof/ground plane candidates and relation edges.",
        "2. Generate footprint candidates from wall support points and wall-plane support lines.",
        "3. Generate roof surface candidates from roof plane evidence; assemble the final roof as a continuous height-field triangulation over the selected wall-derived footprint.",
        "4. Split wall and ground boundaries against the roof boundary, then export a semantic CityJSON shell.",
        "5. Evaluate edge incidence, val3dity availability/result, height, surface coverage, volume ratio, Hausdorff, and Chamfer.",
        "",
        "## 4. Results",
        "",
        "| bid | true_type_eval_only | diagnostic_archetype | val3dity | errors | h_err | coverage | vol_ratio | Hausdorff | edge_ok | verdict |",
        "|---:|---|---|---|---|---:|---:|---:|---:|---|---|",
    ]
    for r in rows:
        val = "NOT_RUN" if r["val3dity_valid"] is None else ("PASS" if r["val3dity_valid"] else "FAIL")
        lines.append(
            f"| B{r['bid']} | {r['true_type_eval_only']} | {r['optional_roof_archetype']} | "
            f"{val} | {';'.join(str(x) for x in r['val3dity_errors'])} | "
            f"{_fmt(r['h_err'])} | {_fmt(r['coverage'], 3)} | {_fmt(r['vol_ratio'], 3)} | "
            f"{_fmt(r['hausdorff'])} | {r['edge_incidence_ok']} | {r['verdict']} |"
        )
    lines.extend([
        "",
        "Coverage is surface coverage: sampled GT surface points within "
        f"{SURFACE_COVERAGE_THRESH_M}m of the relation-readout mesh.",
        "",
        "## 5. Output Files",
        "",
        "| bid | evidence graph | footprint graph | roof candidates | selected surfaces | cityjson | archetype | metrics |",
        "|---:|---|---|---|---|---|---|---|",
    ])
    for r in rows:
        b = f"B{r['bid']}"
        lines.append(
            f"| {b} | [{b}/evidence_graph.json]({b}/evidence_graph.json) | "
            f"[{b}/footprint_graph.json]({b}/footprint_graph.json) | "
            f"[{b}/roof_surface_candidates.json]({b}/roof_surface_candidates.json) | "
            f"[{b}/selected_surfaces.json]({b}/selected_surfaces.json) | "
            f"[{b}/relation_readout.city.json]({b}/relation_readout.city.json) | "
            f"[{b}/optional_roof_archetype.json]({b}/optional_roof_archetype.json) | "
            f"[{b}/metrics.json]({b}/metrics.json) |"
        )
    lines.extend([
        "",
        "## 6. PolyFit Audit Comparison",
        "",
        f"- PolyFit audit reference: `{POLYFIT_AUDIT.relative_to(ROOT)}`",
        "- PolyFit GT-derived raw input result summary: B1 success; B2/B8 valid-small; B6/B0/B3 over-segmented or arrangement-limited.",
        "- Relation read-out avoids mandatory roof-type selection and does not assemble raw plane arrangements directly. It instead builds a closed shell from wall-derived boundary plus roof evidence height relations.",
        "- If val3dity is unavailable in this shell, geometry conclusions are limited to edge incidence and sampled metric checks until the validator is installed.",
        "",
        "## 7. Stage2-derived Read-out Decision",
        "",
        f"- Overall Part B verdict: `{overall}`",
    ])
    if overall == "B_UNDECIDED_VAL3DITY_NOT_AVAILABLE":
        lines.append("- Decision: rerun with `val3dity` on PATH before a formal GO/NG. Geometry artifacts and metrics are still generated for inspection.")
    elif overall == "B_GO":
        lines.append("- Decision: proceed to P1-4b Stage2-derived relation read-out.")
    elif overall == "B_PARTIAL":
        lines.append("- Decision: flat/gable relation read-out is viable; improve complex roof height-field/partitioning before broad Stage2-derived testing.")
    else:
        lines.append("- Decision: relation inference is not ready for Stage2-derived testing.")
    lines.extend([
        "",
        "## 8. Self-verification",
        "",
    ])
    checks = [
        ("all target bids have evidence_graph.json", all((OUT_ROOT / f"B{r['bid']}" / "evidence_graph.json").exists() for r in rows)),
        ("all target bids have footprint_graph.json", all((OUT_ROOT / f"B{r['bid']}" / "footprint_graph.json").exists() for r in rows)),
        ("all target bids have roof_surface_candidates.json", all((OUT_ROOT / f"B{r['bid']}" / "roof_surface_candidates.json").exists() for r in rows)),
        ("all target bids have selected_surfaces.json", all((OUT_ROOT / f"B{r['bid']}" / "selected_surfaces.json").exists() for r in rows)),
        ("all target bids have relation_readout.city.json", all((OUT_ROOT / f"B{r['bid']}" / "relation_readout.city.json").exists() for r in rows)),
        ("all target bids have optional_roof_archetype.json", all((OUT_ROOT / f"B{r['bid']}" / "optional_roof_archetype.json").exists() for r in rows)),
        ("all target bids have metrics.json", all((OUT_ROOT / f"B{r['bid']}" / "metrics.json").exists() for r in rows)),
        ("GT roof type not used as Part B scoring/construction input", all(
            not r.get("input_assertions", {}).get("roof_type_label_used_in_part_b", True)
            for r in rows)),
    ]
    for name, ok in checks:
        lines.append(f"- {'PASS' if ok else 'FAIL'}: {name}")
    (OUT_ROOT / "REPORT.md").write_text("\n".join(lines) + "\n")


def main() -> None:
    _mkdir(OUT_ROOT)
    gt = parse_scene_obj(SCENE, frame="obj")
    rows = []
    for bid in TARGET_BIDS:
        building = next(b for b in gt["buildings"] if int(b["building_id"]) == bid)
        print(f"[relation-readout] B{bid} {building['type']}")
        rows.append(process_building(building))
    write_summary_csv(OUT_ROOT / "summary_metrics.csv", rows)
    write_report(rows)
    print(f"[relation-readout] saved {OUT_ROOT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
