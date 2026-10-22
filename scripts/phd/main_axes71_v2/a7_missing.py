"""PHD-MAIN-AXES71-v2 일 7 (10.2): the missing patches by judgment path and prior right/wrong — table and maps (jointbuildgs:dev, CPU).

  python a7_missing.py    -> AX/tables/a7_missing.json, /docs/tables/일7_결측.md|json, /docs/figures/일7_결측지도_<site>_<prior>.png|pdf|json

Missing patches = the cells 상속 · 결측, 결측 · 사전 정보 틀림 and the code-4 patches of 보존 · 거름 (5.1). Path (config missing.path_rule,
일 1 (마)): SL/work/undecidable/borrow_<site>_<prior>.npz state 1 = 직접; state 2 and J 1 빌린 일치, 0 빌린 충돌, 2 섞임, 3 미판정. Prior
right = code 4, wrong = code 13. Per path x right/wrong, case and prior (three sites): patches, area, GT rows and per result (config
missing.results; 결측 지키기 = fixB_<prior>_s0 of the fix test) 참값 기준 재현율 R(τ), R(0.2 m), 참값 기준 평균 거리. Check: the fix test's
table 2 (order 10.2). Maps: ax_map views; missing patches by path colour, wrong ones hatched; support patches (state 1) within 2 m of a
missing patch light by their J (일치 / 충돌); the other in-range patches light grey. [이 발주에서 냄] scientific_verdict: null."""
import numpy as np
from scipy.spatial import cKDTree

import ax_map as MP
from ax_common import CASES, CFG, CID, DOCS, FL, PRIORS, RES_KO, SITES, TAB, case_ko, dist_file, jdump, log, now, results_of
from ax_arrays import cells

PATHS = CFG["missing"]["paths"]
RESK = CFG["missing"]["results"]
WANT = {"wrong_release": [108, 0, 57, 10, 99, 61], "from_violation": [97, 0, 50, 10, 98, 50], "right_release": [22, 0, 26, 9, 139, 8], "mixed": [44, 4, 88, 6, 42, 2]}


def path_of(site, prior, C):
    B = np.load(FL / "work/undecidable" / f"borrow_{site}_{prior}.npz")
    st, J = B["state"].astype(np.int64), B["J"].astype(np.int64)
    p = np.full(len(st), -1)
    p[st == 1] = 0
    for j, k in ((1, 1), (0, 2), (2, 3), (3, 4)):
        p[(st == 2) & (J == j)] = k
    return p, st, J, B


def missing_mask(C):
    cell, code = C["cell"].astype(np.int64), C["code"].astype(np.int64)
    return (cell == CID["c_inh_miss"]) | (cell == CID["c_miss_wrong"]) | ((cell == CID["c_keep_mask"]) & (code == 4))


def rows_of(site, prior, res):
    f = dist_file(site, prior, res)
    if f is None:
        return None
    z = np.load(f)
    return dict(d=z["r_d"].astype(np.float64), tau=z["r_tau"].astype(np.float64), patch=z["r_patch"].astype(np.int64))


def table2_check(site, prior, C, B):
    R = np.load(f"/out/regions_v3/regions_ext_v3_{site}_{prior}.npz")
    code, ev, pv = R["code_ext_v3"].astype(np.int64), R["in_eval"].astype(bool), R["premise_violation"].astype(bool)
    J = B["J"].astype(np.int64)
    rel4 = ev & (code == 4) & (J == 0)
    mis = B["mis"].astype(np.int64)
    bor = B["borrowed"].astype(np.int64)
    fromv = np.zeros(len(code), bool)
    for i, m in enumerate(mis):
        b = bor[i][bor[i] >= 0]
        fromv[m] = bool(pv[b].any()) if len(b) else False
    return dict(wrong_release=int(rel4.sum()), from_violation=int((rel4 & fromv).sum()), right_release=int((ev & (code == 13) & (J == 0)).sum()),
                mixed=int((ev & np.isin(code, (4, 13)) & (J == 2)).sum()))


