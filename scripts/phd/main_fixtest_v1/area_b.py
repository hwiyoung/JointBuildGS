"""PHD-MAIN-FIXTEST-v1 10 (10월 22일 판단을 돕는 읽기, 판 B; jointbuildgs:dev, CPU; run_step_ft.sh): the area fix B gained and the area it
gave up, per case, against the mean of the method's two seeds:
  얻은 넓이 (gained)  code-4 patches (missing, the prior right): sum over patches of area x (share of the patch's GT rows within 0.2 m of the
                      result, fix - method mean). Rows = the dist71 rows of place c4 (dist npz r_place bit c4, r_patch, r_d): the same rows as
                      결측 R(0.2 m).
  내준 넓이 (given up) code-13 patches (missing, the prior wrong): sum over patches of area x (past-shape inflow share of the patch's rows,
                      fix - method mean). Rows = the metrics rows of the case (S1/defs rows file: code 13, thinned, |s_W| >= 0.2 m) with the
                      result's four-way classes 'cls' (metrics_s2 rows npz): inflow = wrong side + both, as 결측 영역의 과거 형상 유입률.
  Net, positive part and negative part are written; patches without rows are counted apart. Check: the row-pooled share of each result
  is compared with the place table (FT/tables/eval_ft.json c4 R_0.2 and infl13).
Results: fixB_<prior>_s0 and fixAB_<prior>_s0 where they exist; the judgment-only-off method nojudge_<prior>_s0 as a reference.
  python area_b.py
Writes FT/tables/area_b.json and area_b.md. scientific_verdict: null."""
import json
import sys
from pathlib import Path

import numpy as np

PH = Path("/ph")
FTP = PH / "main_fixtest_v1/PHD-MAIN-FIXTEST-v1"
S1 = Path("/out")
S2 = PH / "main_stage2_v1/PHD-MAIN-STAGE2-v1"
S3 = PH / "main_stage3_v1/PHD-MAIN-STAGE3-v1"
SD = PH / "main_dist71_v1/PHD-MAIN-DIST71-v1"
sys.path.insert(0, "/repo/scripts/phd/main_dist71_v1")
sys.path.insert(0, "/repo/scripts/phd/main_stage1_v1")
import dm_common as DC  # noqa: E402

BIT_C4 = 1 << DC.PLACES[1:].index("c4")
CASES = [(s, p) for s in ("B0_b10", "B173nb_b10", "R1rep_b10") for p in ("LoD2", "ALS")]
CFG = json.loads(Path("/repo/configs/phd/main_fixtest_v1/fixtest_v1.json").read_text())
SITE_KO = {"B0_b10": "B0", "B173nb_b10": "B173 주변", "R1rep_b10": "R1"}
PRIOR_KO = {"LoD2": "LoD2", "ALS": "항공 LiDAR"}


def dist_file(site, prior, res):
    for base in (FTP / "dist", SD / "dist"):
        f = base / f"{site}_{prior}__{res}.npz"
        if f.exists():
            return f
    return None


def rows_file(site, prior, res):
    for base in (FTP / "metrics", S3 / "metrics", S1 / "metrics", S2 / "metrics"):
        f = base / site / f"{res}__{prior}_rows.npz"
        if f.exists():
            return f
    return None


def per_patch_r02(site, prior, res, n):
    f = dist_file(site, prior, res)
    if f is None:
        return None
    z = np.load(f)
    m = (z["r_place"] & BIT_C4) > 0
    pa, ok = z["r_patch"][m].astype(np.int64), (z["r_d"][m] <= 0.2)
    cnt = np.bincount(pa, minlength=n).astype(np.float64)
    hit = np.bincount(pa, weights=ok.astype(np.float64), minlength=n)
    return cnt, hit


def per_patch_inflow(site, prior, res, n, sel, pa):
    f = rows_file(site, prior, res)
    if f is None:
        return None
    cls = np.load(f)["cls"][sel]
    cnt = np.bincount(pa, minlength=n).astype(np.float64)
    hit = np.bincount(pa, weights=np.isin(cls, (1, 2)).astype(np.float64), minlength=n)
    return cnt, hit


