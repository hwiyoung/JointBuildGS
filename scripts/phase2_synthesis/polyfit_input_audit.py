"""Audit GT-derived PolyFit Stage A inputs.

This script intentionally reuses the existing Stage A plane clustering,
sampling, and input writer from polyfit_phase2.py. It does not tune PolyFit
parameters or alter the point generation rule.
"""
from __future__ import annotations

import csv
import json
import math
import shutil
import sys
from collections import Counter, defaultdict, deque
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from mpl_toolkits.mplot3d.art3d import Poly3DCollection

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from scripts.phase2_synthesis.obj_gt import parse_scene_obj  # noqa: E402
from scripts.phase2_synthesis.polyfit_phase2 import (  # noqa: E402
    cluster_planes,
    sample_points_on_face,
    write_polyfit_input,
)


SCENE = ROOT / "results/phase2_synthesis/scene.obj"
STAGE_A_METRICS = ROOT / "results/stage3_polyfit_phase2/metrics.json"
OUT_ROOT = ROOT / "results/stage3_v4_validation/polyfit_input_audit"

TARGET_BIDS = [1, 2, 6, 8, 0, 3]
CORE_BIDS = [1, 2, 6, 8, 0]
TARGET_N_POINTS = 500

CLASS_NAME = {1: "roof", 2: "wall", 3: "ground", 0: "unknown", -1: "unknown"}
CLASS_ID_FROM_NAME = {"unknown": 0, "roof": 1, "wall": 2, "ground": 3}
CLASS_COLOR = {
    1: (220, 40, 40),
    2: (45, 95, 215),
    3: (45, 160, 75),
    0: (150, 150, 150),
    -1: (150, 150, 150),
}


def _mkdir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def _fmt_float(v: Optional[float], nd: int = 4) -> str:
    if v is None:
        return "NA"
    if isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
        return "NA"
    return f"{float(v):.{nd}f}"


def _plane_color(pid: int) -> Tuple[int, int, int]:
    if pid < 0:
        return (120, 120, 120)
    hue = ((pid * 0.61803398875) % 1.0)
    sat = 0.62
    val = 0.92
    i = int(hue * 6.0)
    f = hue * 6.0 - i
    p = val * (1.0 - sat)
    q = val * (1.0 - f * sat)
    t = val * (1.0 - (1.0 - f) * sat)
    i %= 6
    if i == 0:
        r, g, b = val, t, p
    elif i == 1:
        r, g, b = q, val, p
    elif i == 2:
        r, g, b = p, val, t
    elif i == 3:
        r, g, b = p, q, val
    elif i == 4:
        r, g, b = t, p, val
    else:
        r, g, b = val, p, q
    return (int(r * 255), int(g * 255), int(b * 255))


def _all_vertices(faces: List[Dict]) -> np.ndarray:
    return np.concatenate([np.asarray(f["vertices"], dtype=np.float64) for f in faces])


def _bbox(points: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
    if len(points) == 0:
        z = np.zeros(3)
        return z.copy(), z.copy()
    return points.min(axis=0), points.max(axis=0)


def _bbox_gap(a_min: np.ndarray, a_max: np.ndarray,
              b_min: np.ndarray, b_max: np.ndarray) -> float:
    gaps = []
    for k in range(3):
        if a_max[k] < b_min[k]:
            gaps.append(b_min[k] - a_max[k])
        elif b_max[k] < a_min[k]:
            gaps.append(a_min[k] - b_max[k])
        else:
            gaps.append(0.0)
    return float(np.linalg.norm(gaps))


def _angle_deg_abs(a: np.ndarray, b: np.ndarray) -> float:
    cos = abs(float(np.dot(a, b)))
    cos = min(1.0, max(-1.0, cos))
    return float(np.degrees(np.arccos(cos)))


def _aligned_d_delta(a_n: np.ndarray, a_d: float, b_n: np.ndarray, b_d: float) -> float:
    if float(np.dot(a_n, b_n)) < 0:
        return abs(a_d + b_d)
    return abs(a_d - b_d)


def _semantic_class_for_faces(faces: List[Dict], face_ids: Iterable[int]) -> int:
    area_by_cls: Dict[int, float] = defaultdict(float)
    for fi in face_ids:
        cls = int(faces[fi].get("semantic_class", 0))
        area_by_cls[cls] += float(faces[fi]["area"])
    if not area_by_cls:
        return 0
    return max(area_by_cls.items(), key=lambda kv: kv[1])[0]


def build_stage_a_input_with_trace(faces: List[Dict], target_n_points: int = TARGET_N_POINTS):
    """Same Stage A input rule, plus face/semantic provenance per sampled point."""
    planes = cluster_planes(faces)
    total_area = sum(float(f["area"]) for f in faces)
    all_pts: List[np.ndarray] = []
    all_normals: List[np.ndarray] = []
    all_pids: List[np.ndarray] = []
    point_face_ids: List[int] = []
    point_class_ids: List[int] = []
    face_to_plane: Dict[int, int] = {}
    face_sample_counts = {i: 0 for i in range(len(faces))}
    face_target_counts = {i: 0 for i in range(len(faces))}

    for pi, (pn, _pd, fis) in enumerate(planes):
        for fi in fis:
            face_to_plane[int(fi)] = int(pi)
            f = faces[fi]
            n_per_face = max(8, int(round(target_n_points * float(f["area"]) / total_area)))
            pts = sample_points_on_face(f, n_per_face)
            all_pts.append(pts)
            all_normals.append(np.tile(pn, (len(pts), 1)))
            all_pids.append(np.full(len(pts), pi))
            point_face_ids.extend([int(fi)] * len(pts))
            point_class_ids.extend([int(f.get("semantic_class", 0))] * len(pts))
            face_sample_counts[int(fi)] = int(len(pts))
            face_target_counts[int(fi)] = int(n_per_face)

    if not all_pts:
        return None
    pts = np.concatenate(all_pts)
    normals = np.concatenate(all_normals)
    pids = np.concatenate(all_pids)
    return {
        "planes": planes,
        "pts": pts,
        "normals": normals,
        "pids": pids,
        "n_planes": len(planes),
        "point_face_ids": np.asarray(point_face_ids, dtype=np.int64),
        "point_class_ids": np.asarray(point_class_ids, dtype=np.int64),
        "face_to_plane": face_to_plane,
        "face_sample_counts": face_sample_counts,
        "face_target_counts": face_target_counts,
    }


def write_building_obj(path: Path, faces: List[Dict]) -> None:
    lines = ["# Per-building GT mesh extracted from results/phase2_synthesis/scene.obj"]
    v_offset = 1
    for fi, face in enumerate(faces):
        lines.append(f"g face_{fi}")
        lines.append(f"usemtl {face.get('material', 'Unknown')}")
        verts = np.asarray(face["vertices"], dtype=np.float64)
        for v in verts:
            lines.append(f"v {v[0]:.6f} {v[1]:.6f} {v[2]:.6f}")
        idxs = " ".join(str(v_offset + j) for j in range(len(verts)))
        lines.append(f"f {idxs}")
        v_offset += len(verts)
    path.write_text("\n".join(lines) + "\n")


def read_polyfit_input(path: Path) -> Dict:
    lines = path.read_text().splitlines()
    header_tokens = lines[0].split() if lines else []
    header_ok = len(header_tokens) >= 2
    header_n_points = int(header_tokens[0]) if header_ok else -1
    header_n_planes = int(header_tokens[1]) if header_ok else -1
    rows = []
    bad_field_lines = []
    for li, line in enumerate(lines[1:], start=2):
        toks = line.split()
        if len(toks) not in (7, 8):
            bad_field_lines.append(li)
            continue
        try:
            rows.append([float(t) for t in toks[:6]] + [int(float(toks[6]))] +
                        ([int(float(toks[7]))] if len(toks) == 8 else []))
        except ValueError:
            bad_field_lines.append(li)
    arr = np.asarray(rows, dtype=np.float64) if rows else np.empty((0, 7))
    return {
        "lines": lines,
        "header_n_points": header_n_points,
        "header_n_planes": header_n_planes,
        "rows": arr,
        "bad_field_lines": bad_field_lines,
    }


def validate_input(path: Path, gt_bbox: Tuple[np.ndarray, np.ndarray]) -> Dict:
    parsed = read_polyfit_input(path)
    rows = parsed["rows"]
    n_actual = int(rows.shape[0])
    n_header = int(parsed["header_n_points"])
    n_planes = int(parsed["header_n_planes"])
    coords = rows[:, :3] if n_actual else np.empty((0, 3))
    normals = rows[:, 3:6] if n_actual else np.empty((0, 3))
    pids = rows[:, 6].astype(int) if n_actual else np.empty((0,), dtype=np.int64)
    finite_xyz = np.isfinite(coords).all(axis=1) if n_actual else np.asarray([], dtype=bool)
    finite_normals = np.isfinite(normals).all(axis=1) if n_actual else np.asarray([], dtype=bool)
    norm_len = np.linalg.norm(normals, axis=1) if n_actual else np.asarray([])
    invalid_normals = int((~finite_normals | (np.abs(norm_len - 1.0) > 1e-3)).sum())
    out_of_range = int(((pids < -1) | (pids >= n_planes)).sum()) if n_actual else 0
    used_planes = set(int(p) for p in pids if 0 <= int(p) < n_planes)
    zero_point_planes = [p for p in range(max(n_planes, 0)) if p not in used_planes]
    if n_actual:
        rounded = np.round(coords, decimals=4)
        unique_count = len({tuple(row.tolist()) for row in rounded})
        duplicate_ratio = float(1.0 - unique_count / max(n_actual, 1))
        in_min, in_max = _bbox(coords)
        gt_min, gt_max = gt_bbox
        bbox_max_abs_delta = float(max(np.max(np.abs(in_min - gt_min)),
                                       np.max(np.abs(in_max - gt_max))))
        gt_span = np.maximum(gt_max - gt_min, 1e-9)
        span_ratio = (in_max - in_min) / gt_span
        bbox_match = bool(bbox_max_abs_delta <= 0.05 and np.all(span_ratio > 0.99))
    else:
        duplicate_ratio = 0.0
        in_min, in_max = np.zeros(3), np.zeros(3)
        bbox_max_abs_delta = float("nan")
        span_ratio = np.zeros(3)
        bbox_match = False
    class_check = "NO_CLASS_COLUMN"
    if rows.shape[1] >= 8:
        class_ids = rows[:, 7].astype(int)
        bad_class = int(~np.isin(class_ids, [0, 1, 2, 3]).sum())
        class_check = "OK" if bad_class == 0 else f"BAD:{bad_class}"
    verdict = "PASS"
    if (n_actual != n_header or parsed["bad_field_lines"] or invalid_normals or
            out_of_range or not bbox_match):
        verdict = "FAIL"
    return {
        "n_points": n_actual,
        "n_points_header": n_header,
        "n_planes": n_planes,
        "line_count_match": n_actual == n_header,
        "bad_field_lines": len(parsed["bad_field_lines"]),
        "invalid_xyz": int((~finite_xyz).sum()) if n_actual else 0,
        "invalid_normals": invalid_normals,
        "out_of_range_plane_id": out_of_range,
        "zero_point_planes": zero_point_planes,
        "duplicate_ratio": duplicate_ratio,
        "bbox_match": bbox_match,
        "bbox_max_abs_delta": bbox_max_abs_delta,
        "input_bbox_min": in_min,
        "input_bbox_max": in_max,
        "span_ratio": span_ratio,
        "class_check": class_check,
        "verdict": verdict,
    }


def write_input_validation_csv(path: Path, bid: int, validation: Dict) -> None:
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=[
            "bid", "n_points", "n_points_header", "n_planes",
            "line_count_match", "bad_field_lines", "invalid_xyz",
            "invalid_normals", "out_of_range_plane_id", "zero_point_planes",
            "duplicate_ratio", "bbox_match", "bbox_max_abs_delta",
            "class_check", "verdict",
        ])
        writer.writeheader()
        row = dict(validation)
        row["bid"] = bid
        row["zero_point_planes"] = ";".join(str(x) for x in validation["zero_point_planes"])
        row["input_bbox_min"] = ""
        row["input_bbox_max"] = ""
        row["span_ratio"] = ""
        writer.writerow({k: row.get(k, "") for k in writer.fieldnames})


