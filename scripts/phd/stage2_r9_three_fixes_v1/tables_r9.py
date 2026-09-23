"""PHD-STAGE2-R9-THREE-FIXES-v1 step 14 (jointbuildgs:dev, CPU): Markdown tables of the three fixes, the four cases and the
protection over time, every cell 'r9 (r8)'.

  python tables_r9.py      # reads /p9/cases/{cases.json, fixes.json} and /r8/cases/cases.json; writes /p9/cases/tables.md"""
import json
from pathlib import Path

P9 = Path("/p9"); R8 = Path("/r8")
R = json.loads((P9 / "cases/cases.json").read_text())
R8C = json.loads((R8 / "cases/cases.json").read_text())
FX = json.loads((P9 / "cases/fixes.json").read_text())
RUNS = ["M_N", "M_N_noprior", "M_B", "L_N", "L_B"]
NAME = {"M_N": "LoD2 정상", "M_B": "LoD2 주지붕 +1 m", "L_N": "항공 LiDAR 정상", "L_B": "항공 LiDAR 주지붕 +1 m",
        "M_N_noprior": "LoD2 정상, 깊이 항 끔"}
KIND = {"roof": "지붕 패치", "wall": "벽 패치", "no_patch": "패치 없음", "injected": "주입한 면 (지붕 패치)", "": "합"}
md = []


def cm(x, sign=False):
    return "–" if x is None or x != x else (f"{x:+.1f}" if sign else f"{x:.1f}")


def pc(x):
    return "–" if x is None or x != x else f"{100 * x:.1f} %"


def n0(x):
    return "–" if x is None else f"{x:,}"


def dg(x, nd=1):
    return "–" if x is None or x != x else f"{x:.{nd}f}°"


def mm(x):
    return "–" if x is None or x != x else f"{x:.0f}"


def P(f, a, b, **kw):
    """'r9 (r8)'."""
    return f"{f(a, **kw)} ({f(b, **kw)})"


def g(src, run, key):
    return src.get(run, {}).get(key, {"n": 0})


# ================================================================== the three fixes
md.append("## 세 고침의 확인 — 칸마다 r9 (r8)\n")
# ---------------- na
md.append("### 표 나-1. 다시 읽을 때마다 보호 중 지지·충돌 패치 위에 있는 사전 정보 가우시안 (r8 표 5의 열)\n")
its = [r["iteration"] for r in FX["na"]["M_N"]["per_read"]]
md.append("| 학습 | " + " | ".join(f"{i:,}회" for i in its) + " |")
md.append("|---|" + "---|" * len(its))
for run in RUNS:
    pr = FX["na"][run]["per_read"]
    md.append(f"| {NAME[run]} | " + " | ".join(P(n0, r["r9_locked_on_support_conflict"], r["r8_locked_on_support_conflict"]) for r in pr) + " |")
md.append("")
md.append("**표 나-1b. r9가 지지·충돌 패치라서 보호에서 뺀 수 (가우시안 신뢰도 < 0.5 · uᵢ ≤ 4τ인데 패치의 판정이 충돌) / 그 자리의 사전 정보 가우시안 수**\n")
md.append("| 학습 | " + " | ".join(f"{i:,}회" for i in its) + " |")
md.append("|---|" + "---|" * len(its))
for run in RUNS:
    pr = FX["na"][run]["per_read"]
    md.append(f"| {NAME[run]} | " + " | ".join(f"{n0(r['r9_excluded_support_conflict'])} / {n0(r['r9_prior_on_support_conflict'])}" for r in pr) + " |")
md.append("")
md.append("### 표 나-2. 3,500회: 지지·충돌 패치 위의 사전 정보 가우시안과, 지지·충돌 패치에서 출발한 처음 가우시안의 제거\n")
md.append("| 학습 | 끝에 이 패치 위 | 불투명도 중앙값 | 불투명도 ≥ 0.5 | 보호됨 | 마지막 다시 읽기에서 본 시점 없음 (새 표면 뒤) | 그 가운데 불투명도 ≥ 0.5 | 처음 가우시안 | 3,000회까지 제거 | 3,001–3,500회 제거 |")
md.append("|---|---|---|---|---|---|---|---|---|---|")
for run in RUNS:
    a, b = FX["na"][run]["r9"], FX["na"][run]["r8"]
    md.append(f"| {NAME[run]} | {P(n0, a['end_on_support_conflict'], b['end_on_support_conflict'])} | {P(lambda x: f'{x:.2f}', a['end_opacity_p50'], b['end_opacity_p50'])} | "
              f"{P(pc, a['end_share_opacity_ge_05'], b['end_share_opacity_ge_05'])} | {P(n0, a['end_protected'], b['end_protected'])} | "
              f"{P(n0, a['end_behind'], b['end_behind'])} | {P(n0, a['end_opaque_behind'], b['end_opaque_behind'])} | "
              f"{P(n0, a['initial_disks_on_support_conflict'], b['initial_disks_on_support_conflict'])} | {P(n0, a['removed_by_3000'], b['removed_by_3000'])} | "
              f"{P(n0, a['removed_after_3000'], b['removed_after_3000'])} |")
