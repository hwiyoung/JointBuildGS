"""Test CGAL PolyFit (Stage 3) on GT scene.obj primitives.

Each GT face is treated as a plane region. Points = sampled face centroids
(densified by area). Plane_id = unique per plane group (coplanar faces merged).

For each building:
  1. Collect faces → planes (cluster by normal + plane d)
  2. Sample N points per face (area-proportional) with plane_id
  3. Write .txt input for polyfit_cli
  4. Run polyfit_cli → .off mesh
  5. Convert .off → CityJSON (flatten per-semantic surfaces if possible)
  6. Run val3dity
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from collections import defaultdict
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from scripts.phase2_synthesis.obj_gt import parse_scene_obj  # noqa: E402

CLI = ROOT / "src/stage3/polyfit_cli"


def cluster_planes(faces, cos_tol=0.98, dist_tol=0.2):
    """Group coplanar faces → planes.

    Two faces are coplanar iff:
      - normals align (|cos| > cos_tol), AND
      - centroid-to-plane distance < dist_tol (meters)
    """
    planes = []  # list of dict(normal, d, face_indices)
    for fi, f in enumerate(faces):
        n = np.array(f['normal'])
        c = np.array(f['centroid'])
        matched = False
        for p in planes:
            pn, pd = p['normal'], p['d']
            cos = float(np.dot(n, pn))
            if abs(cos) < cos_tol:
                continue
            # distance from centroid c to plane (pn, pd):
            # signed dist = (pn · c) - pd. Sign of cos flips pn direction for comparison.
            proj = float(np.dot(pn, c)) - pd
            if abs(proj) < dist_tol:
                p['faces'].append(fi)
                matched = True
                break
        if not matched:
            d = float(np.dot(n, c))
            planes.append({'normal': n.copy(), 'd': d, 'faces': [fi]})
    # return compatible tuple form
    return [(p['normal'], p['d'], p['faces']) for p in planes]


def sample_points_on_face(face, n_samples):
    """Sample points uniformly within a triangular face (use vertices + centroid)."""
    verts = np.array(face['vertices'])  # (V, 3)
    if verts.shape[0] < 3:
        return np.array([face['centroid']])
    # Simple: fan triangulation from vertex 0, uniform sampling per sub-triangle.
    centroid = np.array(face['centroid'])
    pts = [centroid]
    # Add vertices
    for v in verts:
        pts.append(v)
    # Edge midpoints
    for i in range(len(verts)):
        pts.append((verts[i] + verts[(i+1) % len(verts)]) / 2)
    # Truncate/sample up to n_samples
    pts = np.array(pts)
    if len(pts) > n_samples:
        idx = np.random.default_rng(42).choice(len(pts), n_samples, replace=False)
        pts = pts[idx]
    return pts


def build_polyfit_input(faces, target_n_points=500):
    """Generate (points, normals, plane_ids) from building's faces."""
    planes = cluster_planes(faces)
    total_area = sum(f['area'] for f in faces)
    rng = np.random.default_rng(0)
    all_pts, all_normals, all_pids = [], [], []
    for pi, (pn, pd, fis) in enumerate(planes):
        for fi in fis:
            f = faces[fi]
            # Points per face proportional to area
            n_per_face = max(8, int(round(target_n_points * f['area'] / total_area)))
            pts = sample_points_on_face(f, n_per_face)
            all_pts.append(pts)
            all_normals.append(np.tile(pn, (len(pts), 1)))
            all_pids.append(np.full(len(pts), pi))
    all_pts = np.concatenate(all_pts)
    all_normals = np.concatenate(all_normals)
    all_pids = np.concatenate(all_pids)
    return all_pts, all_normals, all_pids, len(planes)


def write_polyfit_input(path: Path, pts, normals, pids, n_planes):
    with open(path, 'w') as f:
        f.write(f"{len(pts)} {n_planes}\n")
        for i in range(len(pts)):
            f.write(f"{pts[i,0]:.4f} {pts[i,1]:.4f} {pts[i,2]:.4f} "
                    f"{normals[i,0]:.4f} {normals[i,1]:.4f} {normals[i,2]:.4f} {pids[i]}\n")


