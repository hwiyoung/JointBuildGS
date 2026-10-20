"""PHD-MAIN-FIXTEST-v1 일 1 표, 일 3 관문, 그림 0 (jointbuildgs:dev, CPU; run_cpu_ft.sh). Reads /out/prep/w1/<region>_<prior>.json
(w1_shares.py) and writes /out/tables/w_table.{md,json}, /out/prep/w_decision.json and /out/figs/fig0_shares.{png,json}.

Two readings of 'NMAD' in the image share (order 5.2: sigma_image = NMAD(d) / sqrt 2) are tabulated side by side:
  literal  the NMAD of the order's metric definition (1.4826 x median absolute deviation, no clip)  -> 'reading L'
  tau      tau's statistic (NMAD after one 3-NMAD clip, tolerance.robust_width)                    -> 'reading T'
The ground-truth shares of the gate use the same statistic as the ground-truth-free shares they are compared with.
NMAD = tau / 2.5 in both readings (order 5.3). The reading used for w is given with --reading (L or T); the other is recorded.

Gate (order 7), per row; ground-truth values outside the evaluation boxes (the whole region when fewer than 1,000 patches outside):
  ga  if the ground-truth prior share and image share differ by more than 1.25x, the ground-truth-free shares have the same smaller side
      (a row that cannot be split -- sigma_image >= NMAD -- is not judged by ga: w = tau there, condition da)
  na  airborne LiDAR: sigma_prior >= the plane-fit spread of the prior surface used in training (flat roof pieces of the region)
  da  sigma_image < NMAD, else w = tau (training goes on)
A case trains fix A only if all its rows pass ga (LoD2: roof and wall) and na (ALS). Narrowed case: trained and w / tau < 0.8 (LoD2: roof).
  python w1_table.py --reading L|T
scientific_verdict: null."""
import argparse
import datetime as dt
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, "/repo/scripts/phd/ch6_support_v1")
W1 = Path("/out/prep/w1")
TAB, FIG = Path("/out/tables"), Path("/out/figs")
REGIONS = (("B0", "B0_b10", "B0"), ("R2", "B173nb_b10", "B173 주변"), ("R1", "R1rep_b10", "R1"))
ROWS = [(r, p, k) for r, _, _ in REGIONS for p, k in (("LoD2", "roof"), ("LoD2", "wall"), ("ALS", "roof"))]
KIND_KO = {("LoD2", "roof"): "LoD2 지붕면", ("LoD2", "wall"): "LoD2 벽면", ("ALS", "roof"): "항공 LiDAR"}
RATIO = 1.25


def reading_values(row, rd):
    """(sigma_image, ci95, separable, sigma_prior, w, w_ci95, gt dict outside/all) of one reading."""
    tau, NM = row["tau"], row["NMAD"]
    if rd == "T":
        si, ci = row["image"]["sigma_image"], row["image"]["sigma_image_ci95"]
        gt = {z: dict(prior=g.get("prior_minus_gt_nmad"), image=g.get("mvs_minus_gt_nmad"), prior_med=g.get("prior_minus_gt_median"),
                      image_med=g.get("mvs_minus_gt_median"), patches=g.get("patches"), pixels=g.get("pixels")) for z, g in row["gt"].items()}
    else:
        b = row["image"]["before_clip"]
        si, ci = b["sigma_image"], b["sigma_image_ci95"]
        gt = {z: dict(prior=g.get("before_clip", {}).get("prior_minus_gt_nmad"), image=g.get("before_clip", {}).get("mvs_minus_gt_nmad"),
                      prior_med=g.get("before_clip", {}).get("prior_minus_gt_median"), image_med=g.get("before_clip", {}).get("mvs_minus_gt_median"),
                      patches=g.get("patches"), pixels=g.get("pixels")) for z, g in row["gt"].items()}
    sep = si < NM
    sp = float(np.sqrt(NM ** 2 - si ** 2)) if sep else float("nan")
    w = float(min(2.5 * sp, tau)) if sep else tau

    def w_of(s):
        return float(min(2.5 * np.sqrt(NM ** 2 - s ** 2), tau)) if s < NM else tau
    wci = [w_of(ci[1]), w_of(ci[0])] if ci else None          # larger sigma_image -> smaller w
    for z, g in gt.items():
        if g["prior"] is not None and g["image"] is not None:
            g["check"] = (g["prior"] ** 2 + g["image"] ** 2) / NM ** 2
    return dict(sigma_image=si, sigma_image_ci95=ci, separable=bool(sep), sigma_prior=sp, w=w, w_ci95=wci, w_over_tau=w / tau, gt=gt)


