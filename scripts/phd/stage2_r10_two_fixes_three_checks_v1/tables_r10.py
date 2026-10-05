"""PHD-STAGE2-R10-TWO-FIXES-THREE-CHECKS-v1 step 14 (jointbuildgs:dev, CPU): Markdown tables of the report, every cell
'r10 (r9)' where an r9 counterpart exists.

  python tables_r10.py      # reads /p10/{premeasure_v5, cases, stage1, verify} and /p9/cases; writes /p10/cases/tables.md"""
import json
from pathlib import Path

P10 = Path("/p10"); P9 = Path("/p9")


def J(p):
    p = Path(p)
    return json.loads(p.read_text()) if p.exists() else {}


PM = J(P10 / "premeasure_v5/tables.json")
C10 = J(P10 / "cases/cases.json"); C9 = J(P9 / "cases/cases.json"); C9X = J(P9 / "cases/cases_extra.json")
GA = J(P10 / "cases/ga.json"); NA = J(P10 / "cases/na.json"); DA = J(P10 / "cases/da.json"); RA = J(P10 / "cases/ra.json")
MA = J(P10 / "cases/ma.json"); PROT = J(P10 / "cases/prot.json"); LAY = J(P10 / "cases/reset_layers.json"); LAY9 = J(P9 / "cases/reset_layers.json")
MESH = J(P10 / "stage1/meshes/meshes_r10.json"); RC = J(P10 / "stage1/ids/render_check.json"); RSC = J(P10 / "cases/reset_states_check.json")
FX9 = J(P9 / "cases/fixes.json")
NAME = {"M_N": "LoD2 정상", "M_N_rep": "LoD2 정상 (다시)", "M_N_nodepth": "LoD2 정상, 깊이 항 끔", "M_B": "LoD2 주지붕 +1 m",
        "L_N_vertex": "항공 LiDAR 정상, 꼭짓점", "L_N_cell": "항공 LiDAR 정상, 칸", "L_N_cell_rep": "항공 LiDAR 정상, 칸 (다시)",
        "L_B_vertex": "항공 LiDAR +1 m, 꼭짓점", "L_B_cell": "항공 LiDAR +1 m, 칸"}
R9OF = {"M_N": "M_N", "M_N_rep": "M_N", "M_N_nodepth": "M_N_noprior", "M_B": "M_B", "L_N_vertex": "L_N", "L_N_cell": "L_N",
        "L_N_cell_rep": "L_N", "L_B_vertex": "L_B", "L_B_cell": "L_B"}
REP = {"M_N": "M_N_rep", "L_N_cell": "L_N_cell_rep"}
RUNS = list(NAME)
md = []


def cm(x, sign=False):
    return "–" if x is None or x != x else (f"{x:+.1f}" if sign else f"{x:.1f}")


def pc(x):
    return "–" if x is None or x != x else f"{100 * x:.1f} %"


def n0(x):
    return "–" if x is None else f"{int(x):,}"


def dg(x, nd=1):
    return "–" if x is None or x != x else f"{x:.{nd}f}°"


def sd(x):
    return "±0" if x == 0 else f"{x:+,}"


def P(f, a, b, **kw):
    return f"{f(a, **kw)} ({f(b, **kw)})"


def g(src, run, key):
    return src.get(run, {}).get(key, {"n": 0})


def r9c(run, key):
    return g(C9, R9OF[run], key)


# ================================================================== 3. pre-measurement
md.append("## 3. 사전 측정 — r9 대비 바뀐 행\n")
md.append("### 표 가. 허용 오차 (칸 = r10 (r9))\n")
md.append("| 사전 정보 | 면 | 표본 수 | 허용 오차 τ | r9 대비 |")
md.append("|---|---|---|---|---|")
for p, pn in (("M", "LoD2"), ("L", "항공 LiDAR")):
    for k, kn in (("roof", "지붕"), ("wall", "벽")):
        r = PM["ga"][p][k]
        md.append(f"| {pn} | {kn} | {P(n0, r['n_r10'], r['n_r9'])} | {r['r10']:.6f} m ({r['r9']:.6f} m) | {r['r10'] - r['r9']:+.1e} m |")
md.append("")
md.append("### 표 나. 잘린 벽 다각형의 패치와 설정 전체 (수 / 넓이 m²; 칸 = r10 (r9))\n")
md.append("| 설정 | 묶음 | 패치 | 지지 · 일치 | 지지 · 충돌 | 결측 | 비가시 |")
md.append("|---|---|---|---|---|---|---|")
for s, sn in (("M_N", "LoD2 정상"), ("M_B", "LoD2 주지붕 +1 m")):
    r = PM["na"][s]
    for key, kn in (("target_party", "대상 건물의 잘린 벽 5면"), ("party_polygons", f"크롭 안 잘린 벽 {r['cut_polygons_in_crop_r9']}면 (r10에 남은 {r['cut_polygons_in_crop_r10']}면)"), ("all", "설정 전체")):
        a, b = r[f"{key}_r10"], r[f"{key}_r9"]
        cell = lambda k: f"{n0(a[k][0])} / {a[k][1]:,.1f} ({n0(b[k][0])} / {b[k][1]:,.1f})"
        md.append(f"| {sn} | {kn} | {cell('all')} | {cell('agree')} | {cell('conflict')} | {cell('missing')} | {cell('invisible')} |")
