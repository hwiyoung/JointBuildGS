"""PHD-STAGE2-R8-FOUR-CASES-v1 step 6 (jointbuildgs:dev, CPU): the pre-measurement with the 2026-10-01 rules (no training),
each table beside the r7 values (PHD-STAGE2-R7-PROPAGATION-v1, its adopted tolerance with the agency spec lower bound).

  python premeasure_v3.py      # after stage1_products_r8.py (all settings) and the dry initialisations
  mounts: /artifacts (ro), /repo (ro), /r7 (ro), /p8 (rw)

Fixed values (configs/phd/stage2_r8_four_cases_v1/r8.json): majority 2/3, minimum 5 units, maximum distance 1 m, cells
0.25 m, tolerance 2.5 x NMAD (no lower bound). Propagation = src/phd/prior_propagation_v2 (r7 values = the same
propagation code on r7's stored states and votes).
Tables (Korean Markdown in /p8/premeasure_v3/tables.md; numbers in tables.json):
  가 tolerance per prior and surface kind       나 judgment units per surface (count and area)
  다 prior pixels without a judgment unit (+ pixels where the prior depth term acts, training resolution)
  라 initialisation by origin and region         마 first protected Gaussians by the same groups"""
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, "/repo")
from src.phd.prior_propagation_v2 import locations as locs  # noqa: E402
from src.phd.prior_propagation_v2 import rule  # noqa: E402

P8 = Path("/p8"); R7 = Path("/r7"); OUT = P8 / "premeasure_v3"; OUT.mkdir(parents=True, exist_ok=True)
CFG = json.loads(Path("/repo/configs/phd/stage2_r8_four_cases_v1/r8.json").read_text())
S2 = Path("/artifacts/JointBuildGS/phase-payloads/phd/stage2_conf_guided_gs_v1/PHD-STAGE2-CONF-GUIDED-GS-v1")
TRAIN = json.loads((S2 / "runs/P_M_N/model/monitor/meta.json").read_text())["train_views"]
V = CFG["values"]
Q, K, R, CELL = V["majority"], V["min_evidence_locations"], V["max_distance_m"], V["cell_m"]
SETTINGS = ["M_N", "M_B", "M_C", "L_N", "L_B"]
TRAINED = ["M_N", "M_B", "L_N", "L_B"]
NAME = {s: CFG["settings"][s]["name_ko"] for s in SETTINGS}
LOD2_NOTE = {3396: "주지붕", 3394: "그늘진 지붕 끝", 3403: "정면 벽", 3404: "끝 경사면", 3393: "뒷지붕", 3387: "날개 지붕", 3389: "날개 지붕",
             3401: "대상 건물 바닥면", 3391: "옆 벽"}
JN = [rule.J_CONFLICT, rule.J_AGREE, rule.J_MIXED, rule.J_INSUFF]
md, res = [], {}


def f0(x):
    return f"{x:,.0f}"


def f1(x):
    return f"{x:,.1f}"


def pc(x):
    return "–" if x is None or x != x else f"{100 * x:.1f} %"


def sd(x):
    return "±0" if x == 0 else f"{x:+,}"


def main_var(s):
    return "poly" if s.startswith("M") else "lod2"


def load8(setting, var=None):
    var = var or main_var(setting)
    st = locs.load_store(P8 / "stage1/products" / setting / f"store_{var}_c{CELL}.npz")
    table = {r["ext"]: r for r in json.loads((P8 / "stage1/products" / setting / f"surfaces_{var}.json").read_text())["surfaces"]}
    return st, table


def judged(st, tag):
    state, vote = st[f"state_{tag}"], st[f"vote_{tag}"]
    J, _ = locs.propagate(st, state, vote, Q, K, R)
    return state, vote, J


