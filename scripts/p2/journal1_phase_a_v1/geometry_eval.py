"""P2-JOURNAL1-PHASE-A-v1 — geometry-level dual-GT point cloud evaluator (A1/A3).

Scores each experiment arm's frozen per-building roofer-input crop (viewer-local
binary PLY with class 2/6) against the two references defined by the journal1
design (docs/experiments/p2/journal1_design_v1/JOURNAL1_EXPERIMENT_DESIGN_ko_v1.md §4.1):

  gt=lod2 — original CityGML LoD2 RoofSurface faces (P0 raw tiles, EPSG:25832
            shifted by the viewer origin): point-to-face distance, face grid
            samples for completeness/coverage, exact face normals.
  gt=e1   — current UAS LiDAR crop (E1 arm bytes): point-to-point NN both ways,
            PCA normals on both sides.

Per-building rows go to JSONL + CSV; the aggregate summary reports per-arm
medians and paired contrasts vs the product baseline arm. Buildings are scored
with BOTH GT suites regardless of change labels; stratified aggregation happens
downstream once labels land (§4.4). Non-confirmatory development readout;
`scientific_verdict` stays null. Run inside the project container.
"""

import argparse
import csv
import json
import math
import sys
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import shapely
from scipy.spatial import cKDTree
from shapely.geometry import Polygon

GML = "{http://www.opengis.net/gml}"
BLDG = "{http://www.opengis.net/citygml/building/1.0}"
GROUND_CLASS = 2
BUILDING_CLASS = 6

PLY_DTYPES = {
    "float": "<f4", "float32": "<f4", "double": "<f8", "float64": "<f8",
    "uchar": "u1", "uint8": "u1", "char": "i1", "int8": "i1",
    "ushort": "<u2", "uint16": "<u2", "short": "<i2", "int16": "<i2",
    "uint": "<u4", "uint32": "<u4", "int": "<i4", "int32": "<i4",
}


def read_ply(path):
    """Minimal binary_little_endian PLY reader → (xyz float64 Nx3, class or None)."""
    with open(path, "rb") as f:
        header = []
        while True:
            line = f.readline().decode("ascii", "replace").strip()
            header.append(line)
            if line == "end_header":
                break
        n = 0
        fields = []
        in_vertex = False
        fmt_ok = False
        for line in header:
            tok = line.split()
            if not tok:
                continue
            if tok[0] == "format":
                fmt_ok = tok[1] == "binary_little_endian"
            elif tok[0] == "element":
                in_vertex = tok[1] == "vertex"
                if in_vertex:
                    n = int(tok[2])
            elif tok[0] == "property" and in_vertex:
                if tok[1] == "list":
                    raise ValueError(f"list property unsupported: {path}")
                fields.append((tok[2], PLY_DTYPES[tok[1]]))
        if not fmt_ok:
            raise ValueError(f"not binary_little_endian: {path}")
        if n == 0:
            return np.zeros((0, 3)), None
        data = np.fromfile(f, dtype=np.dtype(fields), count=n)
    xyz = np.stack([data["x"], data["y"], data["z"]], axis=1).astype(np.float64)
    cls = data["classification"].astype(np.int32) if "classification" in data.dtype.names else None
    return xyz, cls


def roof_points(xyz, cls):
    """Building-class points; falls back to non-ground when class 6 is absent."""
    if cls is None:
        return xyz, "NO_CLASS_FIELD"
    m6 = cls == BUILDING_CLASS
    if m6.any():
        return xyz[m6], None
    m = cls != GROUND_CLASS
    return xyz[m], ("NO_CLASS6_FALLBACK_NONGROUND" if m.any() else "ONLY_GROUND")