md.append("")
md.append("**표 나-2. r9 → r10 패치 대응 (같은 표면, 같은 칸 중심)**\n")
md.append("| 설정 | r9 패치 | r10 패치 | 대응 | 상태·표 같음 | 상태나 표가 바뀜 | r9에만 (잘림): 비가시 · 지지 · 결측 | r10에만 |")
md.append("|---|---|---|---|---|---|---|---|")
for s, sn in (("M_N", "LoD2 정상"), ("M_B", "LoD2 주지붕 +1 m")):
    c = PM["na"][s]["correspondence"]; bs = c["r9_only_by_state"]
    md.append(f"| {sn} | {n0(c['r9'])} | {n0(c['r10'])} | {n0(c['matched'])} | {n0(c['same_state_vote'])} | {n0(c['changed'])} | "
              f"{n0(c['r9_only'])}: {n0(bs['invisible'])} · {n0(bs['support'])} · {n0(bs['missing'])} | {n0(c['r10_unmatched'])} |")
md.append("")
md.append("**표 나-3. r9의 칸 단위 판별(패치 중심이 다른 건물 벽에서 0.1 m 안, 법선 반대)과 r10의 다각형 잘라 내기**\n")
md.append("| 설정 | r9 벽 패치 | r9 판별 맞댄 칸 | r10 잘린 칸 | 둘 다 | r9만 맞댐 (r10은 남김): 비가시 · 지지 · 결측 | r10만 잘림 |")
md.append("|---|---|---|---|---|---|---|")
for s, sn in (("M_N", "LoD2 정상"), ("M_B", "LoD2 주지붕 +1 m")):
    c = PM["na"][s]["r9_cell_rule_vs_cut"]; bs = c["r9_party_kept_by_state"]
    md.append(f"| {sn} | {n0(c['wall_cells_r9'])} | {n0(c['r9_party_cells'])} | {n0(c['cut_cells'])} | {n0(c['both'])} | "
              f"{n0(c['r9_party_kept'])}: {n0(bs['invisible'])} · {n0(bs['support'])} · {n0(bs['missing'])} | {n0(c['cut_not_r9_party'])} |")
md.append("")
md.append("### 표 다. 사전 정보 픽셀과 깊이 항이 작용하는 픽셀 (칸 = r10 (r9))\n")
md.append("| 설정 | 사전 정보 픽셀 (원해상도 15시점) | 잘린 광선 · 그 가운데 r9 사전 정보 픽셀 | 학습 해상도 사전 정보 픽셀 (13시점) | gₚ = 1 | gₚ = 0 |")
md.append("|---|---|---|---|---|---|")
for s, sn in (("M_N", "LoD2 정상"), ("M_B", "LoD2 주지붕 +1 m"), ("L_N", "항공 LiDAR 정상"), ("L_B", "항공 LiDAR 주지붕 +1 m")):
    d = PM["da_px"][s]; a, b = d["r10"], d["r9"]
    g1 = lambda t: sum(v for k, v in t.items() if k.endswith("_g1")); g0 = lambda t: sum(v for k, v in t.items() if k.endswith("_g0"))
    fr = d.get("prior_px_full_res")
    md.append(f"| {sn} | {P(n0, fr['r10'], fr['r9']) if fr else '같음'} | {n0(fr['cut_rays']) + ' · ' + n0(fr['r9_prior_px_on_cut']) if fr else '–'} | "
              f"{P(n0, a['prior_px'], b['prior_px'])} | {P(n0, g1(a), g1(b))} | {P(n0, g0(a), g0(b))} |")
md.append("")
GN = {"image": "관측 출신 (SfM 점)", "support": "사전 정보 · 지지 영역", "support_conflict": "  그 가운데 표 충돌",
      "missing_conflict": "사전 정보 · 결측 → 충돌", "missing_agree": "사전 정보 · 결측 → 일치", "missing_other": "사전 정보 · 결측 → 혼재·근거 부족",
      "invisible": "사전 정보 · 비가시 영역", "no_patch": "사전 정보 · 패치 없음", "total": "합"}
md.append("### 표 라·마. 초기화 — 후보 점, 심은 점, 처음 보호 (첫 반복 직전; 칸 = r10 (r9))\n")
md.append("| 설정 | 점이 속한 곳 | 후보 점 | 심음 | 처음 보호 | r9에서 r10이 뺀 점 (후보 · 처음 보호) |")
md.append("|---|---|---|---|---|---|")
for s, sn in (("M_N", "LoD2 정상"), ("M_B", "LoD2 주지붕 +1 m"), ("L_N", "항공 LiDAR 정상"), ("L_B", "항공 LiDAR 주지붕 +1 m")):
    d = PM["ra_ma"][s]
    for k, kn in GN.items():
        a, b = d["r10"][k], d["r9"][k]
        rm = d.get("r9_removed_in_r10", {}).get(k)
        rmc = f"{n0(rm['candidates'])} · {n0(rm['protected'])}" if rm else "–"
        name = f"**{sn}**" if k == "total" else sn
        md.append(f"| {name} | {kn} | {P(n0, a['candidates'], b['candidates'])} | {P(n0, a['planted'], b['planted'])} | {P(n0, a['protected'], b['protected'])} | {rmc} |")
md.append("")
md.append("### 표 라-0. 학습 전: 항공 LiDAR 패치 위 점의 두 처음 방향 (꼭짓점 법선과 칸 법선이 이루는 방향 없는 각)\n")
md.append("| 설정 | 패치 상태 | 점 | 중앙값 | 95 % | 최대 | 5° 넘음 | 20° 넘음 |")
md.append("|---|---|---|---|---|---|---|---|")
for s, sn in (("L_N", "항공 LiDAR 정상"), ("L_B", "항공 LiDAR 주지붕 +1 m")):
    d = PM["ra_angles"][s]
    for k, kn in (("support_agree", "지지 · 일치"), ("support_conflict", "지지 · 충돌"), ("missing", "결측"), ("invisible", "비가시"), ("all_on_patch", "패치 위 전체")):
        r = d[k]
        md.append(f"| {sn} | {kn} | {n0(r['n'])} | {dg(r['p50'])} | {dg(r['p95'])} | {dg(r['max'])} | {pc(r['share_gt_5deg'])} | {pc(r['share_gt_20deg'])} |")
    md.append(f"| {sn} | 패치 없음 (지면·가파른 삼각형) | {n0(d['no_patch_or_no_cell']['n'])} | 0° (두 방식이 같음) | | | | |")