def plane_connected_components(faces: List[Dict], face_ids: List[int]) -> int:
    if not face_ids:
        return 0
    keys_by_face: Dict[int, set] = {}
    for fi in face_ids:
        verts = np.asarray(faces[fi]["vertices"], dtype=np.float64)
        keys_by_face[fi] = {tuple(np.round(v, 5).tolist()) for v in verts}
    adj: Dict[int, List[int]] = {fi: [] for fi in face_ids}
    for i, a in enumerate(face_ids):
        for b in face_ids[i + 1:]:
            shared = keys_by_face[a].intersection(keys_by_face[b])
            if len(shared) >= 2:
                adj[a].append(b)
                adj[b].append(a)
    seen = set()
    comps = 0
    for fi in face_ids:
        if fi in seen:
            continue
        comps += 1
        q = deque([fi])
        seen.add(fi)
        while q:
            cur = q.popleft()
            for nb in adj[cur]:
                if nb not in seen:
                    seen.add(nb)
                    q.append(nb)
    return comps


def compute_plane_metadata(faces: List[Dict], trace: Dict) -> Tuple[List[Dict], Dict[int, List[str]]]:
    planes = trace["planes"]
    sample_counts = Counter(int(p) for p in trace["pids"])
    largest_area = 0.0
    base_meta = []
    for pi, (pn_raw, pd, fis_raw) in enumerate(planes):
        pn = np.asarray(pn_raw, dtype=np.float64)
        pn = pn / (np.linalg.norm(pn) + 1e-12)
        fis = [int(x) for x in fis_raw]
        area = float(sum(float(faces[fi]["area"]) for fi in fis))
        largest_area = max(largest_area, area)
        cls = _semantic_class_for_faces(faces, fis)
        verts = _all_vertices([faces[fi] for fi in fis])
        mn, mx = _bbox(verts)
        ds = [float(np.dot(pn, np.asarray(faces[fi]["centroid"], dtype=np.float64))) for fi in fis]
        d_spread_mm = (max(ds) - min(ds)) * 1000.0 if ds else 0.0
        normal_spread_deg = max((_angle_deg_abs(pn, np.asarray(faces[fi]["normal"], dtype=np.float64))
                                 for fi in fis), default=0.0)
        class_set = {int(faces[fi].get("semantic_class", 0)) for fi in fis}
        base_meta.append({
            "plane_id": pi,
            "semantic_class_id": cls,
            "semantic_class": CLASS_NAME.get(cls, "unknown"),
            "normal": pn,
            "d": float(pd),
            "area_total": area,
            "n_gt_faces": len(fis),
            "n_sampled_points": int(sample_counts.get(pi, 0)),
            "members_gt_face_ids": fis,
            "d_spread_mm": float(d_spread_mm),
            "normal_spread_deg": float(normal_spread_deg),
            "bbox_min": mn,
            "bbox_max": mx,
            "class_set": class_set,
            "component_count": plane_connected_components(faces, fis),
        })

    major_by_class: Dict[int, List[np.ndarray]] = defaultdict(list)
    for m in base_meta:
        if m["area_total"] >= max(1.0, 0.05 * largest_area):
            major_by_class[int(m["semantic_class_id"])].append(m["normal"])
    warnings_by_plane: Dict[int, List[str]] = defaultdict(list)
    for m in base_meta:
        pid = int(m["plane_id"])
        is_small = bool(m["area_total"] < 1.0 or m["area_total"] < 0.01 * largest_area)
        m["is_small_area"] = is_small
        if m["n_sampled_points"] < 10:
            warnings_by_plane[pid].append("LOW_POINTS")
        if is_small:
            warnings_by_plane[pid].append("SMALL_AREA")
        if m["d_spread_mm"] > 50.0:
            warnings_by_plane[pid].append("HIGH_D_SPREAD")
        if m["normal_spread_deg"] > 5.0:
            warnings_by_plane[pid].append("HIGH_NORMAL_SPREAD")
        if len(m["class_set"]) > 1:
            warnings_by_plane[pid].append("MIXED_SEMANTIC_CLASS")
        if m["component_count"] > 1:
            warnings_by_plane[pid].append("POSSIBLE_UNDERSEGMENT")
        major_normals = major_by_class.get(int(m["semantic_class_id"]), [])
        if not major_normals:
            is_off_axis = False
        else:
            best = max(abs(float(np.dot(m["normal"], n))) for n in major_normals)
            is_off_axis = bool(best < 0.98)
        m["is_off_axis"] = is_off_axis
        if is_off_axis:
            warnings_by_plane[pid].append("ISOLATED_PLANE")
    return base_meta, warnings_by_plane


