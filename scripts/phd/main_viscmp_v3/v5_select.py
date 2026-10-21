"""PHD-MAIN-VISCMP-v3 V5 place (request 3), from the region files, GT, the image depth and the samepath distance file only (no other result
file is opened). Candidates: the '영상이 틀린 곳' patches of each of the six cases (dm_common.Unit.img = the new metric's range: the fill
task's filtered image error minus code-3 premise violations, plus code-3 within-threshold) joined at 0.36 m (3-D centres), as photo figure 5.
Conditions: (1) no gt_suspect patch (one GT layer); (2) area >= 1 m2; (3) the prior is on the GT: median |d_g| of the samepath distance
file's region rows in the piece <= 5 cm; (4) the image is visibly wrong: the camera = the training view holding every piece patch centre
with >= 80 % visible against the prior render depth and the largest footprint; the 1024 x 741 MVS depth map of that view (the training
depth, maps/mvs) as a pixel-grid mesh (vd_dist.depth_mesh); median |d_g| of the piece's region rows to it >= 10 cm.
Pick: the most GT points (region file gt_points) among the pieces meeting all four; the next one = auxiliary. Fallbacks: (3) at 10 cm, then
(4) at 5 cm. Also the fill task's rule place (SL/prep/figpos/obs_masked.json 'main') is copied for its values (not drawn).
  python v5_select.py -> /vc/prep/v5_candidates.json, /docs/tables/V5_candidates.md   scientific_verdict: null"""
import json
import time

import numpy as np
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components
from scipy.spatial import ConvexHull, cKDTree

import vc_common  # noqa: F401
import p0_places as P0
import vd_dist as VD
from vc_common import DOCS, SL, VC, jdump, jl, log, now

CASES = [(s, p) for s in ("B0_b10", "B173nb_b10", "R1rep_b10") for p in ("LoD2", "ALS")]
SITE_KO = {"B0_b10": "B0", "B173nb_b10": "B173 주변", "R1rep_b10": "R1"}


def camera_for(site, prior, P):
    V = P0.views(); best = None
    for v in P0.train_views(site):
        k = P0.vname(v)
        if k is None:
            continue
        u, w, z = V.project(k, P)
        if not ((z > 0) & (u >= 0) & (u < 1024) & (w >= 0) & (w < 741)).all():
            continue
        D = np.load(P0.S0 / "s61/export" / site / prior / "prior" / f"{v}.npy")
        d = D[np.clip(np.floor(w).astype(int), 0, 740), np.clip(np.floor(u).astype(int), 0, 1023)]
        vis = float((np.isfinite(d) & (np.abs(z - d) <= 0.5)).mean())
        if vis < P0.VIS_MIN:
            continue
        try:
            hull = float(ConvexHull(np.column_stack([u, w])).volume)
        except Exception:  # noqa: BLE001
            hull = 0.0
        if best is None or hull > best["hull_px2"]:
            best = dict(view=v, visible=vis, hull_px2=hull, tilt_deg=round(V.tilt(k), 2))
    return best


