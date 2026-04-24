"""Direct conversion: GT scene.obj (per building) -> CityJSON LOD2 + val3dity.

No plane abstraction, no Stage 3 reconstruction. Pure format conversion,
preserving original vertex+face topology. This measures the upper bound of
what "perfect GT topology" achieves via val3dity — isolating Stage 3 algorithm
contributions from mere format compatibility.
"""
from __future__ import annotations

import json
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from scripts.phase2_synthesis.obj_gt import parse_scene_obj  # noqa: E402


SEM_MAP = {1: "RoofSurface", 2: "WallSurface", 3: "GroundSurface"}  # 0=BG


def scene_to_cityjson(building, out_path: Path, scale: float = 0.001):
    """Write per-building CityJSON preserving GT topology.

    Input: building dict from parse_scene_obj with 'faces' (list of face dicts
    with 'vertices' (N,3), 'semantic_class', 'centroid').
    """
    bid = building["building_id"]
    faces = building["faces"]
    if not faces:
        return None

    # Collect all unique vertices (quantized)
    qmap: dict[tuple[int, int, int], int] = {}
    int_verts: list[list[int]] = []

    # First pass: find translate (min of quantized coords) to keep vert ints small
    all_coords = []
    for f in faces:
        for v in f["vertices"]:
            all_coords.append(v)
    all_coords_arr = np.array(all_coords)
    translate = [float(all_coords_arr[:, i].min()) for i in range(3)]
    t_ijk = [round(translate[i] / scale) for i in range(3)]

    def add_vert(v):
        key = tuple(round(v[i] / scale) for i in range(3))
        if key not in qmap:
            qmap[key] = len(int_verts)
            int_verts.append([key[i] - t_ijk[i] for i in range(3)])
        return qmap[key]

    boundaries: list[list[list[int]]] = []
    sem_surfaces: list[dict] = []
    sem_values: list[int] = []
    sem_type_to_idx: dict[str, int] = {}

    for fi, f in enumerate(faces):
        ring = [add_vert(v) for v in f["vertices"]]
        # Remove consecutive duplicates
        cleaned = [ring[0]]
        for idx in ring[1:]:
            if idx != cleaned[-1]:
                cleaned.append(idx)
        if len(cleaned) > 1 and cleaned[-1] == cleaned[0]:
            cleaned = cleaned[:-1]
        if len(cleaned) < 3:
            continue
        boundaries.append([cleaned])
        sem_type = SEM_MAP.get(f["semantic_class"], "WallSurface")
        if sem_type not in sem_type_to_idx:
            sem_type_to_idx[sem_type] = len(sem_surfaces)
            sem_surfaces.append({"type": sem_type})
        sem_values.append(sem_type_to_idx[sem_type])

    if len(boundaries) < 4:
        return None

    # Signed volume → flip winding if needed
    def _sv():
        vol = 0.0
        for bnd in boundaries:
            ring = bnd[0]
            if len(ring) < 3:
                continue
            pts = [np.array(int_verts[i]) * scale for i in ring]
            for k in range(1, len(pts) - 1):
                vol += float(np.dot(pts[0], np.cross(pts[k], pts[k + 1])))
        return vol / 6.0

    vol = _sv()
    if vol < 0:
        for b in boundaries:
            b[0] = b[0][::-1]
        vol = -vol

    bname = f"building_{bid:03d}"
    cj = {
        "type": "CityJSON", "version": "2.0",
        "transform": {"scale": [scale] * 3, "translate": translate},
        "CityObjects": {
            bname: {
                "type": "Building",
                "attributes": {"building_id": int(bid), "type": building.get("type"),
                               "signed_volume": vol},
                "geometry": [{
                    "type": "Solid", "lod": "2",
                    "boundaries": [boundaries],
                    "semantics": {"surfaces": sem_surfaces, "values": [sem_values]},
                }],
            }
        },
        "vertices": int_verts,
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(cj, indent=2))
    return {"n_faces": len(boundaries), "n_vertices": len(int_verts),
            "signed_volume": vol, "cityjson_path": str(out_path)}


def run_val3dity(cj_path: Path, rp_path: Path):
    try:
        r = subprocess.run(["val3dity", "--report", str(rp_path), str(cj_path)],
                           capture_output=True, text=True, timeout=60)
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
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--scene", default=str(ROOT / "results/phase2_synthesis/scene.obj"))
    ap.add_argument("--out", default=str(ROOT / "results/phase2_ablation_citygml/_gt_direct"))
    args = ap.parse_args()

    gt = parse_scene_obj(args.scene)
    buildings = gt["buildings"]
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    n_total = len(buildings)
    n_proc = 0
    n_valid = 0
    err_counts = defaultdict(int)
    by_type = defaultdict(lambda: [0, 0])  # [valid, total]
    per_b = []

    print(f"[gt-direct] {n_total} buildings")
    for b in buildings:
        bid = b["building_id"]
        btype = b.get("type", "?")
        bdir = out_dir / f"building_{bid:03d}"
        cj_path = bdir / "building.city.json"
        res = scene_to_cityjson(b, cj_path)
        by_type[btype][1] += 1
        if res is None:
            per_b.append({"bid": bid, "type": btype, "error": "conversion_none"})
            err_counts["conversion_none"] += 1
            continue
        n_proc += 1
        rp = bdir / "val3dity.json"
        v3d = run_val3dity(cj_path, rp)
        valid = is_valid(v3d)
        if valid:
            n_valid += 1
            by_type[btype][0] += 1
        codes = [e.get("code", "?") for e in
                 (v3d.get("report", {}).get("features", [{}])[0].get("errors", [])
                  if v3d.get("report", {}).get("features") else [])]
        for c in codes:
            err_counts[str(c)] += 1
        per_b.append({"bid": bid, "type": btype, "val3dity_valid": valid,
                      "val3dity_errors": codes, "n_faces": res["n_faces"],
                      "n_vertices": res["n_vertices"],
                      "signed_volume": res["signed_volume"]})

    print(f"\n[gt-direct] summary:")
    print(f"  processed: {n_proc}/{n_total}")
    print(f"  val3dity VALID: {n_valid}/{n_total} = {100*n_valid/max(n_total,1):.1f}%")
    print(f"  errors: {dict(err_counts)}")
    print(f"  by type:")
    for t, (v, n) in sorted(by_type.items()):
        print(f"    {t:12s}: {v:3d}/{n:3d} = {100*v/max(n,1):.1f}%")

    summary = {
        "n_total": n_total, "n_processed": n_proc, "n_valid": n_valid,
        "pass_rate": n_valid / max(n_total, 1),
        "by_type": {t: {"valid": v, "total": n} for t, (v, n) in by_type.items()},
        "errors": dict(err_counts),
        "per_building": per_b,
    }
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2, default=str))
    print(f"[gt-direct] saved {out_dir/'summary.json'}")


if __name__ == "__main__":
    main()