def find_oversegmented_pairs(plane_meta: List[Dict]) -> List[Dict]:
    pairs = []
    for i, a in enumerate(plane_meta):
        for b in plane_meta[i + 1:]:
            if a["semantic_class_id"] != b["semantic_class_id"]:
                continue
            cos = abs(float(np.dot(a["normal"], b["normal"])))
            d_delta = _aligned_d_delta(a["normal"], a["d"], b["normal"], b["d"])
            gap = _bbox_gap(a["bbox_min"], a["bbox_max"], b["bbox_min"], b["bbox_max"])
            if cos > 0.98 and d_delta < 0.2 and gap < 0.5:
                pairs.append({
                    "plane_id_a": int(a["plane_id"]),
                    "plane_id_b": int(b["plane_id"]),
                    "semantic_class": a["semantic_class"],
                    "normal_abs_cos": cos,
                    "d_delta_m": d_delta,
                    "bbox_gap_m": gap,
                    "area_a": float(a["area_total"]),
                    "area_b": float(b["area_total"]),
                })
    return pairs


def find_undersegmented_planes(plane_meta: List[Dict]) -> List[Dict]:
    rows = []
    for m in plane_meta:
        flags = []
        if m["normal_spread_deg"] > 5.0:
            flags.append("HIGH_NORMAL_SPREAD")
        if m["d_spread_mm"] > 50.0:
            flags.append("HIGH_D_SPREAD")
        if m["component_count"] > 1:
            flags.append("MULTI_COMPONENT")
        if flags:
            rows.append({
                "plane_id": int(m["plane_id"]),
                "semantic_class": m["semantic_class"],
                "n_gt_faces": int(m["n_gt_faces"]),
                "component_count": int(m["component_count"]),
                "d_spread_mm": float(m["d_spread_mm"]),
                "normal_spread_deg": float(m["normal_spread_deg"]),
                "warning_flags": ";".join(flags),
                "members_gt_face_ids": ";".join(str(x) for x in m["members_gt_face_ids"]),
            })
    return rows


def write_input_planes_csv(path: Path, plane_meta: List[Dict],
                           warnings_by_plane: Dict[int, List[str]]) -> None:
    fields = [
        "plane_id", "semantic_class", "normal_x", "normal_y", "normal_z", "d",
        "area_total", "n_gt_faces", "n_sampled_points", "members_gt_face_ids",
        "d_spread_mm", "normal_spread_deg", "bbox_min_x", "bbox_min_y",
        "bbox_min_z", "bbox_max_x", "bbox_max_y", "bbox_max_z",
        "is_small_area", "is_off_axis", "component_count", "warning_flags",
    ]
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for m in plane_meta:
            n = m["normal"]
            mn, mx = m["bbox_min"], m["bbox_max"]
            writer.writerow({
                "plane_id": m["plane_id"],
                "semantic_class": m["semantic_class"],
                "normal_x": n[0],
                "normal_y": n[1],
                "normal_z": n[2],
                "d": m["d"],
                "area_total": m["area_total"],
                "n_gt_faces": m["n_gt_faces"],
                "n_sampled_points": m["n_sampled_points"],
                "members_gt_face_ids": ";".join(str(x) for x in m["members_gt_face_ids"]),
                "d_spread_mm": m["d_spread_mm"],
                "normal_spread_deg": m["normal_spread_deg"],
                "bbox_min_x": mn[0],
                "bbox_min_y": mn[1],
                "bbox_min_z": mn[2],
                "bbox_max_x": mx[0],
                "bbox_max_y": mx[1],
                "bbox_max_z": mx[2],
                "is_small_area": int(bool(m["is_small_area"])),
                "is_off_axis": int(bool(m["is_off_axis"])),
                "component_count": m["component_count"],
                "warning_flags": ";".join(warnings_by_plane.get(int(m["plane_id"]), [])),
            })


def write_rows(path: Path, rows: List[Dict], fieldnames: List[str]) -> None:
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k, "") for k in fieldnames})


def write_points_ply(path: Path, pts: np.ndarray, normals: np.ndarray,
                     pids: np.ndarray, class_ids: np.ndarray,
                     color_mode: str) -> None:
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
        "property int plane_id",
        "property int class_id",
        "end_header",
    ]
    for p, n, pid, cls in zip(pts, normals, pids, class_ids):
        color = _plane_color(int(pid)) if color_mode == "plane" else CLASS_COLOR.get(int(cls), CLASS_COLOR[0])
        lines.append(
            f"{p[0]:.6f} {p[1]:.6f} {p[2]:.6f} "
            f"{n[0]:.6f} {n[1]:.6f} {n[2]:.6f} "
            f"{color[0]} {color[1]} {color[2]} {int(pid)} {int(cls)}"
        )
    path.write_text("\n".join(lines) + "\n")


def write_normals_segments_ply(path: Path, pts: np.ndarray, normals: np.ndarray,
                               pids: np.ndarray, scale: float = 0.45) -> None:
    verts = []
    edges = []
    for i, (p, n, pid) in enumerate(zip(pts, normals, pids)):
        color = _plane_color(int(pid))
        verts.append((p, color))
        verts.append((p + n * scale, color))
        edges.append((2 * i, 2 * i + 1, color))
    lines = [
        "ply",
        "format ascii 1.0",
        f"element vertex {len(verts)}",
        "property float x",
        "property float y",
        "property float z",
        "property uchar red",
        "property uchar green",
        "property uchar blue",
        f"element edge {len(edges)}",
        "property int vertex1",
        "property int vertex2",
        "property uchar red",
        "property uchar green",
        "property uchar blue",
        "end_header",
    ]
    for p, color in verts:
        lines.append(f"{p[0]:.6f} {p[1]:.6f} {p[2]:.6f} {color[0]} {color[1]} {color[2]}")
    for v1, v2, color in edges:
        lines.append(f"{v1} {v2} {color[0]} {color[1]} {color[2]}")
    path.write_text("\n".join(lines) + "\n")