# ------------------------------------------------------------------ 가 tolerance
T8 = json.loads((P8 / "stage1/tolerance.json").read_text())["priors"]
T7 = json.loads((R7 / "stage1/tolerance.json").read_text())["priors"]
md.append("### 표 가. 허용 오차 (정상 장면, 15시점, cₚ = 1, 대상 건물의 건물 면; 지붕 = 높이 차이, 벽 = 면에 수직인 거리)\n")
md.append("| 사전 정보 | 면 | 표본 수 | 정합 뒤 중앙값 (거르기 전 → 뒤) | NMAD (거르기 전 → 뒤) | 걸러낸 비율 | 허용 오차 τ = 2.5 × NMAD | 기관 사양 (출처) | 견준 결과 | 경고 | r7 허용 오차 (채택된 쪽) | r7 대비 |")
md.append("|---|---|---|---|---|---|---|---|---|---|---|---|")
A_ = {}
for p, pname in (("M", "LoD2"), ("L", "항공 LiDAR")):
    for kind, kname in (("roof", "지붕"), ("wall", "벽")):
        o = T8[p][kind]; st_ = o["stats"]; o7 = T7[p]["spec"][kind]
        spec_s = "없음" if o["spec"] is None else f"{o['spec']:.2f} m ({'바이에른 항공 LiDAR 연직 정확도' if p == 'L' else 'LoD2 높이 정확도'})"
        cmp_ = "사양 없음" if o["spec"] is None else ("τ가 사양보다 작음" if not o["exceeds_spec"] else "τ가 사양보다 큼")
        warn = "있음" if o.get("warning") else "없음"
        side7 = {"spec": "기관 사양", "data": "실측 폭", "data (no spec)": "실측 폭"}.get(o7["side"], "지붕 값")
        tau_s = f"**{o['tau']:.4f} m**" + ("" if o["side"].startswith("data") else " (지붕 값: 벽이 표면이 아님)")
        if st_["n"]:
            md.append(f"| {pname} | {kname} | {f0(st_['n'])} | {st_['median_before']:+.4f} → {st_['median_after']:+.4f} m | "
                      f"{st_['nmad_before']:.4f} → {st_['nmad_after']:.4f} m | {pc(st_['clipped_share'])} | {tau_s} | {spec_s} | {cmp_} | {warn} | "
                      f"{o7['tau']:.4f} m ({side7}) | {o['tau'] - o7['tau']:+.4f} m |")
        else:
            md.append(f"| {pname} | {kname} | 0 | – | – | – | {tau_s} | {spec_s} | {cmp_} | {warn} | {o7['tau']:.4f} m ({side7}) | {o['tau'] - o7['tau']:+.4f} m |")
        A_[f"{p}_{kind}"] = dict(r8=o, r7_tau=o7["tau"], r7_side=o7["side"])
res["가"] = A_
md.append("")

# ------------------------------------------------------------------ 나 units per surface
md.append("### 표 나. 표면별 패치 (한 칸 0.25 m; 수 / 넓이 m²; 일치·충돌 = 지지 영역 패치의 표, 결측의 판정 = 고정 값 2/3·5곳·1 m의 전파)\n")
md.append("| 설정 | 표면 | 종류 | 지지 | 일치 | 충돌 | 결측 | 결측 → 충돌 | 결측 → 일치 | 결측 → 혼재 | 결측 → 근거 부족 | 비가시 | r7 대비 (일치 / 충돌; 결측 → 충돌·일치·혼재·근거 부족) |")
md.append("|---|---|---|---|---|---|---|---|---|---|---|---|---|")
B = {}


def na(n, a):
    return f"{f0(n)} / {f1(a)}"


