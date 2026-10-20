"""PHD-MAIN-B0REF-v1 일 2 tables (jointbuildgs:dev, CPU): table 1 (two wall selections), table 2 (per wall face, space), roof, the
'about ten times' of 6.3 next to the recount, spacing and the same thinning. Reads /b0/sel/*.npz, /b0/prep/faces.json,
/b0/prep/spacing.json and the FACTS64 record F64/t8/b0_walls.json.

  python s2_counts.py   -> /docs/tables/t1_walls.md|json, t2_faces.md|json, t2b_roof.md|json, t2c_ten_times.md|json, t2d_spacing.md|json

Rows of the raw ULS: all returns, the four return classes, and the study's wall points (vertical test on all returns & single return).
Densities divide by the LoD2 area of the selection (config wall_selection density_area). Candidate clouds (other files) get the same
columns in a second block. [이 요청에서 냄] scientific_verdict: null."""
import numpy as np

from b0_common import B0, DOCS, PH, jdump, jl, now

ROWS_U = [("all", "원래 드론 LiDAR 모든 반사", None), ("single", "단일 반사", 0), ("first", "여러 반사의 처음", 1),
          ("middle", "여러 반사의 가운데", 2), ("last", "여러 반사의 마지막", 3)]
CAND = [("uls_manual", "수동 비행 드론 LiDAR, 판 1.1.0 (같은 날, 자료 폴더)"), ("uls_manual_v120", "수동 비행 드론 LiDAR, 판 1.2.0 (받음)"),
        ("fill_v120", "수동 비행 5 mm 처리본(fillparts), 판 1.2.0 (받음)"), ("fill_v110", "수동 비행 5 mm 처리본(fillparts), 판 1.1.0 (받음)"),
        ("photogrammetry", "드론 영상 점군 (같은 날, 자료 폴더)"), ("uls_nadir_t2first", "원래 드론 LiDAR 2 cm 솎음(칸의 첫 점)"),
        ("uls_nadir_t2mean", "원래 드론 LiDAR 2 cm 솎음(칸 평균)")]


def rows():
    """(key, label, masks dict) per row; masks: space, rule, roof, faces{ext: count}."""
    out = []
    def mk(key, label, S, sub):
        faces = {int(k[5:]): int(sub[S[k]].sum()) for k in S.files if k.startswith("face_")}
        out.append(dict(key=key, label=label, space=int((S["wall_any"] & sub).sum()), rule=int((S["rule"] & sub).sum()),
                        roof=int((S["roof_any"] & sub).sum()), faces=faces, ev=int((S["ev"] & sub).sum())))
    G = np.load(B0 / "sel/geogs.npz")
    mk("geogs", "GeoGS 점군", G, np.ones(len(G["ev"]), bool))
    U = np.load(B0 / "sel/uls_nadir.npz")
    rc = U["rclass"]
    for key, label, c in ROWS_U:
        mk(key, label, U, np.ones(len(rc), bool) if c is None else rc == c)
    mk("study", "이 연구의 벽 점(수직면 & 단일 반사)", U, U["vert"] & (rc == 0))
    out[-1]["note"] = "공간 칸 = 공간 안의 수직면 단일 반사 점; 규칙 칸 = 규칙 & 단일 반사(= 단일 반사 줄의 규칙 칸)"
    cand = []
    for key, label in CAND:
        p = B0 / "sel" / f"{key}.npz"
        if p.exists():
            S = np.load(p)
            n0 = len(out)
            mk(key, label, S, np.ones(len(S["ev"]), bool))
            cand.append(out.pop(n0))
    return out, cand


def fmt(x, nd=0):
    return f"{x:,.{nd}f}"


