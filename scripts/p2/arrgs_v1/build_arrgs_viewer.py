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
]


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
        s2 = json.load(open(s2p))
        # trim cell verts -> edges for wireframe (unique hull edges)
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
                edges = [[v[a].tolist(), v[b].tolist()] for a, b in es]
            except Exception:
                pass
            cells.append({"idx": c["idx"], "centroid": c["centroid"],
                          "fixed": c["fixed"], "o_init": c.get("o_init"),
                          "edges": edges})
        entry["s2"] = {"cells": cells, "faces": s2["faces"],
                       "renderable_faces": s2.get("renderable_faces", []),
                       "gt_labels": s2.get("gt_labels")}
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


def main():
    VIEWER.mkdir(parents=True, exist_ok=True)
    ensure_overlay_links()
    runs = []
    for exp, root in RUN_ROOTS:
        if not root.is_dir():
            continue
        for run_dir in sorted(root.iterdir()):
            if (run_dir / "metrics.json").is_file() or (run_dir / "s2_arrangement.json").is_file():
                try:
                    runs.append(load_run(exp, run_dir))
                except Exception as e:
                    print("skip", run_dir, e)
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