md.append("")

# ================================================================== 4-1 (ga): the reset probe
md.append("## 4. 두 고침의 확인\n")
md.append("### 표 가-1. 3,000회: 같은 학습 상태를 두 차례로 다시 읽은 결과 (r9 다시 읽기 함수, 오프라인)\n")
md.append("| 학습 | 상태 | 보호 | 새로 보호 | 풀림 (모두 c̄ᵢ ≥ 0.5) | c̄ᵢ < 0.5인 사전 정보 | 본 시점 없음 |")
md.append("|---|---|---|---|---|---|---|")
for run in ("M_N", "L_N_vertex"):
    if run not in GA:
        continue
    pr = GA[run]["probe"]["3000"]; ir = GA[run]["in_run"].get("3000", {})
    md.append(f"| {NAME[run]} | 학습 중 다시 읽기 (3,000회 시작, 실제 보호) | {n0(pr['protected_in_effect'])} | {n0(ir.get('newly'))} | {n0(ir.get('released'))} | – | {n0(ir.get('no_view'))} |")
    for t, tn in (("pre", "초기화 직전 상태를 다시 읽음 (문서의 차례)"), ("post", "초기화 직후 상태를 다시 읽음 (반대 차례)")):
        r = pr[t]
        md.append(f"| {NAME[run]} | {tn} | {n0(r['protected'])} | {n0(r['newly'])} | {n0(r['released'])} | {n0(r['E_below'])} | {n0(r['no_seeing_view'])} |")
md.append("")
md.append("**표 가-2. 두 차례의 차이**\n")
md.append("| 학습 | 직후에만 보호 | 직전에만 보호 | c̄ᵢ가 0.5를 넘나듦 (오름 · 내림) | (패치, 시점) 쌍: 가림 판단이 바뀜 / 전체 | 가려짐 → 보임 · 보임 → 가려짐 | 패치 없는 (가우시안, 시점) 쌍: 바뀜 |")
md.append("|---|---|---|---|---|---|---|")
for run in ("M_N", "L_N_vertex"):
    if run not in GA:
        continue
    r = GA[run]["probe"]["3000"]
    md.append(f"| {NAME[run]} | {n0(r['post_not_pre'])} | {n0(r['pre_not_post'])} | {n0(r['E_crossed_threshold'])} ({n0(r['E_up'])} · {n0(r['E_down'])}) | "
              f"{n0(r['cell_view_pairs_changed'])} / {n0(r['cell_view_pairs'])} ({pc(r['cell_view_pairs_changed'] / max(r['cell_view_pairs'], 1))}) | "
              f"{n0(r['cell_view_hidden_to_seen'])} · {n0(r['cell_view_seen_to_hidden'])} | {n0(r['no_patch_view_pairs_changed'])} / {n0(r['no_patch_gaussians'] * 13)} |")
md.append("")
if RSC:
    md.append("**표 가-3. 저장한 두 상태의 직접 대조 (초기화가 읽은 면제 대상과 결과)**\n")
    md.append("| 학습 | 가우시안 | 면제 대상 = 그 반복 다시 읽기의 보호 | 면제 행 불투명도 그대로 | 나머지 행 = min(전, 0.01) (최대 차이) | 위치·회전·크기·색 같음 |")
    md.append("|---|---|---|---|---|---|")
    for k, r in RSC.items():
        md.append(f"| {k} | {n0(r['n'])} | {r['exempt_equals_protection']} ({n0(r['n_exempt'])}) | {r['exempt_opacity_bit_identical']} | "
                  f"{r['reset_rows_max_abs_diff_to_min_op_001']:.1e} | {all(r['same'].values())} |")
    md.append("")

# ================================================================== 4-2 (na): party walls
md.append("### 표 나-4. 잘라 낸 맞댄 벽 (전체 LoD2; 크롭 안은 표 나)\n")
md.append("| 설정 | 벽 다각형 | 맞댄 쌍 | 잘린 다각형 (전부 잘림) | 대상 건물 면 | 겹친 넓이 | 잘라 낸 넓이 (두 벽) | 대상 건물에서 | 두 평면 거리 최대 | 코사인 최대 | 구멍 있는 조각 |")
md.append("|---|---|---|---|---|---|---|---|---|---|---|")
for s, sn in (("M_N", "LoD2 정상"), ("M_B", "LoD2 주지붕 +1 m")):
    r = MESH["settings"][s]
    md.append(f"| {sn} | {n0(r['wall_polygons'])} | {n0(r['pairs'])} | {n0(r['polygons_cut'])} ({n0(r['polygons_fully_cut'])}) | {', '.join(map(str, r['target_polygons_cut']))} | "
              f"{r['overlap_area_m2']:,.1f} m² | {r['cut_area_m2']:,.1f} m² | {r['target_cut_area_m2']:,.1f} m² | {r['gap_max_m']:.3f} m | {r['cos_max']:.3f} | {n0(r['pieces_with_holes'])} |")
