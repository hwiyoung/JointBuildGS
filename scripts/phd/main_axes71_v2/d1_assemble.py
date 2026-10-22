"""PHD-MAIN-AXES71-v2 일 1: assemble the counts (d1_counts.py), the term shapes (d1_terms.py) and the fix-B breakdown (d1_extra.py) into
/docs/tables/일1_정의확인.json (unrounded, with sources) and the md tables of the draft (AX/work/d1/tables_md.md). jointbuildgs:dev, CPU,
read only except those two files. scientific_verdict: null."""
import json
from pathlib import Path

AX = Path("/ph/main_axes71_v2/PHD-MAIN-AXES71-v2")
W = AX / "work/d1"
C = json.loads((W / "counts.json").read_text())
T = json.loads((W / "terms.json").read_text())
X = json.loads((W / "extra.json").read_text())
CASES = list(C["cases"])
KO = {"B0_b10/LoD2": "B0 · LoD2", "B0_b10/ALS": "B0 · 항공 LiDAR", "B173nb_b10/LoD2": "B173 주변 · LoD2", "B173nb_b10/ALS": "B173 주변 · 항공 LiDAR",
      "R1rep_b10/LoD2": "R1 · LoD2", "R1rep_b10/ALS": "R1 · 항공 LiDAR"}


def pa(v):
    return f"{v['patches']:,} · {v['area_m2']:,.1f}"


def sub(a, b):
    return dict(patches=a["patches"] - b["patches"], area_m2=a["area_m2"] - b["area_m2"])


L = []
# ---------------------------------------------------------------- codes
L += ["### 표 0. 평가 범위의 코드별 패치 (패치 · m²)", "", "| 경우 | 평가 범위 | 0 | 2 | 3 | 4 | 5 | 11 | 12 | 13 | 14 |", "|---|---|---|---|---|---|---|---|---|---|---|"]
for k in CASES:
    e = C["cases"][k]
    L.append(f"| {KO[k]} | {pa(e['in_eval'])} | " + " | ".join(pa(e["codes"][c]) for c in ("0", "2", "3", "4", "5", "11", "12", "13", "14")) + " |")
# ---------------------------------------------------------------- (가)
L += ["", "### 표 1. 패치의 사전 정보 어긋남 gt_med 다시 냄", "",
      "| 경우 | gt_med가 있는 패치 (파일 전체) | 소유 행으로 다시 낸 중앙값과의 최대 차 (m) | 수 = gt_n = gt_points | 새 거리 지표 ratio와 같음 | 라벨 규칙과 같음 | 코드 11의 + · − |", "|---|---:|---:|---|---|---|---|"]
for k in CASES:
    g = C["cases"][k]["ga"]
    L.append(f"| {KO[k]} | {g['patches_with_gt_med']:,} | {g['recomputed_max_abs_diff_m']:.1e} | {'예' if g['count_equals_gt_n'] and g['count_equals_gt_points'] else '아니오'} | "
             f"{'예' if g['dist71_ratio_equals'] else '아니오'} | {'예' if g['label_rule_equal'] else '아니오'} | {g['sign_in_eval_code11']['positive']:,} · {g['sign_in_eval_code11']['negative']:,} |")
# ---------------------------------------------------------------- (나)
L += ["", "### 표 2. 코드 3을 정한 영상 깊이 어긋남 (코드 2·3 패치)", "",
      "| 경우 | v2(참값 점 자리, 지붕꼴 5값 이상) | v1_kept(벽꼴, 5값 미만 지붕꼴) | 코드 3 다시 냄 | 코드 12 다시 냄 | 코드 3의 \\|어긋남\\|/τ 중앙값 (5~95 %) | 코드 3에서 MVS가 참값 위 · 아래 |", "|---|---|---|---|---|---|---|"]
for k in CASES:
    n = C["cases"][k]["na"]
    qq = n["code3_misfit_over_tau"]
    L.append(f"| {KO[k]} | {pa(n['v2_patches_code23'])} | {pa(n['v1_kept_patches_code23'])} (벽 {n['v1_kept_by_kind_code23']['wall']:,}) | "
             f"{n['code3_reproduced']:,}/{n['code23']:,} | {n['code12_reproduced']:,}/{n['code1112']:,} | {qq['q50']:.2f} ({qq['q05']:.2f}~{qq['q95']:.1f}) | "
             f"{n['code3_sign']['mvs_above']:,} · {n['code3_sign']['mvs_below']:,} |")
# ---------------------------------------------------------------- (다)
L += ["", "### 표 3. 코드 3의 나눔 (충돌 문턱 kτ)", "",
      "| 경우 | k | 문턱 넘음 (전제 위배) | 문턱 안 | 다시 낸 나눔이 파일과 같음 | \\|MVS − 사전 정보\\|/τ 중앙값: 넘음 · 안 | 넘음의 값 출처 v1_kept · v2 |", "|---|---:|---|---|---|---|---|"]
