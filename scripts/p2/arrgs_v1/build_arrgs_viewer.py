#!/usr/bin/env python3
"""Build the ARRGS viewer (port 8884) payload: manifest.json + app files.

Serve root = artifacts/phase-payloads/p2/arrgs_v1/  (so run payload PNG/OBJ
are reachable by relative path from /viewer/). Usage:
  python build_arrgs_viewer.py            # scans default run roots
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path

ART = Path("/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts")
BASE = ART / "phase-payloads/p2/arrgs_v1"
VIEWER = BASE / "viewer"
REPO_VIEWER = Path(__file__).resolve().parent / "viewer"
THREE_SRC = (ART / "phase-payloads/p2/journal1_phase_b_v1/P2-JOURNAL1-PHASE-B-v1/"
             "viewer/three.module.min.js")

RUN_ROOTS = [
    ("X0", BASE / "P2-ARRGS-X0-v1/runs"),
    ("X1", BASE / "P2-ARRGS-X1-v1/runs"),
    ("X2", BASE / "P2-ARRGS-X2-v1/runs"),
    ("X3", BASE / "P2-ARRGS-X3-v1/runs"),
    ("X4", BASE / "P2-ARRGS-X4-v1/runs"),
    ("ORACLE", BASE / "P2-ARRGS-ORACLE-v1/runs"),
]

ARM_OF_EXP = {"X1": "ARRGS", "X2": "ARRGS", "ORACLE": "ARRGS_ORACLE"}


def load_eval_rows():
    import csv
    p = BASE / "evaluation/rows.csv"
    if not p.is_file():
        return {}
    out = {}
    for r in csv.DictReader(open(p)):
        out[(r["stable_id"], r["arm"], r["gt"])] = {
            k: r[k] for k in ("f1@0.5", "completeness@0.25", "precision@0.5",
                              "acc_median", "z_spread")}
    return out


OVERLAY_SRC = {
    "E7": ART / ("phase-payloads/p2/journal1_phase_a_v1/P2-JOURNAL1-PHASE-A-v1/"
                 "a2/assets_roofer_input/E7"),
    "E1": ART / ("phase-payloads/p2/e1_e6_roofer_ox_review_v1/"
                 "P2-E1-E6-GATE5-DASHBOARD-v1/assets_roofer_input/E1"),
    "E2": ART / ("phase-payloads/p2/e1_e6_roofer_ox_review_v1/"
                 "P2-E1-E6-GATE5-DASHBOARD-v1/assets_roofer_input/E2"),
}


def rel(p: Path) -> str:
    return str(p.relative_to(BASE))


def ensure_overlay_links():
    root = BASE / "viewer_assets"
    root.mkdir(exist_ok=True)
    for arm, src in OVERLAY_SRC.items():
        link = root / arm
        if not link.exists() and src.is_dir():
            link.symlink_to(src)


def load_run(exp: str, run_dir: Path):
    entry = {"exp": exp, "name": run_dir.name, "dir": rel(run_dir)}
    for key, fn in (("s1", "s1_candidates.json"), ("metrics", "metrics.json"),
                    ("run", "run.json")):
        p = run_dir / fn
        if p.is_file():
            entry[key] = json.load(open(p))
    s2p = run_dir / "s2_arrangement.json"
    if s2p.is_file():
        # arrangement geometry goes to a per-run lazy file — embedding it blew
        # the manifest to 243 MB (blank viewer) once S1R runs hit ~9k cells
        s2v = run_dir / "s2_view.json"
        if not s2v.is_file() or s2v.stat().st_mtime < s2p.stat().st_mtime:
            s2 = json.load(open(s2p))
            import numpy as np
            from scipy.spatial import ConvexHull
            cells = []
            for c in s2["cells"]:
                v = np.asarray(c["verts"])
                edges = []
                try:
                    hull = ConvexHull(v)
                    es = set()
                    for s in hull.simplices:
                        for i in range(3):
                            e = tuple(sorted((int(s[i]), int(s[(i + 1) % 3]))))
                            es.add(e)
                    edges = [[np.round(v[a], 2).tolist(), np.round(v[b], 2).tolist()]
                             for a, b in es]
                except Exception:
                    pass
                cells.append({"idx": c["idx"], "centroid": c["centroid"],
                              "fixed": c["fixed"], "o_init": c.get("o_init"),
                              "edges": edges})
            faces = [{k: f[k] for k in ("plane_id", "cell_a", "cell_b", "n", "d",
                                        "poly3d", "area")} for f in s2["faces"]]
            json.dump({"cells": cells, "faces": faces,
                       "renderable_faces": s2.get("renderable_faces", []),
                       "gt_labels": s2.get("gt_labels")}, open(s2v, "w"))
        s2c = json.load(open(s2p))
        entry["s2_ref"] = rel(s2v)
        entry["s2_counts"] = {
            "cells": len(s2c["cells"]),
            "free": sum(1 for c in s2c["cells"] if c["fixed"] is None),
            "faces": len(s2c["faces"]),
            "renderable": len(s2c.get("renderable_faces", []))}
    snaps = []
    snap_dir = run_dir / "snapshots"
    if snap_dir.is_dir():
        for p in sorted(snap_dir.glob("iter_*.json")):
            s = json.load(open(p))
            it = s["iter"]
            s["renders"] = [rel(q) for q in sorted(snap_dir.glob(f"render_v*_{it:06d}.png"))]
            snaps.append(s)
    entry["snapshots"] = snaps
    if (run_dir / "s5_brep.obj").is_file():
        entry["s5_obj"] = rel(run_dir / "s5_brep.obj")
    if (run_dir / "s5_evidence.json").is_file():
        entry["s5_evidence"] = json.load(open(run_dir / "s5_evidence.json"))
    # GT / comparison overlays for real-building runs
    cfg = entry.get("run", {}).get("config", {})
    bkey = cfg.get("scene", {}).get("bkey")
    if bkey:
        ov = {}
        for arm in OVERLAY_SRC:
            if (BASE / "viewer_assets" / arm / f"{bkey}.points.ply").is_file():
                ov[arm] = f"viewer_assets/{arm}/{bkey}.points.ply"
        if ov:
            entry["overlays"] = ov
            entry["bkey"] = bkey
    return entry


def load_lod2_rings(bkeys):
    """LoD2 RoofSurface rings (viewer-local) for S1/S5 GT overlay — evaluation-only."""
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "journal1_phase_a_v1"))
    from geometry_eval import load_lod2_faces
    cfg = json.load(open(Path(__file__).resolve().parents[3] /
                         "configs/p2/arrgs_v1/eval_arrgs_v1.json"))
    tiles = [t.replace("/artifacts/JointBuildGS", str(ART)) for t in cfg["gml_tiles"]]
    sids = {"_".join(b.split("_")[1:]) for b in bkeys}
    faces = load_lod2_faces(tiles, sids, cfg["origin"], cfg["lod2_z_shift_to_viewer_m"])
    out = {}
    for sid, fl in faces.items():
        rings = []
        for verts, n in fl:
            import numpy as np
            v = np.asarray(verts)
            area = 0.5 * np.linalg.norm(sum(
                np.cross(v[i] - v[0], v[i + 1] - v[0]) for i in range(1, len(v) - 1)))
            if area >= 5.0:
                rings.append(np.round(v, 3).tolist())
        out[sid] = rings
    return out


def main():
    VIEWER.mkdir(parents=True, exist_ok=True)
    ensure_overlay_links()
    runs = []
    for exp, root in RUN_ROOTS:
        if not root.is_dir():
            continue
        for run_dir in sorted(root.iterdir()):
            if ((run_dir / "metrics.json").is_file()
                    or (run_dir / "s2_arrangement.json").is_file()
                    or (run_dir / "s5_brep.obj").is_file()):
                try:
                    runs.append(load_run(exp, run_dir))
                except Exception as e:
                    print("skip", run_dir, e)
    # sealed-evaluator f1 rows -> per-run (X1/X2 clean + oracle)
    ev = load_eval_rows()
    for r in runs:
        arm = ARM_OF_EXP.get(r["exp"])
        bkey = r.get("bkey") or (r.get("run", {}).get("config", {})
                                 .get("scene", {}).get("bkey"))
        if r["exp"] == "ORACLE" and not bkey:
            hits = list((BASE / "viewer_assets/E7").glob(f"{r['name']}_*.points.ply"))
            if hits:
                bkey = hits[0].name.replace(".points.ply", "")
                r["bkey"] = bkey
                ov = {}
                for a in OVERLAY_SRC:
                    if (BASE / "viewer_assets" / a / f"{bkey}.points.ply").is_file():
                        ov[a] = f"viewer_assets/{a}/{bkey}.points.ply"
                if ov:
                    r["overlays"] = ov
        if arm and bkey:
            sid = "_".join(bkey.split("_")[1:])
            e = {gt: ev.get((sid, arm, gt)) for gt in ("e1", "lod2")}
            if any(e.values()):
                r["eval"] = e
    bkeys = {r["bkey"] for r in runs if r.get("bkey")}
    if bkeys:
        try:
            rings = load_lod2_rings(bkeys)
            for r in runs:
                sid = "_".join(r["bkey"].split("_")[1:]) if r.get("bkey") else None
                if sid and sid in rings:
                    r["lod2_rings"] = rings[sid]
        except Exception as e:
            print("lod2 rings skipped:", e)
    summaries = {}
    for exp, root in RUN_ROOTS:
        sp = root.parent / f"{exp.lower()}_summary.json"
        if sp.is_file():
            summaries[exp] = json.load(open(sp))
    manifest = {"runs": runs, "summaries": summaries,
                "note": "ARRGS viewer v1 — NOT OFFICIAL, scientific_verdict: null"}
    json.dump(manifest, open(VIEWER / "manifest.json", "w"))
    for fn in ("index.html", "app.js"):
        shutil.copy2(REPO_VIEWER / fn, VIEWER / fn)
    if THREE_SRC.is_file() and not (VIEWER / "three.module.min.js").is_file():
        shutil.copy2(THREE_SRC, VIEWER / "three.module.min.js")
    print(f"viewer built: {VIEWER}  runs={len(runs)}")
    print(f"serve:  cd {BASE} && python3 -m http.server 8884 --bind 0.0.0.0")


if __name__ == "__main__":
    main()