def write_mesh_ply(path: Path, faces: List[Dict], face_to_plane: Dict[int, int],
                   plane_to_class: Dict[int, int]) -> None:
    verts: List[np.ndarray] = []
    face_rows = []
    for fi, face in enumerate(faces):
        start = len(verts)
        fverts = np.asarray(face["vertices"], dtype=np.float64)
        verts.extend([v for v in fverts])
        pid = int(face_to_plane.get(fi, -1))
        cls = int(plane_to_class.get(pid, int(face.get("semantic_class", 0))))
        color = _plane_color(pid)
        face_rows.append((list(range(start, start + len(fverts))), color, pid, cls))
    lines = [
        "ply",
        "format ascii 1.0",
        f"element vertex {len(verts)}",
        "property float x",
        "property float y",
        "property float z",
        f"element face {len(face_rows)}",
        "property list uchar int vertex_indices",
        "property uchar red",
        "property uchar green",
        "property uchar blue",
        "property int plane_id",
        "property int semantic_class",
        "end_header",
    ]
    for v in verts:
        lines.append(f"{v[0]:.6f} {v[1]:.6f} {v[2]:.6f}")
    for idxs, color, pid, cls in face_rows:
        lines.append(
            f"{len(idxs)} {' '.join(str(i) for i in idxs)} "
            f"{color[0]} {color[1]} {color[2]} {pid} {cls}"
        )
    path.write_text("\n".join(lines) + "\n")


def write_plane_legend(path: Path, csv_path: Path, plane_meta: List[Dict]) -> None:
    rows = []
    for m in plane_meta:
        pid = int(m["plane_id"])
        color = _plane_color(pid)
        rows.append({
            "plane_id": pid,
            "semantic_class": m["semantic_class"],
            "red": color[0],
            "green": color[1],
            "blue": color[2],
            "area_total": m["area_total"],
            "n_sampled_points": m["n_sampled_points"],
        })
    write_rows(csv_path, rows, ["plane_id", "semantic_class", "red", "green", "blue",
                                "area_total", "n_sampled_points"])
    n = max(1, len(rows))
    fig_h = max(2.0, min(18.0, 0.28 * n + 0.7))
    fig, ax = plt.subplots(figsize=(5.8, fig_h))
    ax.axis("off")
    for i, row in enumerate(rows):
        y = n - i - 1
        color = (row["red"] / 255.0, row["green"] / 255.0, row["blue"] / 255.0)
        ax.add_patch(plt.Rectangle((0.03, y + 0.18), 0.08, 0.6, color=color))
        ax.text(0.14, y + 0.48,
                f"plane {row['plane_id']:02d}  {row['semantic_class']}  "
                f"A={row['area_total']:.2f}  pts={row['n_sampled_points']}",
                va="center", fontsize=8)
    ax.set_xlim(0, 1)
    ax.set_ylim(0, n)
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)


def _plot_face_edges_2d(ax, faces: List[Dict], axes: Tuple[int, int]) -> None:
    for face in faces:
        verts = np.asarray(face["vertices"], dtype=np.float64)
        closed = np.vstack([verts, verts[0]])
        ax.plot(closed[:, axes[0]], closed[:, axes[1]], color="black",
                linewidth=0.35, alpha=0.45)


def _set_equal_2d(ax, points: np.ndarray, axes: Tuple[int, int]) -> None:
    mn, mx = _bbox(points)
    lo = mn[list(axes)]
    hi = mx[list(axes)]
    span = hi - lo
    pad = max(float(span.max()) * 0.06, 0.5)
    ax.set_xlim(lo[0] - pad, hi[0] + pad)
    ax.set_ylim(lo[1] - pad, hi[1] + pad)
    ax.set_aspect("equal", adjustable="box")


def write_overlay_2d(path: Path, faces: List[Dict], pts: np.ndarray,
                     pids: np.ndarray, class_ids: np.ndarray,
                     axes: Tuple[int, int], labels: Tuple[str, str],
                     color_mode: str, title: str) -> None:
    fig, ax = plt.subplots(figsize=(7, 6))
    _plot_face_edges_2d(ax, faces, axes)
    if color_mode == "plane":
        colors = np.asarray([np.asarray(_plane_color(int(pid))) / 255.0 for pid in pids])
    else:
        colors = np.asarray([np.asarray(CLASS_COLOR.get(int(cls), CLASS_COLOR[0])) / 255.0
                             for cls in class_ids])
    ax.scatter(pts[:, axes[0]], pts[:, axes[1]], c=colors, s=12,
               edgecolors="none", alpha=0.88)
    _set_equal_2d(ax, _all_vertices(faces), axes)
    ax.set_xlabel(labels[0])
    ax.set_ylabel(labels[1])
    ax.set_title(title)
    ax.grid(True, linewidth=0.2, alpha=0.4)
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)


def write_overlay_oblique(path: Path, faces: List[Dict], pts: np.ndarray,
                          pids: np.ndarray, class_ids: np.ndarray,
                          color_mode: str, title: str) -> None:
    fig = plt.figure(figsize=(7.2, 6.2))
    ax = fig.add_subplot(111, projection="3d")
    polys = [np.asarray(f["vertices"], dtype=np.float64) for f in faces]
    coll = Poly3DCollection(polys, facecolors=(0.75, 0.75, 0.75, 0.16),
                            edgecolors=(0, 0, 0, 0.45), linewidths=0.35)
    ax.add_collection3d(coll)
    if color_mode == "plane":
        colors = np.asarray([np.asarray(_plane_color(int(pid))) / 255.0 for pid in pids])
    else:
        colors = np.asarray([np.asarray(CLASS_COLOR.get(int(cls), CLASS_COLOR[0])) / 255.0
                             for cls in class_ids])
    ax.scatter(pts[:, 0], pts[:, 1], pts[:, 2], c=colors, s=11,
               depthshade=False, alpha=0.9)
    allv = _all_vertices(faces)
    mn, mx = _bbox(allv)
    span = np.maximum(mx - mn, 1e-6)
    pad = span.max() * 0.06
    ax.set_xlim(mn[0] - pad, mx[0] + pad)
    ax.set_ylim(mn[1] - pad, mx[1] + pad)
    ax.set_zlim(mn[2] - pad, mx[2] + pad)
    ax.set_box_aspect(span)
    ax.view_init(elev=24, azim=-54)
    ax.set_xlabel("x")
    ax.set_ylabel("y height")
    ax.set_zlabel("z")
    ax.set_title(title)
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)


def write_overlays(bdir: Path, faces: List[Dict], pts: np.ndarray,
                   pids: np.ndarray, class_ids: np.ndarray) -> None:
    specs = [
        ("top", (0, 2), ("x", "z")),
        ("side", (0, 1), ("x", "y height")),
    ]
    for name, axes, labels in specs:
        for mode in ("plane", "class"):
            out = bdir / f"input_vs_gt_overlay_{name}_by_{mode}.png"
            write_overlay_2d(out, faces, pts, pids, class_ids, axes, labels,
                             mode, f"GT overlay {name} by {mode}")
        shutil.copyfile(bdir / f"input_vs_gt_overlay_{name}_by_plane.png",
                        bdir / f"input_vs_gt_overlay_{name}.png")
    for mode in ("plane", "class"):
        out = bdir / f"input_vs_gt_overlay_oblique_by_{mode}.png"
        write_overlay_oblique(out, faces, pts, pids, class_ids, mode,
                              f"GT overlay oblique by {mode}")
    shutil.copyfile(bdir / "input_vs_gt_overlay_oblique_by_plane.png",
                    bdir / "input_vs_gt_overlay_oblique.png")