md.append("")
md.append("**표 나-5. 깊이: 잘린 부분에 닿은 광선 (원해상도 15시점)**\n")
md.append("| 설정 | 잘린 광선 | 그 가운데 r9 사전 정보 픽셀 | r10에서: 사전 정보 없음 · 다른 면 | 잘린 광선 밖에서 바뀐 픽셀 | r9 깊이 재현 (최대 차이) |")
md.append("|---|---|---|---|---|---|")
for s, sn in (("M_N", "LoD2 정상"), ("M_B", "LoD2 주지붕 +1 m")):
    rows = RC["settings"][s]
    nop = sum(r["those_in_r10"]["no_prior"] for r in rows); oth = sum(r["those_in_r10"]["other_face"] for r in rows)
    md.append(f"| {sn} | {n0(RC[f'{s}_cut_rays'])} | {n0(RC[f'{s}_r9_prior_px_on_cut'])} | {n0(nop)} · {n0(oth)} | {n0(sum(r['changed_px_off_cut_rays'] for r in rows))} | "
              f"{max(r['r9_reproduced']['max_abs_depth_diff_m'] for r in rows):.1e} m |")
md.append("")
if NA:
    md.append("**표 나-6. 끝(3,500회)에 잘린 자리의 가우시안** — 처음 원판이 잘린 부분 위였던 사전 정보 가우시안(자식 포함), 그리고 끝 위치가 잘린 자리(r9에서 잘린 패치 중심 0.25 m 안, r10 사전 정보 면에서 0.1 m 넘게 떨어짐)인 가우시안\n")
    md.append("| 학습 | 처음 원판이 잘린 부분 위 (불투명 · 보호) | 끝 위치가 잘린 자리: 사전 정보 출신 (불투명 · 보호) | 그 출발 패치: 지지 · 결측 · 비가시 | 그 이동 중앙값 (m) | 관측 출신 (불투명) | 심은 사전 정보 점 | 처음 보호 → 끝 보호 |")
    md.append("|---|---|---|---|---|---|---|---|")
    for s in ("M_N", "M_B"):
        for k, r in NA.get(s, {}).items():
            if not isinstance(r, dict) or "prior_on_cut" not in r:
                continue
            cc = r.get("prior_on_cut_by_initial_category", {})
            dsp = r.get("prior_on_cut_displacement_p50_m")
            md.append(f"| {k.replace('_', ' ', 1)} | {n0(r.get('from_cut'))} ({n0(r.get('from_cut_opaque'))} · {n0(r.get('from_cut_protected'))}) | "
                      f"{n0(r['prior_on_cut'])} ({n0(r['prior_on_cut_opaque'])} · {n0(r['prior_on_cut_protected'])}) | "
                      f"{n0(cc.get('1', 0))} · {n0(cc.get('2', 0))} · {n0(cc.get('3', 0))} | {'–' if dsp is None else f'{dsp:.2f}'} | "
                      f"{n0(r['image_on_cut'])} ({n0(r['image_on_cut_opaque'])}) | {n0(r['planted_prior'])} | {n0(r['protected_start'])} → {n0(r['protected_end'])} |")
    md.append("")
    md.append("### 표 나-7. 불투명도 초기화(3,000회) 전후의 렌더링 깊이와 누적 불투명도 (r9 표 라-3 형식; 학습 시점 13장, 대상 건물의 지붕·벽 픽셀)\n")
    md.append("| 학습 | \\|D(3,001) − D(3,000)\\| 중앙값 · 95 % (m) | 1 m 넘게 · 10 m 넘게 | \\|D(3,050) − D(3,000)\\| 중앙값 · 95 % (m) | 1 m 넘게 | 누적 불투명도 중앙값 3,000 → 3,001 → 3,050 | 누적 불투명도 < 0.5 3,000 → 3,001 → 3,050 |")
    md.append("|---|---|---|---|---|---|---|")
    LN = {"r10_M_N": "r10 LoD2 정상 (바닥면·맞댄 벽 뺌)", "r9_M_N": "r9 LoD2 정상 (바닥면 뺌)", "ctrl_r8": "r9의 대조: r8 코드 (바닥면 포함)", "r10_L_N_vertex": "r10 항공 LiDAR 정상, 꼭짓점"}
    for k, nm in LN.items():
        t = NA["opacity_reset"].get(k, {}).get("total")
        if not t:
            continue
        md.append(f"| {nm} | {t['d3001']['p50']:.3f} · {t['d3001']['p95']:.3f} | {pc(t['d3001']['share_gt_1m'])} · {pc(t['d3001']['share_gt_10m'])} | "
                  f"{t['d3050']['p50']:.3f} · {t['d3050']['p95']:.3f} | {pc(t['d3050']['share_gt_1m'])} | "
                  f"{t['alpha3000']['p50']:.2f} → {t['alpha3001']['p50']:.2f} → {t['alpha3050']['p50']:.2f} | "
                  f"{pc(t['alpha3000']['share_lt_05'])} → {pc(t['alpha3001']['share_lt_05'])} → {pc(t['alpha3050']['share_lt_05'])} |")
    md.append("")
if LAY:
    md.append("**표 나-8. 층 분류 (r8 LoD2 메시의 모든 교차; 렌더링 깊이가 어느 층에서 0.5 m 안인가)**\n")
    md.append("| 학습 | 반복 | 앞면 | 바닥면 | 맞댄 벽 (잘린 부분) | 다른 안쪽 면 | 사이 | 앞면보다 앞 |")
    md.append("|---|---|---|---|---|---|---|---|")
    LN2 = {"r10": "r10 LoD2 정상", "r9": "r9 LoD2 정상", "ctrl": "대조: r8 코드", "r10_L_N_vertex": "r10 항공 LiDAR 정상, 꼭짓점"}
    for k, nm in LN2.items():
        for it in (3000, 3001, 3050):
            t = LAY["totals"].get(f"{k}_{it}")
            if not t or t.get("n", 0) == 0:
                continue
            md.append(f"| {nm} | {it:,} | {pc(t['front'])} | {pc(t['bottom face'])} | {pc(t['party wall'])} | {pc(t['other inner'])} | {pc(t['between'])} | {pc(t['in front'])} |")
    md.append("")