def run_polyfit(input_path: Path, output_path: Path, timeout: int = 300) -> tuple[bool, str]:
    try:
        r = subprocess.run([str(CLI), str(input_path), str(output_path)],
                           capture_output=True, text=True, timeout=timeout)
        ok = (r.returncode == 0) and output_path.exists()
        msg = r.stderr.strip().split('\n')[-1] if r.stderr else ''
        return ok, msg
    except subprocess.TimeoutExpired:
        return False, "timeout"
    except Exception as e:
        return False, f"{type(e).__name__}: {e}"


def off_to_cityjson(off_path: Path, building_id, out_dir: Path, scale=0.001):
    """Convert OFF mesh → CityJSON LOD2 Solid (no semantic surfaces for now)."""
    lines = off_path.read_text().splitlines()
    if not lines or not lines[0].strip().startswith('OFF'):
        return None
    def _skip_empty(idx):
        while idx < len(lines) and (not lines[idx].strip() or lines[idx].strip().startswith('#')):
            idx += 1
        return idx
    i = _skip_empty(1)
    counts = lines[i].split()
    n_v, n_f = int(counts[0]), int(counts[1])
    i = _skip_empty(i + 1)
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
        faces.append([int(tok[1+j]) for j in range(k)])
        i += 1; read += 1
    if n_f < 4:
        return None
    # Quantize vertices + dedup shared corners across faces.
    # CGAL PolyFit emits per-face vertices independently (duplicated 3D coords),
    # which val3dity interprets as non-manifold edges. Dedup by quantized position.
    translate = [min(v[j] for v in verts) for j in range(3)]
    t_ijk = [round(translate[j] / scale) for j in range(3)]
    qvert_map = {}  # (qx, qy, qz) → canonical idx
    int_verts = []
    remap = [0] * len(verts)
    for vi, v in enumerate(verts):
        key = tuple(round(v[j] / scale) for j in range(3))
        if key not in qvert_map:
            qvert_map[key] = len(int_verts)
            int_verts.append([key[j] - t_ijk[j] for j in range(3)])
        remap[vi] = qvert_map[key]
    # Remap faces to deduped vertex IDs + drop degenerate rings
    boundaries = []
    for f in faces:
        ring = [remap[i] for i in f]
        # remove consecutive duplicates (e.g., merged vertices collapse edge)
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
    # Compute signed volume to check winding (using scaled int verts)
    def _sv():
        vol = 0
        for bnd in boundaries:
            ring = bnd[0]
            if len(ring) < 3: continue
            pts = [np.array(int_verts[i]) * scale for i in ring]
            for k in range(1, len(pts) - 1):
                vol += float(np.dot(pts[0], np.cross(pts[k], pts[k+1])))
        return vol / 6.0
    vol = _sv()
    if vol < 0:
        for b in boundaries:
            b[0] = b[0][::-1]
        vol = -vol
    # Semantic surfaces — uniform (cannot distinguish without normals)
    sem_surfaces = [{"type": "RoofSurface"}]
    sem_values = [0] * len(boundaries)
    bname = f"building_{building_id:03d}"
    cityjson = {
        "type": "CityJSON", "version": "2.0",
        "transform": {"scale": [scale]*3, "translate": translate},
        "CityObjects": {
            bname: {
                "type": "Building",
                "attributes": {"building_id": int(building_id), "signed_volume": vol},
                "geometry": [{
                    "type": "Solid", "lod": "2",
                    "boundaries": [boundaries],
                    "semantics": {"surfaces": sem_surfaces, "values": [sem_values]},
                }],
            }
        },
        "vertices": int_verts,
    }
    out_path = out_dir / "building.city.json"
    out_path.write_text(json.dumps(cityjson, indent=2))
    return {"cityjson_path": str(out_path), "n_surfaces": len(boundaries),
            "n_vertices": len(int_verts), "signed_volume": vol}


def run_val3dity(cj_path: Path, rp_path: Path):
    try:
        r = subprocess.run(["val3dity", "--report", str(rp_path), str(cj_path)],
                           capture_output=True, text=True, timeout=180)
    except Exception as e:
        return {"error": str(e)}
    out = {"returncode": r.returncode}
    if rp_path.exists():
        try:
            out["report"] = json.loads(rp_path.read_text())
        except Exception as e:
            out["report_parse_error"] = str(e)
    return out


