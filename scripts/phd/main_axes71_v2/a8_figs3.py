"""PHD-MAIN-AXES71-v2 일 8 (11.2): V3, V5, V6 drawn again as distributions and sections (jointbuildgs:dev, CPU; no render, no GPU).

  python a8_figs3.py [V3 V5 V6]   -> /docs/figures/일8_<V>.png|pdf|json, AX/work/figs3_<V>.npz

Places and region rows: v4's (configs/phd/main_viscmp_v4/places_v4.json; V3 = the fix test's figure-1 rows of face 1, as v4 f4_fig.py).
Results (config figs3.results): 학습 전 사전 정보, GeoGS, MVS (v4's one-image depth-map mesh: S0/fork_inputs/s61/<site>/maps/mvs/<depth view>.npy,
vd_dist.depth_mesh, cut to the place box), 2DGS, 결합, CDGS*, 본 방법 (seed 0; seed 1 in json). Signed d_g of the place rows: the stored
per-point files (vd_dist.Case.stored); the MVS mesh: vd_dist.Case.dg_rows (the distance task's rule). Under each figure: 참값 기준 재현율 R(τ),
참값 기준 평균 거리, 치우침 (median signed d_g).
V3, V5: (가) the density of signed d_g, one line per result, x -0.3~+0.3 m, the peak of each line written as a number (cm);
(나) one vertical section: GT points within +-0.10 m of the section plane and per result the line of the median height of its result points
within +-0.05 m of the plane in 0.10 m bins along the section (results from the result samples, AX/dist/<site>__<res>__xyz.npy; MVS: the
sample of its mesh). V3: across the face (the minor principal axis of the place's patch centres), V5: across the glass vault (perpendicular to
the long axis of v4 V6's glass patches), both through the place centre.
V6: the band (glass 163 + rim missing 18 patches) seen from above, one small map per result, each patch coloured by the median signed d_g
of its rows (range +-1 m, diverging), the rim missing patches with a thick outline. Titles: from the place's numbers (v4 title form).
[이 발주에서 냄] scientific_verdict: null."""
import sys

sys.path.insert(0, "/repo/scripts/phd/main_viscmp_v4")
import numpy as np  # noqa: E402
from matplotlib import colors as mcolors  # noqa: E402
from scipy.stats import gaussian_kde  # noqa: E402

import vc_common  # noqa: F401,E402
import vd_dist as VD  # noqa: E402
import ax_map as MP  # noqa: E402
from ax_common import CFG, DIST, DOCS, FT, RES_KO, WORK, jdump, jl, log, now, results_of  # noqa: E402
from dm_common import result_sample  # noqa: E402

PLACES = "/repo/configs/phd/main_viscmp_v4/places_v4.json"
ST = CFG["results"]["style"]
KEYS = ["prior", "geogs", "mvs1", "twodgs", "mvsfuse", "cdgs", "method"]


def ko(k):
    return "MVS" if k == "mvs1" else RES_KO[k]


def gather(key):
    P = jl(PLACES)[key]
    site, prior = P["site"], P["prior"]
    case = VD.Case(site, prior)
    place = np.asarray(P["place"], int)
    rows = case.rows_of(place)
    if key == "V3":
        rf = np.load(FT / "prep/figpos_fig1_rows.npz")["rows"]
        pos = np.searchsorted(case.u.rows_idx, rf)
        rows = pos[(pos < len(case.u.rows_idx)) & (case.u.rows_idx[np.minimum(pos, len(case.u.rows_idx) - 1)] == rf)]
    tau = case.u.r_tau[rows]
    cen = case.u.centre
    xy = cen[place][:, :2]
    box = [xy[:, 0].min() - 3, xy[:, 1].min() - 3, xy[:, 0].max() + 3, xy[:, 1].max() + 3]
    out = dict(site=site, prior=prior, rows=rows, tau=tau, d={}, smp={}, src={})
    for k in KEYS + ["method_s1"]:
        if k == "mvs1":
            dv = P["depth_view"]["view"]
            dep = np.load(f"/s0/fork_inputs/s61/{site}/maps/mvs/{dv}.npy")
            V, F, info = VD.depth_mesh(dv, dep)
            kv = (V[:, 0] >= box[0]) & (V[:, 0] <= box[2]) & (V[:, 1] >= box[1]) & (V[:, 1] <= box[3])
            F = F[kv[F].all(1)]
            out["d"][k] = case.dg_rows(V, F, rows)
            out["smp"][k] = result_sample(V, F, case.gt).astype(np.float32)
            out["src"][k] = dict(result="한 장짜리 MVS 깊이 지도 메시 (v4와 같음)", view=dv, mesh=info)
            continue
        res = results_of("method", prior)[1] if k == "method_s1" else results_of(k, prior)[0]
        st = case.stored(res)
        if st is None:
            out["src"][k] = dict(result=res, status="결과 없음")
            continue
        out["d"][k] = st["rows"][rows]
        X = np.load(DIST / f"{site}__{res}__xyz.npy")
        m = (X[:, 0] >= box[0]) & (X[:, 0] <= box[2]) & (X[:, 1] >= box[1]) & (X[:, 1] <= box[3])
        out["smp"][k] = X[m]
        out["src"][k] = dict(result=res, file=st["file"])
    out["gt"] = case.gt.Gb[case.scene_in_box(box)].astype(np.float32)
    out["P"] = P
    out["place"] = place
    out["centres"] = cen
    out["case"] = case
    return out