# ================================================================== 5. three checks
md.append("## 5. 세 확인\n")
if DA:
    md.append("### 표 다-1. 메시 두 층: 겨냥한 가우시안이 메시 0.25 m 안에 든 비율과 메시 면에서 사전 정보 면까지 (칸 = r10 (r9); r9에는 기제 층이 없다)\n")
    md.append("| 학습 | 겨냥한 가우시안 | 0.25 m 안: 학습 시점만 | 결과물 층 (학습 + 더한 시점, 장면 전체) | 기제 층 (더한 시점, 겨냥한 것만) | 메시 → 사전 정보, 결과물 층: 중앙값 · 95 % (cm) | 기제 층 (cm) |")
    md.append("|---|---|---|---|---|---|---|")
    for run in RUNS:
        a = DA.get(f"r10:{run}"); b = DA.get(f"r9:{R9OF[run]}")
        if not a:
            continue
        ga_, gb = a["groups"][a["aimed_key"]], (b["groups"][b["aimed_key"]] if b else {})
        mp, mq = a["mesh_to_prior"], (b["mesh_to_prior"] if b else {})
        w = lambda G, l: G.get(l, {}).get("within_0.25m")
        mtp = lambda M_, l: f"{100 * M_[l]['p50_m']:.1f} · {100 * M_[l]['p95_m']:.1f}" if M_.get(l, {}).get("p50_m") is not None else "–"
        md.append(f"| {NAME[run]} | {P(n0, a['n_region'], b['n_region'] if b else None)} | {P(pc, w(ga_, 'train'), w(gb, 'train'))} | "
                  f"{P(pc, w(ga_, 'train_virtual'), w(gb, 'train_virtual'))} | {pc(w(ga_, 'mechanism'))} | {mtp(mp, 'mesh_train_virtual')} ({mtp(mq, 'mesh_train_virtual')}) | {mtp(mp, 'mesh_mechanism')} |")
    md.append("")
    md.append("**표 다-1b. 메시 → 사전 정보 거리를 꼭짓점 법선으로 나눔 (겨냥한 가우시안 처음 자리 0.5 m 안 꼭짓점; 사전 정보 면과 나란함 = 법선 코사인 ≥ 0.9)**\n")
    md.append("| 학습 | 결과물 층: 나란한 몫 · 나란함 중앙값 · 아님 중앙값 (cm) | 기제 층: 나란한 몫 · 나란함 중앙값 · 아님 중앙값 (cm) |")
    md.append("|---|---|---|")
    for run in RUNS:
        a = DA.get(f"r10:{run}")
        if not a:
            continue
        def al(l):
            m = a["mesh_to_prior"].get(l, {})
            return f"{pc(m.get('aligned_share'))} · {cm(100 * m['aligned_p50_m']) if m.get('aligned_p50_m') is not None else '–'} · {cm(100 * m['not_aligned_p50_m']) if m.get('not_aligned_p50_m') is not None else '–'}"
        md.append(f"| {NAME[run]} | {al('mesh_train_virtual')} | {al('mesh_mechanism')} |")
    md.append("")
    md.append("**표 다-2. 면별 (겨냥한 가우시안이 처음 앉은 면; 결과물 층 / 기제 층)**\n")
    for run in ("M_N", "M_N_rep", "L_N_vertex", "L_N_cell", "L_N_cell_rep"):
        a = DA.get(f"r10:{run}")
        if not a:
            continue
        pf = {k: v for k, v in a["per_face"].items() if k != "all"}
        top = sorted(pf, key=lambda k: -pf[k].get("train_virtual", {}).get("n", 0))[:6]
        cells = [f"{k} ({n0(pf[k]['train_virtual']['n'])}): {pc(pf[k]['train_virtual']['within_025'])} / {pc(pf[k].get('mechanism', {}).get('within_025'))}" for k in top]
        md.append(f"- {NAME[run]}: " + "; ".join(cells))
    md.append("")
    md.append("**표 다-3. 결과물 층에서 겨냥한 가우시안을 가리는 것 (더한 시점 16대 합; (겨냥한 가우시안, 시점) 쌍)**\n")
    md.append("| 학습 | 시점 안 쌍 | 가려진 쌍 | 이 묶음을 빼면 보이게 되는 비율: 관측 출신 · 크기 1 m 초과 · 다른 건물 사전 정보 · 보호됨 · 대상 건물 사전 정보(겨냥 밖) · 겨냥 밖 전부 | 가리는 가우시안 (1σ 안, 불투명도 ≥ 0.5): 관측 출신 · 크기 1 m 초과 · 다른 건물 사전 정보 · 보호됨 |")
    md.append("|---|---|---|---|---|")
    GK = ["image origin", "scale above 1 m", "prior of other buildings", "protected", "prior of the target building (not aimed)", "everything not aimed"]
    for run in RUNS:
        a = DA.get(f"r10:{run}")
        if not a or not a.get("occluders"):
            continue
        o = a["occluders"]; t = o["totals"]
        md.append(f"| {NAME[run]} | {n0(t['inside'])} | {n0(t['hidden'])} ({pc(o['hidden_share'])}) | " + " · ".join(pc(o["freed_share_of_hidden"][k]) for k in GK) +
                  " | " + " · ".join(n0(o["occluders"][k]) for k in GK[:4]) + " |")
    md.append("")