for k in CASES:
    d = C["cases"][k]["da"]
    ok = d["violation_equal"] and d["within_equal"] and d["band_equal"] and d["disjoint"] and d["union_is_code3"]
    L.append(f"| {KO[k]} | {d['k']:g} | {pa(d['violation'])} | {pa(d['within'])} | {'예' if ok else '아니오'} | "
             f"{d['premise_over_tau_violation']['q50']:.2f} · {d['premise_over_tau_within']['q50']:.2f} | {d['premise_kept_rows']['v1_kept']:,} · {d['premise_kept_rows']['v2']:,} |")
# ---------------------------------------------------------------- (라)
L += ["", "### 표 4. 거른 영상 오류(obs_masked)의 코드 (패치 · m²)", "",
      "| 경우 | 모두 | 코드 2 | 코드 3 (그 가운데 문턱 넘음) | 코드 4 | 지붕꼴 · 벽꼴 | 값의 갈래: 참값 점 · 화소 | \\|v_photo\\|/τ 중앙값 (최소~최대) | 광도 깊이가 참값 위 · 아래 | 마스크 1 화소 몫 중앙값 |", "|---|---|---|---|---|---|---|---|---|---|"]
for k in CASES:
    r = C["cases"][k]["ra"]
    v = r["v_photo_over_tau"]
    L.append(f"| {KO[k]} | {pa(r['obs'])} | {pa(r['obs_by_code']['2'])} | {pa(r['obs_by_code']['3'])} ({r['obs_and_violation']['patches']:,}) | {pa(r['obs_by_code']['4'])} | "
             f"{r['obs_by_kind']['roof']['patches']:,} · {r['obs_by_kind']['wall']['patches']:,} | {r['branch']['gt_points']:,} · {r['branch']['pixels']:,} | "
             f"{v['q50']:.2f} ({v['q00']:.2f}~{v['q100']:.1f}) | {r['v_photo_sign']['photo_above_gt']:,} · {r['v_photo_sign']['photo_below_gt']:,} | {r['mask_share_a1']['q50']:.3f} |")
# ---------------------------------------------------------------- (마)
L += ["", "### 표 5. 결측 패치의 판정 길 (패치 수; 평가 범위)", "",
      "| 경우 | 묶음 | 모두 | 직접 | 빌린 일치 | 빌린 충돌 (전제 위배 이웃에게서) | 섞임 (전제 위배 이웃에게서) | 미판정(근거 부족) |", "|---|---|---:|---:|---:|---|---|---:|"]
for k in CASES:
    p = C["cases"][k]["ma"]["path"]
    for g, nm in (("code4_all", "코드 4"), ("code4_obs", "코드 4 · 거른 영상 오류"), ("code4_not_obs", "코드 4 · 그 밖"), ("code13_all", "코드 13")):
        e = p[g]
        L.append(f"| {KO[k]} | {nm} | {e['all']['patches']:,} | {e['direct']['patches']:,} | {e['borrowed_agree']['patches']:,} | "
                 f"{e['borrowed_conflict']['patches']:,} ({e['borrowed_conflict_from_premise']['patches']:,}) | {e['mixed']['patches']:,} ({e['mixed_from_premise']['patches']:,}) | "
                 f"{e['undetermined_insufficient']['patches']:,} |")
REC = {"B0_b10/LoD2": (108, 97, 22, 44), "B0_b10/ALS": (0, 0, 0, 4), "B173nb_b10/LoD2": (57, 50, 26, 88), "B173nb_b10/ALS": (10, 10, 9, 6),
       "R1rep_b10/LoD2": (99, 98, 139, 42), "R1rep_b10/ALS": (61, 50, 8, 2)}
L += ["", "### 표 6. 고친 판 시험 발주 표 2의 재현", "",
      "| 경우 | 잘못 놓음(코드 4) | 그 가운데 전제 위배 이웃에게서 | 맞게 놓음(코드 13) | 섞임 | 기록과 | 판 B 기록(own_depth_changed)과 |", "|---|---:|---:|---:|---:|---|---|"]
t2_all = True
for k in CASES:
    t = C["cases"][k]["ma"]["table2"]
    v = (t["wrong_release_code4"], t["of_which_from_premise"], t["correct_release_code13"], t["mixed"])
    fb = C["cases"][k]["ma"]["fixB"]
    fbv = (fb["changed_in_eval_code4_conflict"], fb["changed_in_eval_code13_conflict"], fb["changed_in_eval_mixed_4_13"])
    same = v == REC[k]
    t2_all &= same
    L.append(f"| {KO[k]} | {v[0]} | {v[1]} | {v[2]} | {v[3]} | {'같음' if same else '어긋남 ' + str(REC[k])} | "
             f"{'같음' if fbv == (v[0], v[2], v[3]) else '다름 ' + str(fbv)} |")
