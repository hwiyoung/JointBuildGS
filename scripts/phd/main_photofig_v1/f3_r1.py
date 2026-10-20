"""PHD-MAIN-PHOTOFIG-v1 figure 3: R1 missing region. Did 결측 지키기 fill the missing patches of the R1 wall, and where did the old shape
stay? (jointbuildgs:dev, CPU)

  python f3_r1.py <key>      key = fig3 (R1 LoD2 wall 19) | fig3_extra (R1 LoD2 wall 49, the most prior-error missing patches) |
                                   fig3b (R1 항공 LiDAR face 7; needs fixAB_ALS_s0)
  -> /docs/figures/photo_<key>_r1.png|pdf|json, /docs/tables/<key>_r1.md|json

Per missing patch: sapr = prior right (code 4): coloured blue when >= half of its GT rows (dist71 rows of place 결측 영역, r_place bit c4)
are within 0.2 m of the result; prior wrong (code 13): red outline, filled red when >= half of its metric rows (S1/defs rows: code 13,
thinned, |s_W| >= 0.2 m) carry the result's past-shape class (metrics rows 'cls' 1 or 2 = wrong side or both; fixtest area_b.py rule).
Section: horizontal band at the place's z (walls) or vertical along the long axis (roofs), 0.5 m; TSDF meshes cut by the plane.
[이 발주에서 냄] scientific_verdict: null"""
import sys
import time

import numpy as np
from matplotlib.collections import LineCollection

import pf_geo as G
from pf_common import DOCS, FT, PF, S0, S1, S2, S3, SD, cfg, jdump, log, now

SITE = "R1rep_b10"
RESULTS = {"LoD2": {"지금 방법 씨앗 0": ("S1", "prop_LoD2_s0"), "지금 방법 씨앗 1": ("S1", "prop_LoD2_s1"), "결측 지키기": ("FT", "fixB_LoD2_s0"),
                    "판정만 끈 방법": ("S3", "nojudge_LoD2_s0")},
           "ALS": {"지금 방법 씨앗 0": ("S1", "prop_ALS_s0"), "지금 방법 씨앗 1": ("S1", "prop_ALS_s1"), "결측 지키기": ("FT", "fixB_ALS_s0"),
                   "결측 지키기 다시 돌림": ("FT", "fixAB_ALS_s0")}}
BASE = {"S1": S1 / "stage1" / SITE, "FT": FT / "runs" / SITE, "S3": S3 / "runs" / SITE}
COL = {"지금 방법 씨앗 0": "#ff7f0e", "지금 방법 씨앗 1": "#fdbf6f", "결측 지키기": "#1f77b4", "판정만 끈 방법": "#bdbdbd", "결측 지키기 다시 돌림": "#9ecae1"}
BIT_C4 = 1 << 3          # dist71 PLACES[1:] = (c11, img, c2, c4, c5, c11s)


def dist_file(prior, res):
    for b in (FT / "dist", SD / "dist"):
        f = b / f"{SITE}_{prior}__{res}.npz"
        if f.exists():
            return f
    return None


def rows_file(prior, res):
    for b in (FT / "metrics", S3 / "metrics", S1 / "metrics", S2 / "metrics"):
        f = b / SITE / f"{res}__{prior}_rows.npz"
        if f.exists():
            return f
    return None


