#!/usr/bin/env python3
"""S1 vs GT: match detected candidate planes against LoD2 RoofSurface planes.

Expected (per unchanged building): every LoD2 roof face of meaningful area has
a candidate plane within ANG_TOL deg / OFF_TOL m (offset measured at the face
centroid). Output: per-face match table + a top-view map (green = matched,
red = missed, annotated with the matching candidate and its errors).

LoD2 is evaluation-only here (S1 QA), consistent with the GT-separation rule.
Caveat: for changed buildings (B173) the stale LoD2 is NOT a valid target —
a mismatch there is correct behaviour, reported as such.
"""
import json
import sys
from pathlib import Path

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

sys.path.insert(0, "/workspace/JointBuildGS/scripts/p2/journal1_phase_a_v1")
sys.path.insert(0, "/workspace/JointBuildGS/scripts/p2/arrgs_v1")
from geometry_eval import load_lod2_faces  # noqa: E402

B = "/artifacts/JointBuildGS/phase-payloads/p2/arrgs_v1"
CFG = json.load(open("/workspace/JointBuildGS/configs/p2/arrgs_v1/eval_arrgs_v1.json"))
ORIGIN = CFG["origin"]
ZSHIFT = CFG["lod2_z_shift_to_viewer_m"]
TILES = CFG["gml_tiles"]

RUNS = [("P2-ARRGS-X1-v1/runs/B022_clean", "B022", "DEBY_LOD2_4906965", "unchanged"),
        ("P2-ARRGS-X2-v1/runs/B173_changed", "B173", "DEBY_LOD2_4959326", "CHANGED(LoD2 stale)"),
        ("P2-ARRGS-X2-v1/runs/B036_hole", "B036", "DEBY_LOD2_4906982", "unchanged?")]
ANG_TOL = 10.0
OFF_TOL = 0.5
MIN_AREA = 5.0

faces_by_bid = load_lod2_faces(TILES, {r[2] for r in RUNS}, ORIGIN, ZSHIFT)

fig, axes = plt.subplots(1, 3, figsize=(16, 6))
for col, (run, label, sid, status) in enumerate(RUNS):
    s1 = json.load(open(f"{B}/{run}/s1_candidates.json"))
    cands = [p for p in s1["planes"] if p["source"] in ("prior_als", "mvs")]
    gt = faces_by_bid.get(sid, [])
    ax = axes[col]
    rowlog = []
    n_match = n_tot = 0
    for verts, n in gt:
        # polygon area (planar, via cross products in 3D)
        area = 0.5 * np.linalg.norm(sum(np.cross(verts[i] - verts[0], verts[i + 1] - verts[0])
                                        for i in range(1, len(verts) - 1)))
        if area < MIN_AREA:
            continue
        n_tot += 1
        c = verts.mean(axis=0)
        best = None
        for p in cands:
            pn = np.asarray(p["n"]); pd = p["d"]
            cos = abs(float(pn @ n))
            ang = np.degrees(np.arccos(min(1.0, cos)))
            off = abs(float(pn @ c - pd))
            if best is None or (ang + off * 20) < (best[1] + best[2] * 20):
                best = (p["id"], ang, off, p["source"])
        ok = best is not None and best[1] <= ANG_TOL and best[2] <= OFF_TOL
        n_match += ok
        rowlog.append((area, ok, best))
        colr = "#2f8f2f" if ok else "#c03030"
        ax.fill(verts[:, 0], verts[:, 1], facecolor=colr, alpha=0.45,
                edgecolor=colr, lw=1.2)
        if area > 30:
            txt = f"{best[0]}\n{best[1]:.0f}deg/{best[2]:.2f}m" if best else "no cand"
            ax.text(c[0], c[1], txt, fontsize=6.5, ha="center", va="center")
    fp = np.asarray(s1["footprint"])
    ax.plot(np.r_[fp[:, 0], fp[0, 0]], np.r_[fp[:, 1], fp[0, 1]], "k-", lw=1)
    ax.set_aspect("equal"); ax.set_xticks([]); ax.set_yticks([])
    rate = n_match / max(1, n_tot)
    ax.set_title(f"{label} [{status}]\nLoD2 roof faces>={MIN_AREA}m2: {n_tot}, "
                 f"matched(<= {ANG_TOL}deg,{OFF_TOL}m): {n_match} ({rate:.0%})",
                 fontsize=10,
                 color="#207020" if rate >= 0.8 and "CHANGED" not in status else
                       ("#555555" if "CHANGED" in status else "#b03030"))
    print(f"[{label}] GT faces {n_tot} matched {n_match} ({rate:.0%})")
    for area, ok, best in sorted(rowlog, key=lambda r: -r[0]):
        print(f"   {'O' if ok else 'X'} area={area:6.0f}m2 best={best[0]:8s}"
              f"({best[3][:4]}) ang={best[1]:5.1f}deg off={best[2]:5.2f}m")
fig.suptitle("S1 vs LoD2 GT roof planes - green=matched candidate exists, red=missed "
             "(text: best candidate, angle/offset error)", fontsize=11)
fig.tight_layout()
fig.savefig(f"{B}/qual_s1_gt_match.png", dpi=100, facecolor="white")
print("saved", f"{B}/qual_s1_gt_match.png")