def load_lod2_faces(tiles, targets, origin, z_shift=0.0):
    """{stable_id: [(ring Nx3 viewer-local, upward unit normal)]} from CityGML.

    z_shift bridges the LoD2 orthometric datum to the viewer frame's ellipsoidal
    lineage (sealed v22 constant `lod2_reference_z_shift_to_viewer_m`).
    """
    origin = np.asarray(origin, dtype=np.float64) - np.array([0.0, 0.0, z_shift])
    out = {}
    for tile in tiles:
        for _, el in ET.iterparse(str(tile), events=("end",)):
            if el.tag != BLDG + "Building":
                continue
            bid = el.get(GML + "id")
            if bid in targets:
                faces = []
                for rs in el.iter(BLDG + "RoofSurface"):
                    for pl in rs.iter(GML + "posList"):
                        v = np.array([float(x) for x in pl.text.split()]).reshape(-1, 3) - origin
                        if len(v) < 4:
                            continue
                        n = np.zeros(3)
                        for i in range(len(v) - 1):
                            n += np.cross(v[i], v[i + 1])
                        ln = np.linalg.norm(n)
                        if ln < 1e-9:
                            continue
                        n /= ln
                        if n[2] < 0:
                            n = -n
                        faces.append((v, n))
                if faces:
                    out[bid] = faces
            el.clear()
    return out


class FaceSet:
    """Per-building LoD2 roof faces with in-plane frames, polygons and samples."""

    def __init__(self, faces, sample_step):
        self.items = []
        samples = []
        sample_normals = []
        for verts, n in faces:
            o = verts[0]
            e = verts[1] - verts[0]
            u = e - np.dot(e, n) * n
            lu = np.linalg.norm(u)
            if lu < 1e-9:
                continue
            u /= lu
            w = np.cross(n, u)
            uv = np.stack([(verts - o) @ u, (verts - o) @ w], axis=1)
            poly = Polygon(uv)
            if not poly.is_valid:
                poly = poly.buffer(0)
            if poly.is_empty or poly.area < 1e-6:
                continue
            self.items.append((o, u, w, n, poly))
            lo0, lo1, hi0, hi1 = poly.bounds
            gx = np.arange(lo0 + sample_step / 2, hi0, sample_step)
            gy = np.arange(lo1 + sample_step / 2, hi1, sample_step)
            if len(gx) == 0 or len(gy) == 0:
                gx = np.array([(lo0 + hi0) / 2])
                gy = np.array([(lo1 + hi1) / 2])
            gu, gv = np.meshgrid(gx, gy)
            gu, gv = gu.ravel(), gv.ravel()
            keep = shapely.contains_xy(poly, gu, gv)
            if not keep.any():
                continue
            pts = o[None, :] + gu[keep, None] * u[None, :] + gv[keep, None] * w[None, :]
            samples.append(pts)
            sample_normals.append(np.tile(n, (int(keep.sum()), 1)))
        self.samples = np.concatenate(samples, axis=0) if samples else np.zeros((0, 3))
        self.sample_normals = (np.concatenate(sample_normals, axis=0)
                               if sample_normals else np.zeros((0, 3)))

    def distances(self, pts):
        """(min distance to any face, normal of the nearest face) per point."""
        m = len(pts)
        best = np.full(m, np.inf)
        best_n = np.zeros((m, 3))
        for o, u, w, n, poly in self.items:
            rel = pts - o[None, :]
            perp = np.abs(rel @ n)
            pu, pv = rel @ u, rel @ w
            d2d = np.zeros(m)
            inside = shapely.contains_xy(poly, pu, pv)
            out_idx = np.nonzero(~inside)[0]
            if len(out_idx):
                lo0, lo1, hi0, hi1 = poly.bounds
                bx = np.clip(pu[out_idx], lo0, hi0) - pu[out_idx]
                by = np.clip(pv[out_idx], lo1, hi1) - pv[out_idx]
                lb = np.hypot(np.hypot(bx, by), perp[out_idx])
                need = out_idx[lb < best[out_idx]]
                if len(need):
                    d2d_need = shapely.distance(
                        poly, shapely.points(np.stack([pu[need], pv[need]], axis=1)))
                    d2d_full = np.full(m, np.inf)
                    d2d_full[need] = d2d_need
                    d2d_full[inside] = 0.0
                    d2d = d2d_full
                else:
                    d2d = np.where(inside, 0.0, np.inf)
            d = np.hypot(d2d, perp)
            upd = d < best
            best[upd] = d[upd]
            best_n[upd] = n
        return best, best_n