md.append("")
md.append("### 표 나-3. 발주문이 지목한 면: 3,500회에 지지·충돌 패치 위의 사전 정보 가우시안 (수 · 불투명도 ≥ 0.5 · 보호됨 · 불투명하고 새 표면 뒤)\n")
md.append("| 학습 | 면 | 수 | 불투명도 ≥ 0.5 | 보호됨 | 불투명하고 본 시점 없음 |")
md.append("|---|---|---|---|---|---|")
for run in ("M_N", "L_N"):
    for e, a in FX["na"][run]["r9"]["by_face"].items():
        b = FX["na"][run]["r8"]["by_face"][e]
        md.append(f"| {NAME[run]} | {('면 ' if run.startswith('M') else '표면 ') + e} | {P(n0, a['n'], b['n'])} | {P(n0, a['opaque'], b['opaque'])} | "
                  f"{P(n0, a['protected'], b['protected'])} | {P(n0, a['opaque_behind'], b['opaque_behind'])} |")
md.append("")
# ---------------- da
md.append("### 표 다-1. 사전 정보 가우시안의 법선과 사전 정보 면 법선이 이루는 각 (방향 없는 각, 중앙값 / 95 %)\n")
md.append("r8의 '처음'은 기반 구현의 무작위 사원수를 재현한 값이다(r8_initial_quaternions: 같은 시드의 같은 추첨, r8 비가시 가우시안의 끝 법선과 중앙값 0.1–0.3° 차이).\n")
md.append("| 학습 | 가우시안 | 수 (끝) | 처음: 중앙값 | 처음: 95 % | 3,500회: 중앙값 | 3,500회: 95 % |")
md.append("|---|---|---|---|---|---|---|")
GRP = (("invisible", "비가시 패치에서 심은 것"), ("visible", "보이는 패치(지지·결측)에서 심은 것"), ("no_patch", "패치 없음 (항공 LiDAR 지면·가파른 삼각형)"))
for run in RUNS:
    for k, lab in GRP:
        d = FX["da_angles"][run][k]
        if not d["r9_end"]["n"] and not d["r8_end"]["n"]:
            continue
        md.append(f"| {NAME[run]} | {lab} | {P(n0, d['r9_end']['n'], d['r8_end']['n'])} | {P(dg, d['r9_start']['p50'], d['r8_start']['p50'])} | "
                  f"{P(dg, d['r9_start']['p95'], d['r8_start']['p95'])} | {P(dg, d['r9_end']['p50'], d['r8_end']['p50'])} | {P(dg, d['r9_end']['p95'], d['r8_end']['p95'])} |")
md.append("")
md.append("### 표 다-2. 메시에 담겼는가와 메시 면이 사전 정보 면에서 얼마나 떨어졌는가\n")
md.append("겨냥한 가우시안 = 학습 시점이 보지 못하는 대상 건물 바깥면의 사전 정보 가우시안(불투명도 ≥ 0.5). 메시 → 사전 정보 거리는 겨냥한 가우시안의 처음 자리에서 0.5 m 안에 있는 메시 꼭짓점에서 잰다.\n")
md.append("| 학습 | 겨냥한 가우시안 | 메시 0.25 m 안: 학습 시점만 | 메시 0.25 m 안: 시점을 더함 | 메시 → 사전 정보 (시점을 더함): 중앙값 · 95 % (cm) | 메시 → 사전 정보 (학습 시점만): 중앙값 · 95 % (cm) |")
md.append("|---|---|---|---|---|---|")
for run in RUNS:
    d = FX["da_mesh"][run]; k = d["aimed_key"]
    a, b = d["r9"][k], d["r8"][[kk for kk in d["r8"] if kk.startswith("target outward")][0]]
    m9, m8 = d["mesh_to_prior"]["r9"], d["mesh_to_prior"]["r8"]

    def dd(m, name):
        x = m.get(name, {})
        return "–" if not x.get("n_vertices_near") else f"{100 * x['p50_m']:.1f} · {100 * x['p95_m']:.1f}"
    md.append(f"| {NAME[run]} | {P(n0, a['n'], b['n'])} | {P(pc, a['train']['within_0.25m'], b['train']['within_0.25m'])} | "
              f"{P(pc, a['train_virtual']['within_0.25m'], b['train_virtual']['within_0.25m'])} | {dd(m9, 'mesh_train_virtual')} ({dd(m8, 'mesh_train_virtual')}) | "
              f"{dd(m9, 'mesh_train')} ({dd(m8, 'mesh_train')}) |")