def main():
    t0 = time.time()
    rows, meta = [], {}
    for site, prior in CASES:
        C = VD.Case(site, prior); u = C.u; R = u.R
        sp = C.stored(f"samepath_{prior}")
        idx = np.nonzero(u.img)[0]
        Cc = u.centre[idx]
        pairs = cKDTree(Cc).query_pairs(0.36, output_type="ndarray")
        A = coo_matrix((np.ones(len(pairs)), (pairs[:, 0], pairs[:, 1])), shape=(len(Cc), len(Cc)))
        nc, lab = connected_components(A, directed=False)
        area = np.bincount(lab, weights=R["area"][idx].astype(np.float64), minlength=nc)
        gtp = np.bincount(lab, weights=R["gt_points"][idx].astype(np.float64), minlength=nc)
        sus = np.bincount(lab, weights=R["gt_suspect"][idx].astype(np.float64), minlength=nc)
        npa = np.bincount(lab, minlength=nc)
        meta[f"{site}/{prior}"] = dict(image_error_patches=int(len(idx)), pieces=int(nc), pieces_ge_1m2=int((area >= 1).sum()))
        for c in np.nonzero(area >= 1.0)[0]:
            mem = idx[lab == c]
            ri = C.rows_of(mem)
            c3 = float(np.median(np.abs(sp["rows"][ri]))) if len(ri) else None
            r = dict(case=f"{site}/{prior}", site=site, prior=prior, piece=int(c), patches=int(len(mem)), area_m2=round(float(area[c]), 2),
                     gt_points=int(gtp[c]), rows=int(len(ri)), multi_layer_patches=int(sus[c]), multi_layer_share=round(float(sus[c] / npa[c]), 3),
                     cond1=bool(sus[c] == 0), cond2=True, prior_dist_cm=None if c3 is None else round(100 * c3, 1), patch_list=[int(x) for x in mem])
            r["cond3_5cm"] = c3 is not None and c3 <= 0.05
            r["cond3_10cm"] = c3 is not None and c3 <= 0.10
            if r["cond1"] and r["cond3_10cm"]:
                U = P0.store(site, prior)
                cam = camera_for(site, prior, P0.patch_corners(U, mem))
                r["camera"] = cam
                if cam:
                    dep = np.load(P0.S0 / "fork_inputs/s61" / site / "maps/mvs" / f"{cam['view']}.npy")
                    V, F, info = VD.depth_mesh(cam["view"], dep)
                    dg = C.dg_rows(V, F, ri)
                    r["image_dist_cm"] = round(100 * float(np.median(np.abs(dg))), 1)
                    r["image_signed_cm"] = round(100 * float(np.median(dg)), 1)
                    r["depth_mesh"] = info
            r["cond4_10cm"] = bool(r.get("image_dist_cm") is not None and r["image_dist_cm"] >= 10.0)
            r["cond4_5cm"] = bool(r.get("image_dist_cm") is not None and r["image_dist_cm"] >= 5.0)
            rows.append(r)
            log(site, prior, c, r["patches"], r["area_m2"], r["multi_layer_patches"], r["prior_dist_cm"], r.get("image_dist_cm"))
        del C
    tiers = [("조건 그대로(3: 5 cm, 4: 10 cm)", "cond3_5cm", "cond4_10cm"), ("조건 3을 10 cm로 넓힘", "cond3_10cm", "cond4_10cm"),
             ("조건 3을 10 cm, 조건 4를 5 cm로", "cond3_10cm", "cond4_5cm")]
    chosen = None
    for name, k3, k4 in tiers:
        ok = [r for r in rows if r["cond1"] and r["cond2"] and r[k3] and r[k4]]
        if ok:
            ok.sort(key=lambda r: -r["gt_points"])
            chosen = dict(tier=name, main=ok[0], auxiliary=ok[1] if len(ok) > 1 else None, passing=len(ok))
            break
    fill = jl(SL / "prep/figpos/obs_masked.json")
    out = dict(made=now(), rule=__doc__.split("\n\n")[0], cases=meta, candidates=rows, chosen=chosen,
               fill_rule_place=dict(source="SL/prep/figpos/obs_masked.json 'main'", main={k: v for k, v in fill["main"].items() if k != "patch_list"},
                                    patch_list=fill["main"]["patch_list"]),
               seconds=round(time.time() - t0, 1), scientific_verdict=None)
    jdump(VC / "prep/v5_candidates.json", out)
    L = ["# V5 후보 — 영상이 틀린 곳의 1 m² 이상 덩어리 [이 발주에서 냄]", "",
         f"- 규칙: `scripts/phd/main_viscmp_v3/v5_select.py` 머리글. 고른 때 {out['made']}. 방법의 결과 메시와 거리 파일(학습 전 사전 정보의 거리 파일 말고)은 열지 않았다.",
         "- 거리 = 덩어리 안 영역 행(솎은 행)의 |d_g| 중앙값. 영상 깊이 = 그 덩어리 카메라의 학습 MVS 깊이 지도를 화소 격자로 이은 메시.", "",
         "| 경우 | 넓이 (m²) | 패치 | 참값 점 | 행 | 여러 층 패치 (몫) | 사전 정보 거리 (cm) | 영상 깊이 거리 (cm) | 카메라 | 고름 |", "|---|---:|---:|---:|---:|---|---:|---:|---|---|"]
    for r in sorted(rows, key=lambda r: (-int(r["cond1"]), -r["gt_points"])):
        tag = ""
        if chosen and r is chosen["main"]:
            tag = "그림"
        elif chosen and chosen["auxiliary"] is not None and r is chosen["auxiliary"]:
            tag = "보조"
        site, prior = r["site"], r["prior"]
        L.append(f"| {SITE_KO[site]} · {'LoD2' if prior == 'LoD2' else '항공 LiDAR'} | {r['area_m2']:.2f} | {r['patches']} | {r['gt_points']:,} | {r['rows']:,} | "
                 f"{r['multi_layer_patches']} ({100 * r['multi_layer_share']:.0f} %) | {'—' if r['prior_dist_cm'] is None else r['prior_dist_cm']} | "
                 f"{'—' if r.get('image_dist_cm') is None else r['image_dist_cm']} | {(r.get('camera') or {}).get('view', '—')} | {tag} |")
    L += ["", f"- 고른 단계: {chosen['tier'] if chosen else '없음'}. 조건을 다 맞춘 덩어리 {chosen['passing'] if chosen else 0}개.",
          "- 영상 깊이 거리는 조건 1과 넓힌 조건 3(10 cm)을 맞춘 덩어리에서만 구했다('—'는 구하지 않음)."]
    (DOCS / "tables/V5_candidates.md").write_text("\n".join(L) + "\n")
    log("chosen", None if not chosen else (chosen["tier"], chosen["main"]["case"], chosen["main"]["patches"], chosen["main"]["gt_points"]))


if __name__ == "__main__":
    main()