def write_sampling_stats(path: Path, faces: List[Dict], trace: Dict) -> List[Dict]:
    rows = []
    by_class: Dict[int, Dict[str, float]] = defaultdict(lambda: {
        "area": 0.0, "points": 0, "target_points": 0, "faces": 0,
    })
    for fi, face in enumerate(faces):
        cls = int(face.get("semantic_class", 0))
        by_class[cls]["area"] += float(face["area"])
        by_class[cls]["points"] += int(trace["face_sample_counts"].get(fi, 0))
        by_class[cls]["target_points"] += int(trace["face_target_counts"].get(fi, 0))
        by_class[cls]["faces"] += 1
    for cls, d in sorted(by_class.items()):
        rows.append({
            "scope": "class",
            "id": CLASS_NAME.get(cls, "unknown"),
            "semantic_class": CLASS_NAME.get(cls, "unknown"),
            "n_faces": int(d["faces"]),
            "area": float(d["area"]),
            "target_points": int(d["target_points"]),
            "actual_points": int(d["points"]),
            "point_density": float(d["points"] / max(d["area"], 1e-12)),
            "actual_to_target_ratio": float(d["points"] / max(d["target_points"], 1)),
        })
    total_area = sum(float(f["area"]) for f in faces)
    rows.append({
        "scope": "all",
        "id": "all",
        "semantic_class": "all",
        "n_faces": len(faces),
        "area": total_area,
        "target_points": sum(trace["face_target_counts"].values()),
        "actual_points": len(trace["pts"]),
        "point_density": len(trace["pts"]) / max(total_area, 1e-12),
        "actual_to_target_ratio": len(trace["pts"]) / max(sum(trace["face_target_counts"].values()), 1),
    })
    write_rows(path, rows, ["scope", "id", "semantic_class", "n_faces", "area",
                            "target_points", "actual_points", "point_density",
                            "actual_to_target_ratio"])
    return rows


def write_face_coverage(path: Path, faces: List[Dict], trace: Dict) -> Tuple[List[Dict], Dict]:
    rows = []
    total_area = 0.0
    unsampled_area = 0.0
    unsampled_by_class: Dict[int, float] = defaultdict(float)
    for fi, face in enumerate(faces):
        area = float(face["area"])
        n_points = int(trace["face_sample_counts"].get(fi, 0))
        cls = int(face.get("semantic_class", 0))
        flags = []
        if n_points == 0:
            flags.append("UNSAMPLED_FACE")
        if n_points < 8:
            flags.append("LOW_POINTS")
        total_area += area
        if n_points == 0:
            unsampled_area += area
            unsampled_by_class[cls] += area
        rows.append({
            "gt_face_id": fi,
            "semantic_class": CLASS_NAME.get(cls, "unknown"),
            "area": area,
            "assigned_plane_id": int(trace["face_to_plane"].get(fi, -1)),
            "n_points": n_points,
            "point_density": float(n_points / max(area, 1e-12)),
            "sampled": int(n_points > 0),
            "warning_flags": ";".join(flags),
        })
    write_rows(path, rows, ["gt_face_id", "semantic_class", "area", "assigned_plane_id",
                            "n_points", "point_density", "sampled", "warning_flags"])
    summary = {
        "n_gt_faces": len(faces),
        "unsampled_faces": sum(1 for r in rows if not r["sampled"]),
        "unsampled_area_ratio": unsampled_area / max(total_area, 1e-12),
        "roof_unsampled_area": unsampled_by_class.get(1, 0.0),
        "wall_unsampled_area": unsampled_by_class.get(2, 0.0),
        "ground_unsampled_area": unsampled_by_class.get(3, 0.0),
    }
    return rows, summary


def compare_existing_input(new_input: Path, bid: int, out_path: Path) -> str:
    candidates = [
        ROOT / f"results/stage3_polyfit_phase2/stageA/building_{bid:02d}/polyfit_input.txt",
        ROOT / f"results/stage3_polyfit_phase2/stageA/building_{bid:03d}/polyfit_input.txt",
        ROOT / f"results/phase2_ablation_citygml/_gt_polyfit_test/building_{bid:03d}/polyfit_input.txt",
        ROOT / f"results/phase2_ablation_citygml/_gt_polyfit_test/building_{bid:02d}/polyfit_input.txt",
    ]
    existing = next((p for p in candidates if p.exists()), None)
    if existing is None:
        out_path.write_text(
            "NO_EXISTING_INPUT\n"
            "No prior Stage A polyfit_input.txt was found under the known result paths.\n"
        )
        return "NO_EXISTING_INPUT"
    new_lines = new_input.read_text().splitlines()
    old_lines = existing.read_text().splitlines()
    if new_lines == old_lines:
        out_path.write_text(f"REPRO_OK\nexisting={existing.relative_to(ROOT)}\n")
        return "REPRO_OK"

    def _summary(lines: List[str]) -> Dict:
        parsed_header = lines[0].split() if lines else ["0", "0"]
        n_points = int(parsed_header[0]) if len(parsed_header) >= 1 else 0
        n_planes = int(parsed_header[1]) if len(parsed_header) >= 2 else 0
        rows = []
        for line in lines[1:]:
            toks = line.split()
            if len(toks) >= 7:
                rows.append([float(x) for x in toks[:6]] + [int(float(toks[6]))])
        arr = np.asarray(rows) if rows else np.empty((0, 7))
        if len(arr):
            return {
                "line_count": len(lines),
                "n_points": n_points,
                "n_planes": n_planes,
                "plane_id_count": len(set(arr[:, 6].astype(int).tolist())),
                "coord_min": arr[:, :3].min(axis=0).tolist(),
                "coord_max": arr[:, :3].max(axis=0).tolist(),
                "normal_min": arr[:, 3:6].min(axis=0).tolist(),
                "normal_max": arr[:, 3:6].max(axis=0).tolist(),
            }
        return {"line_count": len(lines), "n_points": n_points, "n_planes": n_planes}

    text = [
        "REPRO_DIFF",
        f"existing={existing.relative_to(ROOT)}",
        f"new_summary={json.dumps(_summary(new_lines), sort_keys=True)}",
        f"existing_summary={json.dumps(_summary(old_lines), sort_keys=True)}",
    ]
    out_path.write_text("\n".join(text) + "\n")
    return "REPRO_DIFF"


def load_stage_a_metrics() -> Dict[int, Dict]:
    if not STAGE_A_METRICS.exists():
        return {}
    raw = json.loads(STAGE_A_METRICS.read_text())
    return {int(k): v for k, v in raw.get("stageA", {}).items()}


def choose_verdict(bid: int, btype: str, metrics: Dict, validation: Dict,
                   plane_meta: List[Dict], coverage_summary: Dict) -> Tuple[str, str, str]:
    if validation["verdict"] != "PASS":
        return "INPUT_AMBIGUOUS_NEEDS_SIMPLIFIED_GT", "input line validation failed", "inspect input_validation.csv"
    n_planes = len(plane_meta)
    small_ratio = sum(1 for m in plane_meta if m["is_small_area"]) / max(n_planes, 1)
    high_spread = sum(1 for m in plane_meta if m["d_spread_mm"] > 50.0 or m["normal_spread_deg"] > 5.0)
    unsampled_ratio = float(coverage_summary["unsampled_area_ratio"])
    if unsampled_ratio > 0.05:
        return "INPUT_SAMPLING_INSUFFICIENT", "one or more GT surface areas received no samples", "fix sampling coverage before backend tests"
    if n_planes > 20 or small_ratio > 0.30:
        return "INPUT_OVERSEGMENTED", f"plane_count={n_planes}, small_area_plane_ratio={small_ratio:.1%}", "test simplified GT major-plane input"
    if high_spread >= 2:
        return "INPUT_UNDERSEGMENTED", f"{high_spread} planes have high d/normal spread", "inspect plane grouping before backend tests"
    if not metrics.get("skipped") and metrics.get("val3dity_valid") and float(metrics.get("coverage", 0.0)) > 0.25:
        return "INPUT_OK", "reference successful Stage A case", "keep as good-case reference"
    if metrics:
        return "INPUT_OK_BACKEND_FAIL", "input covers GT and validates, but PolyFit output is invalid or low coverage", "treat as PolyFit backend/objective failure"
    return "INPUT_AMBIGUOUS_NEEDS_SIMPLIFIED_GT", "no linked PolyFit metric found", "rerun or recover Stage A metrics"