def pca_normals(pts, k, chunk=50000):
    """Unit PCA normals via k-NN covariance; NaN rows when neighborhood degenerates."""
    n = len(pts)
    if n < k:
        return np.full((n, 3), np.nan)
    tree = cKDTree(pts)
    out = np.empty((n, 3))
    for s in range(0, n, chunk):
        q = pts[s:s + chunk]
        _, idx = tree.query(q, k=k, workers=-1)
        nb = pts[idx]
        nb = nb - nb.mean(axis=1, keepdims=True)
        cov = np.einsum("nki,nkj->nij", nb, nb) / k
        _, vec = np.linalg.eigh(cov)
        out[s:s + chunk] = vec[:, :, 0]
    norm = np.linalg.norm(out, axis=1, keepdims=True)
    with np.errstate(invalid="ignore", divide="ignore"):
        out = out / norm
    return out


def angles_deg(a, b):
    dot = np.abs(np.sum(a * b, axis=1))
    dot = np.clip(dot, 0.0, 1.0)
    return np.degrees(np.arccos(dot))


def cell_index(xy, cell):
    return np.floor(xy / cell).astype(np.int64)


def z_spread(pts, cell, min_pts=5):
    """Median over occupied XY cells of the per-cell z p90−p10 (double-surface probe)."""
    if len(pts) < min_pts:
        return None
    ij = cell_index(pts[:, :2], cell)
    order = np.lexsort((ij[:, 1], ij[:, 0]))
    ij_s, z_s = ij[order], pts[order, 2]
    boundaries = np.nonzero(np.any(np.diff(ij_s, axis=0) != 0, axis=1))[0] + 1
    spreads = [np.percentile(seg, 90) - np.percentile(seg, 10)
               for seg in np.split(z_s, boundaries) if len(seg) >= min_pts]
    return float(np.median(spreads)) if spreads else None


def coverage(a_pts, r_pts, cell, z_tol):
    """Fraction of reference-occupied XY cells that the arm fills at compatible height."""
    if len(r_pts) == 0:
        return None
    r_ij = cell_index(r_pts[:, :2], cell)
    a_map = {}
    if len(a_pts):
        a_ij = cell_index(a_pts[:, :2], cell)
        for (i, j), z in zip(map(tuple, a_ij), a_pts[:, 2]):
            a_map.setdefault((i, j), []).append(z)
    r_map = {}
    for (i, j), z in zip(map(tuple, r_ij), r_pts[:, 2]):
        r_map.setdefault((i, j), []).append(z)
    hit = 0
    for key, zs in r_map.items():
        az = a_map.get(key)
        if az is not None and abs(np.median(az) - np.median(zs)) <= z_tol:
            hit += 1
    return hit / len(r_map)


def distance_metrics(d_a, d_r, taus, tau_out):
    row = {}
    if len(d_a):
        row["acc_median"] = float(np.median(d_a))
        row["rmsd"] = float(np.sqrt(np.mean(d_a ** 2)))
        p95 = np.percentile(d_a, 95)
        trimmed = d_a[d_a <= p95]
        row["rmsd_t95"] = float(np.sqrt(np.mean(trimmed ** 2))) if len(trimmed) else None
        row["outlier_rate"] = float(np.mean(d_a > tau_out))
    for tau in taus:
        p = float(np.mean(d_a <= tau)) if len(d_a) else None
        c = float(np.mean(d_r <= tau)) if len(d_r) else None
        row[f"precision@{tau}"] = p
        row[f"completeness@{tau}"] = c
        row[f"f1@{tau}"] = (2 * p * c / (p + c)) if p and c and (p + c) > 0 else 0.0 \
            if (p is not None and c is not None) else None
    return row


def subsample(pts, cap):
    if cap and len(pts) > cap:
        stride = int(math.ceil(len(pts) / cap))
        return pts[::stride], stride
    return pts, 1