md.append("")
md.append("**표 다-3. 시점을 더한 메시의 0.25 m 안 비율을 가르기**: 같은 r9 장면을 r8의 더한 카메라 16대로 메시화한 값(카메라 자리의 효과를 뺀 비교)과, 겨냥한 가우시안이 처음 앉은 면별 값\n")
md.append("| 학습 | r9, r9 카메라 | r9, r8 카메라 | r8, r8 카메라 | 면별 (수: r9 카메라 / r8 카메라 / r8) |")
md.append("|---|---|---|---|---|")
for run in RUNS:
    d = FX["da_mesh"][run]; k = d["aimed_key"]
    k8 = [kk for kk in d["r8"] if kk.startswith("target outward")][0]
    v = d.get("r9_with_r8_cameras")
    pf9, pf8 = d["per_face"]["r9"], d["per_face"]["r8"]
    pfv = v["per_face"] if v else {}
    faces = sorted(set(pf9) | set(pf8), key=lambda f_: -max(pf9.get(f_, {}).get("train_virtual", {}).get("n", 0), pf8.get(f_, {}).get("train_virtual", {}).get("n", 0)))[:5]

    def w(pf, f_):
        x = pf.get(f_, {}).get("train_virtual")
        return "–" if not x else f"{pc(x['within_025'])}"
    per = "; ".join(f"{f_} ({n0(pf9.get(f_, {}).get('train_virtual', {}).get('n', 0))}): {w(pf9, f_)} / {w(pfv, f_)} / {w(pf8, f_)}" for f_ in faces)
    md.append(f"| {NAME[run]} | {pc(d['r9'][k]['train_virtual']['within_0.25m'])} | {pc(v['groups'][k]['train_virtual']['within_0.25m']) if v else '–'} | "
              f"{pc(d['r8'][k8]['train_virtual']['within_0.25m'])} | {per} |")
md.append("")
# ---------------- ra
md.append("### 표 라-1. LoD2 바닥면에서 심긴 가우시안과 보호 수\n")
md.append("| 학습 | 바닥면에서 심음 (대상 건물) | 끝에 남음 (대상 건물) | 끝에 남은 것 중 불투명도 ≥ 0.5 · 보호됨 | 처음 보호 (그 가운데 바닥면) | 끝 보호 (그 가운데 바닥면) |")
md.append("|---|---|---|---|---|---|")
for run in ("M_N", "M_N_noprior", "M_B"):
    a, b = FX["ra"][run]["r9"], FX["ra"][run]["r8"]
    md.append(f"| {NAME[run]} | {n0(a['planted_on_bottom'])} ({n0(a['planted_on_target_bottom'])}) — r8 {n0(b['planted_on_bottom'])} ({n0(b['planted_on_target_bottom'])}) | "
              f"{n0(a['end_on_bottom'])} ({n0(a['end_on_target_bottom'])}) — r8 {n0(b['end_on_bottom'])} ({n0(b['end_on_target_bottom'])}) | "
              f"{n0(a['end_on_bottom_opaque'])} · {n0(a['end_on_bottom_protected'])} — r8 {n0(b['end_on_bottom_opaque'])} · {n0(b['end_on_bottom_protected'])} | "
              f"{n0(a['protected_start'])} ({n0(a['protected_start_on_bottom'])}) — r8 {n0(b['protected_start'])} ({n0(b['protected_start_on_bottom'])}) | "
              f"{n0(a['protected_end'])} ({n0(a['protected_end_on_bottom'])}) — r8 {n0(b['protected_end'])} ({n0(b['protected_end_on_bottom'])}) |")
