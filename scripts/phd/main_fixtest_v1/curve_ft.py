"""PHD-MAIN-FIXTEST-v1 9.1-2 (어긋난 크기별 재현율 곡선; jointbuildgs:dev, CPU; run_step_ft.sh): the dist71 task's 일 5 curve with this
task's fix results added. d5_curve.groups_of and d5_curve.curve_of of scripts/phd/main_dist71_v1 run unchanged: per case the thinned GT rows
of code-2 and code-11 patches by the patch misfit |gt_med| / tau, the groups from the method's seed 0 (bins under 10,000 rows merged as
there, never across 4 tau), per group R(tau) and 거리 (median |d|, cm).
  method seeds, prior before training   SD/dist (the dist71 task; recomputed here with the same function and compared with SD/tables/d5_curve.json)
  this task's results                   FT/dist (fixA_, fixAT_, fixB_, fixAB_)
Also the raw bins 1~1.5 and 1.5~2 (not merged) of every case, for prediction A5 (order 10: '곡선의 1~1.5τ, 1.5~2τ 구간'); a raw bin
under 10,000 rows is read at most 가능·근거 불완전 and under 100 rows not read (표본 부족), as in order 9.2.
Reading of a fix per group (order 9.2, one seed): R(tau) criterion = max(2.8 |s0 - s1| / sqrt 2, 300 / rows) (%p; no pooled band per group),
거리 criterion = 2.8 |s0 - s1| / sqrt 2 (cm).
  python curve_ft.py
Writes FT/tables/curve_ft.json and curve_ft.md. scientific_verdict: null."""
import json
import math
import sys

import numpy as np

sys.path.insert(0, "/repo/scripts/phd/main_dist71_v1")
sys.path.insert(0, "/repo/scripts/phd/main_stage1_v1")
import dm_common as DC  # noqa: E402
import d5_curve as D5  # noqa: E402

FTP = DC.PH / "main_fixtest_v1/PHD-MAIN-FIXTEST-v1"
DIST_FT = FTP / "dist"
SD = DC.PH / "main_dist71_v1/PHD-MAIN-DIST71-v1"
FIX = (("A", "판 A (읽기 L)"), ("AT", "판 A (읽기 T)"), ("B", "판 B"), ("AB", "함께 켠 판"))
RAW = ((1.0, 1.5), (1.5, 2.0))
CFG = json.loads(open("/repo/configs/phd/main_fixtest_v1/fixtest_v1.json").read())


def status_of(site, res):
    run = next((r for r in CFG["runs"] if r["site"] == site and r["result"] == res), None)
    if run is not None and not run["train"]:
        return "읽기 L과 같음" if "갈음" in run["why"] else ("관문" if "관문" in run["why"] else "학습 안 함")
    return "결과 없음"


def raw_bins(z):
    c11 = (z["r_place"] & D5.BITS["c11"]) > 0
    ratio = z["r_ratio"].astype(np.float64)
    d, tau = z["r_d"].astype(np.float64), z["r_tau"].astype(np.float64)
    out = []
    for lo, hi in RAW:
        m = c11 & (ratio >= lo) & (ratio < hi)
        out.append(dict(bin=f"{lo:g}~{hi:g} (묶지 않음)", range=[lo, hi], n=int(m.sum()), R_tau=float((d[m] <= tau[m]).mean()) if m.any() else None,
                        dist=float(np.median(d[m])) * 100 if m.any() else None))
    return out


def read(fx, b0, b1, n, m):
    if fx is None or b0 is None or b1 is None:
        return dict(grade="—")
    if m == "R_tau":
        fx, b0, b1 = 100 * fx, 100 * b0, 100 * b1
    mean = 0.5 * (b0 + b1)
    terms = {"case": 2.8 * abs(b0 - b1) / math.sqrt(2)}
    if m == "R_tau" and n:
        terms["300/n"] = 300.0 / n
    crit = max(terms.values())
    diff = fx - mean
    if n < 100:
        return dict(grade="표본 부족", diff=diff, criterion=crit, n=n)
    g = "확인" if abs(diff) > 2 * crit else ("가능·근거 불완전" if abs(diff) > crit else "같음")
    if g == "확인" and n < 10000:
        g = "가능·근거 불완전"
    side = "같음" if g == "같음" else ("나음" if (diff > 0) == (m == "R_tau") else "못함")
    return dict(grade=g, side=side, diff=diff, criterion=crit, terms=terms, n=n)