def vals(d, tau):
    a = np.abs(d)
    return dict(n=int(len(d)), R_tau=float((a <= tau).mean()), mean_cm=float(a.mean() * 100), med_cm=float(np.median(a) * 100), bias_cm=float(np.median(d) * 100))


def peak(d):
    x = np.linspace(-0.3, 0.3, 601)
    dd = d[(d > -0.6) & (d < 0.6)]
    if len(dd) < 10:
        return x, np.zeros_like(x), None
    k = gaussian_kde(dd, bw_method=0.15)(x)
    return x, k, float(x[np.argmax(k)])


def section_axis(key, g):
    cen = g["centres"]
    if key == "V5":
        glass = np.asarray(jl(PLACES)["V6"]["glass"], int)
        xy = cen[glass][:, :2]
        w, v = np.linalg.eigh(np.cov((xy - xy.mean(0)).T))
        along = v[:, 0]                        # perpendicular to the vault's long axis
    else:
        xy = cen[g["place"]][:, :2]
        w, v = np.linalg.eigh(np.cov((xy - xy.mean(0)).T))
        along = v[:, 0]                        # the minor axis: across the face
    c = cen[g["place"]][:, :2].mean(0)
    return c, along / np.linalg.norm(along)


def section_lines(g, c, along):
    nrm = np.array([-along[1], along[0]])
    out = {}
    G = g["gt"].astype(np.float64)
    sg = (G[:, :2] - c) @ along
    og = np.abs((G[:, :2] - c) @ nrm)
    xy = g["centres"][g["place"]][:, :2]
    s_place = (xy - c) @ along
    lo, hi = s_place.min() - 2.0, s_place.max() + 2.0
    mg = (og < 0.10) & (sg >= lo) & (sg <= hi)
    out["gt"] = np.c_[sg[mg], G[mg, 2]]
    bins = np.arange(lo, hi + 0.1, 0.1)
    for k, X in g["smp"].items():
        X = X.astype(np.float64)
        s = (X[:, :2] - c) @ along
        o = np.abs((X[:, :2] - c) @ nrm)
        m = (o < 0.05) & (s >= lo) & (s <= hi)
        idx = np.digitize(s[m], bins)
        z = X[m, 2]
        line = [(0.5 * (bins[i - 1] + bins[i]), float(np.median(z[idx == i]))) for i in range(1, len(bins)) if (idx == i).sum() >= 3]
        out[k] = np.asarray(line) if line else np.zeros((0, 2))
    return out, (lo, hi)