md.append("")
sw = FX["ra"]["shared_walls"]
md.append("### 표 라-2. 이웃 건물과 맞댄 벽 (두 건물의 벽면이 0.1 m 안에서 겹치고 바깥 법선이 반대; LoD2 정상의 패치)\n")
md.append("| 맞댄 벽 면 | 그 가운데 대상 건물 면 | 맞댄 패치 (넓이) | 패치 상태: 비가시 · 지지 · 결측 | 끝에 이 패치 위 가우시안 r9 LoD2 정상: 수 · 불투명도 ≥ 0.5 · 보호됨 | 같은 칸 r8 |")
md.append("|---|---|---|---|---|---|")
bs = sw["by_state"]
a, b = sw["r9_M_N_end"], sw["r8_M_N_end"]
md.append(f"| {len(sw['polygons'])}개 ({', '.join(str(x) for x in sw['polygons'][:12])}{' …' if len(sw['polygons']) > 12 else ''}) | {len(sw['target_building_polygons'])}개 | "
          f"{n0(sw['n_shared_cells'])} ({sw['shared_area_m2']:.1f} m²) | {n0(bs.get('invisible'))} · {n0(bs.get('support'))} · {n0(bs.get('missing'))} | "
          f"{n0(a['n'])} · {n0(a['opaque'])} · {n0(a['protected'])} | {n0(b['n'])} · {n0(b['opaque'])} · {n0(b['protected'])} |")
md.append("")
dep = FX["ra"]["opacity_reset"]
md.append("### 표 라-3. 불투명도 초기화(3,000회) 전후의 렌더링 깊이와 누적 불투명도 (학습 시점 13장, 대상 건물의 지붕·벽 픽셀)\n")
md.append("| 학습 | \\|D(3,001) − D(3,000)\\| 중앙값 · 95 % (m) | 1 m 넘게 바뀐 픽셀 · 10 m 넘게 | \\|D(3,050) − D(3,000)\\| 중앙값 · 95 % (m) | 1 m 넘게 · 10 m 넘게 | 누적 불투명도 중앙값 3,000 → 3,001 → 3,050 | 누적 불투명도 < 0.5인 픽셀 3,000 → 3,001 → 3,050 |")
md.append("|---|---|---|---|---|---|---|")
for tag, lab in (("r9", "r9 LoD2 정상 (바닥면 뺌)"), ("ctrl", "대조: r8 코드 그대로 (바닥면 포함)")):
    t = dep[tag]["total"]
    md.append(f"| {lab} | {t['d3001']['p50']:.3f} · {t['d3001']['p95']:.3f} | {pc(t['d3001']['share_gt_1m'])} · {pc(t['d3001']['share_gt_10m'])} | "
              f"{t['d3050']['p50']:.3f} · {t['d3050']['p95']:.3f} | {pc(t['d3050']['share_gt_1m'])} · {pc(t['d3050']['share_gt_10m'])} | "
              f"{t['alpha3000']['p50']:.2f} → {t['alpha3001']['p50']:.2f} → {t['alpha3050']['p50']:.2f} | "
              f"{pc(t['alpha3000']['share_lt_05'])} → {pc(t['alpha3001']['share_lt_05'])} → {pc(t['alpha3050']['share_lt_05'])} |")
rv = dep["representative_view"]
md.append("")
md.append(f"대표 시점(그림): {rv} — 대조 학습에서 \\|D(3,001) − D(3,000)\\|의 95 %가 가장 큰 학습 시점.\n")
for tag, lab in (("r9", "r9"), ("ctrl", "대조")):
    v = dep[tag]["per_view"][rv]
    md.append(f"- {lab}: 대표 시점 \\|ΔD\\| 3,001회 중앙값 {v['d3001']['p50']:.3f} m, 95 % {v['d3001']['p95']:.3f} m, 1 m 넘게 {pc(v['d3001']['share_gt_1m'])}; "
              f"누적 불투명도 < 0.5 {pc(v['alpha3000']['share_lt_05'])} → {pc(v['alpha3001']['share_lt_05'])} → {pc(v['alpha3050']['share_lt_05'])}")
cv = dep["control_vs_r8"]
mism = [r for r in cv if r["control"] != r["r8"]]
txt = "모두 같다" if not mism else "다르다: " + ", ".join("%d회 %s 대 %s" % (r["iteration"], n0(r["control"]), n0(r["r8"])) for r in mism)
md.append(f"- 대조 학습이 r8 LoD2 정상과 같은 보호 수를 다시 냈는가 (1–3,000회 다시 읽기 {len(cv)}번): {txt}")
md.append("")