def surface_rows(st, table, state, vote, J, vote7, J7):
    rows = []
    a = st["loc_area"]
    for s in range(len(st["surf_ext"])):
        m = st["loc_surface"] == s
        if not m.any():
            continue
        ext = int(st["surf_ext"][s]); t = table.get(ext, {})
        sup = m & (state == rule.ST_SUPPORT); mis = m & (state == rule.ST_MISSING); inv = m & (state == rule.ST_INVISIBLE)
        row = dict(ext=ext, kind=int(st["surf_kind"][s]), target=bool(t.get("target")), raised=t.get("raised_share", 0.0),
                   area=float(a[m].sum()), sup=(int(sup.sum()), float(a[sup].sum())), mis=(int(mis.sum()), float(a[mis].sum())),
                   inv=(int(inv.sum()), float(a[inv].sum())))
        for nm, vv in (("agree", rule.V_AGREE), ("conflict", rule.V_CONFLICT)):
            sel = sup & (vote == vv); row[nm] = (int(sel.sum()), float(a[sel].sum()))
            row[nm + "_r7"] = int((sup & (vote7 == vv)).sum())
        row["J"] = [(int((mis & (J == j)).sum()), float(a[mis & (J == j)].sum())) for j in JN]
        row["J_r7"] = [int((mis & (J7 == j)).sum()) for j in JN]
        rows.append(row)
    return rows


def label(setting, r):
    if setting.startswith("M"):
        e = r["ext"]
        if e >= 100000:
            return f"단차면 {e - 100000} (올린 면 둘레)"
        return f"면 {e} ({LOD2_NOTE.get(e, '대상 건물' if r['target'] else '이웃 건물')})"
    where = "대상 건물 윤곽 안" if r["target"] else "이웃 건물 윤곽 안"
    return f"표면 {r['ext']} ({where}{', 올린 점' if r['raised'] >= 0.5 else ''})"


def emit(tag, lab, kind, r):
    d = [r["agree"][0] - r["agree_r7"], r["conflict"][0] - r["conflict_r7"]]
    dj = [r["J"][i][0] - r["J_r7"][i] for i in range(4)]
    diff = f"{sd(d[0])} / {sd(d[1])}; " + " · ".join(sd(x) for x in dj)
    md.append(f"| {tag} | {lab} | {kind} | {na(*r['sup'])} | {na(*r['agree'])} | {na(*r['conflict'])} | {na(*r['mis'])} | "
              + " | ".join(na(*x) for x in r["J"]) + f" | {na(*r['inv'])} | {diff} |")


for setting in SETTINGS:
    st, table = load8(setting)
    st7 = locs.load_store(R7 / "stage1/products" / setting / f"store_{main_var(setting)}_c{CELL}.npz")
    assert np.array_equal(st7["state_spec"], st["state_data"]), f"{setting}: unit states differ from r7"
    state, vote, J = judged(st, "data")
    _, vote7, J7 = judged(st7, "spec")
    rows = surface_rows(st, table, state, vote, J, vote7, J7)
    B[setting] = rows
    shown = [r for r in rows if (r["target"] and (r["sup"][0] + r["mis"][0] > 0) and (setting.startswith("M") or r["area"] >= 5))
             or r["mis"][0] >= 100 or r["sup"][0] >= 1500]
    shown.sort(key=lambda r: (r["kind"], not r["target"], -(r["sup"][0] + r["mis"][0])))
    for r in shown:
        emit(NAME[setting], label(setting, r), "지붕" if r["kind"] == 1 else "벽", r)
    rest = [r for r in rows if r not in shown]
    for kind, kn in ((1, "지붕"), (2, "벽")):
        rr = [r for r in rest if r["kind"] == kind]
        if not rr:
            continue
        agg = dict(sup=(sum(r["sup"][0] for r in rr), sum(r["sup"][1] for r in rr)), mis=(sum(r["mis"][0] for r in rr), sum(r["mis"][1] for r in rr)),
                   inv=(sum(r["inv"][0] for r in rr), sum(r["inv"][1] for r in rr)),
                   agree=(sum(r["agree"][0] for r in rr), sum(r["agree"][1] for r in rr)), conflict=(sum(r["conflict"][0] for r in rr), sum(r["conflict"][1] for r in rr)),
                   agree_r7=sum(r["agree_r7"] for r in rr), conflict_r7=sum(r["conflict_r7"] for r in rr),
                   J=[(sum(r["J"][i][0] for r in rr), sum(r["J"][i][1] for r in rr)) for i in range(4)], J_r7=[sum(r["J_r7"][i] for r in rr) for i in range(4)])
        emit(NAME[setting], f"그 밖의 {len(rr)}개 표면 합", kn, agg)
    tot = dict(sup=(sum(r["sup"][0] for r in rows), sum(r["sup"][1] for r in rows)), mis=(sum(r["mis"][0] for r in rows), sum(r["mis"][1] for r in rows)),
               inv=(sum(r["inv"][0] for r in rows), sum(r["inv"][1] for r in rows)),
               agree=(sum(r["agree"][0] for r in rows), sum(r["agree"][1] for r in rows)), conflict=(sum(r["conflict"][0] for r in rows), sum(r["conflict"][1] for r in rows)),
               agree_r7=sum(r["agree_r7"] for r in rows), conflict_r7=sum(r["conflict_r7"] for r in rows),
               J=[(sum(r["J"][i][0] for r in rows), sum(r["J"][i][1] for r in rows)) for i in range(4)], J_r7=[sum(r["J_r7"][i] for r in rows) for i in range(4)])
    emit(f"**{NAME[setting]}**", f"**전체 {len(rows)}개 표면**", "–", tot)
    B[setting + "_total"] = tot
