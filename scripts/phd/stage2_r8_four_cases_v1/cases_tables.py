"""PHD-STAGE2-R8-FOUR-CASES-v1 step 9 (jointbuildgs:dev, CPU): Markdown tables of the four cases and the protection over time.

  python cases_tables.py      # reads /p8/cases/cases.json, writes /p8/cases/tables.md (Korean, report wording)"""
import json
from pathlib import Path

P8 = Path("/p8")
R = json.loads((P8 / "cases/cases.json").read_text())
RUNS = ["M_N", "M_N_noprior", "M_B", "L_N", "L_B"]
NAME = {"M_N": "LoD2 정상", "M_B": "LoD2 주지붕 +1 m", "L_N": "항공 LiDAR 정상", "L_B": "항공 LiDAR 주지붕 +1 m",
        "M_N_noprior": "LoD2 정상, 사전 정보 깊이 항 끔"}
KIND = {"roof": "지붕 패치", "wall": "벽 패치", "no_patch": "패치 없음", "injected": "주입한 면 (지붕 패치)", "": "합"}
md = []


def cm(x, sign=False):
    return "–" if x is None or x != x else (f"{x:+.1f}" if sign else f"{x:.1f}")


def pc(x):
    return "–" if x is None or x != x else f"{100 * x:.1f} %"


def n0(x):
    return f"{x:,}"


def g(run, key):
    return R[run].get(key, {"n": 0})


# ---------------------------------------------------------------- 1
md.append("### 표 1. 관측 있음 · 허용 오차 안 (cₚ = 1, gₚ = 1)\n")
md.append("| 학습 | 픽셀 | 수 | 결과 − MVS, 중앙값 \\|·\\| (cm) | MVS에서 τ 안 | 결과 − 사전 정보, 중앙값 \\|·\\| (부호 중앙값) (cm) | 사전 정보에서 τ 안 |")
md.append("|---|---|---|---|---|---|---|")
for run in RUNS:
    for sub in ("|roof", "|wall", "|no_patch", ""):
        d = g(run, "c1" + sub)
        if d["n"] == 0:
            continue
        md.append(f"| {NAME[run]} | {KIND[sub.strip('|')]} | {n0(d['n'])} | {cm(d['median_abs_dM_cm'])} | {pc(d['within_tau_of_mvs'])} | "
                  f"{cm(d['median_abs_dP_cm'])} ({cm(d['median_dP_cm'], True)}) | {pc(d['within_tau_of_prior'])} |")
md.append("")
md.append("**표 1-2. LoD2 정상: 사전 정보 깊이 항을 켠 학습(1번)과 끈 학습(5번)** (같은 픽셀)\n")
md.append("| 픽셀 | 결과 − MVS \\|·\\| (cm): 켬 / 끔 | MVS에서 τ 안: 켬 / 끔 | 결과 − 사전 정보 \\|·\\| (cm): 켬 / 끔 | 사전 정보에서 τ 안: 켬 / 끔 |")
md.append("|---|---|---|---|---|")
for sub in ("|roof", "|wall", ""):
    a, b = g("M_N", "c1" + sub), g("M_N_noprior", "c1" + sub)
    if a["n"] == 0:
        continue
    md.append(f"| {KIND[sub.strip('|')]} ({n0(a['n'])}) | {cm(a['median_abs_dM_cm'])} / {cm(b['median_abs_dM_cm'])} | {pc(a['within_tau_of_mvs'])} / {pc(b['within_tau_of_mvs'])} | "
              f"{cm(a['median_abs_dP_cm'])} / {cm(b['median_abs_dP_cm'])} | {pc(a['within_tau_of_prior'])} / {pc(b['within_tau_of_prior'])} |")
md.append("")

# ---------------------------------------------------------------- 2
md.append("### 표 2. 관측 있음 · 허용 오차 밖 (충돌로 판정된 지지 영역 패치의 cₚ = 1 픽셀; 항공 LiDAR는 패치 없는 cₚ = 1 충돌 픽셀도)\n")
md.append("| 학습 | 픽셀 | 수 | MVS에서 τ 안 | 사전 정보에서 τ 안 | 결과 − MVS, 중앙값 \\|·\\| (cm) | 결과 − 사전 정보, 부호 중앙값 (cm) |")
md.append("|---|---|---|---|---|---|---|")
for run in RUNS:
    for key, lab in (("c2|roof", "지붕 패치"), ("c2|wall", "벽 패치"), ("c2|injected", "주입한 면 (지붕 패치)"), ("c2", "패치 합"),
                     ("c2_no_patch", "패치 없음 (충돌 표시)")):
        d = g(run, key)
        if d["n"] == 0:
            continue
        md.append(f"| {NAME[run]} | {lab} | {n0(d['n'])} | {pc(d['within_tau_of_mvs'])} | {pc(d['within_tau_of_prior'])} | {cm(d['median_abs_dM_cm'])} | {cm(d['median_dP_cm'], True)} |")