if C10:
    md.append("### 표 라-1. 항공 LiDAR 정상: 꼭짓점과 칸 (r9 표 S-L_N의 행; 칸 = 비율)\n")
    cols = [("r9 L_N (r9)", lambda k: g(C9, "L_N", k)), ("r9 다 끔", lambda k: g(C9X, "L_N_noorient", k)), ("r8 다시", lambda k: g(C9X, "r8rep_L_N", k)),
            ("꼭짓점 (r10)", lambda k: g(C10, "L_N_vertex", k)), ("칸", lambda k: g(C10, "L_N_cell", k)), ("칸 다시", lambda k: g(C10, "L_N_cell_rep", k))]
    md.append("| 값 | " + " | ".join(c[0] for c in cols) + " |")
    md.append("|---|" + "---|" * len(cols))
    rows = [("경우 1 지붕: MVS에서 τ 안", "c1|roof", "within_tau_of_mvs"), ("경우 1 지붕: 사전 정보에서 τ 안", "c1|roof", "within_tau_of_prior"),
            ("경우 1 패치 없음: 사전 정보에서 τ 안", "c1|no_patch", "within_tau_of_prior"), ("경우 2: MVS에서 τ 안", "c2", "within_tau_of_mvs"),
            ("경우 2 패치 없음: MVS에서 τ 안", "c2_no_patch", "within_tau_of_mvs"),
            ("경우 3 일치: 사전 정보에서 τ 안", "c3_agree", "within_tau_of_prior"), ("경우 3 미판정: 사전 정보에서 τ 안", "c3_undetermined", "within_tau_of_prior"),
            ("경우 3 충돌: 세워진 비율", "c3_conflict", "built_share"),
            ("지지·일치 패치의 cₚ 0 픽셀: 사전 정보에서 τ 안", "x_support_c0_agree", "within_tau_of_prior"),
            ("지지·충돌 패치의 cₚ 0 픽셀: 사전 정보에서 τ 안", "x_support_c0_conflict", "within_tau_of_prior"),
            ("경우 3 일치: 참값에서 τ 안", "c3_agree", "within_tau_of_gt"), ("경우 3 충돌: 참값에서 τ 안", "c3_conflict", "within_tau_of_gt"),
            ("경우 3 미판정: 참값에서 τ 안", "c3_undetermined", "within_tau_of_gt")]
    for nm, k, v in rows:
        md.append(f"| {nm} | " + " | ".join(pc(c[1](k).get(v)) for c in cols) + " |")
    md.append("| 경우 4: 끝 불투명도 ≥ 0.5 | " + " | ".join(pc((C9 if i == 0 else C9X if i in (1, 2) else C10).get(["L_N", "L_N_noorient", "r8rep_L_N", "L_N_vertex", "L_N_cell", "L_N_cell_rep"][i], {}).get("case4", {}).get("share_end_opacity_ge_05")) for i in range(6)) + " |")
    md.append("")
if RA:
    md.append("### 표 라-2. 사전 정보 가우시안의 법선과 처음 면 법선이 이루는 각 (방향 없는 각, 중앙값 / 95 %; 끝 = 3,500회)\n")
    md.append("| 학습 | 가우시안 | 처음 | 끝 (그 방식의 처음 면 법선 대비) | 끝 (꼭짓점 법선 대비) |")
    md.append("|---|---|---|---|---|")
    for tag in ("r9:L_N", "r10:L_N_vertex", "r10:L_N_cell", "r10:L_N_cell_rep", "r9:L_B", "r10:L_B_vertex", "r10:L_B_cell"):
        a = RA["angles"].get(tag)
        if not a:
            continue
        for k, kn in (("invisible", "비가시 패치에서 심은 것"), ("visible", "보이는 패치(지지·결측)"), ("no_patch", "패치 없음")):
            r = a[k]
            f_ = lambda s_: f"{dg(s_['p50'])} / {dg(s_['p95'])}"
            md.append(f"| {tag} | {kn} | {f_(r['start'])} | {f_(r['end'])} | {f_(r['end_vs_vertex'])} |")
    md.append("")
if MA:
    md.append("### 표 마-1. 경우 3의 참값 열 (r9와 같은 정의; 결과 − 참값의 크기 중앙값 cm · 참값에서 τ 안 · 참값 픽셀 수; 참고: 사전 정보 − 참값 크기 중앙값)\n")
    md.append("| 학습 | 일치 | 충돌 | 미판정 | 참고: 사전 정보 − 참값 (일치 · 충돌 · 미판정) |")
    md.append("|---|---|---|---|---|")
    for tag, r in MA["runs"].items():
        cell = lambda k: f"{cm(r[k].get('median_abs_dG_cm'))} · {pc(r[k].get('within_tau_of_gt'))} · {n0(r[k].get('n_gt'))}"
        ref = " · ".join(cm(r[k].get("median_abs_gt_minus_prior_cm")) for k in ("c3_agree", "c3_conflict", "c3_undetermined"))
        md.append(f"| {tag} | {cell('c3_agree')} | {cell('c3_conflict')} | {cell('c3_undetermined')} | {ref} |")
    md.append("")

