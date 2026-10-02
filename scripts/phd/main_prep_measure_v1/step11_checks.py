"""PHD-MAIN-PREP-MEASURE-v1 step 11 (jointbuildgs:dev, CPU): implementation checks (5.7).

  python step11_checks.py

1. party-wall gaps (LoD2): rays that enter the gap between touching buildings (first hit on a probe face inside the gap),
   per range before / after the caps (step 03 counts); for the view with the most gap rays of each range that has any,
   the photo crop with the gap pixels before and after.
2. ALS cell method: angle between the initial direction of a prior Gaussian (cell t1 x t2, signed like the vertex normal)
   and the normal of the patch face it sits on, the vertex-normal angle for comparison, and the points that sit on no
   patch, split by ALS class (2 ground, 6 building, other).
Outputs: step11/checks.json, step11/gaps_<range>.png, step11/orientation.png. scientific_verdict: null."""
import json

import cv2
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager
import numpy as np

from common import DENSE, OUT, GRID_H, GRID_W, Views, inside_range, jdump
from src.phd.prior_propagation_v4 import surfaces as surf
import step03_stage1 as s3

for f in ("/fonts/NotoSansCJK-Regular.ttc", "/fonts/NotoSansCJK-Bold.ttc"):
    try:
        font_manager.fontManager.addfont(f)
    except Exception:
        pass