md.append("")

# ---------------------------------------------------------------- 3
md.append("### 표 3. 관측 없음 · 영상에 찍힘 (결측 영역 패치의 cₚ = 0 픽셀, 전파받은 판정별)\n")
md.append("결과 − 사전 정보의 부호: + = 결과가 사전 정보보다 카메라에서 멀다(지붕이면 아래). 참값 열은 해석을 돕는 참고값이며 판정이나 값을 정하는 데 쓰지 않았다(참값 점이 투영된 픽셀만).\n")
md.append("| 학습 | 전파받은 판정 (gₚ) | 수 | 결과 − 사전 정보, 부호 중앙값 (cm) | 사전 정보에서 τ 안 | 세워진 비율 (불투명도 합 ≥ 0.5) | 참고: 참값 픽셀 · 결과 − 참값 \\|·\\| (cm) · 참값에서 τ 안 |")
md.append("|---|---|---|---|---|---|---|")
JL = (("c3_agree", "일치 (1)"), ("c3_conflict", "충돌 (0)"), ("c3_undetermined", "미판정 (1)"))
for run in RUNS:
    for key, lab in JL:
        d = g(run, key)
        if d["n"] == 0:
            continue
        md.append(f"| {NAME[run]} | {lab} | {n0(d['n'])} | {cm(d['median_dP_cm'], True)} | {pc(d['within_tau_of_prior'])} | {pc(d['built_share'])} | "
                  f"{n0(d['n_gt'])} · {cm(d['median_abs_dG_cm'])} · {pc(d['within_tau_of_gt'])} |")
md.append("")
md.append("**표 3-2. 변화를 넣은 설정: 주입한 면의 결측 패치 (cₚ = 0)** — 결과가 넣은 변화(1 m 올린 사전 정보) 쪽으로 옮겨 갔는가\n")
md.append("| 학습 | 전파받은 판정 | 수 | 올린 사전 정보에서 τ 안 (넣은 변화를 따름) | 올리기 전 높이에서 τ 안 | 결과 − 올린 사전 정보, 부호 중앙값 (cm) | 세워진 비율 | 참고: 참값 픽셀 · 결과 − 참값 \\|·\\| (cm) · 참값 − 올린 사전 정보 (cm) |")
md.append("|---|---|---|---|---|---|---|---|")
for run in ("M_B", "L_B"):
    for key, lab in (("c3_conflict|injected", "충돌 (0)"), ("c3_undetermined|injected", "미판정 (1)"), ("c3_agree|injected", "일치 (1)")):
        d = g(run, key)
        if d["n"] == 0:
            continue
        md.append(f"| {NAME[run]} | {lab} | {n0(d['n'])} | {pc(d['within_tau_of_raised'])} | {pc(d['within_tau_of_nominal'])} | {cm(d['median_dP_cm'], True)} | "
                  f"{pc(d['built_share'])} | {n0(d['n_gt'])} · {cm(d['median_abs_dG_cm'])} · {cm(d['median_gt_minus_prior_cm'], True)} |")
md.append("")
md.append("**표 3-3. 관측 없음 · 영상에 찍힘의 나머지 픽셀** (설계의 네 경우 밖에서 같은 cₚ = 0인 곳: 지지 영역 패치의 cₚ = 0 픽셀은 그 패치의 표대로, 패치 없는 픽셀은 gₚ = 1)\n")
md.append("| 학습 | 픽셀 (gₚ) | 수 | 결과 − 사전 정보, 부호 중앙값 (cm) | 사전 정보에서 τ 안 | 세워진 비율 |")
md.append("|---|---|---|---|---|---|")
for run in RUNS:
    for key, lab in (("x_support_c0_agree", "지지 패치 · 표 일치 (1)"), ("x_support_c0_conflict", "지지 패치 · 표 충돌 (0)"), ("x_no_patch_c0", "패치 없음 (1)")):
        d = g(run, key)
        if d["n"] == 0:
            continue
        md.append(f"| {NAME[run]} | {lab} | {n0(d['n'])} | {cm(d['median_dP_cm'], True)} | {pc(d['within_tau_of_prior'])} | {pc(d['built_share'])} |")
md.append("")