# ================================================================== 6. the four cases (r9 tables 1 - 4)
if C10:
    md.append("## 6. 네 경우 (칸 = r10 (r9); 흔들림 = 같은 코드를 다시 돌린 학습의 값)\n")
    KIND = {"roof": "지붕 패치", "wall": "벽 패치", "no_patch": "패치 없음", "injected": "주입한 면 (지붕 패치)", "": "합"}
    md.append("### 표 1. 관측 있음 · 허용 오차 안 (cₚ = 1, gₚ = 1)\n")
    md.append("| 학습 | 픽셀 | 수 | 결과 − MVS \\|·\\| (cm) | MVS에서 τ 안 | 결과 − 사전 정보 \\|·\\| (cm) | 사전 정보에서 τ 안 | 흔들림: MVS · 사전 정보에서 τ 안 |")
    md.append("|---|---|---|---|---|---|---|---|")
    for run in RUNS:
        kinds = ["roof", "wall", ""] if run.startswith("M") else ["roof", "no_patch", ""]
        for kd in kinds:
            key = "c1" + (f"|{kd}" if kd else "")
            a, b = g(C10, run, key), r9c(run, key)
            if not a.get("n"):
                continue
            rp = g(C10, REP[run], key) if run in REP else None
            sp = f"{pc(rp.get('within_tau_of_mvs'))} · {pc(rp.get('within_tau_of_prior'))}" if rp and rp.get("n") else "–"
            md.append(f"| {NAME[run]} | {KIND[kd]} | {P(n0, a['n'], b.get('n'))} | {P(cm, a['median_abs_dM_cm'], b.get('median_abs_dM_cm'))} | "
                      f"{P(pc, a['within_tau_of_mvs'], b.get('within_tau_of_mvs'))} | {P(cm, a['median_abs_dP_cm'], b.get('median_abs_dP_cm'))} | "
                      f"{P(pc, a['within_tau_of_prior'], b.get('within_tau_of_prior'))} | {sp} |")
    md.append("")
    md.append("### 표 2. 관측 있음 · 허용 오차 밖 (충돌로 판정된 지지 패치의 cₚ = 1 픽셀; 항공 LiDAR는 패치 없는 cₚ = 1 충돌 픽셀도)\n")
    md.append("| 학습 | 픽셀 | 수 | MVS에서 τ 안 | 사전 정보에서 τ 안 | 결과 − MVS \\|·\\| (cm) | 결과 − 사전 정보 부호 중앙값 (cm) | 흔들림: MVS에서 τ 안 |")
    md.append("|---|---|---|---|---|---|---|---|")
    for run in RUNS:
        keys = ["c2|roof", "c2|wall", "c2"] if run.startswith("M") else ["c2|roof", "c2_no_patch"]
        if run in ("M_B", "L_B_vertex", "L_B_cell"):
            keys = keys[:-1] + ["c2|injected"] + keys[-1:] if run == "M_B" else ["c2|roof", "c2|injected", "c2_no_patch"]
        for key in keys:
            a, b = g(C10, run, key), r9c(run, key)
            if not a.get("n"):
                continue
            nm = {"c2|roof": "지붕 패치", "c2|wall": "벽 패치", "c2": "패치 합", "c2|injected": "주입한 면", "c2_no_patch": "패치 없음 (충돌 표시)"}[key]
            rp = g(C10, REP[run], key) if run in REP else None
            sp = pc(rp.get("within_tau_of_mvs")) if rp and rp.get("n") else "–"
            md.append(f"| {NAME[run]} | {nm} | {P(n0, a['n'], b.get('n'))} | {P(pc, a['within_tau_of_mvs'], b.get('within_tau_of_mvs'))} | "
                      f"{P(pc, a['within_tau_of_prior'], b.get('within_tau_of_prior'))} | {P(cm, a['median_abs_dM_cm'], b.get('median_abs_dM_cm'))} | "
                      f"{P(cm, a['median_dP_cm'], b.get('median_dP_cm'), sign=True)} | {sp} |")
    md.append("")
    md.append("### 표 3. 관측 없음 · 영상에 찍힘 (결측 패치의 cₚ = 0 픽셀, 전파받은 판정별)\n")
    md.append("| 학습 | 전파받은 판정 | 수 | 결과 − 사전 정보 부호 중앙값 (cm) | 사전 정보에서 τ 안 | 세워진 비율 | 참고: 결과 − 참값 \\|·\\| (cm) · 참값에서 τ 안 | 흔들림: 사전 정보에서 τ 안 · 참값에서 τ 안 |")
    md.append("|---|---|---|---|---|---|---|---|")
    for run in RUNS:
        for key, nm in (("c3_agree", "일치 (1)"), ("c3_conflict", "충돌 (0)"), ("c3_undetermined", "미판정 (1)")):
            a, b = g(C10, run, key), r9c(run, key)
            if not a.get("n"):
                continue
            rp = g(C10, REP[run], key) if run in REP else None
            sp = f"{pc(rp.get('within_tau_of_prior'))} · {pc(rp.get('within_tau_of_gt'))}" if rp and rp.get("n") else "–"
            md.append(f"| {NAME[run]} | {nm} | {P(n0, a['n'], b.get('n'))} | {P(cm, a['median_dP_cm'], b.get('median_dP_cm'), sign=True)} | "
                      f"{P(pc, a['within_tau_of_prior'], b.get('within_tau_of_prior'))} | {P(pc, a['built_share'], b.get('built_share'))} | "
                      f"{cm(a['median_abs_dG_cm'])} ({cm(b.get('median_abs_dG_cm'))}) · {P(pc, a['within_tau_of_gt'], b.get('within_tau_of_gt'))} | {sp} |")
    md.append("")
    md.append("**표 3-2. 변화를 넣은 설정: 주입한 면의 결측 패치 (cₚ = 0)**\n")
    md.append("| 학습 | 전파받은 판정 | 수 | 올린 사전 정보에서 τ 안 | 올리기 전 높이에서 τ 안 | 결과 − 올린 사전 정보 부호 중앙값 (cm) | 세워진 비율 |")
    md.append("|---|---|---|---|---|---|---|")
    for run in ("M_B", "L_B_vertex", "L_B_cell"):
        for key, nm in (("c3_conflict|injected", "충돌 (0)"), ("c3_undetermined|injected", "미판정 (1)")):
            a, b = g(C10, run, key), r9c(run, key)
            if not a.get("n"):
                continue
            md.append(f"| {NAME[run]} | {nm} | {P(n0, a['n'], b.get('n'))} | {P(pc, a.get('within_tau_of_raised'), b.get('within_tau_of_raised'))} | "
                      f"{P(pc, a.get('within_tau_of_nominal'), b.get('within_tau_of_nominal'))} | {P(cm, a['median_dP_cm'], b.get('median_dP_cm'), sign=True)} | "
                      f"{P(pc, a['built_share'], b.get('built_share'))} |")
    md.append("")
    md.append("**표 3-3. 관측 없음 · 영상에 찍힘의 나머지 픽셀** (지지 패치의 cₚ = 0 픽셀, 패치 없는 cₚ = 0 픽셀)\n")
    md.append("| 학습 | 픽셀 (gₚ) | 수 | 결과 − 사전 정보 부호 중앙값 (cm) | 사전 정보에서 τ 안 | 세워진 비율 | 흔들림: 사전 정보에서 τ 안 |")
    md.append("|---|---|---|---|---|---|---|")
    for run in RUNS:
        for key, nm in (("x_support_c0_agree", "지지 패치 · 표 일치 (1)"), ("x_support_c0_conflict", "지지 패치 · 표 충돌 (0)"), ("x_no_patch_c0", "패치 없음 (1)")):
            a, b = g(C10, run, key), r9c(run, key)
            if not a.get("n"):
                continue
            rp = g(C10, REP[run], key) if run in REP else None
            sp = pc(rp.get("within_tau_of_prior")) if rp and rp.get("n") else "–"
            md.append(f"| {NAME[run]} | {nm} | {P(n0, a['n'], b.get('n'))} | {P(cm, a['median_dP_cm'], b.get('median_dP_cm'), sign=True)} | "
                      f"{P(pc, a['within_tau_of_prior'], b.get('within_tau_of_prior'))} | {P(pc, a['built_share'], b.get('built_share'))} | {sp} |")
    md.append("")
    md.append("### 표 4. 영상에 찍히지 않음 (비가시 패치에서 심은 가우시안)\n")
    import numpy as np
    md.append("| 학습 | 처음 | 끝 (처음 가우시안 가운데 남음) | 끝 불투명도 ≥ 0.5 | uᵢ 중앙값 · 99 % (mm) | 3차원 이동 중앙값 (mm) | 끝에 보호됨 | 마지막 다시 읽기에서 본 시점 없음 | 흔들림: 불투명도 ≥ 0.5 |")
    md.append("|---|---|---|---|---|---|---|---|---|")
    for run in RUNS:
        a = C10.get(run, {}).get("case4"); b = C9.get(R9OF[run], {}).get("case4", {})
        if not a:
            continue
        rp = C10.get(REP[run], {}).get("case4") if run in REP else None
        dz = np.load(P10 / "runs" / run / "model/dump/iteration_3500/gaussians.npz")
        alive = int(((dz["init_category_of_initial"] == 3) & (dz["init_removed_at"] < 0)).sum())
        md.append(f"| {NAME[run]} | {P(n0, a['n_initial'], b.get('n_initial'))} | {P(n0, alive, b.get('n_initial_ids_alive'))} | "
                  f"{P(pc, a['share_end_opacity_ge_05'], b.get('share_end_opacity_ge_05'))} | {a['u_median_mm']:.0f} · {a['u_p99_mm']:.0f} ({b.get('u_median_mm', float('nan')):.0f} · {b.get('u_p99_mm', float('nan')):.0f}) | "
                  f"{P(lambda x: f'{x:.0f}', a['drift3d_median_mm'], b.get('drift3d_median_mm', float('nan')))} | {P(n0, a['protected_end'], b.get('protected_end'))} | "
                  f"{P(n0, a['no_seeing_view_last_read'], b.get('no_seeing_view_last_read'))} | {pc(rp['share_end_opacity_ge_05']) if rp else '–'} |")
    md.append("")