# ================================================================== the four cases (r8 report tables 1 - 4-3)
md.append("## 네 경우 — 칸마다 r9 (r8)\n")
md.append("### 표 1. 관측 있음 · 허용 오차 안 (cₚ = 1, gₚ = 1)\n")
md.append("| 학습 | 픽셀 | 수 | 결과 − MVS, 중앙값 \\|·\\| (cm) | MVS에서 τ 안 | 결과 − 사전 정보, 중앙값 \\|·\\| (cm) | 사전 정보에서 τ 안 |")
md.append("|---|---|---|---|---|---|---|")
for run in RUNS:
    for sub in ("|roof", "|wall", "|no_patch", ""):
        a, b = g(R, run, "c1" + sub), g(R8C, run, "c1" + sub)
        if a["n"] == 0:
            continue
        md.append(f"| {NAME[run]} | {KIND[sub.strip('|')]} | {P(n0, a['n'], b['n'])} | {P(cm, a['median_abs_dM_cm'], b['median_abs_dM_cm'])} | "
                  f"{P(pc, a['within_tau_of_mvs'], b['within_tau_of_mvs'])} | {P(cm, a['median_abs_dP_cm'], b['median_abs_dP_cm'])} | {P(pc, a['within_tau_of_prior'], b['within_tau_of_prior'])} |")
md.append("")
md.append("**표 1-2. LoD2 정상: 사전 정보 깊이 항을 켠 학습과 끈 학습 (같은 픽셀; 칸 = 켬 / 끔, 괄호 r8)**\n")
md.append("| 픽셀 | 결과 − MVS \\|·\\| (cm) | MVS에서 τ 안 | 결과 − 사전 정보 \\|·\\| (cm) | 사전 정보에서 τ 안 |")
md.append("|---|---|---|---|---|")
for sub in ("|roof", "|wall", ""):
    a, b = g(R, "M_N", "c1" + sub), g(R, "M_N_noprior", "c1" + sub)
    a8, b8 = g(R8C, "M_N", "c1" + sub), g(R8C, "M_N_noprior", "c1" + sub)
    if a["n"] == 0:
        continue
    md.append(f"| {KIND[sub.strip('|')]} ({n0(a['n'])}) | {cm(a['median_abs_dM_cm'])} / {cm(b['median_abs_dM_cm'])} ({cm(a8['median_abs_dM_cm'])} / {cm(b8['median_abs_dM_cm'])}) | "
              f"{pc(a['within_tau_of_mvs'])} / {pc(b['within_tau_of_mvs'])} ({pc(a8['within_tau_of_mvs'])} / {pc(b8['within_tau_of_mvs'])}) | "
              f"{cm(a['median_abs_dP_cm'])} / {cm(b['median_abs_dP_cm'])} ({cm(a8['median_abs_dP_cm'])} / {cm(b8['median_abs_dP_cm'])}) | "
              f"{pc(a['within_tau_of_prior'])} / {pc(b['within_tau_of_prior'])} ({pc(a8['within_tau_of_prior'])} / {pc(b8['within_tau_of_prior'])}) |")
md.append("")
md.append("### 표 2. 관측 있음 · 허용 오차 밖 (충돌로 판정된 지지 패치의 cₚ = 1 픽셀; 항공 LiDAR는 패치 없는 cₚ = 1 충돌 픽셀도)\n")
md.append("| 학습 | 픽셀 | 수 | MVS에서 τ 안 | 사전 정보에서 τ 안 | 결과 − MVS, 중앙값 \\|·\\| (cm) | 결과 − 사전 정보, 부호 중앙값 (cm) |")
md.append("|---|---|---|---|---|---|---|")
for run in RUNS:
    for key, lab in (("c2|roof", "지붕 패치"), ("c2|wall", "벽 패치"), ("c2|injected", "주입한 면 (지붕 패치)"), ("c2", "패치 합"), ("c2_no_patch", "패치 없음 (충돌 표시)")):
        a, b = g(R, run, key), g(R8C, run, key)
        if a["n"] == 0:
            continue
        md.append(f"| {NAME[run]} | {lab} | {P(n0, a['n'], b['n'])} | {P(pc, a['within_tau_of_mvs'], b['within_tau_of_mvs'])} | {P(pc, a['within_tau_of_prior'], b['within_tau_of_prior'])} | "
                  f"{P(cm, a['median_abs_dM_cm'], b['median_abs_dM_cm'])} | {P(cm, a['median_dP_cm'], b['median_dP_cm'], sign=True)} |")