def is_valid(v):
    rep = v.get("report", {})
    feats = rep.get("features", [])
    return bool(feats[0].get("validity", False)) if feats else False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--scene", default=str(ROOT / "results/phase2_synthesis/scene.obj"))
    ap.add_argument("--out", default=str(ROOT / "results/phase2_ablation_citygml/_gt_polyfit_test"))
    ap.add_argument("--n-points", type=int, default=500, help="target points per building")
    ap.add_argument("--limit", type=int, default=0, help="limit n buildings (0=all)")
    args = ap.parse_args()

    out_dir = Path(args.out); out_dir.mkdir(parents=True, exist_ok=True)
    print(f"[gt-polyfit] loading {args.scene}")
    gt = parse_scene_obj(args.scene)
    n_total = len(gt['buildings'])
    print(f"[gt-polyfit] {n_total} buildings")

    buildings = gt['buildings'][:args.limit] if args.limit else gt['buildings']
    from collections import defaultdict
    errs = defaultdict(int)
    by_type = defaultdict(lambda: [0, 0])
    per_b = []
    n_proc, n_valid = 0, 0

    for bi, b in enumerate(buildings):
        bid = b['building_id']
        btype = b['type']
        faces = b['faces']
        if len(faces) < 4:
            continue
        bdir = out_dir / f"building_{bid:03d}"
        bdir.mkdir(parents=True, exist_ok=True)

        pts, normals, pids, n_planes = build_polyfit_input(faces, args.n_points)
        in_path = bdir / "polyfit_input.txt"
        off_path = bdir / "polyfit_output.off"
        write_polyfit_input(in_path, pts, normals, pids, n_planes)

        ok, msg = run_polyfit(in_path, off_path)
        by_type[btype][1] += 1
        if not ok:
            per_b.append({"bid": bid, "type": btype, "error": f"polyfit: {msg}"})
            errs['polyfit_fail'] += 1
            continue

        result = off_to_cityjson(off_path, bid, bdir)
        if result is None:
            per_b.append({"bid": bid, "type": btype, "error": "off_to_cityjson"})
            errs['citygml_fail'] += 1
            continue

        n_proc += 1
        cj_path = Path(result["cityjson_path"])
        rp_path = bdir / "val3dity.json"
        v3d = run_val3dity(cj_path, rp_path)
        valid = is_valid(v3d)
        if valid:
            n_valid += 1
            by_type[btype][0] += 1
        err_codes = [e.get("code", "?") for e in
                     (v3d.get("report", {}).get("features", [{}])[0].get("errors", [])
                      if v3d.get("report", {}).get("features") else [])]
        per_b.append({"bid": bid, "type": btype, "val3dity_valid": valid,
                      "val3dity_errors": err_codes, "n_planes": n_planes,
                      "n_points": len(pts), "n_surfaces": result["n_surfaces"],
                      "signed_volume": result["signed_volume"]})
        for c in err_codes:
            errs[str(c)] += 1
        if (bi + 1) % 20 == 0:
            print(f"  [{bi+1}/{len(buildings)}] processed={n_proc} valid={n_valid}")

    rate = n_valid / max(n_total, 1)
    print(f"\n[gt-polyfit] summary:")
    print(f"  processed:      {n_proc}/{n_total}")
    print(f"  val3dity VALID: {n_valid}/{n_total} = {rate*100:.1f}%")
    print(f"  errors: {dict(errs)}")
    print("  by type:")
    for t, (v, n) in sorted(by_type.items()):
        print(f"    {t:12s}: {v:3d}/{n:3d} = {100*v/max(n,1):.1f}%")

    summary = {
        "n_total": n_total, "n_processed": n_proc, "n_valid": n_valid,
        "pass_rate": rate,
        "by_type": {t: {"valid": v, "total": n} for t, (v, n) in by_type.items()},
        "errors": dict(errs),
        "per_building": per_b,
    }
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2, default=str))
    print(f"[gt-polyfit] saved {out_dir/'summary.json'}")


if __name__ == "__main__":
    main()