# ---------------------------------------------------------------- no GT, no patch
L += ["", "### 표 7. 참값 행이 없는 패치 (has_gt 거짓; 패치 · m²)", "",
      "| 경우 | 모두 | 코드 0 | 코드 2~14 (코드별) | gt_points = 0 (모두 코드 0) | has_gt 거짓이나 gt_points > 0 | 코드 0인데 행이 있음 (솎은 행) |", "|---|---|---|---|---|---|---|"]
derived = {}
for k in CASES:
    n = C["cases"][k]["nogt"]
    e = C["cases"][k]
    oth = {c: v["patches"] for c, v in n["no_rows_by_code"].items() if c != "0" and v["patches"]}
    c0r = sub(e["codes"]["0"], n["no_rows_by_code"]["0"])
    derived[k] = dict(code0_with_rows=c0r, code0_with_rows_thinned_rows=n["thinned_rows_by_code"]["0"],
                      coded_no_rows=sub(n["no_rows"], n["no_rows_by_code"]["0"]))
    L.append(f"| {KO[k]} | {pa(n['no_rows'])} | {pa(n['no_rows_by_code']['0'])} | {', '.join(f'{c}: {v}' for c, v in oth.items())} | {pa(n['gt_points_zero'])} | "
             f"{pa(n['no_rows_but_gt_points'])} | {pa(c0r)} ({n['thinned_rows_by_code']['0']:,}) |")
L += ["", "### 표 8. 패치가 없는 장면 참값 점 (dm_common.owner_of_scene_points)", "",
      "| 경우 | 장면 참값 점 | 패치 없음 | 그 가운데 수직면 점 | 패치 있음 | 그 패치가 평가 범위 밖 | 새 거리 지표 기록(패치 있음) |", "|---|---:|---:|---:|---:|---:|---|"]
D71 = {"B0_b10/LoD2": 1739696, "B0_b10/ALS": 1378138, "B173nb_b10/LoD2": 3537798, "B173nb_b10/ALS": 2947910, "R1rep_b10/LoD2": 2348309, "R1rep_b10/ALS": 1717898}
for k in CASES:
    o = C["cases"][k]["nopatch"]
    L.append(f"| {KO[k]} | {o['scene_points']:,} | {o['no_patch']:,} ({100 * o['no_patch'] / o['scene_points']:.1f} %) | {o['no_patch_vertical']:,} | {o['with_patch']:,} | "
             f"{o['with_patch_outside_eval']:,} | {'같음' if o['with_patch'] == D71[k] else '어긋남 ' + str(D71[k])} |")
# ---------------------------------------------------------------- exclusion
L += ["", "### 표 9. 참값에서 뺀 칸 (평가 범위, 0.5 m 칸)", "",
      "| 지역 | 나무 | 일시 물체 | 둘 중 하나(any) | 사전 정보 쪽 나무 (any 밖) | any 안 드론 LiDAR 점 | any 안 주 참값 점 | 사전 정보 쪽 나무(any 밖)의 드론 LiDAR 점 |", "|---|---|---|---|---|---:|---:|---:|"]
for s, v in C["sites"].items():
    x = v["exclusion_cells"]
    g = x["gt_points"]
    L.append(f"| {s} | {x['trees']['cells']:,} · {x['trees']['area_m2']:,.2f} | {x['transient']['cells']:,} · {x['transient']['area_m2']:,.2f} | "
             f"{x['any']['cells']:,} · {x['any']['area_m2']:,.2f} | {x['prior_side_trees_not_any']['cells']:,} · {x['prior_side_trees_not_any']['area_m2']:,.2f} | "
             f"{g['gt_points']['in_any_cells']:,} | {g.get('gt_primary', {}).get('in_any_cells', '—') if 'gt_primary' not in g else format(g['gt_primary']['in_any_cells'], ',')} | "
             f"{g['gt_points']['in_prior_side_trees_not_any']:,} |")
L += ["", "### 표 10. 제외 칸 때문에 참값을 쓰지 않은 패치 (평가 범위; 패치 · m²)", "",
      "| 경우 | 제외 패치 (모두 코드 0) | 나무·일시 물체 | 사전 정보 쪽 나무만 | 코드 0 가운데 5점 미만(제외 아님) |", "|---|---|---|---|---|"]
for k in CASES:
    x = C["cases"][k]["excl_patches"]
    L.append(f"| {KO[k]} | {pa(x['excluded'])} | {pa(x['trees_transient'])} | {pa(x['prior_side_trees_only'])} | {pa(x['code0_lt5_not_excluded'])} |")