md.append("")
md.append("### 표 3. 관측 없음 · 영상에 찍힘 (결측 패치의 cₚ = 0 픽셀, 전파받은 판정별)\n")
md.append("결과 − 사전 정보의 부호: + = 결과가 사전 정보보다 카메라에서 멀다(지붕이면 아래). 참값 열은 해석을 돕는 참고값이다.\n")
md.append("| 학습 | 전파받은 판정 (gₚ) | 수 | 결과 − 사전 정보, 부호 중앙값 (cm) | 사전 정보에서 τ 안 | 세워진 비율 | 참고: 결과 − 참값 \\|·\\| (cm) · 참값에서 τ 안 |")
md.append("|---|---|---|---|---|---|---|")
JL = (("c3_agree", "일치 (1)"), ("c3_conflict", "충돌 (0)"), ("c3_undetermined", "미판정 (1)"))
for run in RUNS:
    for key, lab in JL:
        a, b = g(R, run, key), g(R8C, run, key)
        if a["n"] == 0:
            continue
        md.append(f"| {NAME[run]} | {lab} | {P(n0, a['n'], b['n'])} | {P(cm, a['median_dP_cm'], b['median_dP_cm'], sign=True)} | {P(pc, a['within_tau_of_prior'], b['within_tau_of_prior'])} | "
                  f"{P(pc, a['built_share'], b['built_share'])} | {P(cm, a['median_abs_dG_cm'], b['median_abs_dG_cm'])} · {P(pc, a['within_tau_of_gt'], b['within_tau_of_gt'])} |")
md.append("")
md.append("**표 3-2. 변화를 넣은 설정: 주입한 면의 결측 패치 (cₚ = 0)**\n")
md.append("| 학습 | 전파받은 판정 | 수 | 올린 사전 정보에서 τ 안 | 올리기 전 높이에서 τ 안 | 결과 − 올린 사전 정보, 부호 중앙값 (cm) | 세워진 비율 |")
md.append("|---|---|---|---|---|---|---|")
for run in ("M_B", "L_B"):
    for key, lab in (("c3_conflict|injected", "충돌 (0)"), ("c3_undetermined|injected", "미판정 (1)"), ("c3_agree|injected", "일치 (1)")):
        a, b = g(R, run, key), g(R8C, run, key)
        if a["n"] == 0:
            continue
        md.append(f"| {NAME[run]} | {lab} | {P(n0, a['n'], b['n'])} | {P(pc, a['within_tau_of_raised'], b.get('within_tau_of_raised'))} | {P(pc, a['within_tau_of_nominal'], b.get('within_tau_of_nominal'))} | "
                  f"{P(cm, a['median_dP_cm'], b.get('median_dP_cm'), sign=True)} | {P(pc, a['built_share'], b.get('built_share'))} |")
md.append("")
md.append("**표 3-3. 관측 없음 · 영상에 찍힘의 나머지 픽셀** (지지 패치의 cₚ = 0 픽셀, 패치 없는 cₚ = 0 픽셀)\n")
md.append("| 학습 | 픽셀 (gₚ) | 수 | 결과 − 사전 정보, 부호 중앙값 (cm) | 사전 정보에서 τ 안 | 세워진 비율 |")
md.append("|---|---|---|---|---|---|")
for run in RUNS:
    for key, lab in (("x_support_c0_agree", "지지 패치 · 표 일치 (1)"), ("x_support_c0_conflict", "지지 패치 · 표 충돌 (0)"), ("x_no_patch_c0", "패치 없음 (1)")):
        a, b = g(R, run, key), g(R8C, run, key)
        if a["n"] == 0:
            continue
        md.append(f"| {NAME[run]} | {lab} | {P(n0, a['n'], b['n'])} | {P(cm, a['median_dP_cm'], b['median_dP_cm'], sign=True)} | {P(pc, a['within_tau_of_prior'], b['within_tau_of_prior'])} | {P(pc, a['built_share'], b['built_share'])} |")
md.append("")
md.append("### 표 4. 영상에 찍히지 않음 (비가시 패치에서 심은 가우시안)\n")
md.append("| 학습 | 처음 | 끝 (처음 가우시안 가운데 남음) | 끝 불투명도 ≥ 0.5 | uᵢ 중앙값 · 99 % (mm) | 3차원 이동 중앙값 (mm) | 끝에 보호됨 | 마지막 다시 읽기에서 본 시점 없음 |")
md.append("|---|---|---|---|---|---|---|---|")
for run in RUNS:
    a, b = R[run]["case4"], R8C[run]["case4"]
    md.append(f"| {NAME[run]} | {P(n0, a['n_initial'], b['n_initial'])} | {P(n0, a['n_initial_ids_alive'], b['n_initial_ids_alive'])} | {P(pc, a['share_end_opacity_ge_05'], b['share_end_opacity_ge_05'])} | "
              f"{mm(a['u_median_mm'])} · {mm(a['u_p99_mm'])} ({mm(b['u_median_mm'])} · {mm(b['u_p99_mm'])}) | {P(mm, a['drift3d_median_mm'], b['drift3d_median_mm'])} | "
              f"{P(n0, a['protected_end'], b['protected_end'])} | {P(n0, a['no_seeing_view_last_read'], b['no_seeing_view_last_read'])} |")