def main():
    E = json.loads((FTP / "tables/eval_ft.json").read_text())["cases"]
    out = {}
    for site, prior in CASES:
        R = np.load(S1 / "regions_v3" / f"regions_ext_v3_{site}_{prior}.npz")
        code, area, ev = R["code_ext_v3"].astype(np.int64), R["area"].astype(np.float64), R["in_eval"].astype(bool)
        n = len(code)
        rows = np.load(S1 / "defs" / site / f"rows_{prior}.npz")
        sel13 = (rows["code"] == 13) & rows["thin"].astype(bool) & (np.abs(rows["sW"].astype(np.float64)) >= 0.2)
        pa13 = rows["patch"][sel13].astype(np.int64)
        res = {"s0": f"prop_{prior}_s0", "s1": f"prop_{prior}_s1", "B": f"fixB_{prior}_s0", "AB": f"fixAB_{prior}_s0", "nojudge": f"nojudge_{prior}_s0"}
        r02 = {k: per_patch_r02(site, prior, r, n) for k, r in res.items()}
        inf = {k: per_patch_inflow(site, prior, r, n, sel13, pa13) for k, r in res.items()}
        if r02["s0"] is None or r02["s1"] is None or inf["s0"] is None or inf["s1"] is None:
            continue
        c4 = (code == 4) & ev & (r02["s0"][0] > 0)
        c13 = (code == 13) & (inf["s0"][0] > 0)
        e = dict(case=f"{SITE_KO[site]} {PRIOR_KO[prior]}", code4=dict(patches=int(c4.sum()), area_m2=float(area[c4].sum()),
                 patches_without_rows=int(((code == 4) & ev & (r02["s0"][0] == 0)).sum())),
                 code13=dict(patches=int(c13.sum()), area_m2=float(area[c13].sum()), rows=int(len(pa13))), results={})
        sh = lambda t, m: np.where(t[0] > 0, t[1] / np.maximum(t[0], 1), 0.0)[m]  # noqa: E731
        base4 = 0.5 * (sh(r02["s0"], c4) + sh(r02["s1"], c4))
        base13 = 0.5 * (sh(inf["s0"], c13) + sh(inf["s1"], c13))
        cfg = {r["result"]: r for r in CFG["runs"] if r["site"] == site}
        for k in ("B", "AB", "nojudge"):
            if k in ("B", "AB") and res[k] not in cfg:
                continue                                              # not a run of the configuration (A + B is run only where fix A is)
            if k in ("B", "AB") and not cfg[res[k]]["train"]:
                e["results"][k] = dict(result=res[k], status="관문")
                continue
            if r02[k] is None or inf[k] is None:
                e["results"][k] = dict(result=res[k], status="결과 없음")
                continue
            d4 = area[c4] * (sh(r02[k], c4) - base4)
            d13 = area[c13] * (sh(inf[k], c13) - base13)
            pooled4 = float(r02[k][1][c4].sum() / max(r02[k][0][c4].sum(), 1))
            pooled13 = float(inf[k][1][c13].sum() / max(inf[k][0][c13].sum(), 1))
            tab = E[f"{site}/{prior}"]["places"]["c4"]
            col = {"B": "B", "AB": "AB", "nojudge": "nojudge"}[k]
            t4, t13 = (tab.get("R_0.2", {}).get(col) or {}).get("v"), (tab.get("infl13", {}).get(col) or {}).get("v")
            e["results"][k] = dict(result=res[k], gained_net_m2=float(d4.sum()) + 0.0, gained_plus_m2=float(d4[d4 > 0].sum()) + 0.0,
                                   gained_minus_m2=float(-d4[d4 < 0].sum()) + 0.0, given_net_m2=float(d13.sum()) + 0.0,
                                   given_plus_m2=float(d13[d13 > 0].sum()) + 0.0, given_minus_m2=float(-d13[d13 < 0].sum()) + 0.0,
                                   check=dict(r02_rows_pooled=100 * pooled4, r02_table=t4, inflow_rows_pooled=100 * pooled13, inflow_table=t13))
        out[f"{site}/{prior}"] = e
    (FTP / "tables/area_b.json").write_text(json.dumps(dict(task="PHD-MAIN-FIXTEST-v1", rule=__doc__.split("\n\n")[0], cases=out, scientific_verdict=None),
                                                       indent=1, ensure_ascii=False, default=float))
    L = ["# 판 B가 얻은 넓이와 내준 넓이 [이 발주에서 냄]", "",
         "얻은 넓이 = 평가 범위의 코드 4 패치마다 넓이 × (참값 행 가운데 결과 0.2 m 안 몫: 고친 판 − 본 방법 평균)의 합. "
         "내준 넓이 = 코드 13 패치마다 넓이 × (과거 형상 유입 몫: 고친 판 − 본 방법 평균)의 합. m², 순(늘어난 쪽 / 줄어든 쪽). "
         "점검 열은 행을 모두 합친 몫(곳 표와 같아야 함).", "",
         "| 경우 | 결과 | 코드 4 패치 (넓이) | 얻은 넓이 | 코드 13 패치 (넓이) | 내준 넓이 | 점검: R(0.2 m) 행 합침 / 곳 표 | 점검: 유입률 행 합침 / 곳 표 |",
         "|---|---|---|---|---|---|---|---|"]
    for u, e in out.items():
        for k, x in e["results"].items():
            if "gained_net_m2" not in x:
                L.append(f"| {e['case']} | {x['result']} | {e['code4']['patches']} ({e['code4']['area_m2']:.1f} m²) | {x['status']} | "
                         f"{e['code13']['patches']} ({e['code13']['area_m2']:.1f} m²) | {x['status']} | — | — |")
                continue
            c = x["check"]
            fmt = lambda v: "—" if v is None else f"{v:.1f}"  # noqa: E731
            L.append(f"| {e['case']} | {x['result']} | {e['code4']['patches']} ({e['code4']['area_m2']:.1f} m²) | {x['gained_net_m2']:+.2f} "
                     f"({x['gained_plus_m2']:.2f} / {x['gained_minus_m2']:.2f}) | {e['code13']['patches']} ({e['code13']['area_m2']:.1f} m²) | "
                     f"{x['given_net_m2']:+.2f} ({x['given_plus_m2']:.2f} / {x['given_minus_m2']:.2f}) | {fmt(c['r02_rows_pooled'])} / {fmt(c['r02_table'])} | "
                     f"{fmt(c['inflow_rows_pooled'])} / {fmt(c['inflow_table'])} |")
    (FTP / "tables/area_b.md").write_text("\n".join(L) + "\n")
    print("\n".join(L))


if __name__ == "__main__":
    main()