# ---------------------------------------------------------------- size
L += ["", "### 표 11. 패치의 크기와 간격 (평가 범위)", "",
      "| 경우 | 넓이 중앙값 (m²) | 넓이 5~95 % | 최소 | 이웃 중심 거리 중앙값 3차원 (m) | 3차원 5~95 % | 평면 중앙값 (m) |", "|---|---:|---|---:|---:|---|---:|"]
for k in CASES:
    z = C["cases"][k]["size"]
    a, n3 = z["area_all"], z["nn_centre_3d_m"]
    L.append(f"| {KO[k]} | {a['q50']:.4f} | {a['q05']:.4f}~{a['q95']:.4f} | {a['q00']:.4f} | {n3['q50']:.4f} | {n3['q05']:.4f}~{n3['q95']:.4f} | {z['nn_centre_xy_m']['q50']:.4f} |")
# ---------------------------------------------------------------- terms
pc = T["per_case"]
L += ["", "### 표 12. 경우마다의 τ와 두 항의 값 (한 화소, n_px = 1, λ = 0.05, f = 1)", "",
      "| 경우 | 면 | τ (cm) | 사전 정보 항 끝값 λ·3τ | 판 A w: 읽기 L (w/τ, 학습) | 판 A w: 읽기 T (w/τ, 학습) | 5τ에서 MVS 항 λ·5τ |", "|---|---|---:|---:|---|---|---:|"]
for k, v in pc.items():
    for kn, e in v.items():
        fa, fb = e["fixA_L"], e["fixA_T"]
        L.append(f"| {KO[k]} | {'지붕' if kn == 'roof' else '벽'} | {100 * e['tau_m']:.2f} | {e['cap_loss']:.5f} | {100 * fa['w_m']:.2f} ({fa['w_over_tau']:.2f}, {'함' if fa['trained'] else '안 함'}) | "
                 f"{100 * fb['w_m']:.2f} ({fb['w_over_tau']:.2f}, {'함' if fb['trained'] else '안 함'}) | {e['mvs_a1']['5tau']['loss']:.5f} |")
(W / "tables_md.md").write_text("\n".join(L) + "\n")

# ---------------------------------------------------------------- the json of the draft
SRC = dict(
    region_file="S1/regions_v3/regions_ext_v3_<site>_<prior>.npz", rows="S1/defs/<site>/rows_<prior>.npz", obs="SL/work/obs_masked/region_<site>_<prior>.npz",
    borrow="SL/work/undecidable/borrow_<site>_<prior>.npz", dry="S3/checks/dry/r14_<site>_<prior>/model/monitor/locations.npz",
    labels="S1/v3/box_gt/<site>/labels_<prior>.npz (B0: labels_uls_<prior>.npz도)", owner="S1/v3/box_gt/<site>/gt_owner_<prior>.npz (B0 장면 점: gt_owner_uls_<prior>.npz)",
    exclusion="S1/v3/box_gt/<site>/exclusion_cells.npz", gt_classes="S1/defs/<site>/gt_classes.npz", fixB="FT/runs/<site>/fixB_<prior>_s0/model/monitor/locations.npz",
    w="FT/prep/w_decision_L.json, w_decision_T.json", figure="docs/experiments/phd/main_axes71_v2/figures/일1_두항의꼴.{png,pdf,json}")
out = dict(task_id="PHD-MAIN-AXES71-v2", item="일 1 정의 확인 — 수와 넓이, 다시 낸 확인, 두 항의 꼴", written=C["written"], new="[이 발주에서 냄]",
           scripts=["scripts/phd/main_axes71_v2/d1_counts.py", "scripts/phd/main_axes71_v2/d1_terms.py", "scripts/phd/main_axes71_v2/d1_extra.py",
                    "scripts/phd/main_axes71_v2/d1_assemble.py"],
           scope="평가 범위(영역 파일 in_eval) 안, 넓이 m², 반올림 전", sources=SRC, table2_reproduced=bool(t2_all),
           cases=C["cases"], sites=C["sites"], derived=derived, fixB_by_code=X,
           terms=dict(lambda_mvs=T["lambda_"], lambda_prior=T["lambda_"], receipts=T["receipts"], code=T["code"], r16_switches_off_equal_r15=T["r16_switches_off_equal_r15"],
                      per_case=T["per_case"]),
           scientific_verdict=None)
Path("/docs/tables").mkdir(parents=True, exist_ok=True)
Path("/docs/tables/일1_정의확인.json").write_text(json.dumps(out, ensure_ascii=False, indent=1))
print("ok table2", t2_all, len("\n".join(L)))