def simplified_recommendation(btype: str, verdict: str, plane_meta: List[Dict]) -> Tuple[bool, str]:
    small_ratio = sum(1 for m in plane_meta if m["is_small_area"]) / max(len(plane_meta), 1)
    needed = verdict in {"INPUT_OVERSEGMENTED", "INPUT_AMBIGUOUS_NEEDS_SIMPLIFIED_GT"} or len(plane_meta) > 20 or small_ratio > 0.30
    templates = {
        "flat": "ground + major walls + 1 roof plane",
        "gable": "ground + major walls + 2 roof planes",
        "hip": "ground + major walls + roof normal modes",
        "tri-slope": "ground + major walls + 3 roof planes",
        "complex": "ground + dominant wall modes + dominant roof modes only",
    }
    return needed, templates.get(btype, "ground + dominant wall/roof major planes")


def metric_summary(metrics: Dict) -> Dict:
    if not metrics:
        return {
            "polyfit_val3dity": "NA", "polyfit_errors": "NA", "polyfit_coverage": None,
            "output_h": None, "GT_h": None, "vol_ratio": None,
            "hausdorff": None, "chamfer": None,
        }
    if metrics.get("skipped"):
        val = "SKIPPED"
        errors = metrics.get("reason", "")
    else:
        val = "PASS" if metrics.get("val3dity_valid") else "FAIL"
        errors = ";".join(str(e) for e in metrics.get("val3dity_errors", []))
    return {
        "polyfit_val3dity": val,
        "polyfit_errors": errors,
        "polyfit_coverage": metrics.get("coverage"),
        "output_h": metrics.get("output_h"),
        "GT_h": metrics.get("GT_h"),
        "vol_ratio": metrics.get("vol_ratio"),
        "hausdorff": metrics.get("hausdorff"),
        "chamfer": metrics.get("chamfer"),
    }


def write_bid_report(path: Path, bid: int, btype: str, metrics: Dict, validation: Dict,
                     plane_meta: List[Dict], over_pairs: List[Dict], under_rows: List[Dict],
                     coverage_summary: Dict, verdict: str, key_issue: str,
                     recommended_next: str, needs_simplified: bool,
                     simplified_planes: str) -> None:
    ms = metric_summary(metrics)
    n_small = sum(1 for m in plane_meta if m["is_small_area"])
    n_low = sum(1 for m in plane_meta if m["n_sampled_points"] < 10)
    n_off = sum(1 for m in plane_meta if m["is_off_axis"])
    visually_covers = validation["bbox_match"] and coverage_summary["unsampled_faces"] == 0
    major_classes = Counter(m["semantic_class"] for m in plane_meta)
    text = [
        f"# PolyFit Input Audit - B{bid} {btype}",
        "",
        "## Linked Stage A result",
        "",
        f"- val3dity: {ms['polyfit_val3dity']}",
        f"- errors: {ms['polyfit_errors']}",
        f"- output_h / GT_h: {_fmt_float(ms['output_h'])} / {_fmt_float(ms['GT_h'])}",
        f"- coverage: {_fmt_float(ms['polyfit_coverage'], 6)}",
        f"- vol_ratio: {_fmt_float(ms['vol_ratio'], 6)}",
        f"- Hausdorff / Chamfer: {_fmt_float(ms['hausdorff'])} / {_fmt_float(ms['chamfer'])}",
        "",
        "## Input validation",
        "",
        f"- n_points: {validation['n_points']}",
        f"- n_planes: {validation['n_planes']}",
        f"- invalid_normals: {validation['invalid_normals']}",
        f"- out_of_range_plane_id: {validation['out_of_range_plane_id']}",
        f"- duplicate_ratio: {validation['duplicate_ratio']:.4f}",
        f"- bbox_match: {validation['bbox_match']} (max abs delta {validation['bbox_max_abs_delta']:.4f} m)",
        f"- line verdict: {validation['verdict']}",
        "",
        "## Plane and sampling summary",
        "",
        f"- plane_count: {len(plane_meta)}",
        f"- semantic plane counts: {dict(major_classes)}",
        f"- small_area_planes: {n_small}",
        f"- low_point_planes: {n_low}",
        f"- isolated/off-axis planes: {n_off}",
        f"- possible_oversegmented_pairs: {len(over_pairs)}",
        f"- possible_undersegmented_planes: {len(under_rows)}",
        f"- unsampled_faces: {coverage_summary['unsampled_faces']} / {coverage_summary['n_gt_faces']}",
        f"- unsampled_area_ratio: {coverage_summary['unsampled_area_ratio']:.6f}",
        "",
        "## Required questions",
        "",
        f"1. PolyFit input points visually cover the GT: {'yes' if visually_covers else 'no'}; see overlay PNGs.",
        f"2. Major roof/wall/ground planes present: {'yes' if {'roof', 'wall', 'ground'}.issubset(set(major_classes)) else 'no'} ({dict(major_classes)}).",
        f"3. Plane count excessive for roof type: {'yes' if verdict == 'INPUT_OVERSEGMENTED' else 'no'} ({len(plane_meta)} planes).",
        f"4. Many small/isolated planes: {'yes' if n_small / max(len(plane_meta), 1) > 0.30 or n_off > 0 else 'no'} ({n_small} small, {n_off} isolated).",
        f"5. Valid-but-low-coverage interpretation: {'backend/objective likely selected a small valid surface' if verdict == 'INPUT_OK_BACKEND_FAIL' else 'input preparation is a plausible contributor'}.",
        f"6. Non-manifold interpretation: {'plane arrangement complexity is plausible' if len(plane_meta) > 15 else 'not primarily explained by plane count'}.",
        f"7. GT-derived input is PolyFit-ready: {'yes' if verdict in {'INPUT_OK', 'INPUT_OK_BACKEND_FAIL'} else 'not without simplification'}.",
        "",
        "## Verdict",
        "",
        f"- input_verdict: {verdict}",
        f"- key_issue: {key_issue}",
        f"- recommended_next: {recommended_next}",
        "",
        "## Simplified GT major-plane input",
        "",
        f"- needed: {'yes' if needs_simplified else 'no'}",
        f"- planes_to_keep: {simplified_planes}",
        "",
        "## Visual/diagnostic files",
        "",
        "- [input_points_by_plane.ply](input_points_by_plane.ply)",
        "- [input_points_by_class.ply](input_points_by_class.ply)",
        "- [input_points_with_normals.ply](input_points_with_normals.ply)",
        "- [gt_mesh_with_plane_groups.ply](gt_mesh_with_plane_groups.ply)",
        "- [input_vs_gt_overlay_top_by_plane.png](input_vs_gt_overlay_top_by_plane.png)",
        "- [input_vs_gt_overlay_top_by_class.png](input_vs_gt_overlay_top_by_class.png)",
        "- [input_vs_gt_overlay_side_by_plane.png](input_vs_gt_overlay_side_by_plane.png)",
        "- [input_vs_gt_overlay_side_by_class.png](input_vs_gt_overlay_side_by_class.png)",
        "- [input_vs_gt_overlay_oblique_by_plane.png](input_vs_gt_overlay_oblique_by_plane.png)",
        "- [input_vs_gt_overlay_oblique_by_class.png](input_vs_gt_overlay_oblique_by_class.png)",
    ]
    path.write_text("\n".join(text) + "\n")


