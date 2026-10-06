"""PHD-MAIN-METRICS-FIX-v1 4.2: region files v2 of the four sites x two priors (jointbuildgs:dev, CPU; pre-training data only;
definitions = configs metrics_fix_v1.json 'regions_v2').

  python regions_v2.py [site ...]          default: the four sites

Per site: the box MVS (geometric depth of every view of /prep/mvs/box_<site>) back-projected with the stage-1 camera convention;
z_MVS at a GT point = median of the MVS points in its 0.1 m cell (>= 3). The points read: every GT point owned by a roof-like
patch (either prior, its label source) and every GT point in the evaluation range (for 4.6). Per prior: d = per patch the
median of z_MVS - z_GT over its GT points with a value; codes 2 / 3 and 11 / 12 of the v1 file re-split by |d| <= tau; fewer
than 5 values or wall-like -> the v1 code, flagged v1_kept.
Writes /out/regions_v2/regions_ext_v2_<site>_<prior>.npz, /out/regions_v2/mvs_at_gt_<site>.npz, moves.json / moves.md,
/out/figs/regions_v2_<site>.png. scientific_verdict: null."""
import json
import sys

import numpy as np
from matplotlib.lines import Line2D
from matplotlib.patches import Patch

from mf_common import COL, FCFG, KO, MT, NAME, ORDER, OUT, PREP, PRIOR_KO, S0, SITES, Timer, Views, boxes, in_eval_uv, jdump, label_source, log, mvs_views, owner_rows, read_depth_bin, setup_fonts, xy_to_uv
from src.phd.metrics_v2 import regions
from src.phd.metrics_v2.cells import CellMedian

plt = setup_fonts()
RV = FCFG["regions_v2"]


def mvs_at(site, xy_query, V):
    cm = CellMedian(xy_query, RV["cell_m"])
    names = mvs_views(site)
    kept = 0
    mv = PREP / "mvs" / f"box_{site}" / "stereo/depth_maps"
    for i, n in enumerate(names):
        d = read_depth_bin(mv / f"{n}.geometric.bin")
        ok = np.isfinite(d) & (d > 0)
        P = V.C(n)[None, :] + d[ok][:, None].astype(np.float64) * V.rays(n, np.float64)[ok]
        kept += cm.add(P)
    z, cnt = cm.medians(RV["cell_min_points"])
    return z, cnt, len(names), kept


def outline(ax, uv, moved, cell=0.25):
    """black outline of the area covered by the moved patches (0.25 m raster of their centres, closed by one cell)."""
    import scipy.ndimage as ndi
    if not moved.any():
        return
    lo = uv[moved].min(0) - 2 * cell
    q = np.floor((uv[moved] - lo) / cell).astype(int)
    g = np.zeros(q.max(0)[::-1] + 3, bool)
    g[q[:, 1], q[:, 0]] = True
    g = ndi.binary_closing(ndi.binary_dilation(g, iterations=1), iterations=1)
    xs = lo[0] + (np.arange(g.shape[1]) + 0.5) * cell
    ys = lo[1] + (np.arange(g.shape[0]) + 0.5) * cell
    ax.contour(xs, ys, g.astype(float), levels=[0.5], colors="k", linewidths=0.9)