def eval_building_arm(a_xyz, a_cls, faceset, e1_roof, e1_normals, cfg, is_reference_arm):
    rows = []
    roof, flag = roof_points(a_xyz, a_cls)
    base = {"n_raw": int(len(a_xyz)), "n_roof": int(len(roof)), "flag": flag}
    if len(roof) < cfg["min_points"]:
        base["flag"] = (flag + "+" if flag else "") + "EMPTY_ARM"
        for gt in (["lod2"] if is_reference_arm else ["lod2", "e1"]):
            rows.append({**base, "gt": gt})
        return rows
    roof_s, stride = subsample(roof, cfg["max_points_per_arm"])
    a_norm = pca_normals(roof_s, cfg["knn"])

    if faceset is not None and len(faceset.items):
        d_a, near_n = faceset.distances(roof_s)
        tree_a = cKDTree(roof_s)
        d_r, _ = tree_a.query(faceset.samples, k=1, workers=-1)
        m = d_a <= cfg["normal_match_tau"]
        valid = m & ~np.isnan(a_norm).any(axis=1)
        ang = angles_deg(a_norm[valid], near_n[valid]) if valid.any() else np.array([])
        row = {**base, "gt": "lod2", "stride": stride,
               "n_ref": int(len(faceset.samples)),
               "normal_med_deg": float(np.median(ang)) if len(ang) else None,
               "coverage": coverage(roof_s, faceset.samples, cfg["cell"], cfg["coverage_z_tol"]),
               "z_spread": z_spread(roof_s, cfg["cell"])}
        row.update(distance_metrics(d_a, d_r, cfg["taus"], cfg["tau_outlier"]))
        rows.append(row)
    else:
        rows.append({**base, "gt": "lod2", "flag": (flag + "+" if flag else "") + "NO_LOD2_REF"})

    if not is_reference_arm:
        if e1_roof is not None and len(e1_roof) >= cfg["min_points"]:
            tree_r = cKDTree(e1_roof)
            d_a, idx_r = tree_r.query(roof_s, k=1, workers=-1)
            tree_a = cKDTree(roof_s)
            d_r, _ = tree_a.query(e1_roof, k=1, workers=-1)
            m = d_a <= cfg["normal_match_tau"]
            pair_n = e1_normals[idx_r]
            valid = m & ~np.isnan(a_norm).any(axis=1) & ~np.isnan(pair_n).any(axis=1)
            ang = angles_deg(a_norm[valid], pair_n[valid]) if valid.any() else np.array([])
            row = {**base, "gt": "e1", "stride": stride, "n_ref": int(len(e1_roof)),
                   "normal_med_deg": float(np.median(ang)) if len(ang) else None,
                   "coverage": coverage(roof_s, e1_roof, cfg["cell"], cfg["coverage_z_tol"]),
                   "z_spread": z_spread(roof_s, cfg["cell"])}
            row.update(distance_metrics(d_a, d_r, cfg["taus"], cfg["tau_outlier"]))
            rows.append(row)
        else:
            rows.append({**base, "gt": "e1", "flag": (flag + "+" if flag else "") + "E1_REF_EMPTY"})
    return rows


def find_crop(arm_dir, sid):
    hits = sorted(Path(arm_dir).glob(f"*_{sid}.points.ply"))
    return hits[0] if hits else None