md.append("")
md.append("**표 4-2. 메시에 담겼는가** (TSDF 0.10 m 칸; 가우시안 중심에서 메시 면까지 0.25 m 안 비율 — 학습 시점만 / 시점을 더함)\n")
md.append("| 학습 | 대상 건물 바깥면의 비가시 가우시안 (불투명도 ≥ 0.5) | 대상 건물 바닥면 | 그 밖의 비가시 사전 정보 | 참고: 보이는 사전 정보 |")
md.append("|---|---|---|---|---|")


def gm(groups, prefix):
    k = [kk for kk in groups if kk.startswith(prefix)]
    return groups[k[0]] if k else {"n": 0}


def cell(a, b):
    def one(x):
        return "0개" if not x.get("n") else f"{x['n']:,}개: {pc(x['train']['within_0.25m'])} / {pc(x['train_virtual']['within_0.25m'])}"
    return f"{one(a)} ({one(b)})"


for run in RUNS:
    a = R[run]["case4"].get("mesh") or json.loads((P9 / "mesh" / run / "mesh.json").read_text())["groups"]
    b = R8C[run]["case4"].get("mesh") or json.loads((R8 / "mesh" / run / "mesh.json").read_text())["groups"]
    md.append(f"| {NAME[run]} | {cell(gm(a, 'target outward'), gm(b, 'target outward'))} | {cell(gm(a, 'target bottom'), gm(b, 'target bottom'))} | "
              f"{cell(gm(a, 'other invisible'), gm(b, 'other invisible'))} | {cell(gm(a, 'seen prior'), gm(b, 'seen prior'))} |")
md.append("")
md.append("**표 4-3. 지지 영역 충돌 패치 위에서 끝에 보호된 가우시안** (r9는 식 (7)이 패치의 판정으로 뺀다)\n")
md.append("| 학습 | 끝에 보호된 사전 정보 가우시안 | 그 가운데 지지 · 충돌 패치 위 | 그 가운데 본 시점 없음 |")
md.append("|---|---|---|---|")
for run in RUNS:
    a, b = R[run]["case4"], R8C[run]["case4"]
    md.append(f"| {NAME[run]} | {P(n0, a['protected_total'], b['protected_total'])} | {P(n0, a['protected_on_support_conflict']['n'], b['protected_on_support_conflict']['n'])} | "
              f"{P(n0, a['protected_on_support_conflict']['no_seeing_view'], b['protected_on_support_conflict']['no_seeing_view'])} |")
md.append("")