def draw_maps(site):
    """the stage-0 layout (LoD2 roofs, LoD2 walls from above, ALS) of the v2 codes, the area of the moved patches outlined."""
    b = boxes()[SITES[site]]
    fig, axs = plt.subplots(1, 3, figsize=(19, 6.6), constrained_layout=True)
    for prior in ("LoD2", "ALS"):
        R = np.load(OUT / "regions_v2" / f"regions_ext_v2_{site}_{prior}.npz")
        c1, c2, kind = R["code_ext"], R["code_ext_v2"], R["kind"]
        uv = xy_to_uv(R["centre"][:, :2])
        panels = [(0, 1), (1, 2)] if prior == "LoD2" else [(2, 1)]
        for ax_i, kv in panels:
            ax = axs[ax_i]
            m = R["in_eval"] & (kind == kv)
            for c in [0, 2, 4, 5, 3, 12, 13, 14, 11]:
                mm = m & (c2 == c)
                ax.scatter(uv[mm, 0], uv[mm, 1], s=0.6 if kv == 1 else 1.6, c=COL[c], marker="s", linewidths=0, rasterized=True)
            mv = m & (c1 != c2)
            outline(ax, uv, mv)
            ax.plot([b["eval_u"][0], b["eval_u"][1], b["eval_u"][1], b["eval_u"][0], b["eval_u"][0]],
                    [b["eval_v"][0], b["eval_v"][0], b["eval_v"][1], b["eval_v"][1], b["eval_v"][0]], "k-", lw=0.8)
            ax.set_aspect("equal")
            ax.set_xlabel("u (m)")
            ax.set_ylabel("v (m)")
            title = {(0, 1): "LoD2 지붕", (1, 2): "LoD2 벽 (위에서 본 자리)", (2, 1): "항공 LiDAR"}[(ax_i, kv)]
            ax.set_title(f"{title} — v1에서 바뀐 패치 {int(mv.sum()):,}개(검은 윤곽 안)", fontsize=11)
    handles = [Patch(color=COL[c], label=KO[c]) for c in ORDER] + [Line2D([], [], color="k", lw=1, label="v1에서 바뀐 패치의 윤곽")]
    fig.legend(handles=handles, loc="lower center", ncol=5, fontsize=10, bbox_to_anchor=(0.5, -0.1))
    fig.suptitle(f"{site} 영역 v2 (지지 일치/관측 오류와 사전 정보 오류/이중 오류를 참값 점 자리의 MVS로 다시 가름; 학습 전 자료)", fontsize=12, x=0.01, ha="left")
    fig.savefig(OUT / "figs" / f"regions_v2_{site}.png", dpi=110, bbox_inches="tight")
    plt.close(fig)