def audit_one(gt_building: Dict, metrics: Dict[int, Dict]) -> Dict:
    bid = int(gt_building["building_id"])
    btype = gt_building["type"]
    faces = gt_building["faces"]
    bdir = OUT_ROOT / f"B{bid}"
    _mkdir(bdir)

    write_building_obj(bdir / "gt_mesh.obj", faces)
    trace = build_stage_a_input_with_trace(faces)
    if trace is None:
        raise RuntimeError(f"B{bid}: no Stage A input points")
    write_polyfit_input(bdir / "polyfit_input.txt", trace["pts"], trace["normals"],
                        trace["pids"], trace["n_planes"])
    repro_status = compare_existing_input(bdir / "polyfit_input.txt", bid,
                                          bdir / "input_repro_diff.txt")

    validation = validate_input(bdir / "polyfit_input.txt", _bbox(_all_vertices(faces)))
    write_input_validation_csv(bdir / "input_validation.csv", bid, validation)

    plane_meta, warnings_by_plane = compute_plane_metadata(faces, trace)
    over_pairs = find_oversegmented_pairs(plane_meta)
    for pair in over_pairs:
        warnings_by_plane[int(pair["plane_id_a"])].append("POSSIBLE_OVERSEGMENT")
        warnings_by_plane[int(pair["plane_id_b"])].append("POSSIBLE_OVERSEGMENT")
    under_rows = find_undersegmented_planes(plane_meta)
    write_input_planes_csv(bdir / "input_planes.csv", plane_meta, warnings_by_plane)
    write_rows(bdir / "possible_oversegmented_pairs.csv", over_pairs,
               ["plane_id_a", "plane_id_b", "semantic_class", "normal_abs_cos",
                "d_delta_m", "bbox_gap_m", "area_a", "area_b"])
    write_rows(bdir / "possible_undersegmented_planes.csv", under_rows,
               ["plane_id", "semantic_class", "n_gt_faces", "component_count",
                "d_spread_mm", "normal_spread_deg", "warning_flags",
                "members_gt_face_ids"])

    write_sampling_stats(bdir / "input_sampling_stats.csv", faces, trace)
    _coverage_rows, coverage_summary = write_face_coverage(bdir / "gt_face_sampling_coverage.csv",
                                                           faces, trace)

    plane_to_class = {int(m["plane_id"]): int(m["semantic_class_id"]) for m in plane_meta}
    class_ids = np.asarray([plane_to_class.get(int(pid), 0) for pid in trace["pids"]],
                           dtype=np.int64)
    write_points_ply(bdir / "input_points_by_plane.ply", trace["pts"], trace["normals"],
                     trace["pids"], class_ids, "plane")
    write_points_ply(bdir / "input_points_by_class.ply", trace["pts"], trace["normals"],
                     trace["pids"], class_ids, "class")
    write_points_ply(bdir / "input_points_with_normals.ply", trace["pts"], trace["normals"],
                     trace["pids"], class_ids, "plane")
    write_normals_segments_ply(bdir / "input_normals_segments.ply", trace["pts"],
                               trace["normals"], trace["pids"])
    write_mesh_ply(bdir / "gt_mesh_with_plane_groups.ply", faces, trace["face_to_plane"],
                   plane_to_class)
    write_plane_legend(bdir / "plane_id_legend.png", bdir / "plane_id_legend.csv",
                       plane_meta)
    write_overlays(bdir, faces, trace["pts"], trace["pids"], class_ids)

    m = metrics.get(bid, {})
    verdict, key_issue, recommended_next = choose_verdict(
        bid, btype, m, validation, plane_meta, coverage_summary)
    needs_simplified, simplified_planes = simplified_recommendation(btype, verdict, plane_meta)
    write_bid_report(bdir / "audit_report.md", bid, btype, m, validation,
                     plane_meta, over_pairs, under_rows, coverage_summary,
                     verdict, key_issue, recommended_next, needs_simplified,
                     simplified_planes)

    ms = metric_summary(m)
    small_ratio = sum(1 for x in plane_meta if x["is_small_area"]) / max(len(plane_meta), 1)
    return {
        "bid": bid,
        "type": btype,
        "n_planes": len(plane_meta),
        "n_points": int(len(trace["pts"])),
        "n_gt_faces": len(faces),
        "repro_status": repro_status,
        "validation_verdict": validation["verdict"],
        "invalid_normals": validation["invalid_normals"],
        "out_of_range_plane_id": validation["out_of_range_plane_id"],
        "duplicate_ratio": validation["duplicate_ratio"],
        "bbox_match": validation["bbox_match"],
        "small_area_plane_ratio": small_ratio,
        "low_point_planes": sum(1 for x in plane_meta if x["n_sampled_points"] < 10),
        "possible_oversegmented_pairs": len(over_pairs),
        "possible_undersegmented_planes": len(under_rows),
        "unsampled_faces": coverage_summary["unsampled_faces"],
        "unsampled_area_ratio": coverage_summary["unsampled_area_ratio"],
        "roof_unsampled_area": coverage_summary["roof_unsampled_area"],
        "wall_unsampled_area": coverage_summary["wall_unsampled_area"],
        "ground_unsampled_area": coverage_summary["ground_unsampled_area"],
        "polyfit_val3dity": ms["polyfit_val3dity"],
        "polyfit_errors": ms["polyfit_errors"],
        "polyfit_coverage": ms["polyfit_coverage"],
        "output_h": ms["output_h"],
        "GT_h": ms["GT_h"],
        "vol_ratio": ms["vol_ratio"],
        "hausdorff": ms["hausdorff"],
        "chamfer": ms["chamfer"],
        "input_verdict": verdict,
        "key_issue": key_issue,
        "recommended_next": recommended_next,
        "needs_simplified_gt_input": needs_simplified,
        "simplified_planes_to_keep": simplified_planes,
    }