# ================================================================== 7. protection over time (r9 table 5)
if PROT:
    md.append("## 7. 보호의 변화 (500회마다 다시 읽은 직후; 칸 = r10 (r9))\n")
    md.append("| 학습 | 반복 | 보호 | 새로 보호 | 풀림 | 풀린 까닭: c̄ᵢ ≥ 0.5 · 전파된 충돌 · 지지 패치의 충돌 · uᵢ > 4τ | 보호 중 처음 비가시 · 결측 · 지지 · 패치 없음 |")
    md.append("|---|---|---|---|---|---|---|")
    for run in RUNS:
        a_rows = PROT.get(f"r10:{run}", []); b_rows = PROT.get(f"r9:{R9OF[run]}", [])
        bmap = {r["iteration"]: r for r in b_rows}
        for r in a_rows:
            b = bmap.get(r["iteration"], {})
            rb, rb9 = r["released_by"], b.get("released_by", {})
            cat = r["by_category"]; cat9 = b.get("by_category", {})
            cats = lambda c: " · ".join(n0(c.get(k)) for k in ("invisible unit", "missing unit", "support unit", "prior without a unit"))
            md.append(f"| {NAME[run]} | {r['iteration']:,} | {P(n0, r['n_locked'], b.get('n_locked'))} | {P(n0, r['newly'], b.get('newly'))} | {P(n0, r['released'], b.get('released'))} | "
                      f"{rb['E_at_or_above_threshold']} · {rb['propagated_conflict']} · {rb['support_conflict']} · {rb['u_beyond_bound']} "
                      f"({rb9.get('E_at_or_above_threshold', '–')} · {rb9.get('propagated_conflict', '–')} · {rb9.get('support_conflict', '–')} · {rb9.get('u_beyond_bound', '–')}) | "
                      f"{cats(cat)} ({cats(cat9)}) |")
    md.append("")
(P10 / "cases/tables.md").write_text("\n".join(md) + "\n")
print("written", P10 / "cases/tables.md", len(md), "lines")