plt.rcParams["font.family"] = ["Noto Sans CJK JP", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False
RANGES = ["R1", "R2", "R3", "R3E", "R4", "R5", "SW", "B0"]


def main():
    D = OUT / "step11"; D.mkdir(parents=True, exist_ok=True)
    V = Views()
    out = dict(task_id="PHD-MAIN-PREP-MEASURE-v1", step="11 implementation checks (5.7)", scientific_verdict=None, gaps={}, als_orientation={})
    rngs = json.loads((OUT / "step01/ranges.json").read_text())
    for rid in RANGES:
        S1 = OUT / "step03" / rid / "LoD2"
        g = json.loads((S1 / "gaps.json").read_text()) if (S1 / "gaps.json").exists() else []
        tot_b = sum(x["before"] for x in g); tot_a = sum(x["after"] for x in g)
        worst = max(g, key=lambda x: x["before"]) if g else None
        rec = dict(views=len(g), rays_before=tot_b, rays_after=tot_a, views_with_before=sum(x["before"] > 0 for x in g),
                   views_with_after=sum(x["after"] > 0 for x in g), worst_view=worst["view"] if worst else None,
                   worst_before=worst["before"] if worst else 0, worst_after=worst["after"] if worst else 0)
        meshj = json.loads((OUT / "step02" / rid / "lod2_surfaces.json").read_text())
        rec["party_wall_pairs"] = len(meshj.get("party_wall", [])); rec["caps"] = meshj.get("n_caps"); rec["probe_triangles"] = meshj.get("n_probe_tris")
        out["gaps"][rid] = rec
        if tot_a > 0:   # rays still marked after the caps: depth difference to the first non-probe surface on the same ray
            pr_ = s3.Prior(OUT / "step02" / rid, "LoD2")
            pr_.shift = np.asarray(json.loads((S1 / "summary.json").read_text())["registration"]["shift_applied"], float)
            sc_a, na_ = pr_.scene(with_caps=True, with_probe=True); sc_n, _ = pr_.scene(with_caps=True, with_probe=False)
            dd = []
            for x in g:
                if not x["after"]:
                    continue
                Dr = V.rays(x["view"]); C = V.C(x["view"])
                ta, tra = sc_a.cast(C, Dr); tn, _ = sc_n.cast(C, Dr)
                m = tra >= na_
                dd += (tn[m] - ta[m]).tolist()
            dd = np.array(dd)
            rec["after_rays_tie_lt_2mm"] = int((dd < 0.002).sum())
            rec["after_rays_into_gap_mouth"] = int(((dd >= 0.002) & np.isfinite(dd)).sum())
            rec["after_rays_into_gap_max_mm"] = float(1000 * dd[np.isfinite(dd)].max()) if np.isfinite(dd).any() else None
            rec["after_rays_through_gap_no_surface_behind"] = int((~np.isfinite(dd)).sum())
        if worst and worst["before"] > 0:
            pr = s3.Prior(OUT / "step02" / rid, "LoD2")
            pr.shift = np.asarray(json.loads((S1 / "summary.json").read_text())["registration"]["shift_applied"], float)
            sc_b, nb = pr.scene(with_caps=False, with_probe=True); sc_a, na_ = pr.scene(with_caps=True, with_probe=True)
            n = worst["view"]; Dr = V.rays(n); C = V.C(n)
            _, tb = sc_b.cast(C, Dr); _, ta = sc_a.cast(C, Dr)
            gb = tb >= nb; ga = ta >= na_
            img = cv2.imread(str(DENSE / "images" / n))[:, :, ::-1]; img = cv2.resize(img, (GRID_W, GRID_H), interpolation=cv2.INTER_AREA)
            ys, xs = np.nonzero(gb)
            cy, cx = int(np.median(ys)), int(np.median(xs))
            y0, y1 = max(0, cy - 120), min(GRID_H, cy + 120); x0, x1 = max(0, cx - 160), min(GRID_W, cx + 160)
            fig, axs = plt.subplots(1, 3, figsize=(15, 4.4), constrained_layout=True)
            axs[0].imshow(img[y0:y1, x0:x1]); axs[0].set_title(f"{rid} 시점 {n[-12:-4]}", fontsize=9)
            for ax, m, t in ((axs[1], gb, f"막기 전: 틈으로 들어간 시선 {int(gb.sum())}픽셀"), (axs[2], ga, f"막은 뒤: {int(ga.sum())}픽셀")):
                ov = img[y0:y1, x0:x1].copy().astype(float) * 0.55
                mm = m[y0:y1, x0:x1]
                ov[mm] = [255, 0, 255]
                ax.imshow(ov.astype(np.uint8)); ax.set_title(t, fontsize=9)
            for ax in axs:
                ax.set_xticks([]); ax.set_yticks([])
            fig.savefig(D / f"gaps_{rid}.png", dpi=90); plt.close(fig)
        # ALS orientation and unseated points
        SA = OUT / "step03" / rid / "ALS"
        summ = json.loads((SA / "summary.json").read_text())
        oc = summ["unplanted"].get("orientation_cell_method", {})
        pa = s3.Prior(OUT / "step02" / rid, "ALS")
        eligible = np.zeros(int(pa.tri_surface.max()) + 2, bool)
        for e in pa.table:
            eligible[e] = True
        vs = surf.vertex_surface(pa.F, pa.tri_surface, eligible)
        sh = np.asarray(summ["registration"]["shift_applied"], float)
        inr = inside_range((pa.V0 + sh)[:, :2], rngs[rid])
        uns = inr & (vs < 0)
        cls = pa.cls
        out["als_orientation"][rid] = dict(points=int(inr.sum()), seated=int((inr & (vs >= 0)).sum()), unseated=int(uns.sum()),
                                           unseated_by_class={"2 ground": int((uns & (cls == 2)).sum()), "6 building": int((uns & (cls == 6)).sum()),
                                                              "other": int((uns & (cls != 2) & (cls != 6)).sum())},
                                           cell_method=oc)
    # orientation figure (all ranges pooled)
    angs_q, angs_v = [], []
    for rid in RANGES:
        o = np.load(OUT / "step03" / rid / "ALS" / "orientation_angles.npz")
        angs_q.append(o["initial_vs_face"]); angs_v.append(o["vertex_vs_face"])
    q = np.concatenate(angs_q); v = np.concatenate(angs_v)
    fig, axs = plt.subplots(1, 2, figsize=(12, 3.8), constrained_layout=True)
    axs[0].hist(np.clip(q, 0, 1e-12), bins=40, color="#2a9d3a"); axs[0].set_title(f"칸 방식 처음 방향 − 앉은 패치 면 법선 (점 {len(q):,}개, 최대 {q.max():.1e}°)", fontsize=9)
    axs[0].set_xlabel("각도 (도)")
    axs[1].hist(v, bins=90, range=(0, 90), color="#999999"); axs[1].set_yscale("log")
    axs[1].set_title(f"비교: 꼭짓점 법선 − 패치 면 법선 (중앙값 {np.median(v):.1f}°, 95 % {np.quantile(v, 0.95):.1f}°)", fontsize=9)
    axs[1].set_xlabel("각도 (도)")
    fig.savefig(D / "orientation.png", dpi=90); plt.close(fig)
    out["als_orientation_pooled"] = dict(points=int(len(q)), initial_vs_face_max_deg=float(q.max()), vertex_vs_face_p50=float(np.median(v)),
                                         vertex_vs_face_p95=float(np.quantile(v, 0.95)), vertex_vs_face_over_10deg_share=float((v > 10).mean()))
    jdump(D / "checks.json", out)
    print("gaps", {k: (v_["rays_before"], v_["rays_after"]) for k, v_ in out["gaps"].items()})
    print("als", {k: (v_["unseated"], v_["unseated_by_class"]) for k, v_ in out["als_orientation"].items()})


if __name__ == "__main__":
    main()