def aggregate(rows, cfg):
    """Per arm×gt medians plus per-building paired deltas vs the baseline arm."""
    key_metrics = ["f1@0.25", "f1@0.5", "completeness@0.5", "precision@0.5",
                   "acc_median", "rmsd_t95", "outlier_rate", "coverage",
                   "normal_med_deg", "z_spread"]
    summary = {"per_arm": {}, "paired_vs_baseline": {}, "baseline_arm": cfg["baseline_arm"]}
    by = {}
    for r in rows:
        if r.get("f1@0.5") is None and r.get("acc_median") is None:
            continue
        by.setdefault((r["arm"], r["gt"]), []).append(r)
    for (arm, gt), rs in sorted(by.items()):
        entry = {"n_buildings": len(rs)}
        for m in key_metrics:
            vals = [r[m] for r in rs if r.get(m) is not None]
            entry[f"{m}_median"] = float(np.median(vals)) if vals else None
        summary["per_arm"][f"{arm}|{gt}"] = entry
    base_rows = {(r["stable_id"], r["gt"]): r for r in rows if r["arm"] == cfg["baseline_arm"]}
    for (arm, gt), rs in sorted(by.items()):
        if arm == cfg["baseline_arm"]:
            continue
        deltas = {}
        for m in key_metrics:
            pair = [(r[m], base_rows[(r["stable_id"], gt)][m]) for r in rs
                    if (r["stable_id"], gt) in base_rows
                    and r.get(m) is not None
                    and base_rows[(r["stable_id"], gt)].get(m) is not None]
            if len(pair) >= 5:
                d = np.array([a - b for a, b in pair])
                entry = {"n_pairs": len(pair), "delta_median": float(np.median(d)),
                         "wins": int(np.sum(d > 0)), "losses": int(np.sum(d < 0))}
                try:
                    from scipy.stats import wilcoxon
                    nz = d[d != 0]
                    if len(nz) >= 10:
                        entry["wilcoxon_p"] = float(wilcoxon(nz).pvalue)
                except Exception:
                    pass
                deltas[m] = entry
        summary["paired_vs_baseline"][f"{arm}|{gt}"] = deltas
    return summary


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", required=True)
    ap.add_argument("--limit", type=int, default=0, help="only the first N buildings")
    ap.add_argument("--buildings", default="", help="comma-separated stable_id subset")
    ap.add_argument("--arms", default="", help="comma-separated arm subset")
    args = ap.parse_args()

    cfg = json.load(open(args.config))
    assert cfg.get("scientific_verdict") is None
    out_dir = Path(cfg["out_dir"])
    out_dir.mkdir(parents=True, exist_ok=True)

    fp = json.load(open(cfg["footprints_geojson"]))
    sids = sorted(f["properties"]["stable_id"] for f in fp["features"])
    if args.buildings:
        want = set(args.buildings.split(","))
        sids = [s for s in sids if s in want]
    if args.limit:
        sids = sids[:args.limit]

    arms = {k: v for k, v in cfg["arms"].items()
            if not args.arms or k in args.arms.split(",")}

    print(f"[journal1-A] buildings={len(sids)} arms={list(arms)}", flush=True)
    t0 = time.time()
    lod2 = load_lod2_faces(cfg["gml_tiles"], set(sids), cfg["origin"],
                           cfg.get("lod2_z_shift_to_viewer_m", 0.0))
    print(f"[journal1-A] lod2 faces loaded for {len(lod2)}/{len(sids)} "
          f"buildings in {time.time()-t0:.1f}s", flush=True)

    started = datetime.now(timezone.utc).isoformat()
    rows = []
    jsonl = open(out_dir / "rows.jsonl", "w")
    for bi, sid in enumerate(sids):
        tb = time.time()
        faceset = FaceSet(lod2[sid], cfg["lod2_sample_step"]) if sid in lod2 else None
        e1_path = find_crop(cfg["e1_reference_dir"], sid)
        e1_roof, e1_norm = None, None
        if e1_path is not None:
            e1_xyz, e1_cls = read_ply(e1_path)
            e1_roof, _ = roof_points(e1_xyz, e1_cls)
            e1_roof, _ = subsample(e1_roof, cfg["max_points_per_arm"])
            if len(e1_roof) >= cfg["min_points"]:
                e1_norm = pca_normals(e1_roof, cfg["knn"])
            else:
                e1_roof = None
        for arm, spec in arms.items():
            path = find_crop(spec["dir"], sid)
            if path is None:
                rows.append({"stable_id": sid, "arm": arm, "gt": "lod2",
                             "flag": "MISSING_FILE"})
                continue
            a_xyz, a_cls = read_ply(path)
            for row in eval_building_arm(a_xyz, a_cls, faceset, e1_roof, e1_norm,
                                         cfg, spec.get("reference_arm", False)):
                row.update({"stable_id": sid, "arm": arm})
                rows.append(row)
                jsonl.write(json.dumps(row) + "\n")
        jsonl.flush()
        print(f"[journal1-A] {bi+1}/{len(sids)} {sid} {time.time()-tb:.1f}s", flush=True)
    jsonl.close()

    keys = sorted({k for r in rows for k in r})
    with open(out_dir / "rows.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=keys)
        w.writeheader()
        w.writerows(rows)

    summary = aggregate(rows, cfg)
    json.dump(summary, open(out_dir / "summary.json", "w"), indent=1)
    receipt = {"task_id": cfg["task_id"], "schema": "jointbuildgs.p2.journal1_phase_a_v1.geometry_eval.v1",
               "config": cfg, "started_utc": started,
               "ended_utc": datetime.now(timezone.utc).isoformat(),
               "n_buildings": len(sids), "n_rows": len(rows),
               "versions": {"python": sys.version.split()[0], "numpy": np.__version__,
                            "shapely": shapely.__version__},
               "scientific_verdict": None}
    json.dump(receipt, open(out_dir / "receipt.json", "w"), indent=1)
    print(json.dumps(summary["per_arm"], indent=1))
    print(f"[journal1-A] done → {out_dir}", flush=True)


if __name__ == "__main__":
    main()