def write_global_reports(rows: List[Dict]) -> None:
    fields = [
        "bid", "type", "n_planes", "n_points", "n_gt_faces", "repro_status",
        "validation_verdict", "invalid_normals", "out_of_range_plane_id",
        "duplicate_ratio", "bbox_match", "small_area_plane_ratio",
        "low_point_planes", "possible_oversegmented_pairs",
        "possible_undersegmented_planes", "unsampled_faces",
        "unsampled_area_ratio", "roof_unsampled_area", "wall_unsampled_area",
        "ground_unsampled_area", "polyfit_val3dity", "polyfit_errors",
        "polyfit_coverage", "output_h", "GT_h", "vol_ratio", "hausdorff",
        "chamfer", "input_verdict", "key_issue", "recommended_next",
        "needs_simplified_gt_input", "simplified_planes_to_keep",
    ]
    write_rows(OUT_ROOT / "audit_summary.csv", rows, fields)
    validation_fields = [
        "bid", "n_points", "n_planes", "invalid_normals",
        "out_of_range_plane_id", "duplicate_ratio", "bbox_match",
        "validation_verdict",
    ]
    write_rows(OUT_ROOT / "input_validation_summary.csv", rows, validation_fields)
    write_rows(OUT_ROOT / "input_validation.csv", rows, validation_fields)
    write_rows(OUT_ROOT / "gt_face_sampling_coverage_summary.csv", rows, [
        "bid", "n_gt_faces", "unsampled_faces", "unsampled_area_ratio",
        "roof_unsampled_area", "wall_unsampled_area", "ground_unsampled_area",
    ])

    core = [r for r in rows if int(r["bid"]) in CORE_BIDS]
    n_backend = sum(1 for r in core if r["input_verdict"] == "INPUT_OK_BACKEND_FAIL")
    n_input_prep = sum(1 for r in core if r["input_verdict"] in {
        "INPUT_OVERSEGMENTED", "INPUT_SAMPLING_INSUFFICIENT"})
    b1 = next((r for r in rows if int(r["bid"]) == 1), None)
    b2 = next((r for r in rows if int(r["bid"]) == 2), None)
    if n_backend >= 4:
        go_ng = "PolyFit backend/objective problem dominates; hold final Stage 3 PolyFit adoption."
    elif n_input_prep >= 3:
        go_ng = "GT-derived input preparation is the main cause; move to simplified GT major-plane input."
    elif b1 and b2 and b1["input_verdict"] == "INPUT_OK" and b2["input_verdict"] in {
            "INPUT_OVERSEGMENTED", "INPUT_SAMPLING_INSUFFICIENT"}:
        go_ng = "Flat cases differ by input preparation; simplify/standardize GT input."
    else:
        go_ng = ("Mixed result: valid-low-coverage cases point to PolyFit objective/backend, "
                 "while complex/non-manifold cases need simplified major-plane input.")

    lines = [
        "# GT-derived PolyFit Input Audit",
        "",
        f"- source GT: `{SCENE.relative_to(ROOT)}`",
        f"- linked metrics: `{STAGE_A_METRICS.relative_to(ROOT)}`",
        f"- target bids: {', '.join('B' + str(r['bid']) for r in rows)}",
        f"- core GO/NG bids: {', '.join('B' + str(x) for x in CORE_BIDS)}",
        "",
        "## Existing PolyFit result summary",
        "",
        "| bid | type | val3dity | errors | coverage | vol_ratio | Hausdorff | Chamfer |",
        "|---:|---|---|---|---:|---:|---:|---:|",
    ]
    for r in rows:
        lines.append(
            f"| B{r['bid']} | {r['type']} | {r['polyfit_val3dity']} | "
            f"{r['polyfit_errors']} | {_fmt_float(r['polyfit_coverage'], 6)} | "
            f"{_fmt_float(r['vol_ratio'], 6)} | {_fmt_float(r['hausdorff'])} | "
            f"{_fmt_float(r['chamfer'])} |"
        )
    lines.extend([
        "",
        "## Input validation summary",
        "",
        "| bid | n_points | n_planes | invalid_normals | out_of_range_plane_id | duplicate_ratio | bbox_match | verdict |",
        "|---:|---:|---:|---:|---:|---:|---|---|",
    ])
    for r in rows:
        lines.append(
            f"| B{r['bid']} | {r['n_points']} | {r['n_planes']} | "
            f"{r['invalid_normals']} | {r['out_of_range_plane_id']} | "
            f"{r['duplicate_ratio']:.4f} | {r['bbox_match']} | "
            f"{r['validation_verdict']} |"
        )
    lines.extend([
        "",
        "## Plane count / sampling density summary",
        "",
        "| bid | type | n_gt_faces | n_planes | n_points | small_area_plane_ratio | low_point_planes | unsampled_faces | unsampled_area_ratio |",
        "|---:|---|---:|---:|---:|---:|---:|---:|---:|",
    ])
    for r in rows:
        lines.append(
            f"| B{r['bid']} | {r['type']} | {r['n_gt_faces']} | {r['n_planes']} | "
            f"{r['n_points']} | {r['small_area_plane_ratio']:.3f} | "
            f"{r['low_point_planes']} | {r['unsampled_faces']} | "
            f"{r['unsampled_area_ratio']:.6f} |"
        )
    lines.extend([
        "",
        "## Over/under segmentation summary",
        "",
        "| bid | possible_oversegmented_pairs | possible_undersegmented_planes | key issue |",
        "|---:|---:|---:|---|",
    ])
    for r in rows:
        lines.append(
            f"| B{r['bid']} | {r['possible_oversegmented_pairs']} | "
            f"{r['possible_undersegmented_planes']} | {r['key_issue']} |"
        )
    lines.extend([
        "",
        "## Visualization links",
        "",
        "| bid | plane PLY | class PLY | GT plane mesh | top | side | oblique | report |",
        "|---:|---|---|---|---|---|---|---|",
    ])
    for r in rows:
        b = f"B{r['bid']}"
        lines.append(
            f"| {b} | [{b}/input_points_by_plane.ply]({b}/input_points_by_plane.ply) | "
            f"[{b}/input_points_by_class.ply]({b}/input_points_by_class.ply) | "
            f"[{b}/gt_mesh_with_plane_groups.ply]({b}/gt_mesh_with_plane_groups.ply) | "
            f"[top]({b}/input_vs_gt_overlay_top_by_plane.png) | "
            f"[side]({b}/input_vs_gt_overlay_side_by_plane.png) | "
            f"[oblique]({b}/input_vs_gt_overlay_oblique_by_plane.png) | "
            f"[audit]({b}/audit_report.md) |"
        )
    lines.extend([
        "",
        "## Final verdict table",
        "",
        "| bid | type | n_planes | n_points | polyfit_val3dity | polyfit_coverage | input_verdict | key_issue | recommended_next |",
        "|---:|---|---:|---:|---|---:|---|---|---|",
    ])
    for r in rows:
        lines.append(
            f"| B{r['bid']} | {r['type']} | {r['n_planes']} | {r['n_points']} | "
            f"{r['polyfit_val3dity']} | {_fmt_float(r['polyfit_coverage'], 6)} | "
            f"{r['input_verdict']} | {r['key_issue']} | {r['recommended_next']} |"
        )
    lines.extend([
        "",
        "## Simplified GT major-plane input recommendation",
        "",
        "| bid | needed | planes to keep |",
        "|---:|---|---|",
    ])
    for r in rows:
        lines.append(
            f"| B{r['bid']} | {'yes' if r['needs_simplified_gt_input'] else 'no'} | "
            f"{r['simplified_planes_to_keep']} |"
        )
    lines.extend([
        "",
        "## GO/NG interpretation",
        "",
        f"- INPUT_OK_BACKEND_FAIL among 5 core bids: {n_backend}/5",
        f"- INPUT_OVERSEGMENTED or INPUT_SAMPLING_INSUFFICIENT among 5 core bids: {n_input_prep}/5",
        f"- Decision: {go_ng}",
        "",
        "## Self-verification",
        "",
    ])
    checks = [
        ("all bid input_points_by_plane.ply", all((OUT_ROOT / f"B{r['bid']}" / "input_points_by_plane.ply").exists() for r in rows)),
        ("all bid gt_mesh_with_plane_groups.ply", all((OUT_ROOT / f"B{r['bid']}" / "gt_mesh_with_plane_groups.ply").exists() for r in rows)),
        ("all bid top/side/oblique overlay PNG", all(
            (OUT_ROOT / f"B{r['bid']}" / "input_vs_gt_overlay_top_by_plane.png").exists() and
            (OUT_ROOT / f"B{r['bid']}" / "input_vs_gt_overlay_side_by_plane.png").exists() and
            (OUT_ROOT / f"B{r['bid']}" / "input_vs_gt_overlay_oblique_by_plane.png").exists()
            for r in rows)),
        ("all bid input_planes.csv", all((OUT_ROOT / f"B{r['bid']}" / "input_planes.csv").exists() for r in rows)),
        ("all bid audit_report.md", all((OUT_ROOT / f"B{r['bid']}" / "audit_report.md").exists() for r in rows)),
        ("overall AUDIT_REPORT.md", True),
        ("each bid has verdict", all(bool(r["input_verdict"]) for r in rows)),
        ("core metrics linked", all(r["polyfit_val3dity"] != "NA" for r in rows if int(r["bid"]) in CORE_BIDS)),
    ]
    for name, ok in checks:
        lines.append(f"- {'PASS' if ok else 'FAIL'}: {name}")
    (OUT_ROOT / "AUDIT_REPORT.md").write_text("\n".join(lines) + "\n")


def main() -> None:
    _mkdir(OUT_ROOT)
    gt = parse_scene_obj(SCENE, frame="obj")
    metrics = load_stage_a_metrics()
    rows = []
    for bid in TARGET_BIDS:
        b = next(x for x in gt["buildings"] if int(x["building_id"]) == bid)
        print(f"[audit] B{bid} {b['type']}")
        rows.append(audit_one(b, metrics))
    write_global_reports(rows)
    print(f"[audit] saved {OUT_ROOT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