def main():
    plt = MP.setup_plt()
    from matplotlib.patches import Patch
    out, checks, info = {}, {}, {}
    for prior in PRIORS:
        rows_all = {}
        for site in SITES:
            C = cells(site, prior)
            p, st, J, B = path_of(site, prior, C)
            mm = missing_mask(C)
            right = C["code"].astype(np.int64) == 4
            area = C["area"].astype(np.float64)
            checks[f"{site}/{prior}"] = table2_check(site, prior, C, B)
            info[f"{site}/{prior}"] = dict(missing=int(mm.sum()), paths={PATHS[k]: int((mm & (p == k)).sum()) for k in range(5)}, path_none=int((mm & (p < 0)).sum()))
            rows_all[site] = dict(p=p, mm=mm, right=right, area=area, res={})
            for rk in RESK:
                for res in results_of(rk, prior):
                    rows_all[site]["res"].setdefault(rk, {})[res] = rows_of(site, prior, res)
            # map
            map_case(plt, Patch, site, prior, C, p, st, J, mm, right)
        for ss, u in [([s], f"{s}/{prior}") for s in SITES] + [(list(SITES), f"합/{prior}")]:
            e = {}
            for k, pname in enumerate(PATHS):
                for rw, rwn in ((True, "맞음"), (False, "틀림")):
                    key = f"{pname}|{rwn}"
                    pm = {s: rows_all[s]["mm"] & (rows_all[s]["p"] == k) & (rows_all[s]["right"] == rw) for s in ss}
                    o = dict(patches=int(sum(pm[s].sum() for s in ss)), area=float(sum(rows_all[s]["area"][pm[s]].sum() for s in ss)), res={})
                    for rk in RESK:
                        vals = []
                        for res, rw_ in rows_all[ss[0]]["res"][rk].items():
                            parts = [rows_all[s]["res"][rk][res] for s in ss]
                            if any(x is None for x in parts):
                                vals.append(None)
                                continue
                            d = np.concatenate([x["d"][pm[s][x["patch"]]] for s, x in zip(ss, parts)])
                            t = np.concatenate([x["tau"][pm[s][x["patch"]]] for s, x in zip(ss, parts)])
                            vals.append(dict(n=int(len(d)), R_tau=float((d <= t).mean()) if len(d) else None, R_02=float((d <= 0.2).mean()) if len(d) else None,
                                             mean=float(d.mean() * 100) if len(d) else None))
                        if any(v is None for v in vals):
                            o["res"][rk] = dict(status="결과 없음")
                            continue
                        n = vals[0]["n"]
                        o["rows"] = n
                        if not n:
                            o["res"][rk] = dict(n=0)
                            continue
                        o["res"][rk] = dict(n=n, R_tau=float(np.mean([v["R_tau"] for v in vals])), R_02=float(np.mean([v["R_02"] for v in vals])),
                                            mean=float(np.mean([v["mean"] for v in vals])), seeds=vals if len(vals) > 1 else None)
                    e[key] = o
            out[u] = e
        log(prior, "missing done")
    chk = []
    for i, (site, prior) in enumerate(CASES):
        got = checks[f"{site}/{prior}"]
        chk.append(dict(case=f"{site}/{prior}", **{k: dict(want=WANT[k][i], here=got[k], same=WANT[k][i] == got[k]) for k in WANT}))
    jdump(TAB / "a7_missing.json", dict(task="PHD-MAIN-AXES71-v2", work="일 7 결측", made=now(), rule=__doc__.split("\n\n")[1], data=out, info=info, checks=chk, scientific_verdict=None))
    jdump(DOCS / "tables/일7_결측.json", dict(task="PHD-MAIN-AXES71-v2", work="일 7 결측", made=now(), data=out, info=info, checks=chk, scientific_verdict=None))
    L = ["# 일 7 결측 패치의 판정 길과 정오 (PHD-MAIN-AXES71-v2) [이 발주에서 냄]", "", f"- 만든 때 {now()}. 결측 패치 = 상속 · 결측 + 결측 · 사전 정보 틀림 + 보존 · 거름 가운데 코드 4. 정오: 코드 4 = 사전 정보 맞음, 코드 13 = 틀림.",
         "- 칸 = 참값 기준 재현율 R(τ) (%) · R(0.2 m) (%) · 참값 기준 평균 거리 (cm). 본 방법 = 두 씨앗 평균. CDGS* = 시점별 크기 맞추기를 생략한 변형.", ""]
    for u, e in out.items():
        nm = (("LoD2" if u.endswith("LoD2") else "항공 LiDAR") + " 합(세 지역)") if u.startswith("합") else case_ko(*u.split("/"))
        L += [f"## {nm}", "", "| 판정 길 | 정오 | 패치 | 넓이 (m²) | 참값 점 | " + " | ".join(RES_KO[k] for k in RESK) + " |", "|---|---|---:|---:|---:|" + "---|" * len(RESK)]
        for key, o in e.items():
            if not o["patches"]:
                continue
            pn, rw = key.split("|")
            n = o.get("rows", 0)
            cs = []
            for rk in RESK:
                v = o["res"].get(rk, {})
                if v.get("status"):
                    cs.append(v["status"])
                elif not v.get("n"):
                    cs.append("참값 점 없음")
                elif v["n"] < 100:
                    cs.append("표본 부족")
                else:
                    cs.append(f"{100 * v['R_tau']:.1f} · {100 * v['R_02']:.1f} · {v['mean']:.1f}" + ("*" if v["n"] < 10000 else ""))
            L.append(f"| {pn} | {rw} | {o['patches']:,} | {o['area']:.1f} | {n:,} | " + " | ".join(cs) + " |")
        L.append("")
    L += ["## 맞춰 볼 값 (고친 판 시험 발주 표 2)", "", "| 경우 | 잘못 놓음(코드 4) | 그 가운데 전제 위배 이웃 | 맞게 놓음(코드 13) | 섞임 |", "|---|---|---|---|---|"]
    for c in chk:
        L.append(f"| {case_ko(*c['case'].split('/'))} | " + " | ".join(f"{c[k]['here']} ({'같음' if c[k]['same'] else '어긋남 ! 기록 ' + str(c[k]['want'])})" for k in WANT) + " |")
    (DOCS / "tables/일7_결측.md").write_text("\n".join(L) + "\n")