def main(key):
    t0 = time.time()
    C = cfg()
    P = C["places"][key] if key in C["places"] else G.jl(PF / "prep/places_after.json")[key]   # fig3_extra2: [결과를 본 뒤 더함]
    prior = P["prior"]
    R = np.load(S1 / "regions_v3" / f"regions_ext_v3_{SITE}_{prior}.npz")
    U = np.load(S0 / "s61/box" / SITE / prior / "units.npz")
    code = R["code_ext_v3"].astype(int); ev = R["in_eval"].astype(bool); se = R["surf_ext"].astype(int)
    face = P["ext"]
    mp = np.nonzero(ev & (se == face) & np.isin(code, [4, 13]))[0]
    res = {k: v for k, v in RESULTS[prior].items() if (BASE[v[0]] / v[1] / "post/mesh_tsdf.ply").exists() and dist_file(prior, v[1])}
    missing_res = [k for k in RESULTS[prior] if k not in res]
    rows = np.load(S1 / "defs" / SITE / f"rows_{prior}.npz")
    sel13 = (rows["code"] == 13) & rows["thin"].astype(bool) & (np.abs(rows["sW"].astype(np.float64)) >= 0.2)
    per = {}
    for k, (b, r) in res.items():
        d = np.load(dist_file(prior, r))
        c4 = (d["r_place"] & BIT_C4) > 0
        pa = d["r_patch"].astype(np.int64); ok = d["r_d"] <= 0.2
        n4 = np.bincount(pa[c4], minlength=len(code)); w4 = np.bincount(pa[c4], weights=ok[c4].astype(float), minlength=len(code))
        rf = rows_file(prior, r)
        if rf is not None:
            cls = np.load(rf)["cls"][sel13]
            p13 = rows["patch"][sel13].astype(np.int64)
            n13 = np.bincount(p13, minlength=len(code)); i13 = np.bincount(p13, weights=np.isin(cls, (1, 2)).astype(float), minlength=len(code))
        else:
            n13 = i13 = np.zeros(len(code))
        face_m = np.zeros(len(code), bool); face_m[mp] = True
        fr4 = face_m[pa] & c4
        p13m = face_m[rows["patch"][sel13].astype(np.int64)] if rf is not None else np.zeros(0, bool)
        sgn = d["r_d"].astype(np.float64) * np.where(d["r_sign"] == 0, 1, d["r_sign"])
        fr_all = face_m[pa]
        per[k] = dict(r02_face=float(ok[fr4].mean()) if fr4.any() else None, rows_c4_face=int(fr4.sum()),
                      signed_median_face_m=float(np.median(sgn[fr_all])) if fr_all.any() else None, rows_face=int(fr_all.sum()),
                      r02_unit=float(ok[c4].mean()) if c4.any() else None, rows_c4_unit=int(c4.sum()),
                      inflow_face=float(np.isin(cls, (1, 2))[p13m].mean()) if (rf is not None and p13m.any()) else None, rows_c13_face=int(p13m.sum()),
                      inflow_unit=float(np.isin(cls, (1, 2)).mean()) if rf is not None else None, rows_c13_unit=int(len(cls)) if rf is not None else 0,
                      patch_r02={int(p): float(w4[p] / n4[p]) for p in mp if code[p] == 4 and n4[p] > 0},
                      patch_inflow={int(p): float(i13[p] / n13[p]) for p in mp if code[p] == 13 and n13[p] > 0},
                      patches_within_0_2=int(sum(1 for p in mp if code[p] == 4 and n4[p] > 0 and w4[p] / n4[p] >= 0.5)),
                      patches_old_shape=int(sum(1 for p in mp if code[p] == 13 and n13[p] > 0 and i13[p] / n13[p] >= 0.5)),
                      dist=str(dist_file(prior, r)), rows=str(rf))
        log(k, {kk: per[k][kk] for kk in ("r02_face", "inflow_face", "r02_unit", "inflow_unit")})
    # photo
    view = P["photo"]["view"]
    lm = G.export(SITE, prior, "locmap", view)
    pts = U["loc_center"][mp].astype(np.float64)
    u, v, z = G.project(view, pts)
    ins = (z > 0) & (u >= 0) & (u < 1024) & (v >= 0) & (v < 741)
    x0, x1 = int(max(u[ins].min() - 30, 0)), int(min(u[ins].max() + 30, 1024)); y0, y1 = int(max(v[ins].min() - 30, 0)), int(min(v[ins].max() + 30, 741))
    im = G.image(SITE, view)[y0:y1, x0:x1]
    from PIL import Image
    (DOCS / "figures/crops").mkdir(exist_ok=True)
    Image.fromarray(im).save(DOCS / "figures/crops" / f"photo_{key}_{view}_{x0}_{y0}_{x1}_{y1}.png")
    lmc = lm[y0:y1, x0:x1]
    # section
    sec = P["section"]; c = np.asarray(sec["centre_xy"]); a = np.asarray(sec["axis_xy"]); sr = sec["s_range_m"]
    xy = U["loc_center"][mp][:, :2]
    xb = [float(xy[:, 0].min() - 3), float(xy[:, 1].min() - 3), float(xy[:, 0].max() + 3), float(xy[:, 1].max() + 3)]
    segs = {}
    for k, (b, r) in res.items():
        V, F, info = G.read_ply_mesh_box(BASE[b] / r / "post/mesh_tsdf.ply", xb, margin=5.0)
        segs[k] = G.cut_horizontal(V, F, sec["z_m"], c, a, sr) if sec["kind"] == "horizontal" else G.cut_vertical(V, F, c, a, sr)
        log("mesh", k, info)
    Vp, Fp = G.prior_mesh(SITE, prior)
    seg_p = G.cut_horizontal(Vp, Fp, sec["z_m"], c, a, sr) if sec["kind"] == "horizontal" else G.cut_vertical(Vp, Fp, c, a, sr)
    Xg, _, _ = G.gt_points(SITE, xb, margin=2.0)
    nrm = np.array([-a[1], a[0]])
    if sec["kind"] == "horizontal":
        mg = (np.abs(Xg[:, 2] - sec["z_m"]) <= 0.25)
        sg = (Xg[:, :2] - c) @ a; dg = (Xg[:, :2] - c) @ nrm
        mg &= (sg >= sr[0]) & (sg <= sr[1]) & (np.abs(dg) <= 3.0)
        gt_xy = np.column_stack([sg[mg], dg[mg]])
    else:
        mg, sg = G.band(Xg, c, a, sr); gt_xy = np.column_stack([sg[mg], Xg[mg, 2]])
    train = G.jl(S0 / "fork_inputs/s61" / SITE / "split.json")["train"]
    AP = []
    for n in train:
        l2 = G.export(SITE, prior, "locmap", n)
        mk = np.isin(l2, mp)
        if not mk.any():
            continue
        cf = G.export(SITE, prior, "conf", n) > 0.5
        X, _, _ = G.backproject(n, G.export(SITE, prior, "mvs", n), mk & cf)
        if not len(X):
            continue
        if sec["kind"] == "horizontal":
            s_ = (X[:, :2] - c) @ a; d_ = (X[:, :2] - c) @ nrm
            m_ = (np.abs(X[:, 2] - sec["z_m"]) <= 0.25) & (s_ >= sr[0]) & (s_ <= sr[1]) & (np.abs(d_) <= 3.0)
            AP.append(np.column_stack([s_[m_], d_[m_]]))
        else:
            b_, s_ = G.band(X, c, a, sr); AP.append(np.column_stack([s_[b_], X[b_, 2]]))
    AP = np.concatenate(AP) if AP else np.zeros((0, 2))
    # draw
    plt = G.setup_plt()
    fig = plt.figure(figsize=(15, 13))
    gs = fig.add_gridspec(2, 2, height_ratios=[1.0, 0.9], hspace=0.16, wspace=0.04)
    if im.shape[0] > 1.5 * im.shape[1]:
        plt.close(fig)
    show = [k for k in ("지금 방법 씨앗 0", "결측 지키기") if k in res]
    c4p = [int(p) for p in mp if code[p] == 4]; c13p = [int(p) for p in mp if code[p] == 13]
    rot = im.shape[0] > 1.5 * im.shape[1]          # [그리는 법만 바꿈] a tall crop is shown turned 90 deg (left = image top)
    R90 = (lambda a_: np.rot90(a_)) if rot else (lambda a_: a_)
    if rot:
        fig = plt.figure(figsize=(15, 15))
        gs = fig.add_gridspec(3, 1, height_ratios=[0.5, 0.5, 0.9], hspace=0.16)
    for col, k in enumerate(show):
        ax = fig.add_subplot(gs[col, 0] if rot else gs[0, col])
        ax.imshow(R90(im), interpolation="nearest")
        blue = [p for p in c4p if per[k]["patch_r02"].get(p, 0) >= 0.5]
        red = [p for p in c13p if per[k]["patch_inflow"].get(p, 0) >= 0.5]
        if blue:
            ax.contourf(R90(np.isin(lmc, blue).astype(float)), levels=[0.5, 1.5], colors=["#1f77b4"], alpha=0.55)
        if c4p:
            ax.contour(R90(np.isin(lmc, c4p).astype(float)), levels=[0.5], colors=["#1f77b4"], linewidths=0.8)
        if red:
            ax.contourf(R90(np.isin(lmc, red).astype(float)), levels=[0.5, 1.5], colors=["#d62728"], alpha=0.6)
        if c13p:
            ax.contour(R90(np.isin(lmc, c13p).astype(float)), levels=[0.5], colors=["#d62728"], linewidths=1.6)
        lab = "(가)" if col == 0 else "(나)"
        ax.text(0.02, 0.98, f"{lab} {k}\n사전 정보가 맞는 결측 {len(c4p)} 가운데 0.2 m 안 {per[k]['patches_within_0_2']} (파랑 칠)\n사전 정보가 틀린 결측 {len(c13p)} 가운데 옛 모양 {per[k]['patches_old_shape']} (빨강 칠)",
                transform=ax.transAxes, va="top", fontsize=9, bbox=dict(fc="w", ec="none", alpha=0.85))
        ax.set_xticks([]); ax.set_yticks([])
    ax = fig.add_subplot(gs[2, 0] if rot else gs[1, :])
    ax.add_collection(LineCollection(seg_p, colors="#7f7f7f", linewidths=2.2, zorder=2))
    if len(AP):
        ax.plot(AP[:, 0], AP[:, 1], "o", color="#8c564b", ms=1.6, alpha=0.4, zorder=2)
    ax.plot(gt_xy[:, 0], gt_xy[:, 1], ".", color="#000000", ms=1.2, zorder=3)
    for k, sgm in segs.items():
        ax.add_collection(LineCollection(sgm, colors=COL[k], linewidths=1.6 if k not in ("판정만 끈 방법", "지금 방법 씨앗 1") else 1.2,
                                         linestyles="--" if k in ("지금 방법 씨앗 1", "결측 지키기 다시 돌림") else "-", zorder=4 if k != "판정만 끈 방법" else 3))
    sp = (U["loc_center"][mp][:, :2] - c) @ (a / np.linalg.norm(a))
    ax.set_xlim(max(sr[0], sp.min() - 2.0), min(sr[1], sp.max() + 2.0))   # [그리는 법만 바꿈] the missing patches' extent + 2 m (the band is unchanged)
    if sec["kind"] == "horizontal":
        ax.set_ylim(-2.0, 2.0); ax.set_ylabel("벽에서 바깥으로 (m)"); ax.set_xlabel(f"벽을 따라 (m), 높이 {sec['z_m']:.1f} m의 수평 단면")
    else:
        zs = [np.nanpercentile(gt_xy[:, 1], 1), np.nanpercentile(gt_xy[:, 1], 99)]
        if len(seg_p):
            zs += [np.nanmin(seg_p[:, :, 1]), np.nanmax(seg_p[:, :, 1])]
        ax.set_ylim(min(zs) - 0.3, max(zs) + 0.3); ax.set_ylabel("높이 (m)"); ax.set_xlabel("긴 축을 따라 (m)")   # [그리는 법만 바꿈] the prior is kept in view
    pname = "LoD2" if prior == "LoD2" else "항공 LiDAR"
    txt = [("검정 점: 참값", "#000000"), (f"회색: {pname}", "#7f7f7f"), ("갈색 점: 영상 깊이(통과)", "#8c564b")] + [(k + (" (점선)" if k in ("지금 방법 씨앗 1", "결측 지키기 다시 돌림") else ""), COL[k]) for k in segs]
    for i, (t, col) in enumerate(txt):
        ax.text(0.01 + 0.135 * i, 0.97, t, transform=ax.transAxes, color=col, fontsize=8.5, va="top")
    ax.text(0.01, 0.05, f"(다) 단면(폭 0.5 m). 결과 면 = 지표와 같은 TSDF 메시", transform=ax.transAxes, fontsize=9, bbox=dict(fc="w", ec="none", alpha=0.8))
    G.locator(fig, SITE, np.asarray(c), rect=(0.86, 0.92, 0.1, 0.06))
    def f(x):
        return "—" if x is None else f"{x*100:.1f} %"
    line = " · ".join(f"{k}: 이 면의 결측 R(0.2 m) {f(per[k]['r02_face'])} ({per[k]['rows_c4_face']}행), 유입률 {f(per[k]['inflow_face'])} ({per[k]['rows_c13_face']}행); 단위 전체 {f(per[k]['r02_unit'])} · {f(per[k]['inflow_unit'])}" for k in res)
    title = {"fig3": "결측 지키기가 R1 벽의 결측 패치를 채웠는가, 옛 모양은 어디에 남았나", "fig3_extra": "결측 지키기가 R1 벽의 결측 패치를 채웠는가, 옛 모양은 어디에 남았나 — 사전 정보가 틀린 결측이 가장 많은 벽면",
             "fig3b": "절단을 풀자 사전 정보가 결과 면을 끌어 내렸는가",
             "fig3_extra2": "결측 지키기가 R1 벽의 결측 패치를 채웠는가, 옛 모양은 어디에 남았나 — 사전 정보가 틀린 결측이 가장 많은 면(지붕 포함, 결과를 본 뒤 더함)"}[key]
    fig.suptitle(title, fontsize=14, y=0.995)
    fig.text(0.01, 0.004, line.replace("R(0.2 m)", "재현율(0.2 m)"), fontsize=8, wrap=True)
    for ext in ("png", "pdf"):
        fig.savefig(DOCS / "figures" / f"photo_{key}_r1.{ext}", dpi=150, bbox_inches="tight")
    plt.close(fig)
    out = dict(key=key, site=SITE, prior=prior, face=face, missing_patches=int(len(mp)), code4=len(c4p), code13=len(c13p), photo=view, crop_px=[x0, y0, x1, y1],
               results={k: {kk: vv for kk, vv in per[k].items() if kk not in ("patch_r02", "patch_inflow")} for k in res}, missing_results=missing_res,
               per_patch={k: dict(r02=per[k]["patch_r02"], inflow=per[k]["patch_inflow"]) for k in res}, section=dict(gt=int(len(gt_xy)), mvs=int(len(AP)), segments={k: int(len(v)) for k, v in segs.items()}),
               numbers_line=line, seconds=round(time.time() - t0, 1), made=now(), scientific_verdict=None)
    jdump(DOCS / "tables" / f"{key}_r1.json", out)
    jdump(DOCS / "figures" / f"photo_{key}_r1.json", dict(title=title, numbers_line=line, crop=dict(view=view, box_px=[x0, y0, x1, y1]), made=now(), scientific_verdict=None))
    L = [f"# {title} — 숫자 [이 발주에서 냄]", "", f"- R1 · {pname}, 면 {face}: 결측 패치 {len(mp)} (사전 정보가 맞는 {len(c4p)}, 틀린 {len(c13p)}). 사진 {view}.", "",
         "| 결과 | 이 면 결측 재현율(0.2 m) (행) | 이 면 과거 형상 유입률 (행) | 0.2 m 안 패치 | 옛 모양 패치 | 이 면 결측 패치의 결과 − 참값 중앙값 (행) | 단위 전체 재현율 (행) | 단위 전체 유입률 (행) |", "|---|---|---|---:|---:|---|---|---|"]
    for k in res:
        q = per[k]
        sm = "—" if q["signed_median_face_m"] is None else f"{q['signed_median_face_m']*100:+.1f} cm"
        L.append(f"| {k} | {f(q['r02_face'])} ({q['rows_c4_face']:,}) | {f(q['inflow_face'])} ({q['rows_c13_face']:,}) | {q['patches_within_0_2']} / {len(c4p)} | {q['patches_old_shape']} / {len(c13p)} | {sm} ({q['rows_face']:,}) | {f(q['r02_unit'])} ({q['rows_c4_unit']:,}) | {f(q['inflow_unit'])} ({q['rows_c13_unit']:,}) |")
    if missing_res:
        L.append(f"\n- 아직 없는 결과(메시나 거리 파일 없음): {', '.join(missing_res)}")
    (DOCS / "tables" / f"{key}_r1.md").write_text("\n".join(L) + "\n")
    log("done", out["seconds"])


if __name__ == "__main__":
    main(sys.argv[1])