def main():
    F = jl(B0 / "prep/faces.json")
    walls = sorted([f for f in F["faces"] if f["kind"] == 2], key=lambda f: -f["area_space_in_eval_m2"])
    A_space = F["totals"]["wall_space_area_in_eval_m2"]; A_rule = F["totals"]["wall_area_in_eval_m2"]; A_roof = F["totals"]["roof_area_in_eval_m2"]
    R, C = rows()
    for r in R + C:
        r["space_per_m2"] = r["space"] / A_space; r["rule_per_m2"] = r["rule"] / A_rule; r["roof_per_m2"] = r["roof"] / A_roof
    t1 = dict(rows=R, candidates=C, area_space_m2=A_space, area_rule_m2=A_rule, area_roof_m2=A_roof, building=F["building"],
              rule="config wall_selection (locked 10:47:53, sha256 4a4ff8d2...)", made=now(), scientific_verdict=None)
    jdump(DOCS / "tables/t1_walls.json", t1)
    L = ["# 표 1. B0 대상 건물 벽의 점 수, 벽을 고르는 두 법 [이 요청에서 냄]", "",
         f"- 범위: 평가 범위 안. 공간 = 벽면에서 수평 1.0 m 안, 아래 끝 + 0.5 m ~ 위 끝 − 0.5 m(넓이 {A_space:,.1f} m²). 규칙 = 이 연구의 수직면 판정(모든 반사에 걸고 반사 횟수 조건은 뺌)과 벽 2 m 대응(넓이 = 벽면의 평가 범위 안 넓이 {A_rule:,.1f} m²).",
         "- 두 점군 모두 정리 전(비교 좌표). 반사의 종류 줄은 원래 드론 LiDAR(연직 비행 파일)를 나눈 것이다.", "",
         "| 줄 | 공간으로 고른 점 | 공간 1 m²당 | 규칙으로 고른 점 | 규칙 1 m²당 |", "|---|---:|---:|---:|---:|"]
    for r in R:
        L.append(f"| {r['label']} | {fmt(r['space'])} | {fmt(r['space_per_m2'], 1)} | {fmt(r['rule'])} | {fmt(r['rule_per_m2'], 1)} |")
    if C:
        L += ["", "후보 자료(일 4, 같은 셈):", "", "| 자료 | 공간으로 고른 점 | 공간 1 m²당 | 규칙으로 고른 점 | 규칙 1 m²당 |", "|---|---:|---:|---:|---:|"]
        for r in C:
            L.append(f"| {r['label']} | {fmt(r['space'])} | {fmt(r['space_per_m2'], 1)} | {fmt(r['rule'])} | {fmt(r['rule_per_m2'], 1)} |")
    (DOCS / "tables/t1_walls.md").write_text("\n".join(L) + "\n")
    # table 2 per face
    keys = [r["key"] for r in R]
    t2 = []
    for f in walls:
        a = f["area_space_in_eval_m2"]
        t2.append(dict(ext=f["ext"], facing=f["facing"], azimuth_deg=f["azimuth_deg"], area_space_m2=a, area_face_m2=f["area_face_in_eval_m2"],
                       counts={r["key"]: r["faces"].get(f["ext"], 0) for r in R + C},
                       per_m2={r["key"]: (r["faces"].get(f["ext"], 0) / a if a > 0 else None) for r in R + C}))
    jdump(DOCS / "tables/t2_faces.json", dict(faces=t2, labels={r["key"]: r["label"] for r in R + C}, made=now(), scientific_verdict=None))
    short = {"geogs": "GeoGS", "all": "모든 반사", "single": "단일", "first": "처음", "middle": "가운데", "last": "마지막", "study": "이 연구의 벽 점"}
    L = ["# 표 2. 벽면마다 공간으로 고른 점의 1 m²당 점 수 [이 요청에서 냄]", "",
         "- 넓이 = 그 벽면의 공간 넓이(평가 범위 안). 향한 쪽 = 바깥 법선의 방위. 넓이가 큰 면부터. 괄호 안은 점 수.", "",
         "| 면 | 향한 쪽 | 넓이 (m²) | " + " | ".join(short[k] for k in keys) + " |", "|---|---|---:|" + "---:|" * len(keys)]
    for r in t2:
        if r["area_space_m2"] <= 0:
            continue
        L.append(f"| {r['ext']} | {r['facing']} ({r['azimuth_deg']:.0f}°) | {r['area_space_m2']:,.1f} | " +
                 " | ".join(f"{r['per_m2'][k]:,.1f} ({r['counts'][k]:,})" for k in keys) + " |")
    if C:
        ck = [c["key"] for c in C]
        L += ["", "후보 자료:", "", "| 면 | 넓이 (m²) | " + " | ".join(c["label"] for c in C) + " |", "|---|---:|" + "---:|" * len(ck)]
        for r in t2:
            if r["area_space_m2"] > 0:
                L.append(f"| {r['ext']} | {r['area_space_m2']:,.1f} | " + " | ".join(f"{r['per_m2'][k]:,.1f} ({r['counts'][k]:,})" for k in ck) + " |")
    (DOCS / "tables/t2_faces.md").write_text("\n".join(L) + "\n")
    # roof
    L = ["# 표 2b. 대상 건물 지붕의 점 수 [이 요청에서 냄]", "", f"- 지붕 공간 = 지붕면에서 법선 방향 1.0 m 안, 평가 범위 안(넓이 {A_roof:,.1f} m²).", "",
         "| 줄 | 지붕 점 | 1 m²당 | 벽(공간) 1 m²당 ÷ 지붕 1 m²당 |", "|---|---:|---:|---:|"]
    for r in R + C:
        L.append(f"| {r['label']} | {fmt(r['roof'])} | {fmt(r['roof_per_m2'], 1)} | {r['space_per_m2'] / r['roof_per_m2']:.2f} |" if r["roof"] else
                 f"| {r['label']} | 0 | 0 | — |")
    (DOCS / "tables/t2b_roof.md").write_text("\n".join(L) + "\n")
    jdump(DOCS / "tables/t2b_roof.json", dict(rows=[dict(key=r["key"], label=r["label"], roof=r["roof"], roof_per_m2=r["roof_per_m2"]) for r in R + C],
                                               area_roof_m2=A_roof, made=now(), scientific_verdict=None))
    # ten times
    T8 = jl(PH / "ch6_facts64_v1/PHD-CH6-FACTS64-v1/t8/b0_walls.json")
    e8 = T8["evaluation_range"]
    g = {r["key"]: r for r in R}
    ten = dict(facts64_2_8_4=dict(geogs_vertical_points_on_target_walls=e8["gt_clean_points_on_these_walls"],
                                  uls_vertical_single_points_on_target_walls=e8["uls_single_return_points_on_these_walls"],
                                  ratio=e8["gt_clean_points_on_these_walls"] / e8["uls_single_return_points_on_these_walls"],
                                  wall_area_m2=e8["wall_area_m2"], source="F64/t8/b0_walls.json (scripts/phd/ch6_facts64_v1/t8_b0_walls.py; S1/v3/box_gt/B0_b10 gt_owner)"),
               facts64_2_8_3=dict(geogs_vertical_share=T8["vertical_surface_points"]["gt_primary_share"], uls_vertical_single_share=T8["vertical_surface_points"]["uls_share"],
                                  geogs_points=T8["gt_primary"]["points"], uls_points_box=26994350, source="S1/v3/box_gt/B0_b10/gt_summary.json"),
               recount=dict(rule_geogs=g["geogs"]["rule"], rule_study=g["study"]["rule"], rule_ratio=g["geogs"]["rule"] / g["study"]["rule"],
                            rule_all=g["all"]["rule"], rule_ratio_to_all=g["geogs"]["rule"] / g["all"]["rule"],
                            space_geogs=g["geogs"]["space"], space_study=g["study"]["space"], space_ratio=g["geogs"]["space"] / g["study"]["space"],
                            space_all=g["all"]["space"], space_ratio_to_all=g["geogs"]["space"] / g["all"]["space"]),
               made=now(), scientific_verdict=None)
    jdump(DOCS / "tables/t2c_ten_times.json", ten)
    f4, rc = ten["facts64_2_8_4"], ten["recount"]
    L = ["# 표 2c. 6.3의 '약 열 배'가 나온 셈과 다시 센 값", "",
         "| 셈 | GeoGS 점군 | 드론 LiDAR | 배수 | 출처 |", "|---|---:|---:|---:|---|",
         f"| FACTS64 2.8-4(정리 뒤, 이 연구의 좌표; 대상 건물 벽 패치에 대응한 점) | {f4['geogs_vertical_points_on_target_walls']:,} (수직면 점) | {f4['uls_vertical_single_points_on_target_walls']:,} (수직면 단일 반사 점) | {f4['ratio']:.2f} | {f4['source']} |",
         f"| 다시 셈: 규칙으로 고름, 이 연구의 벽 점 [이 요청에서 냄] | {rc['rule_geogs']:,} | {rc['rule_study']:,} | {rc['rule_ratio']:.2f} | 표 1 |",
         f"| 다시 셈: 규칙으로 고름, 모든 반사 [이 요청에서 냄] | {rc['rule_geogs']:,} | {rc['rule_all']:,} | {rc['rule_ratio_to_all']:.2f} | 표 1 |",
         f"| 다시 셈: 공간으로 고름, 이 연구의 벽 점 [이 요청에서 냄] | {rc['space_geogs']:,} | {rc['space_study']:,} | {rc['space_ratio']:.2f} | 표 1 |",
         f"| 다시 셈: 공간으로 고름, 모든 반사 [이 요청에서 냄] | {rc['space_geogs']:,} | {rc['space_all']:,} | {rc['space_ratio_to_all']:.2f} | 표 1 |",
         "", f"- FACTS64 2.8-3(상자 전체, 기록): GeoGS 점 {ten['facts64_2_8_3']['geogs_points']:,}점 가운데 수직면 점의 몫 {ten['facts64_2_8_3']['geogs_vertical_share']:.3f}, 드론 LiDAR {ten['facts64_2_8_3']['uls_points_box']:,}점 가운데 수직면 단일 반사 점의 몫 {ten['facts64_2_8_3']['uls_vertical_single_share']:.3f}. 상자에는 이웃 건물이 들어 있어 배수로 쓰지 않는다."]
    (DOCS / "tables/t2c_ten_times.md").write_text("\n".join(L) + "\n")
    # spacing
    S = jl(B0 / "prep/spacing.json")
    L = ["# 표 2d. 점 간격과 2 cm 칸 [이 요청에서 냄]", "", "| 점군 | 곳 | 점 | 가장 가까운 이웃 중앙값 (mm) | 5 분위 | 95 분위 | 최솟값 | 2 cm보다 가까운 몫 |", "|---|---|---:|---:|---:|---:|---:|---:|"]
    for k, lab in (("geogs", "GeoGS 점군"), ("uls_nadir", "원래 드론 LiDAR 모든 반사")):
        for w, wl in (("all", "평가 범위 전체"), ("wall_space", "벽(공간)"), ("roof_space", "지붕")):
            q = S[k][w]
            L.append(f"| {lab} | {wl} | {q['n']:,} | {q['median_m']*1e3:.1f} | {q['p05_m']*1e3:.1f} | {q['p95_m']*1e3:.1f} | {q['min_m']*1e3:.2f} | {q['share_below_grid']*100:.1f} % |")
    L += ["", "| 점군 | 2 cm 칸 | 점이 둘 이상인 칸 | 칸에 혼자인 점의 몫 | 한 칸의 최대 점 수 |", "|---|---:|---:|---:|---:|"]
    for k, lab in (("geogs", "GeoGS 점군"), ("uls_nadir", "원래 드론 LiDAR 모든 반사")):
        o = S[k]["occupancy_2cm"]
        L.append(f"| {lab} | {o['cells']:,} | {o['cells_with_more_than_one']:,} | {o['share_points_alone_in_cell']*100:.2f} % | {o['max_points_in_cell']} |")
    th = S["thinned"]
    L += ["", f"- 같은 솎음(2 cm 칸; GeoGS 코드와 문서에 솎음 법이 없어 설정의 두 법): 원래 드론 LiDAR {th['raw_points']:,}점(상자) → 칸의 첫 점 {th['first_points']:,}점, 칸 평균 {th['mean_points']:,}점. 벽과 지붕의 점 수는 표 1·표 2b의 후보 자료 줄."]
    (DOCS / "tables/t2d_spacing.md").write_text("\n".join(L) + "\n")
    jdump(DOCS / "tables/t2d_spacing.json", S)
    print(open(DOCS / "tables/t1_walls.md").read()); print(open(DOCS / "tables/t2c_ten_times.md").read()); print(open(DOCS / "tables/t2d_spacing.md").read())


if __name__ == "__main__":
    main()
