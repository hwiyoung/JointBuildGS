"""PHD-MAIN-VISCMP-v4 일 라: 정밀도 진단 그림 (request 5). Per case (config work_ra.cases): panels 학습 전 사전 정보, 결합, 본 방법 (씨앗 0)
x two oblique perspective views of the whole evaluation range (45 deg from vertical, compass azimuths 225 and 45 deg, looking at the
centre of the range). The result points = 일 다's sample (the distance task's result sample regenerated and checked; /vc/work/
sample_<site>_<prior>__<res>.npz), coloured by 일 다's relation: d_r <= 0.2 m light grey, 0.2-1.0 m orange, > 1.0 m red; points in the GT-
excluded cells sky blue. Nearest point per pixel (z-buffer), 2 x 2 supersampled and averaged. Under the panels: 정밀도 and the three
relation shares (all points); the json adds the four colour shares.
  python d4_diag.py   -> /docs/figures/진단/<case>.png|pdf|json   scientific_verdict: null"""
import time

import numpy as np
from matplotlib import colors

import vc_common  # noqa: F401
import pf_geo as G
import vc_render as RD
from vc_common import CFG, DOCS, PRIOR_KO, SITE_KO, VC, jdump, jl, log, now

SS, PW = 2, 900
RES = {"학습 전 사전 정보": "samepath_{p}", "결합": "mvsfuse_{p}", "본 방법": "prop_{p}_s0"}


def camera(lo, hi, az_deg, tilt_deg, size=None):
    c = 0.5 * (lo + hi); ext = float(np.linalg.norm((hi - lo)[:2]))
    a, t = np.radians(az_deg), np.radians(tilt_deg)
    d = np.array([np.sin(a) * np.sin(t), np.cos(a) * np.sin(t), np.cos(t)])
    eye = c + 2.5 * ext * d
    fit = np.array([[x, y, z] for x in (lo[0], hi[0]) for y in (lo[1], hi[1]) for z in (lo[2], hi[2])])
    if size is None:
        pr = RD.LookAt(eye, c, [0, 0, 1], fit, [PW, PW], margin=0.04)
        u, v, _ = pr.project(fit)
        size = [PW, int(round(PW * np.clip((v.max() - v.min()) / (u.max() - u.min()), 0.35, 1.2)))]
    return eye, c, fit, size


def render(cam, X, col):
    img, n = RD.splat_rgb(cam, X, col, radius=0, bg=(1.0, 1.0, 1.0))
    return np.stack([RD.down(img[..., k], SS) for k in range(3)], -1), n