# ================================================================== spread and attribution (extra runs)
EXF = P9 / "cases/cases_extra.json"
if EXF.exists():
    EXR = json.loads(EXF.read_text())
    md.append("## 흔들림과 고침별 몫 — 같은 코드를 다시 돌린 r8과, 처음 방향(다)만 끈 r9\n")
    md.append("같은 코드·같은 입력의 r8을 한 번 더 돌린 값(r8 다시)이 두 r8 사이의 흔들림이다. r9와 'r9, 다 끔'의 차이가 처음 방향 고침(다)의 몫이고, "
              "'r9, 다 끔'과 r8의 차이가 나머지 고침(나, LoD2는 라도)의 몫이다.\n")
    METRICS = [("c1|roof", "within_tau_of_mvs", "경우 1 지붕: MVS에서 τ 안"), ("c1|roof", "within_tau_of_prior", "경우 1 지붕: 사전 정보에서 τ 안"),
               ("c1|wall", "within_tau_of_prior", "경우 1 벽: 사전 정보에서 τ 안"), ("c1|no_patch", "within_tau_of_prior", "경우 1 패치 없음: 사전 정보에서 τ 안"),
               ("c2", "within_tau_of_mvs", "경우 2: MVS에서 τ 안"), ("c2_no_patch", "within_tau_of_mvs", "경우 2 패치 없음: MVS에서 τ 안"),
               ("c3_agree", "within_tau_of_prior", "경우 3 일치: 사전 정보에서 τ 안"), ("c3_undetermined", "within_tau_of_prior", "경우 3 미판정: 사전 정보에서 τ 안"),
               ("c3_conflict", "built_share", "경우 3 충돌: 세워진 비율"),
               ("x_support_c0_agree", "within_tau_of_prior", "지지·일치 패치의 cₚ 0 픽셀: 사전 정보에서 τ 안"),
               ("x_support_c0_conflict", "within_tau_of_prior", "지지·충돌 패치의 cₚ 0 픽셀: 사전 정보에서 τ 안")]
    for base, rep8, nor in (("M_N", "r8rep_M_N", "M_N_noorient"), ("L_N", "r8rep_L_N", "L_N_noorient")):
        if rep8 not in EXR or nor not in EXR:
            continue
        md.append(f"**표 S-{base}. {NAME[base]}** (칸 = 비율)\n")
        md.append("| 값 | r8 | r8 다시 | r9 | r9, 다 끔 |")
        md.append("|---|---|---|---|---|")
        for key, fld, lab in METRICS:
            vals = [R8C[base].get(key, {}).get(fld), EXR[rep8].get(key, {}).get(fld), R[base].get(key, {}).get(fld), EXR[nor].get(key, {}).get(fld)]
            if all(v is None for v in vals):
                continue
            md.append(f"| {lab} | " + " | ".join(pc(v) for v in vals) + " |")
        a4 = [R8C[base]["case4"], EXR[rep8]["case4"], R[base]["case4"], EXR[nor]["case4"]]
        md.append("| 경우 4: 끝 불투명도 ≥ 0.5 | " + " | ".join(pc(x["share_end_opacity_ge_05"]) for x in a4) + " |")
        if base == "M_N" and "mesh_aimed" in EXR.get(rep8, {}) and "mesh_aimed" in EXR.get(nor, {}):
            d = FX["da_mesh"][base]
            k9, k8 = d["aimed_key"], [kk for kk in d["r8"] if kk.startswith("target outward")][0]
            tv = [d["r8"][k8]["train_virtual"]["within_0.25m"], EXR[rep8]["mesh_aimed"]["groups"][EXR[rep8]["mesh_aimed"]["key"]]["train_virtual"]["within_0.25m"],
                  d["r9"][k9]["train_virtual"]["within_0.25m"], EXR[nor]["mesh_aimed"]["groups"][EXR[nor]["mesh_aimed"]["key"]]["train_virtual"]["within_0.25m"]]
            md.append("| 겨냥한 비가시 가우시안이 시점을 더한 메시 0.25 m 안 | " + " | ".join(pc(v) for v in tv) + " |")
            for face in ("3405", "3393", "3400"):
                fv = [d["per_face"]["r8"].get(face, {}).get("train_virtual", {}).get("within_025"), EXR[rep8]["mesh_aimed"]["per_face"].get(face, {}).get("train_virtual", {}).get("within_025"),
                      d["per_face"]["r9"].get(face, {}).get("train_virtual", {}).get("within_025"), EXR[nor]["mesh_aimed"]["per_face"].get(face, {}).get("train_virtual", {}).get("within_025")]
                md.append(f"| 　그 가운데 면 {face} | " + " | ".join(pc(v) for v in fv) + " |")
        md.append("")

# ================================================================== protection over time (r8 table 5)
md.append("## 보호의 변화 — 표 5 (500회마다 다시 읽은 직후; 칸마다 r9 (r8))\n")
md.append("| 학습 | 반복 | 보호 | 새로 보호 | 풀림 | 풀린 까닭: c̄ᵢ ≥ 0.5 · 전파된 충돌 · 지지 패치의 충돌 · uᵢ > 4τ | 보호 중 처음 비가시 · 결측 · 지지 · 패치 없음 | 보호에서 뺀 지지 충돌 (r9) | 3차원 거리였다면 풀렸을 보호 |")
md.append("|---|---|---|---|---|---|---|---|---|")
for run in RUNS:
    for a, b in zip(R[run]["protection"], R8C[run]["protection"]):
        rb, rb8 = a["released_by"], b["released_by"]
        bc, bc8 = a["by_category"], b["by_category"]
        cats = ("invisible unit", "missing unit", "support unit", "prior without a unit")
        md.append(f"| {NAME[run]} | {a['iteration']:,} | {P(n0, a['n_locked'], b['n_locked'])} | {P(n0, a['newly'], b['newly'])} | {P(n0, a['released'], b['released'])} | "
                  f"{rb['E_at_or_above_threshold']:,} · {rb['propagated_conflict']:,} · {rb.get('support_conflict', 0):,} · {rb['u_beyond_bound']:,} "
                  f"({rb8['E_at_or_above_threshold']:,} · {rb8['propagated_conflict']:,} · – · {rb8['u_beyond_bound']:,}) | "
                  + " · ".join(f"{bc.get(c, 0):,}" for c in cats) + " (" + " · ".join(f"{bc8.get(c, 0):,}" for c in cats) + ") | "
                  f"{n0(a.get('excluded_support_conflict'))} | {P(n0, a['differ_3d']['protected_now_but_3d_beyond'], b['differ_3d']['protected_now_but_3d_beyond'])} |")
md.append("")
(P9 / "cases/tables.md").write_text("\n".join(md) + "\n")
print("\n".join(md)[:3000])
print("... written", P9 / "cases/tables.md")