def map_case(plt, Patch, site, prior, C, p, st, J, mm, right):
    cell = C["cell"].astype(np.int64)
    R = np.load(f"/out/regions_v3/regions_ext_v3_{site}_{prior}.npz")
    cen = R["centre"].astype(np.float64)
    ev = cell >= 0
    lab = np.full(len(cell), 0)                     # 0 other in-range
    if mm.any():
        near = cKDTree(cen[mm]).query(cen, distance_upper_bound=2.0)[0] <= 2.0
    else:
        near = np.zeros(len(cell), bool)
    lab[ev & near & (st == 1) & (J == 1)] = 1        # support, agreement
    lab[ev & near & (st == 1) & (J == 0)] = 2        # support, conflict
    for k in range(5):
        lab[mm & (p == k) & right] = 10 + k
        lab[mm & (p == k) & ~right] = 20 + k
    lab[mm & (p < 0)] = 30
    idx = np.nonzero(ev)[0]
    P_, pa = MP.patch_points(site, prior, idx)
    L_ = lab[pa]
    MC = CFG["missing"]["colours"]
    pal = {0: MP.rgb("#eeeeee"), 1: MP.rgb(CFG["missing"]["support_colours"]["일치"]), 2: MP.rgb(CFG["missing"]["support_colours"]["충돌"]), 30: MP.rgb("#000000")}
    hat = {}
    for k, nm in enumerate(PATHS):
        pal[10 + k] = MP.rgb(MC[nm])
        hat[20 + k] = (MP.rgb(MC[nm]), MP.rgb("#000000"))
    lo, hi = P_.min(0), P_.max(0)
    px = CFG["maps"]["px_m"]
    T, _ = MP.top_labels(P_, L_, lo, hi, px)
    top = MP.paint(T, pal, hat)
    fig = plt.figure(figsize=(17.0 / 2.54, 11.0 / 2.54))
    ax = fig.add_axes([0.01, 0.55, 0.30, 0.38]); ax.imshow(top, interpolation="nearest"); ax.set_axis_off()
    MP.scalebar(ax, px, top.shape[1], top.shape[0], 10.0 if (hi[0] - lo[0]) < 120 else 20.0); MP.north(ax, top.shape[1], top.shape[0])
    ax.set_title("위에서 · 평가 범위 전체", fontsize=6.5)
    cams = []
    zoom = None
    if mm.any():
        cz = cen[mm]
        zlo, zhi = np.percentile(cz, 5, 0) - 1.5, np.percentile(cz, 95, 0) + 1.5     # the bulk of the missing patches (a far single patch left out)
        U_ = np.load(MP.S0U.format(site=site, prior=prior))
        nn = np.cross(U_["loc_t1"][mm], U_["loc_t2"][mm]); nn /= np.maximum(np.linalg.norm(nn, axis=1, keepdims=True), 1e-12)
        wall = np.abs(nn[:, 2]) < 0.5
        az = CFG["maps"]["oblique"]["azimuth_deg"][0]
        if wall.mean() > 0.5:          # mostly walls: look at the wall face (horizontal normal, sign toward the range centre's outside)
            h = nn[wall][:, :2]
            out_ = cz[wall][:, :2] - cen[ev][:, :2].mean(0)
            h = h * np.where((h * out_).sum(1) < 0, -1.0, 1.0)[:, None]
            hm = h.mean(0)
            az = float(np.degrees(np.arctan2(hm[0], hm[1])) % 360)
        ax.add_patch(__import__("matplotlib.patches", fromlist=["Rectangle"]).Rectangle(((zlo[0] - lo[0]) / px, (hi[1] - zhi[1]) / px), (zhi[0] - zlo[0]) / px,
                     (zhi[1] - zlo[1]) / px, fill=False, ec="k", lw=0.8))
        inb = np.all((P_[:, :2] >= zlo[:2]) & (P_[:, :2] <= zhi[:2]), 1)
        pz = max(0.02, float(max(zhi[0] - zlo[0], zhi[1] - zlo[1])) / 900.0)
        Tz, _ = MP.top_labels(P_[inb], L_[inb], np.r_[zlo[:2], P_[inb, 2].min()], np.r_[zhi[:2], P_[inb, 2].max()], pz)
        a1 = fig.add_axes([0.32, 0.17, 0.33, 0.76]); a1.imshow(MP.paint(Tz, pal, hat), interpolation="nearest"); a1.set_axis_off()
        MP.scalebar(a1, pz, Tz.shape[1], Tz.shape[0], 2.0 if (zhi[0] - zlo[0]) < 30 else 5.0)
        a1.set_title("위에서 · 결측 패치 둘레 확대", fontsize=6.5)
        cam = MP.camera(P_[inb].min(0), P_[inb].max(0), az, CFG["maps"]["oblique"]["tilt_deg"])
        O, _ = MP.oblique_labels(cam, P_[inb], L_[inb], ss=1)
        a2 = fig.add_axes([0.66, 0.17, 0.33, 0.76]); a2.imshow(MP.paint(O, pal, hat), interpolation="nearest"); a2.set_axis_off()
        a2.set_title(f"비스듬히 · 확대 · 방위 {az:.0f}°", fontsize=6.5)
        cams.append(dict(azimuth=az, azimuth_rule="결측 패치 대부분이 벽이면 그 벽을 마주 보는 방위(바깥 법선의 수평 평균), 아니면 225°", camera=cam.record(), zoom_box=[zlo.tolist(), zhi.tolist()], zoom_px_m=pz))
        zoom = [zlo.tolist(), zhi.tolist()]
    hs = [Patch(facecolor=MC[nm], edgecolor="#777777", lw=0.4, label=nm) for nm in PATHS]
    hs += [Patch(facecolor="#ffffff", edgecolor="k", hatch="////", lw=0.4, label="빗금: 사전 정보 틀림(코드 13)"),
           Patch(facecolor=CFG["missing"]["support_colours"]["일치"], edgecolor="#777777", lw=0.4, label="둘레 지지 · 일치"),
           Patch(facecolor=CFG["missing"]["support_colours"]["충돌"], edgecolor="#777777", lw=0.4, label="둘레 지지 · 충돌")]
    fig.legend(handles=hs, loc="lower center", ncol=5, fontsize=6, frameon=False, bbox_to_anchor=(0.5, 0.0))
    fig.suptitle(f"{case_ko(site, prior)} · 결측 패치 {int(mm.sum())}개", fontsize=8, y=0.995)
    stem = DOCS / "figures" / f"일7_결측지도_{site}_{prior}"
    for e in ("png", "pdf"):
        fig.savefig(f"{stem}.{e}", dpi=300)
    plt.close(fig)
    jdump(f"{stem}.json", dict(task="PHD-MAIN-AXES71-v2", work="일 7 결측 지도", case=f"{site}/{prior}", made=now(), missing=int(mm.sum()),
                               paths={nm: dict(right=int((mm & (p == k) & right).sum()), wrong=int((mm & (p == k) & ~right).sum())) for k, nm in enumerate(PATHS)},
                               support_near=dict(agree=int((lab == 1).sum()), conflict=int((lab == 2).sum())), cameras=cams, zoom=zoom, scientific_verdict=None))


if __name__ == "__main__":
    main()
