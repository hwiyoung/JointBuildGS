"""PHD-MAIN-UNCERT-v1 일 1 tables (jointbuildgs:dev, CPU): what was found (order 3) and the matching checks, from the point receipts
(points/<site>/*.json), the patch facts (work/patches_<site>.json), the 2.8 checks (work/check_mvs_*.json, diag_views_*.json), the GT
files and the R = 1.5 m patch values (densities, p_M of the refine patches, p_A).

  python u1_facts.py   -> /docs/tables/u1_found.md|json, /docs/tables/u1_checks.md|json   scientific_verdict: null."""
import sys

import numpy as np

sys.path.insert(0, "/repo/scripts/phd/main_uncert_v1")
import u3_lib as L  # noqa: E402
import uc_common as U  # noqa: E402
from u3_lib import fmt, md_table  # noqa: E402

A_IN = np.pi * U.D["inner_radius_m"] ** 2


def main():
    S = L.Store(1.5)
    rows, js = [], {}
    for s in U.SITES:
        pa = U.jl(U.PTS / s / "mvs_a.json")
        pb = U.jl(U.PTS / s / "mvs_b.json")
        al = U.jl(U.PTS / s / "als.json")
        gt = U.jl(U.PTS / s / "gt.json")
        pf = U.jl(U.WORK / f"patches_{s}.json")["facts"]
        js[s] = dict(mvs_a={k: pa[k] for k in ("n_points", "views", "views_with_depth", "depth_dir", "conf_dir", "depth_checks", "level_prefix_counts", "seconds")},
                     mvs_b={k: pb[k] for k in ("n_points", "views", "views_with_depth", "depth_dir", "conf_dir", "depth_checks", "seconds")},
                     cameras=pa["cameras"], als={k: al[k] for k in ("n_points", "by_class", "multi_return", "shift_applied", "shift_equal", "tiles")},
                     gt={k: gt[k] for k in ("n_points", "sources")}, patches=pf)
        rows.append([U.SITE_KO[s], pa["views"], f"{pa['n_points']:,}", f"{pb['n_points']:,}", f"{al['n_points']:,} (2: {al['by_class'].get('2', 0):,}, 6: {al['by_class'].get('6', 0):,})",
                     "같음" if al["shift_equal"] else "다름", f"{gt['n_points']:,}"])
    body = md_table(["지역", "학습 영상", "MVS 점 판 가", "MVS 점 판 나", "항공 LiDAR 점(분류 2, 6)", "정합 이동 = 영역 파일", "참값 점"], rows)
    # patches and cells
    rows_p = []
    for s in U.SITES:
        pf = js[s]["patches"]
        for p in U.PRIORS:
            f = pf[p]
            cmp = f["cells"].get("axes71_compare", {})
            rows_p.append([U.case_ko(s, p), f"{f['patches']:,}", f"{f['in_eval']:,}", f"{f['band']:,}", f"{f['roof_like_in_eval']:,}", f"{f['wall_like_in_eval']:,}",
                           f"{f['area_m2']['in_eval']:.1f}", "같음" if cmp.get("differ") == 0 else f"다름 {cmp.get('differ')}",
                           ", ".join(f"{x:g}" for x in f["tau_values_cm"])])
    body += "\n\n## 패치와 칸\n\n" + md_table(["경우", "패치", "평가 범위", "둘레 띠", "지붕꼴(평가)", "벽꼴(평가)", "평가 넓이 m²", "칸 = 두 축 평가", "τ (cm)"], rows_p)
    rows_c = []
    for s in U.SITES:
        for p in U.PRIORS:
            f = js[s]["patches"][p]
            for c in U.CELLS:
                cc = f["cell_counts"][c]
                rows_c.append([U.case_ko(s, p), U.CELL_KO[c], f"{cc['patches']:,}", f"{cc['area_m2']:.1f}"])
    body += "\n\n## 칸마다 패치 수와 넓이\n\n" + md_table(["경우", "칸", "패치", "넓이 m²"], rows_c)
    # LoD2 roof types
    rows_r = []
    for s in U.SITES:
        f = js[s]["patches"]["LoD2"]
        for k, v in f["roof_type"].items():
            rows_r.append([U.SITE_KO[s], k or "없음", U.CFG["patch"]["roof_type_ko"].get(k, ""), len(v["buildings"]), f"{v['roof_like_area_in_eval_m2']:.1f}"])
        lw = f["lod2_wall_outward"]
        js[s]["lod2_wall_outward_totals"] = lw["totals"]
    body += "\n\n## LoD2 지붕 형태(bldg:roofType, 평가 범위 지붕꼴 넓이)\n\n" + md_table(["지역", "코드", "형태", "건물", "지붕 넓이 m²"], rows_r)
    # densities per m2 (inner points / 0.785 m2), median over patches with a value
    rows_d = []
    for s, p in U.CASES:
        z = S.get(s, p)
        e = L.ev(z)
        rl = z["roof_like"].astype(bool)
        for d, k in (("mvs_a", "mvs_a_n_inner_all"), ("als", "als_n_inner_all"), ("gt", "gt_n_inner")):
            if k not in z:
                continue
            ok = (z[f"{d}_status"] == 0) if d != "gt" else (z["gt_status"] == 0)
            for fn, fm in (("지붕꼴", rl), ("벽꼴", ~rl)):
                m = e & ok & fm
                v = z[k][m] / A_IN
                rows_d.append([U.case_ko(s, p), U.DATA_KO[d], fn, f"{int(m.sum()):,}", fmt(float(np.median(v)) if m.any() else None, "v", int(m.sum())),
                               fmt(float(np.quantile(v, .1)) if m.any() else None, "v", int(m.sum()))])
    body += ("\n\n## 1 m²당 점 수 (안쪽 원 점 ÷ 0.785 m², 값이 있는 평가 범위 패치의 중앙값과 10 % 값; MVS는 솎기 전, 여러 영상이 겹친 수)\n\n"
             + md_table(["경우", "자료", "면", "패치", "중앙값", "10 %"], rows_d))
    L.write(U.DOCS / "tables", "u1_found", "일 1. 찾은 것", body, js,
            "MVS 깊이 지도·카메라·깊이의 뜻은 u1_checks와 보고서 2절. 경로는 json(depth_dir, conf_dir, cameras).")
    # ---------------------------------------------------------------- checks
    rows_m, jc = [], {}
    for s, p in U.CASES:
        z = S.get(s, p)
        e = L.ev(z)
        tau = U.CFG["cells"]["tau_cm"][s]
        rl = z["roof_like"].astype(bool)
        groups = [("지붕꼴", rl, tau["roof"] if p == "LoD2" else tau["als"]), ("벽꼴", ~rl, tau["wall"] if p == "LoD2" else tau["als"])]
        for fn, fm, t in groups:
            m = e & (z["cell"] == U.CID["c_refine"]) & fm & L.has(z, "mvs_a")
            pm = 100 * z["mvs_a_p"][m].astype(np.float64)
            md_, nm_ = (float(np.median(pm)), L.nmad(pm)) if m.any() else (None, None)
            flag = "두 배 넘음" if (nm_ is not None and nm_ > 2 * t / 2.5) else ("넘음" if (nm_ is not None and nm_ > t / 2.5) else "안")
            jc[f"{s}_{p}_{fn}"] = dict(patches=int(m.sum()), p_M_med_cm=md_, p_M_nmad_cm=nm_, tau_over_2_5_cm=t / 2.5, flag=flag)
            rows_m.append([U.case_ko(s, p), fn, f"{int(m.sum()):,}", fmt(md_, "v", int(m.sum())), fmt(nm_, "v", int(m.sum())), f"{t / 2.5:.1f}",
                           flag if m.sum() >= 30 else "표본 부족"])
    body = md_table(["경우", "면", "다듬기 패치(값 있음)", "p_M 중앙값", "p_M NMAD", "τ ÷ 2.5", "NMAD와 τ ÷ 2.5"], rows_m)
    rows_a = []
    for s in U.SITES:
        z = S.get(s, "ALS")
        m = L.ev(z) & L.has(z, "als")
        pa = 100 * z["als_p"][m].astype(np.float64)
        jc[f"{s}_pA"] = dict(patches=int(m.sum()), med_cm=float(np.median(pa)), nmad_cm=L.nmad(pa))
        rows_a.append([U.case_ko(s, "ALS"), f"{int(m.sum()):,}", fmt(float(np.median(pa))), fmt(L.nmad(pa))])
    body += "\n\n## 원래 항공 LiDAR 점의 자리 p_A와 사전 정보 면(0)의 차\n\n" + md_table(["경우", "패치(값 있음)", "중앙값", "NMAD"], rows_a)
    rows_s = []
    for s in U.SITES:
        c = U.jl(U.WORK / f"check_mvs_{s}.json")["result"]["mvs_a"]
        dv = U.jl(U.WORK / f"diag_views_{s}.json")
        sm = dv["summary"]
        dm = dv["depth_meaning"]
        zd = [x["z_depth"]["abs_normal_dist_p50_cm"] for x in dm if "z_depth" in x]
        rd = [x["ray_distance"]["abs_normal_dist_p50_cm"] for x in dm if "ray_distance" in x and x["ray_distance"]["abs_normal_dist_p50_cm"] is not None]
        big = [v for v in dv["views"] if abs(v["t_v_cm"] - np.median([w["t_v_cm"] for w in dv["views"]])) > 7.5]
        jc[f"{s}_stop"] = dict(check=c, diag_summary=sm, depth_meaning=dm)
        rows_s.append([U.SITE_KO[s], f"{c['with_value']:,}", f"{c['p_M_median_cm']:.1f}", f"{c['view_spread_cm']:.1f}", f"{sm['paired_abs_p50_cm']:.1f}",
                       f"{len(big)} / {sm['views']}", f"{max(zd):.3f}", f"{min(rd):.1f}~{max(rd):.1f}" if rd else "결과 없음"])
    body += ("\n\n## 2.8 멈춤 점검 (항공 LiDAR 경우 다듬기 패치 무작위 3,000개, 판 가)\n\n"
             + md_table(["지역", "값 있는 패치", "p_M 중앙값 (cm)", "영상별 중앙값의 벌어짐 (cm)", "짝지은 차 크기의 중앙값 (cm)", "7.5 cm 넘게 벗어난 영상",
                         "렌더 깊이를 광축 깊이로: LoD2 면까지 중앙값 (cm, 영상 6장 중 가장 큰 것)", "광선 거리로 읽으면 (cm)"], rows_s)
            + "\n\n- 멈춤 조건(영상 사이 15 cm 넘게 벌어짐)이 세 지역 모두에서 걸렸다. 깊이의 뜻과 좌표를 확인했고(위 두 열), 2026-10-23 09:31 사용자 결정 '그대로 진행'.")
    L.write(U.DOCS / "tables", "u1_checks", "일 1. 맞춰 보기", body, jc,
            "p_M = MVS 판 가 안쪽 원 점(솎은 2,000점)의 법선 거리 중앙값(사전 정보 면 0), 고리 1.5 m의 값(p_M은 고리 크기와 무관).")


if __name__ == "__main__":
    main()