def gate_row(v, plane_prior, prior_kind):
    gz = "outside" if (v["gt"].get("outside", {}).get("patches") or 0) >= 1000 else "all"
    g = v["gt"][gz]
    out = dict(gt_zone=gz)
    if not v["separable"]:
        out.update(ga="나누지 못함(가 판정 없음)", ga_pass=True)
    else:
        P_, M_ = g["prior"], g["image"]
        big = max(P_, M_) / max(min(P_, M_), 1e-12)
        if big <= RATIO:
            out.update(ga=f"참값 두 몫 비 {big:.2f} ≤ 1.25 (조건 없음)", ga_pass=True)
        else:
            gt_small = "prior" if P_ < M_ else "image"
            free_small = "prior" if v["sigma_prior"] < v["sigma_image"] else "image"
            ok = gt_small == free_small
            ko = {"prior": "사전 정보", "image": "영상"}
            out.update(ga=f"참값 비 {big:.2f}: 작은 쪽 참값 {ko[gt_small]}, 참값 없이 {ko[free_small]}", ga_pass=bool(ok))
    if prior_kind == "ALS":
        ok = (not v["separable"]) or (plane_prior is not None and v["sigma_prior"] >= plane_prior)
        out.update(na=(f"σ_사전 {100 * v['sigma_prior']:.2f} cm ≥ 평면 맞춤 {100 * plane_prior:.2f} cm" if v["separable"] else "나누지 못함")
                   + ("" if ok else " (아님)"), na_pass=bool(ok))
    else:
        out.update(na="해당 없음 (LoD2)", na_pass=True)
    out["da"] = "σ_영상 < NMAD" if v["separable"] else "σ_영상 ≥ NMAD: w = τ"
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--reading", choices=["L", "T"], required=True)
    a = ap.parse_args()
    TAB.mkdir(parents=True, exist_ok=True); FIG.mkdir(parents=True, exist_ok=True)
    J = {(r, p): json.loads((W1 / f"{r}_{p}.json").read_text()) for r, _, _ in REGIONS for p in ("LoD2", "ALS")}
    rows = []
    for r, p, k in ROWS:
        res = J[(r, p)]
        row = res["rows"][k]
        pf_als = J[(r, "ALS")]["plane_fit"]          # MVS and ground-truth plane fits: flat pieces of the airborne LiDAR surface (both rows)
        pf_own = res["plane_fit"]
        plane = dict(prior=(pf_own.get("prior_surface") or {}).get("nmad_pooled"),
                     mvs=(pf_als.get("mvs") or {}).get("nmad_pooled"), gt=(pf_als.get("gt") or {}).get("nmad_pooled"),
                     mvs_before_clip=(pf_als.get("mvs") or {}).get("nmad_pooled_before_clip"), gt_before_clip=(pf_als.get("gt") or {}).get("nmad_pooled_before_clip"),
                     pieces_als=pf_als.get("pieces"), area_als_m2=pf_als.get("area_m2"), pieces_own=pf_own.get("pieces"), area_own_m2=pf_own.get("area_m2"),
                     mvs_on_own_pieces=(pf_own.get("mvs") or {}).get("nmad_pooled"), gt_on_own_pieces=(pf_own.get("gt") or {}).get("nmad_pooled"))
        e = dict(region=r, prior=p, kind=k, kind_ko=KIND_KO[(p, k)], n_residuals=row["n_tau_residuals"], tau=row["tau"], NMAD=row["NMAD"],
                 residual_median=row["residual_median_all"], residual_median_clipped=row["residual_median_clipped"], pairs=row["image"]["pairs"],
                 patches_with_pairs=row["image"]["patches_with_pairs"], plane=plane, spec=row.get("spec_agency"),
                 L=reading_values(row, "L"), T=reading_values(row, "T"))
        for rd in ("L", "T"):
            e[rd]["gate"] = gate_row(e[rd], plane["prior"], p)
        rows.append(e)
    # cases
    cases = {}
    for r, site, ko in REGIONS:
        for p in ("LoD2", "ALS"):
            mine = [e for e in rows if e["region"] == r and e["prior"] == p]
            c = {}
            for rd in ("L", "T"):
                ok = all(e[rd]["gate"]["ga_pass"] and e[rd]["gate"]["na_pass"] for e in mine)
                roof = next(e for e in mine if e["kind"] == "roof")
                wall = next((e for e in mine if e["kind"] == "wall"), roof)
                c[rd] = dict(train=bool(ok), w_roof=roof[rd]["w"], w_wall=wall[rd]["w"], tau_roof=roof["tau"], tau_wall=wall["tau"],
                             w_over_tau_roof=roof[rd]["w_over_tau"], narrowed=bool(ok and roof[rd]["w_over_tau"] < 0.8),
                             failed=[f"{e['kind_ko']}: " + ("가" if not e[rd]["gate"]["ga_pass"] else "") + ("나" if not e[rd]["gate"]["na_pass"] else "")
                                     for e in mine if not (e[rd]["gate"]["ga_pass"] and e[rd]["gate"]["na_pass"])])
            cases[f"{site}/{p}"] = dict(site=site, prior=p, search_region=r, site_ko=ko, **c)
    now = dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S KST")
    out = dict(task_id="PHD-MAIN-FIXTEST-v1", written=now, reading_used=a.reading,
               readings=dict(L="발주 4.3의 NMAD(지우기 없음)로 σ_영상과 참값 두 몫을 구함 — 발주문 글 'σ_영상 = NMAD(차) ÷ √2' 그대로",
                             T="τ의 통계(3 NMAD 한 번 지운 뒤 NMAD)로 σ_영상과 참값 두 몫을 구함 — τ와 같은 통계"),
               rows=rows, cases=cases, rule=__doc__.split("\n\n")[1:3], scientific_verdict=None)
    (TAB / "w_table.json").write_text(json.dumps(out, indent=1, default=float))
    for rd_ in ("L", "T"):
        dec = {k: dict(site=v["site"], prior=v["prior"], train=v[rd_]["train"], narrowed=v[rd_]["narrowed"], w_roof=v[rd_]["w_roof"],
                       w_wall=v[rd_]["w_wall"], tau_roof=v[rd_]["tau_roof"], tau_wall=v[rd_]["tau_wall"], failed=v[rd_]["failed"])
               for k, v in cases.items()}
        (Path("/out/prep") / f"w_decision_{rd_}.json").write_text(json.dumps(dict(written=now, reading=rd_, primary=rd_ == a.reading, cases=dec), indent=1))
    # markdown
    f1 = lambda x: "—" if x is None or x != x else f"{100 * x:.2f}"
    md = [f"# 일 1 표: 두 자료의 몫과 판 A의 폭 w — [이 발주에서 냄] {now}", "",
          f"- w에 쓴 읽기: **{a.reading}** ({out['readings'][a.reading]}). 다른 읽기는 아래 '읽기 T' 표에 함께 적는다.",
          "- 단위 cm. τ, NMAD(= τ ÷ 2.5), 잔차 수와 잔차 중앙값은 τ를 낸 표본(버리는 기준 작업 s52/s03의 residual_samples.npz)에서 옮김. "
          "잔차 = 사전 정보 − MVS(지붕은 연직, 벽은 법선 방향).",
          "- σ_영상: 패치 중심을 본 시점마다 투영해 그 화소의 τ 잔차를 읽고, 같은 점을 본 두 시점의 잔차 차의 NMAD ÷ √2 (패치마다 쌍 10개까지, 씨앗 0). "
          "95 % 구간은 패치를 1,000번 다시 뽑은 값.",
          "- 평면 맞춤 흔들림: 사전 정보 면 = 그 사전 정보의 평지붕 조각(법선이 연직 5° 안, 10 m² 이상)에서, MVS·참값 = 지역마다 항공 LiDAR 면의 평지붕 조각에서 구함(두 사전 정보 줄에 같은 값).",
          "- 참값으로 구한 몫(관문에만 씀): 평가 상자 밖 패치의 τ 잔차 화소에서 (사전 정보 − 참값), (MVS − 참값)의 NMAD; 참값은 빈칸 채우기 8.4의 라벨.", ""]
    for rd in (a.reading, "T" if a.reading == "L" else "L"):
        md += [f"## 읽기 {rd}{' (w에 씀)' if rd == a.reading else ' (기록)'}", "",
               "| 탐색 지역 | 줄 | 잔차 수 | τ | NMAD | 잔차 중앙값 | σ_영상 | σ_영상 95 % 구간 | σ_사전 | w | w 95 % 구간 | w ÷ τ | 평면 맞춤 사전 정보 | 평면 맞춤 MVS | 평면 맞춤 참값 | 참값 사전 정보 몫 (밖) | 참값 영상 몫 (밖) | 참값 사전 정보 몫 (안) | 참값 영상 몫 (안) | 확인 값 (밖) | 기관 정확도 |",
               "|---|---|---:|---:|---:|---:|---:|---|---:|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|"]
        for e in rows:
            v = e[rd]
            go, gi = v["gt"].get("outside", {}), v["gt"].get("inside", {})
            ci = v["sigma_image_ci95"]; wci = v["w_ci95"]
            chk = "—" if go.get("check") is None else f"{go['check']:.2f}"
            md.append(f"| {e['region']} | {e['kind_ko']} | {e['n_residuals']:,} | {f1(e['tau'])} | {f1(e['NMAD'])} | {f1(e['residual_median'])} | {f1(v['sigma_image'])} | "
                      f"{f1(ci[0])}~{f1(ci[1])} | {f1(v['sigma_prior']) if v['separable'] else '나누지 못함'} | {f1(v['w'])} | {f1(wci[0])}~{f1(wci[1])} | {v['w_over_tau']:.2f} | "
                      f"{f1(e['plane']['prior'])} | {f1(e['plane']['mvs'])} | {f1(e['plane']['gt'])} | {f1(go.get('prior'))} | {f1(go.get('image'))} | {f1(gi.get('prior'))} | "
                      f"{f1(gi.get('image'))} | {chk} | "
                      f"{'—' if e['spec'] is None else f1(e['spec'])} |")
        md += ["", f"### 관문 (읽기 {rd})", "", "| 탐색 지역 | 줄 | 가 | 나 | 다 |", "|---|---|---|---|---|"]
        for e in rows:
            g = e[rd]["gate"]
            md.append(f"| {e['region']} | {e['kind_ko']} | {'통과' if g['ga_pass'] else '걸림'}: {g['ga']} ({'상자 밖' if g['gt_zone'] == 'outside' else '지역 전체'}) | "
                      f"{'통과' if g['na_pass'] else '걸림'}: {g['na']} | {g['da']} |")
        md += ["", f"### 경우마다 (읽기 {rd})", "", "| 경우 | 판 A 학습 | 걸린 줄 | w 지붕 | w 벽 | w ÷ τ (지붕) | 폭이 좁아진 경우 |", "|---|---|---|---:|---:|---:|---|"]
        for k, c in cases.items():
            v = c[rd]
            md.append(f"| {c['site_ko']} {'항공 LiDAR' if c['prior'] == 'ALS' else 'LoD2'} | {'함' if v['train'] else '관문'} | {', '.join(v['failed']) or '—'} | "
                      f"{f1(v['w_roof'])} | {f1(v['w_wall'])} | {v['w_over_tau_roof']:.2f} | {'예' if v['narrowed'] else '아니오'} |")
        md.append("")
    (TAB / "w_table.md").write_text("\n".join(md) + "\n")
    # figure 0
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib import font_manager
    for f in ("/fonts/NotoSansCJK-Regular.ttc", "/fonts/NotoSansCJK-Bold.ttc"):
        try:
            font_manager.fontManager.addfont(f)
        except Exception:
            pass
    plt.rcParams["font.family"] = ["Noto Sans CJK JP", "DejaVu Sans"]
    plt.rcParams["axes.unicode_minus"] = False
    def draw(rd):
        fig, ax = plt.subplots(figsize=(14, 5.2))
        xs = np.arange(len(rows))
        wbar = 0.2
        C_IMG, C_PRI = "#4C78A8", "#E45756"
        vals = []
        for i, e in enumerate(rows):
            v = e[rd]
            g = v["gt"][v["gate"]["gt_zone"]]
            sp = v["sigma_prior"] if v["separable"] else 0.0
            bars = [(-1.5, v["sigma_image"], C_IMG, 1.0), (-0.5, g["image"], C_IMG, 0.45), (0.5, sp, C_PRI, 1.0), (1.5, g["prior"], C_PRI, 0.45)]
            for off, val, col, alpha in bars:
                ax.bar(i + off * wbar, 100 * val, wbar, color=col, alpha=alpha, edgecolor=col)
            top = 100 * max(b[1] for b in bars)
            ax.text(i, top + 0.6, f"τ {100 * e['tau']:.1f}\nw {100 * v['w']:.1f}", ha="center", va="bottom", fontsize=9)
            if not v["separable"]:
                ax.text(i + 0.5 * wbar, 0.3, "나누지\n못함", ha="center", va="bottom", fontsize=7, color=C_PRI)
            mark = "" if (v["gate"]["ga_pass"] and v["gate"]["na_pass"]) else "관문 걸림"
            if mark:
                ax.text(i, -2.2, mark, ha="center", va="top", fontsize=8, color="#B00020")
            vals.append(dict(region=e["region"], kind=e["kind_ko"], sigma_image=v["sigma_image"], sigma_prior=v["sigma_prior"] if v["separable"] else None,
                             gt_image=g["image"], gt_prior=g["prior"], gt_zone=v["gate"]["gt_zone"], tau=e["tau"], w=v["w"], gate_pass=bool(v["gate"]["ga_pass"] and v["gate"]["na_pass"])))
        ax.set_xticks(xs)
        ax.set_xticklabels([f"{e['region']}\n{e['kind_ko']}" for e in rows], fontsize=9)
        ax.set_ylabel("cm")
        ax.set_ylim(-3.5, 1.22 * max(100 * max(v["sigma_image"], v["sigma_prior"] or 0, v["gt_image"], v["gt_prior"]) for v in vals) + 4)
        ax.axhline(0, color="#888", lw=0.6)
        ax.text(0.01, 0.97, "막대 넷 (왼쪽부터): 영상의 몫 참값 없이 · 참값으로 / 사전 정보의 몫 참값 없이 · 참값으로 (옅은 막대 = 참값으로 구함)",
                transform=ax.transAxes, fontsize=9, va="top")
        fails = [f"{v['region']} {v['kind']}" for v in vals if not v["gate_pass"]]
        nsep = sum(1 for e in rows if not e[rd]["separable"])
        ttl = (f"참값 없이 나눈 두 몫은 {len(rows) - len(fails) - nsep}줄에서 참값과 어긋나지 않았고, {len(fails)}줄({', '.join(fails)})은 관문에 걸렸으며, "
               f"{nsep}줄은 영상의 몫이 NMAD보다 커서 나누지 못했다" if fails else "참값 없이 나눈 두 몫은 관문에 걸린 줄이 없다")
        ax.set_title(ttl, fontsize=11, loc="left", wrap=True)
        cap = (f"읽기 {rd}: {out['readings'][rd]}. 참값 막대는 평가 상자 밖 패치(상자 밖이 1,000패치 미만이면 지역 전체)의 τ 잔차 화소에서 구함. "
               "막대 위 숫자는 그 줄의 τ와 w(cm). 관문 걸림 = 그 줄이 관문 가 또는 나에 걸림.")
        fig.text(0.01, 0.01, cap, fontsize=8, wrap=True)
        fig.tight_layout(rect=(0, 0.06, 1, 1))
        fig.savefig(FIG / f"fig0_shares_{rd}.png", dpi=130)
        (FIG / f"fig0_shares_{rd}.json").write_text(json.dumps(dict(title=ttl, caption=cap, values=vals, written=now), indent=1, default=float))

    for rd in ("L", "T"):
        draw(rd)
    rd = a.reading
    print("[w1_table] reading", rd, json.dumps({k: (v[rd]["train"], round(100 * v[rd]["w_roof"], 2), round(v[rd]["w_over_tau_roof"], 3), v[rd]["narrowed"]) for k, v in cases.items()}, ensure_ascii=False))
    print("[w1_table] other reading", json.dumps({k: (v["T" if rd == "L" else "L"]["train"], round(100 * v["T" if rd == "L" else "L"]["w_roof"], 2)) for k, v in cases.items()}, ensure_ascii=False))


if __name__ == "__main__":
    main()