def main():
    ref = json.loads((SD / "tables/d5_curve.json").read_text())["data"]
    data, check = {}, {}
    for site, prior in DC.CASES:
        u = f"{site}/{prior}"
        z0 = np.load(SD / "dist" / f"{site}_{prior}__prop_{prior}_s0.npz")
        c11 = (z0["r_place"] & D5.BITS["c11"]) > 0
        counts, groups = D5.groups_of(z0["r_ratio"][c11].astype(np.float64))
        e = dict(case=DC.case_ko(site, prior), raw_counts=counts,
                 groups=[[[D5.EDGES[i], None if not np.isfinite(D5.EDGES[i + 1]) else D5.EDGES[i + 1]] for i in g] for g in groups], results={})
        todo = [("s0", f"prop_{prior}_s0", SD / "dist"), ("s1", f"prop_{prior}_s1", SD / "dist"), ("samepath", f"samepath_{prior}", SD / "dist")]
        todo += [(c, f"fix{c}_{prior}_s0", DIST_FT) for c, _ in FIX]
        for k, r, base in todo:
            f = base / f"{site}_{prior}__{r}.npz"
            if not f.exists():
                e["results"][k] = dict(result=r, status=status_of(site, r) if r.startswith("fix") else "결과 없음")
                continue
            z = np.load(f)
            e["results"][k] = dict(result=r, source=str(f).replace(str(DC.PH), "PH"), curve=D5.curve_of(z, groups), raw=raw_bins(z))
        # the method's mean against the dist71 table (same function, same files)
        mean = [dict(b0, R_tau=0.5 * (b0["R_tau"] + b1["R_tau"]) if b0["R_tau"] is not None else None,
                     dist=0.5 * (b0["dist"] + b1["dist"]) if b0["dist"] is not None else None)
                for b0, b1 in zip(e["results"]["s0"]["curve"], e["results"]["s1"]["curve"])]
        rm = ref[u]["methods"]["method"]["mean"]
        check[u] = all(a["n"] == b["n"] and (a["R_tau"] is None or abs(a["R_tau"] - b["R_tau"]) < 1e-12) and (a["dist"] is None or abs(a["dist"] - b["dist"]) < 1e-9)
                       for a, b in zip(mean, rm)) and len(mean) == len(rm)
        e["method_mean"] = mean
        for c, _ in FIX:
            x = e["results"].get(c, {})
            if "curve" not in x:
                continue
            x["read"] = []
            for i, b in enumerate(x["curve"]):
                b0, b1 = e["results"]["s0"]["curve"][i], e["results"]["s1"]["curve"][i]
                x["read"].append({m: read(b[m], b0[m], b1[m], b0["n"], m) for m in ("R_tau", "dist")})
            x["read_raw"] = []
            for i, b in enumerate(x["raw"]):
                b0, b1 = e["results"]["s0"]["raw"][i], e["results"]["s1"]["raw"][i]
                x["read_raw"].append({m: read(b[m], b0[m], b1[m], b0["n"], m) for m in ("R_tau", "dist")})
        data[u] = e
    DC.jdump(FTP / "tables/curve_ft.json", dict(task="PHD-MAIN-FIXTEST-v1", work="9.1-2", made=DC.now(), rule=__doc__.split("\n\n")[0],
                                                same_as_dist71_table=check, data=data, scientific_verdict=None))
    L = ["# 어긋난 크기별 재현율 곡선 (9.1의 2) [이 발주에서 냄]", "",
         "칸 = R(τ) % · 거리 cm (행 수는 구간 열). 본 방법은 두 씨앗 평균(새 거리 지표 작업의 표와 같음: "
         + ", ".join(f"{data[u]['case']} {'같음' if ok else '다름'}" for u, ok in check.items()) + "). 고친 판의 읽기는 R(τ)의 읽기다. "
         "1만 행 미만 `*`(가능·근거 불완전까지), 100행 미만 '표본 부족'.", ""]
    for u, e in data.items():
        L += [f"**{e['case']}**", "", "| 구간 (τ의 배) | 행 | 본 방법 평균 | " + " | ".join(lab for _, lab in FIX) + " | 학습 전 사전 정보 |", "|---|---:|" + "---|" * (len(FIX) + 2)]
        rows = [(b, i, "curve") for i, b in enumerate(e["method_mean"])]
        raw_mean = [dict(b0, R_tau=None if b0["R_tau"] is None else 0.5 * (b0["R_tau"] + b1["R_tau"]), dist=None if b0["dist"] is None else 0.5 * (b0["dist"] + b1["dist"]))
                    for b0, b1 in zip(e["results"]["s0"]["raw"], e["results"]["s1"]["raw"])]
        rows += [(b, i, "raw") for i, b in enumerate(raw_mean)]
        for b, i, kind in rows:
            n = b["n"]
            star = "*" if n < 10000 else ""

            def fmt(x):
                return "표본 부족" if n < 100 else (f"{100 * x['R_tau']:.1f} · {x['dist']:.1f}{star}" if x.get("R_tau") is not None else "—")
            cells = [fmt(b)]
            for c, _ in FIX:
                x = e["results"].get(c, {})
                if kind not in x:
                    cells.append(x.get("status", "—"))
                    continue
                rr = x["read" if kind == "curve" else "read_raw"][i]["R_tau"]
                g = rr.get("grade", "—")
                cells.append(fmt(x[kind][i]) + ("" if g in ("같음", "—", "표본 부족") else f" ({g}, {rr['side']} {rr['diff']:+.1f})"))
            sp = e["results"].get("samepath", {})
            cells.append(fmt(sp[kind][i]) if kind in sp else "—")
            L.append(f"| {b['bin']} | {n:,} | " + " | ".join(cells) + " |")
        L.append("")
    (FTP / "tables/curve_ft.md").write_text("\n".join(L) + "\n")
    print("curve_ft done", check)


if __name__ == "__main__":
    main()