res["나"] = B
md.append("")
# second outline source (comparison): TIN surfaces with the classification as building / non-building only
md.append("| 항공 LiDAR 설정 | 윤곽 | 건물 표면 수 | 패치 | 지지 | 결측 | 비가시 | 가장 큰 표면 넓이 m² | 대상 건물 바닥면 안에 넓이의 절반 이상이 든 표면 수 |")
md.append("|---|---|---|---|---|---|---|---|---|")
for setting in ("L_N", "L_B"):
    for var, vn in (("lod2", "LoD2 바닥면 (주어진 윤곽, 학습에 씀)"), ("cls2", "자체 분류 = 건물 여부만, 건물끼리는 가파른 삼각형 (둘째 출처)")):
        st, table = load8(setting, var)
        state = st["state_data"]
        areas = np.bincount(st["loc_surface"], weights=st["loc_area"], minlength=len(st["surf_ext"]))
        n_t = sum(1 for r in table.values() if r["is_building_face"] and r.get("target_footprint_share", 0) >= 0.5)
        md.append(f"| {NAME[setting]} | {vn} | {f0(len(st['surf_ext']))} | {f0(len(state))} | {f0((state == rule.ST_SUPPORT).sum())} | "
                  f"{f0((state == rule.ST_MISSING).sum())} | {f0((state == rule.ST_INVISIBLE).sum())} | {f1(areas.max())} | {f0(n_t)} |")
md.append("")

# ------------------------------------------------------------------ 다 pixels without a unit
md.append("### 표 다. 패치가 없는 사전 정보 픽셀 (학습 시점 13장, 원해상도)\n")
md.append("| 설정 | 사전 정보 픽셀 | 패치 없음 (비율) | 그 가운데 가파른 삼각형 / 건물이 아닌 면 | 그 가운데 cₚ = 1 (비율) | cₚ = 1 가운데 일치 | cₚ = 1 가운데 충돌 | r7 대비 |")
md.append("|---|---|---|---|---|---|---|---|")
C_ = {}
for setting in SETTINGS:
    sm = json.loads((P8 / "stage1/products" / setting / "summary.json").read_text())
    tot = {k: sum(sm["pixels"][v][k] for v in TRAIN) for k in sm["pixels"][TRAIN[0]]}
    C_[setting] = tot
    nu = tot["no_unit_px"]; a1 = tot["no_unit_a1_px"]
    r7note = ("패치가 없는 픽셀이 없다" if nu == 0 else
              "r7: 이 픽셀의 사전 정보 깊이 항 무게는 1 − cₚ (cₚ = 1이면 꺼짐); 일치·충돌은 쓰지 않았다")
    md.append(f"| {NAME[setting]} | {f0(tot['prior_px'])} | {f0(nu)} ({pc(nu / tot['prior_px'])}) | {f0(tot['no_unit_steep_px'])} / {f0(tot['no_unit_nonbuilding_surface_px'])} | "
              f"{f0(a1)} ({pc(a1 / nu) if nu else '–'}) | {pc(tot['no_unit_agree_px'] / a1) if a1 else '–'} | {pc(tot['no_unit_conflict_px'] / a1) if a1 else '–'} | {r7note} |")