def main():
    t0 = time.time()
    C = jl(CFG); W = C["work_ra"]; rb = C["work_da"]["relation_bins_m"]
    cols = {k: np.array(colors.to_rgb(v)) for k, v in W["colours"].items()}
    names = list(W["colours"].keys())       # 가까움, 1 m 안에 참값, 1 m 안에 참값 없음, 참값에서 뺀 칸
    plt = G.setup_plt()
    from matplotlib.patches import Patch
    fs = 6.5
    plt.rcParams.update({"font.size": fs})
    (DOCS / "figures/진단").mkdir(parents=True, exist_ok=True)
    for u in W["cases"]:
        site, prior = u.split("/")
        S = {}
        for m, r in RES.items():
            f = VC / "work" / f"sample_{site}_{prior}__{r.format(p=prior)}.npz"
            S[m] = np.load(f) if f.exists() else None
        X0 = S["학습 전 사전 정보"]["xyz"].astype(np.float64)
        lo, hi = np.percentile(X0, 0.5, 0), np.percentile(X0, 99.5, 0)
        views = []
        for az in (225.0, 45.0):
            eye, tg, fit, size = camera(lo, hi, az, 45.0)
            views.append(dict(az=az, eye=eye, target=tg, fit=fit, size=size))
        imgs, rec = {}, {}
        for m, z in S.items():
            res = RES[m].format(p=prior)
            if z is None:
                rec[m] = dict(result=res, status="결과 없음"); continue
            X = z["xyz"].astype(np.float64); dr = z["dr"].astype(np.float64); ex = z["excl"].astype(bool)
            cl = np.where(dr <= rb[0], 0, np.where(dr <= rb[1], 1, 2)); cl[ex] = 3
            col = np.stack([cols[names[k]] for k in range(4)])[cl]
            rec[m] = dict(result=res, status="ok", sample=f"/vc/work/sample_{site}_{prior}__{res}.npz", points=int(len(X)), precision=float((dr <= rb[0]).mean()),
                          relation_shares=dict(zip(C["work_da"]["relation_names"], [float((dr <= rb[0]).mean()), float(((dr > rb[0]) & (dr <= rb[1])).mean()), float((dr > rb[1]).mean())])),
                          colour_shares={names[k]: float((cl == k).mean()) for k in range(4)}, views={})
            for i, v in enumerate(views):
                cam = RD.LookAt(v["eye"], v["target"], [0, 0, 1], v["fit"], [v["size"][0] * SS, v["size"][1] * SS], margin=0.04)
                imgs[(m, i)], n = render(cam, X, col)
                rec[m]["views"][str(int(v["az"]))] = dict(points_in_view=int(n))
            log(u, m, rec[m]["precision"], rec[m]["colour_shares"])
        # draw
        IN = 2.54; fw = 16 / IN; lab = 0.18; ncol = 3
        cw = (fw - lab - 0.05) / ncol; chs = [cw * v["size"][1] / v["size"][0] for v in views]
        head, valh, legh = 0.36, 0.34, 0.3
        fh = head + 0.14 + chs[0] + 0.14 + 0.14 + chs[1] + valh + legh
        fig = plt.figure(figsize=(fw, fh))
        ys = [fh - head - 0.14 - chs[0]]; ys.append(ys[0] - 0.28 - chs[1])
        for i, v in enumerate(views):
            for j, m in enumerate(RES):
                ax = fig.add_axes([(lab + j * cw + 0.012) / fw, ys[i] / fh, (cw - 0.024) / fw, chs[i] / fh]); ax.set_xticks([]); ax.set_yticks([])
                for sp in ax.spines.values():
                    sp.set_linewidth(0.4)
                if i == 0:
                    ax.set_title(m, fontsize=fs + 0.5, pad=2, weight="bold" if m == "본 방법" else "normal")
                if (m, i) not in imgs:
                    ax.text(0.5, 0.5, "결과 없음", transform=ax.transAxes, ha="center", va="center"); continue
                ax.imshow(imgs[(m, i)], interpolation="nearest")
                if i == 1:
                    e = rec[m]; rs = list(e["relation_shares"].values())
                    ax.text(0.5, -0.03, f"정밀도 {100 * e['precision']:.1f} %\n주황 {100 * e['colour_shares'][names[1]]:.1f} % · 빨강 {100 * e['colour_shares'][names[2]]:.1f} % · "
                            f"하늘색 {100 * e['colour_shares'][names[3]]:.1f} %", transform=ax.transAxes, ha="center", va="top", fontsize=fs - 0.5)
            fig.text(0.07 / fw, (ys[i] + chs[i] / 2) / fh, f"방위 {int(v['az'])}°", rotation=90, ha="center", va="center", fontsize=fs)
        fig.text(0.5, 1 - 0.08 / fh, f"{SITE_KO[site]} · {PRIOR_KO[prior]}: 결과 점마다 가장 가까운 참값 점까지의 거리", ha="center", va="top", fontsize=fs + 1.3, weight="bold")
        lab_ = {names[0]: "연한 회색: 0.2 m 안에 참값", names[1]: "주황: 1 m 안에 참값(0.2 m 밖)", names[2]: "빨강: 1 m 안에 참값 없음", names[3]: "하늘색: 참값에서 뺀 칸(나무, 일시 물체)"}
        fig.legend(handles=[Patch(fc=W["colours"][k], ec="#777777", label=lab_[k]) for k in names], loc="lower center", bbox_to_anchor=(0.5, 0.02 / fh), ncol=4,
                   fontsize=fs - 0.5, frameon=False, handlelength=1.1, columnspacing=1.2)
        fn = f"진단_{site.split('_')[0]}_{prior}"
        for e in ("png", "pdf"):
            fig.savefig(DOCS / "figures/진단" / f"{fn}.{e}", dpi=300)
        plt.close(fig)
        jdump(DOCS / "figures/진단" / f"{fn}.json", dict(task="PHD-MAIN-VISCMP-v4", work="일 라", case=u, panels=rec, relation_bins_m=rb,
                                                       views=[dict(azimuth_deg=v["az"], tilt_deg=45.0, eye=v["eye"].tolist(), target=v["target"].tolist(), size=v["size"]) for v in views],
                                                       range_box=dict(rule="the prior sample's 0.5-99.5 percentile box", lo=lo.tolist(), hi=hi.tolist()), colours=W["colours"],
                                                       size_cm=[16.0, round(fh * IN, 2)], made=now(), seconds=round(time.time() - t0, 1), scientific_verdict=None))
    log("done", round(time.time() - t0, 1))


if __name__ == "__main__":
    main()