# ---------------------------------------------------------------- 4
md.append("### 표 4. 영상에 찍히지 않음 (비가시 영역 패치에서 심은 가우시안)\n")
md.append("| 학습 | 처음 | 끝 (처음 가우시안 가운데 남음 / 자식 포함) | 끝 불투명도 ≥ 0.5 | uᵢ 중앙값 · 99 % · 최대 (mm) | 3차원 이동 중앙값 · 최대 (mm) | 끝에 보호됨 | 마지막 다시 읽기에서 본 시점 없음 |")
md.append("|---|---|---|---|---|---|---|---|")
for run in RUNS:
    c = R[run]["case4"]
    md.append(f"| {NAME[run]} | {n0(c['n_initial'])} | {n0(c['n_initial_ids_alive'])} / {n0(c['n_end'])} | {pc(c['share_end_opacity_ge_05'])} | "
              f"{c['u_median_mm']:.1f} · {c['u_p99_mm']:.0f} · {c['u_max_mm']:.0f} | {c['drift3d_median_mm']:.1f} · {c['drift3d_max_mm']:.0f} | "
              f"{n0(c['protected_end'])} | {n0(c['no_seeing_view_last_read'])} |")
md.append("")
md.append("**표 4-2. 메시에 담겼는가** (TSDF 0.10 m 칸; 가우시안 중심에서 메시 면까지 거리 0.25 m 안 비율 — 학습 시점만 / 학습 시점 + 더한 시점)\n")
md.append("| 학습 | 대상 건물 바깥면의 비가시 가우시안 (불투명도 ≥ 0.5) | 대상 건물 바닥면 | 그 밖의 비가시 사전 정보 | 참고: 보이는 사전 정보 | 더한 시점 수 |")
md.append("|---|---|---|---|---|---|")
for run in RUNS:
    c = R[run]["case4"]
    mj = P8 / "mesh" / run / "mesh.json"
    mfull = json.loads(mj.read_text()) if mj.exists() else None
    m = mfull["groups"] if mfull else c.get("mesh")
    if mfull:
        c = dict(c, mesh_virtual_cameras=mfull["n_virtual_cameras"])
    if not m:
        md.append(f"| {NAME[run]} | – | – | – | – | – |")
        continue

    def cell(key):
        for k, v in m.items():
            if k.startswith(key):
                if v["n"] == 0:
                    return "0개"
                return f"{n0(v['n'])}개: {pc(v['train']['within_0.25m'])} / {pc(v['train_virtual']['within_0.25m'])}"
        return "–"
    md.append(f"| {NAME[run]} | {cell('target outward')} | {cell('target bottom')} | {cell('other invisible')} | {cell('seen prior')} | {c.get('mesh_virtual_cameras', '–')} |")
md.append("")
md.append("**표 4-3. 지지 영역 충돌 패치 위에서 끝에 보호된 가우시안** (식 (7)은 전파된 충돌만 뺀다)\n")
md.append("| 학습 | 끝에 보호된 사전 정보 가우시안 | 그 가운데 지지 · 충돌 패치 위 | 그 가운데 본 시점 없음 | 가장 많은 표면 (수) |")
md.append("|---|---|---|---|---|")
for run in RUNS:
    c = R[run]["case4"]; s = c["protected_on_support_conflict"]
    top = ", ".join(f"{k} ({v:,})" for k, v in list(s["top_surfaces"].items())[:4])
    md.append(f"| {NAME[run]} | {n0(c['protected_total'])} | {n0(s['n'])} | {n0(s['no_seeing_view'])} | {top} |")
md.append("")

# ---------------------------------------------------------------- 5
md.append("### 표 5. 보호의 변화 (500회마다 다시 읽은 직후)\n")
md.append("| 학습 | 반복 | 보호 | 새로 보호 | 풀림 | 풀린 까닭: c̄ᵢ ≥ 0.5 · 전파된 충돌 · uᵢ > 4τ (둘 이상) | 보호 중 처음 비가시 · 결측 · 지지 패치 · 패치 없음 | 보호 중 지지 · 충돌 패치 위 | 3차원 거리였다면 풀렸을 보호 |")
md.append("|---|---|---|---|---|---|---|---|---|")
for run in RUNS:
    for r in R[run]["protection"]:
        rb = r["released_by"]; bc = r["by_category"]
        md.append(f"| {NAME[run]} | {r['iteration']:,} | {n0(r['n_locked'])} | {n0(r['newly'])} | {n0(r['released'])} | "
                  f"{n0(rb['E_at_or_above_threshold'])} · {n0(rb['propagated_conflict'])} · {n0(rb['u_beyond_bound'])} ({n0(rb['several_reasons'])}) | "
                  f"{n0(bc['invisible unit'])} · {n0(bc['missing unit'])} · {n0(bc['support unit'])} · {n0(bc['prior without a unit'])} | {n0(r['on_support_conflict'])} | "
                  f"{n0(r['differ_3d']['protected_now_but_3d_beyond'])} |")
md.append("")
(P8 / "cases/tables.md").write_text("\n".join(md) + "\n")
print("tables written", len(md), "lines")