res["다"] = C_
md.append("")
md.append("**표 다-2. 사전 정보 깊이 항이 작용하는 픽셀** (학습 해상도 1600 × 1157, 학습 시점 13장; r8 = 첫 반복 직전의 gₚ, r7 = 무게 (1 − cₚ) × 차단)\n")
md.append("| 설정 | 사전 정보 픽셀 | r8: gₚ = 1 (패치 있음 · cₚ 1 / cₚ 0, 없음 · cₚ 1 / cₚ 0) | r8: gₚ = 0 (패치 있음 · cₚ 1 / cₚ 0, 없음 · cₚ 1) | r7: 켜짐 | r7: 꺼짐 (cₚ = 1 / 충돌 차단) |")
md.append("|---|---|---|---|---|---|")
C2 = {}
for setting in TRAINED:
    r8 = json.loads((P8 / "runs" / f"dry_{setting}" / "model/monitor/init_report.json").read_text())["prior_weight"]["totals"]
    r7 = json.loads((R7 / "runs" / f"{setting}_spec" / "model/monitor/init_report.json").read_text())["prior_gate"]
    g1 = r8["unit_c1_g1"] + r8["unit_c0_g1"] + r8["no_unit_c1_g1"] + r8["no_unit_c0_g1"]
    g0 = r8["unit_c1_g0"] + r8["unit_c0_g0"] + r8["no_unit_c1_g0"]
    pp = r8["prior_px"]
    r7_on = r7["on"]; r7_off_c = r7["off_conflict"]; r7_off_a = pp - r7["prior_term_px"]
    C2[setting] = dict(r8=r8, r7=dict(on=r7_on, off_conflict=r7_off_c, off_observed=r7_off_a, prior_term_px=r7["prior_term_px"]))
    md.append(f"| {NAME[setting]} | {f0(pp)} | {f0(g1)} ({pc(g1 / pp)}): {f0(r8['unit_c1_g1'])} / {f0(r8['unit_c0_g1'])}, {f0(r8['no_unit_c1_g1'])} / {f0(r8['no_unit_c0_g1'])} | "
              f"{f0(g0)} ({pc(g0 / pp)}): {f0(r8['unit_c1_g0'])} / {f0(r8['unit_c0_g0'])}, {f0(r8['no_unit_c1_g0'])} | {f0(r7_on)} ({pc(r7_on / pp)}) | {f0(r7_off_a)} / {f0(r7_off_c)} |")
res["다-2"] = C2
md.append("")

# ------------------------------------------------------------------ 라 / 마 initialisation and first protection
GROUPS = [("image", "관측 출신 (SfM 점)"), ("support", "사전 정보 · 지지 영역"), ("missing_conflict", "사전 정보 · 결측 → 충돌"),
          ("missing_agree", "사전 정보 · 결측 → 일치"), ("missing_undetermined", "사전 정보 · 결측 → 혼재·근거 부족"),
          ("invisible", "사전 정보 · 비가시 영역"), ("no_unit", "사전 정보 · 패치 없음")]


def groups_of(z, has_unit_state_field="state"):
    pr = z["origin"] == 1
    loc = z["location"]; stt = z[has_unit_state_field]; Jt = z["judgment"]
    has = pr & (loc >= 0)
    return {"image": ~pr, "support": has & (stt == rule.ST_SUPPORT), "missing_conflict": has & (stt == rule.ST_MISSING) & (Jt == rule.J_CONFLICT),
            "missing_agree": has & (stt == rule.ST_MISSING) & (Jt == rule.J_AGREE),
            "missing_undetermined": has & (stt == rule.ST_MISSING) & np.isin(Jt, [rule.J_MIXED, rule.J_INSUFF]),
            "invisible": has & (stt == rule.ST_INVISIBLE), "no_unit": pr & ~has}