def fig_dist_section(plt, key, g, title):
    tau = g["tau"]
    fig, axs = plt.subplots(1, 2, figsize=(17 / 2.54, 7.5 / 2.54), gridspec_kw=dict(width_ratios=[1, 1.25]))
    rec = {}
    ax = axs[0]
    for k in KEYS:
        if k not in g["d"]:
            continue
        x, y, pk = peak(g["d"][k])
        s = ST["mvs" if k == "mvs1" else k]
        ax.plot(x * 100, y, color=s["color"], ls=s["ls"], lw=s["lw"] * 0.8, label=ko(k))
        rec[k] = dict(vals(g["d"][k], tau), peak_cm=None if pk is None else 100 * pk)
        if pk is not None:
            ax.annotate(f"{100 * pk:+.0f}", (100 * pk, y.max()), fontsize=5.5, color=s["color"], ha="center", va="bottom")
    ax.axvline(0, color="#888888", lw=0.6, ls=":")
    ax.set_xlim(-30, 30); ax.set_xlabel("부호 있는 d_g (cm)", fontsize=6); ax.set_ylabel("밀도", fontsize=6); ax.set_yticks([])
    ax.tick_params(labelsize=5.5, length=2)
    for sp in ("top", "right"):
        ax.spines[sp].set_visible(False)
    ax.set_title("(가) 참값 점마다 부호 있는 거리의 분포", fontsize=6.5)
    c, along = section_axis(key, g)
    L, (lo, hi) = section_lines(g, c, along)
    ax = axs[1]
    ax.scatter(L["gt"][:, 0], L["gt"][:, 1], s=0.5, c="k", lw=0, label="참값 점", rasterized=True)
    for k in KEYS:
        if k not in L or not len(L[k]):
            continue
        s = ST["mvs" if k == "mvs1" else k]
        ax.plot(L[k][:, 0], L[k][:, 1], color=s["color"], ls=s["ls"], lw=s["lw"] * 0.7)
    zz = np.concatenate([L["gt"][:, 1]] + [L[k][:, 1] for k in KEYS if k in L and len(L[k])])
    zlo, zhi = np.percentile(zz, 1), np.percentile(zz, 99)
    ax.set_ylim(zlo - 0.5, zhi + 0.5)
    ax.set_xlabel("단면을 따라 (m)", fontsize=6); ax.set_ylabel("높이 (m)", fontsize=6)
    ax.tick_params(labelsize=5.5, length=2)
    for sp in ("top", "right"):
        ax.spines[sp].set_visible(False)
    ax.set_title("(나) 연직 단면: 참값 점과 결과마다 면의 높이", fontsize=6.5)
    from matplotlib.lines import Line2D
    hs = [Line2D([0], [0], color=ST["mvs" if k == "mvs1" else k]["color"], ls=ST["mvs" if k == "mvs1" else k]["ls"], lw=1.2, label=ko(k)) for k in KEYS if k in g["d"]]
    hs.append(Line2D([0], [0], marker="o", ls="none", color="k", ms=2, label="참값 점"))
    fig.legend(handles=hs, loc="lower center", ncol=8, fontsize=5.5, frameon=False, bbox_to_anchor=(0.5, 0.0))
    txt = "   ".join(f"{ko(k)} {100 * v['R_tau']:.1f} · {v['mean_cm']:.1f} · {v['bias_cm']:+.1f}" for k, v in rec.items())
    fig.text(0.5, 0.075, "R(τ) % · 참값 기준 평균 거리 cm · 치우침 cm — " + txt, ha="center", fontsize=5, wrap=True)
    fig.suptitle(title, fontsize=7)
    fig.tight_layout(rect=(0, 0.11, 1, 0.94))
    return fig, rec, dict(centre=c.tolist(), along=along.tolist(), range_m=[lo, hi], slab_gt_m=0.10, slab_result_m=0.05, bin_m=0.10)