def main(sites):
    T = Timer()
    O = OUT / "regions_v2"
    O.mkdir(parents=True, exist_ok=True)
    (OUT / "figs").mkdir(exist_ok=True)
    bx = boxes()
    V = Views()
    moves, md = {}, []
    for site in sites:
        b = bx[SITES[site]]
        D = S0 / "s61/box_gt" / site
        arrays = {"gt_points": np.load(D / "gt_points.npz")["xyz"].astype(np.float64)}
        if (D / "gt_primary.npz").exists():
            arrays["gt_primary"] = np.load(D / "gt_primary.npz")["xyz"].astype(np.float64)
        # the points whose MVS height is read: GT points owned by roof-like patches (both priors, label sources) + evaluation range
        need = {k: np.zeros(len(v), bool) for k, v in arrays.items()}
        rows = {}
        for prior in ("LoD2", "ALS"):
            R = np.load(MT / "regions_ext" / f"regions_ext_{site}_{prior}.npz")
            uls = label_source(site, prior, len(R["code_ext"]))
            rows[prior] = owner_rows(site, prior, uls)
            for name, pt, pa, va, kd in rows[prior]:
                need[name][pt[kd == 1]] = True
        need["gt_points"] |= in_eval_uv(arrays["gt_points"], b)
        keys = [k for k in arrays]
        idx = {k: np.nonzero(need[k])[0] for k in keys}
        xy = np.concatenate([arrays[k][idx[k], :2] for k in keys])
        z, cnt, nviews, kept = mvs_at(site, xy, V)
        out_mvs, o = {}, 0
        zfull = {}
        for k in keys:
            n = len(idx[k])
            out_mvs[f"{k}_index"] = idx[k]
            out_mvs[f"{k}_z_mvs"] = z[o:o + n].astype(np.float32)
            out_mvs[f"{k}_n"] = cnt[o:o + n].astype(np.int32)
            zf = np.full(len(arrays[k]), np.nan)
            zf[idx[k]] = z[o:o + n]
            zfull[k] = zf
            o += n
        np.savez_compressed(O / f"mvs_at_gt_{site}.npz", views=np.array(mvs_views(site)), **out_mvs)
        log(site, "MVS views", nviews, "points kept", kept, "query", len(xy), "with value", int(np.isfinite(z).sum()), T.mark(f"mvs_{site}"))
        for prior in ("LoD2", "ALS"):
            R = np.load(MT / "regions_ext" / f"regions_ext_{site}_{prior}.npz")
            n_p = len(R["code_ext"])
            pas = []
            vals = []
            for name, pt, pa, va, kd in rows[prior]:
                m = kd == 1
                vals.append(zfull[name][pt[m]] - arrays[name][pt[m], 2])
                pas.append(pa[m])
            dmed, ncnt = regions.patch_median(np.concatenate(pas), np.concatenate(vals), n_p)
            c2, kept_v1 = regions.split_v2(R["code_ext"], R["kind"], R["tau"], dmed, ncnt, RV["min_points"])
            out = {k: R[k] for k in R.files}
            out.update(code_ext_v2=c2, mvs_minus_gt_at_gt=dmed.astype(np.float32), n_mvs_at_gt=ncnt.astype(np.int32), v1_kept=kept_v1)
            np.savez_compressed(O / f"regions_ext_v2_{site}_{prior}.npz", **out)
            area = R["area"]
            c1 = R["code_ext"]
            e = {}
            for a_, b_ in ((2, 3), (3, 2), (11, 12), (12, 11)):
                m = (c1 == a_) & (c2 == b_)
                e[f"{a_}->{b_}"] = dict(patches=int(m.sum()), area_m2=round(float(area[m].sum()), 1))
            for cc in (2, 3, 11, 12):
                e[f"v1 {cc}"] = dict(patches=int((c1 == cc).sum()), area_m2=round(float(area[c1 == cc].sum()), 1))
                e[f"v2 {cc}"] = dict(patches=int((c2 == cc).sum()), area_m2=round(float(area[c2 == cc].sum()), 1))
            e["v1_kept"] = dict(patches=int(kept_v1.sum()), roof_like=int((kept_v1 & (R["kind"] == 1)).sum()), area_m2=round(float(area[kept_v1].sum()), 1))
            moves[f"{site}/{prior}"] = e
            log(site, prior, {k: v["patches"] for k, v in e.items() if "->" in k}, "kept", e["v1_kept"])
        draw_maps(site)
    prev = json.loads((O / "moves.json").read_text())["moves"] if (O / "moves.json").exists() else {}
    prev.update(moves)
    jdump(O / "moves.json", dict(rule=RV, moves=prev, seconds=T.marks, scientific_verdict=None))
    md.append("| 지역 · 사전 정보 | 지지 일치 → 관측 오류 | 관측 오류 → 지지 일치 | 사전 정보 오류 → 이중 오류 | 이중 오류 → 사전 정보 오류 | v1 그대로 둔 지붕류 패치 |")
    md.append("|---|---|---|---|---|---|")
    for k, e in prev.items():
        cells = [f"{e[t]['patches']:,} · {e[t]['area_m2']:,.0f} m²" for t in ("2->3", "3->2", "11->12", "12->11")]
        md.append(f"| {k.replace('/', ' · ')} | " + " | ".join(cells) + f" | {e['v1_kept']['roof_like']:,} |")
    md.append("")
    md.append("| 지역 · 사전 정보 | 지지 일치 v1 → v2 | 관측 오류 v1 → v2 | 사전 정보 오류 v1 → v2 | 이중 오류 v1 → v2 |")
    md.append("|---|---|---|---|---|")
    for k, e in prev.items():
        md.append(f"| {k.replace('/', ' · ')} | " + " | ".join(f"{e[f'v1 {c}']['area_m2']:,.0f} → {e[f'v2 {c}']['area_m2']:,.0f} m²" for c in (2, 3, 11, 12)) + " |")
    (O / "moves.md").write_text("\n".join(md) + "\n")
    print("regions v2 done", T.marks)


if __name__ == "__main__":
    if sys.argv[1:2] == ["--maps-only"]:
        for st in sys.argv[2:] or list(SITES):
            draw_maps(st)
    else:
        main(sys.argv[1:] or list(SITES))