md_l = ["### 표 라. 초기화 — 심은 점과 심지 않은 점 (첫 반복 직전, 출처와 점이 속한 곳별)\n",
        "| 설정 | 점이 속한 곳 | 후보 점 | 심음 | 심지 않음 | r7 심음 | r7 대비 |", "|---|---|---|---|---|---|---|"]
md_m = ["### 표 마. 처음 보호되는 가우시안 (첫 반복 직전, 식 (7): 사전 정보 출신 · 전파된 판정 충돌 아님 · c̄ᵢ < 0.5 · uᵢ = 0 ≤ 4τ)\n",
        "| 설정 | 점이 속한 곳 | r8 보호 | 그 가운데 본 시점 0 | r7 보호 | r7 대비 |", "|---|---|---|---|---|---|"]
D_, E_ = {}, {}
for setting in TRAINED:
    z8 = np.load(P8 / "runs" / f"dry_{setting}" / "model/monitor/init_points.npz")
    z7 = np.load(R7 / "runs" / f"{setting}_spec" / "model/monitor/init_points.npz")
    g8 = groups_of(z8); g7 = groups_of(z7)
    p8 = z8["planted"]; p7 = z7["planted"]
    pr8 = z8["origin"] == 1; pr7 = z7["origin"] == 1
    prot8 = p8 & pr8 & (z8["E_first"] < 0.5) & (z8["judgment"] != rule.J_CONFLICT)
    prot7 = p7 & pr7 & (z7["E_first"] < 0.5) & (z7["judgment"] != rule.J_CONFLICT)
    n0 = z8["n_seeing_first"] == 0
    rep8 = json.loads((P8 / "runs" / f"dry_{setting}" / "model/monitor/init_report.json").read_text())
    assert int(prot8.sum()) == rep8["protection"]["n_protected"], (setting, int(prot8.sum()), rep8["protection"]["n_protected"])
    D_[setting], E_[setting] = {}, {}
    for key, lab in GROUPS:
        a, b = g8[key], g7[key]
        D_[setting][key] = dict(candidates=int(a.sum()), planted=int((a & p8).sum()), unplanted=int((a & ~p8).sum()), r7_planted=int((b & p7).sum()))
        E_[setting][key] = dict(protected=int((a & prot8).sum()), protected_no_view=int((a & prot8 & n0).sum()), r7_protected=int((b & prot7).sum()))
        d, e = D_[setting][key], E_[setting][key]
        md_l.append(f"| {NAME[setting]} | {lab} | {f0(d['candidates'])} | {f0(d['planted'])} | {f0(d['unplanted'])} | {f0(d['r7_planted'])} | {sd(d['planted'] - d['r7_planted'])} |")
        md_m.append(f"| {NAME[setting]} | {lab} | {f0(e['protected'])} | {f0(e['protected_no_view'])} | {f0(e['r7_protected'])} | {sd(e['protected'] - e['r7_protected'])} |")
    tp8 = int(p8.sum()); tp7 = int(p7.sum())
    md_l.append(f"| **{NAME[setting]}** | **합** | {f0(len(p8))} | {f0(tp8)} | {f0(len(p8) - tp8)} | {f0(tp7)} | {sd(tp8 - tp7)} |")
    md_m.append(f"| **{NAME[setting]}** | **합** | {f0(prot8.sum())} | {f0((prot8 & n0).sum())} | {f0(prot7.sum())} | {sd(int(prot8.sum()) - int(prot7.sum()))} |")
md += md_l + [""] + md_m + [""]
res["라"] = D_; res["마"] = E_

(OUT / "tables.md").write_text("\n".join(md) + "\n")
(OUT / "tables.json").write_text(json.dumps(res, indent=1, default=float))
print("\n".join(md))