def fig_v6(plt, g, title):
    P = jl(PLACES)["V6"]
    glass, rim = np.asarray(P["glass"], int), np.asarray(P["ring_missing"], int)
    band = np.r_[glass, rim]
    case = g["case"]
    rp = case.u.r_pa[g["rows"]]
    norm = mcolors.Normalize(-1.0, 1.0, clip=True)
    cmap = plt.get_cmap("RdBu_r")
    ks = [k for k in KEYS if k in g["d"]]
    fig, axs = plt.subplots(1, len(ks), figsize=(17 / 2.54, 6.2 / 2.54))
    rec = {}
    U = np.load(MP.S0U.format(site=g["site"], prior=g["prior"]))
    for ax, k in zip(axs, ks):
        d = g["d"][k]
        med = {}
        for p in band:
            m = rp == p
            med[int(p)] = float(np.median(d[m])) if m.any() else np.nan
        for p in band:
            c = U["loc_center"][p]; t1 = U["loc_t1"][p] * 0.125; t2 = U["loc_t2"][p] * 0.125
            q = np.array([c + t1 + t2, c + t1 - t2, c - t1 - t2, c - t1 + t2])[:, :2]
            v = med[int(p)]
            fc = "#dddddd" if not np.isfinite(v) else cmap(norm(v))
            ax.fill(q[:, 0], q[:, 1], color=fc, lw=1.2 if p in rim else 0.0, ec="k" if p in rim else fc, zorder=3 if p in rim else 2)
        ax.set_aspect("equal"); ax.set_axis_off()
        dd = d
        rec[k] = dict(vals(dd, g["tau"]), glass=vals(d[np.isin(rp, glass)], g["tau"][np.isin(rp, glass)]) if np.isin(rp, glass).any() else None,
                      rim=vals(d[np.isin(rp, rim)], g["tau"][np.isin(rp, rim)]) if np.isin(rp, rim).any() else None)
        ax.set_title(ko(k), fontsize=6)
        ax.text(0.5, -0.04, f"{100 * rec[k]['R_tau']:.1f} · {rec[k]['mean_cm']:.1f} · {rec[k]['bias_cm']:+.1f}", transform=ax.transAxes, ha="center", va="top", fontsize=5)
    sm = plt.cm.ScalarMappable(norm=norm, cmap=cmap)
    cb = fig.colorbar(sm, ax=list(axs), orientation="horizontal", fraction=0.05, pad=0.12, aspect=40)
    cb.set_label("패치마다 부호 있는 d_g의 중앙값 (m); 굵은 테두리 = 둘레 결측 패치", fontsize=5.5); cb.ax.tick_params(labelsize=5)
    fig.text(0.5, 0.02, "칸 아래: R(τ) % · 참값 기준 평균 거리 cm · 치우침 cm", ha="center", fontsize=5)
    fig.suptitle(title, fontsize=7)
    return fig, rec


def title_of(key, rec):
    def pk(k):
        return rec.get(k, {}).get("peak_cm")
    if key == "V3":
        return (f"두 자료가 모두 맞는 이 평평한 지붕에서 거리 분포의 봉우리는 학습 전 사전 정보 {pk('prior'):+.0f} cm, 결합 {pk('mvsfuse'):+.0f} cm, "
                f"본 방법 {pk('method'):+.0f} cm, MVS {pk('mvs1'):+.0f} cm")
    if key == "V5":
        return (f"영상이 틀린 이 유리 지붕 조각에서 본 방법의 치우침은 {rec['method']['bias_cm']:+.0f} cm, 학습 전 사전 정보 {rec['prior']['bias_cm']:+.0f} cm, "
                f"GeoGS {rec['geogs']['bias_cm']:+.0f} cm")
    r = rec["method"]
    return (f"판단할 수 없는 유리 띠: 본 방법은 유리에서 {r['glass']['bias_cm']:+.0f} cm, 둘레 결측에서 {r['rim']['bias_cm']:+.0f} cm 치우침"
            if r.get("glass") and r.get("rim") else "판단할 수 없는 유리 띠")


def main(keys):
    plt = MP.setup_plt()
    for key in keys:
        g = gather(key)
        if key in ("V3", "V5"):
            tmp = {k: dict(vals(g["d"][k], g["tau"]), peak_cm=None if peak(g["d"][k])[2] is None else 100 * peak(g["d"][k])[2]) for k in KEYS if k in g["d"]}
            title = title_of(key, tmp)
            fig, rec, sec = fig_dist_section(plt, key, g, title)
        else:
            tmp = None
            fig, rec = fig_v6(plt, g, "V6")
            title = title_of(key, rec)
            fig.suptitle(title, fontsize=7)
            sec = None
        stem = DOCS / "figures" / f"일8_{key}"
        for e in ("png", "pdf"):
            fig.savefig(f"{stem}.{e}", dpi=300)
        plt.close(fig)
        s1 = vals(g["d"]["method_s1"], g["tau"]) if "method_s1" in g["d"] else None
        jdump(f"{stem}.json", dict(task="PHD-MAIN-AXES71-v2", work=f"일 8 {key}", made=now(), title=title, rows=int(len(g["rows"])), values=rec, method_seed1=s1,
                                   section=sec, sources=g["src"], rule=__doc__.split("\n\n")[1:4], scientific_verdict=None))
        np.savez_compressed(WORK / f"figs3_{key}.npz", **{f"d_{k}": v for k, v in g["d"].items()}, rows=g["rows"], tau=g["tau"])
        log(key, title)


if __name__ == "__main__":
    main(sys.argv[1:] or ["V3", "V5", "V6"])
