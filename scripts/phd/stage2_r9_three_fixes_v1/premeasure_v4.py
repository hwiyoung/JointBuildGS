"""PHD-STAGE2-R9-THREE-FIXES-v1 step 9 (jointbuildgs:dev, CPU): the pre-measurement of r8 (tables 가-마) with the r9 rules
and inputs, each table beside the r8 values (PHD-STAGE2-R8-FOUR-CASES-v1). No training.

  python premeasure_v4.py      # after stage1_products_r9.py, prepare_r9_inputs.py and the dry initialisations
  mounts: /artifacts (ro), /repo (ro), /r7 (ro), /r8 (ro), /p9 (rw)

Fixed values as r8 (configs/phd/stage2_r9_three_fixes_v1/r9.json). Propagation = src/phd/prior_propagation_v3.
Expected changes (order r9 step 4): LoD2 table 나 (bottom-face rows), 라 (invisible points), 마 (first protected).
Tables (Korean Markdown in /p9/premeasure_v4/tables.md; numbers in tables.json):
  가 tolerance per prior and surface kind       나 patches per surface (count and area)
  다 prior pixels without a patch (+ pixels where the prior depth term acts, training resolution)
  라 initialisation by origin and region         마 first protected Gaussians by the same groups (eq. 7 with the patch judgment)"""
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, "/repo")
from src.phd.prior_propagation_v3 import locations as locs  # noqa: E402
from src.phd.prior_propagation_v3 import rule  # noqa: E402

P9 = Path("/p9"); R8 = Path("/r8"); OUT = P9 / "premeasure_v4"; OUT.mkdir(parents=True, exist_ok=True)
CFG = json.loads(Path("/repo/configs/phd/stage2_r9_three_fixes_v1/r9.json").read_text())
S2 = Path("/artifacts/JointBuildGS/phase-payloads/phd/stage2_conf_guided_gs_v1/PHD-STAGE2-CONF-GUIDED-GS-v1")
TRAIN = json.loads((S2 / "runs/P_M_N/model/monitor/meta.json").read_text())["train_views"]
V = CFG["values"]
Q, K, R, CELL = V["majority"], V["min_evidence_locations"], V["max_distance_m"], V["cell_m"]
SETTINGS = ["M_N", "M_B", "L_N", "L_B"]
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


def load(root, setting, var=None):
    var = var or main_var(setting)
    st = locs.load_store(root / "stage1/products" / setting / f"store_{var}_c{CELL}.npz")
    table = {r["ext"]: r for r in json.loads((root / "stage1/products" / setting / f"surfaces_{var}.json").read_text())["surfaces"]}
    return st, table


def judged(st):
    state, vote = st["state_data"], st["vote_data"]
    J, _ = locs.propagate(st, state, vote, Q, K, R)
    return state, vote, J


# ------------------------------------------------------------------ 가 tolerance
T9 = json.loads((P9 / "stage1/tolerance.json").read_text())["priors"]
T8 = json.loads((R8 / "stage1/tolerance.json").read_text())["priors"]
md.append("### 표 가. 허용 오차 (정상 장면, 15시점, cₚ = 1, 대상 건물의 건물 면; 지붕 = 높이 차이, 벽 = 면에 수직인 거리)\n")
md.append("| 사전 정보 | 면 | 표본 수 (r8) | 정합 뒤 중앙값 (거르기 전 → 뒤) | NMAD (거르기 전 → 뒤) | 걸러낸 비율 | 허용 오차 τ = 2.5 × NMAD | r8 허용 오차 | r8 대비 | 기관 사양 | 경고 |")
md.append("|---|---|---|---|---|---|---|---|---|---|---|")
A_ = {}
for p, pname in (("M", "LoD2"), ("L", "항공 LiDAR")):
    for kind, kname in (("roof", "지붕"), ("wall", "벽")):
        o = T9[p][kind]; st_ = o["stats"]; o8 = T8[p][kind]
        spec_s = "없음" if o["spec"] is None else f"{o['spec']:.2f} m"
        warn = "있음" if o.get("warning") else "없음"
        tau_s = f"**{o['tau']:.6f} m**" + ("" if o["side"].startswith("data") else " (지붕 값)")
        n8 = o8["stats"].get("n") or 0
        if st_.get("n"):
            md.append(f"| {pname} | {kname} | {f0(st_['n'])} ({sd(st_['n'] - n8)}) | {st_['median_before']:+.4f} → {st_['median_after']:+.4f} m | "
                      f"{st_['nmad_before']:.4f} → {st_['nmad_after']:.4f} m | {pc(st_['clipped_share'])} | {tau_s} | {o8['tau']:.6f} m | {o['tau'] - o8['tau']:+.1e} m | {spec_s} | {warn} |")
        else:
            md.append(f"| {pname} | {kname} | 0 | – | – | – | {tau_s} | {o8['tau']:.6f} m | {o['tau'] - o8['tau']:+.1e} m | {spec_s} | {warn} |")
        A_[f"{p}_{kind}"] = dict(r9=o, r8_tau=o8["tau"], r8_n=n8)
res["가"] = A_
md.append("")

# ------------------------------------------------------------------ 나 patches per surface
md.append("### 표 나. 표면별 패치 (한 칸 0.25 m; 수 / 넓이 m²; 일치·충돌 = 지지 영역 패치의 표, 결측의 판정 = 고정 값 2/3·5곳·1 m의 전파)\n")
md.append("| 설정 | 표면 | 종류 | 지지 | 일치 | 충돌 | 결측 | 결측 → 충돌 | 결측 → 일치 | 결측 → 혼재 | 결측 → 근거 부족 | 비가시 | r8 대비 (지지 · 일치 · 충돌 · 결측 · 비가시) |")
md.append("|---|---|---|---|---|---|---|---|---|---|---|---|---|")
B = {}


def na(n, a):
    return f"{f0(n)} / {f1(a)}"


def surface_rows(st, table, state, vote, J):
    rows = {}
    a = st["loc_area"]
    for s in range(len(st["surf_ext"])):
        m = st["loc_surface"] == s
        if not m.any():
            continue
        ext = int(st["surf_ext"][s]); t = table.get(ext, {})
        sup = m & (state == rule.ST_SUPPORT); mis = m & (state == rule.ST_MISSING); inv = m & (state == rule.ST_INVISIBLE)
        row = dict(ext=ext, kind=int(st["surf_kind"][s]), target=bool(t.get("target")), type=t.get("type"), raised=t.get("raised_share", 0.0),
                   area=float(a[m].sum()), sup=(int(sup.sum()), float(a[sup].sum())), mis=(int(mis.sum()), float(a[mis].sum())),
                   inv=(int(inv.sum()), float(a[inv].sum())))
        for nm, vv in (("agree", rule.V_AGREE), ("conflict", rule.V_CONFLICT)):
            sel = sup & (vote == vv); row[nm] = (int(sel.sum()), float(a[sel].sum()))
        row["J"] = [(int((mis & (J == j)).sum()), float(a[mis & (J == j)].sum())) for j in JN]
        rows[ext] = row
    return rows


def label(setting, r):
    if setting.startswith("M"):
        e = r["ext"]
        if e >= 100000:
            return f"단차면 {e - 100000} (올린 면 둘레)"
        return f"면 {e} ({LOD2_NOTE.get(e, '대상 건물' if r['target'] else '이웃 건물')})"
    where = "대상 건물 윤곽 안" if r["target"] else "이웃 건물 윤곽 안"
    return f"표면 {r['ext']} ({where}{', 올린 점' if r['raised'] >= 0.5 else ''})"


ZERO = dict(sup=(0, 0.0), mis=(0, 0.0), inv=(0, 0.0), agree=(0, 0.0), conflict=(0, 0.0), J=[(0, 0.0)] * 4)


def diff(r9, r8):
    return " · ".join(sd(r9[k][0] - r8[k][0]) for k in ("sup", "agree", "conflict", "mis", "inv"))


def agg(rr):
    if not rr:
        return dict(ZERO)
    return dict(sup=(sum(r["sup"][0] for r in rr), sum(r["sup"][1] for r in rr)), mis=(sum(r["mis"][0] for r in rr), sum(r["mis"][1] for r in rr)),
                inv=(sum(r["inv"][0] for r in rr), sum(r["inv"][1] for r in rr)),
                agree=(sum(r["agree"][0] for r in rr), sum(r["agree"][1] for r in rr)), conflict=(sum(r["conflict"][0] for r in rr), sum(r["conflict"][1] for r in rr)),
                J=[(sum(r["J"][i][0] for r in rr), sum(r["J"][i][1] for r in rr)) for i in range(4)])


def emit(tag, lab, kind, r, r8):
    md.append(f"| {tag} | {lab} | {kind} | {na(*r['sup'])} | {na(*r['agree'])} | {na(*r['conflict'])} | {na(*r['mis'])} | "
              + " | ".join(na(*x) for x in r["J"]) + f" | {na(*r['inv'])} | {diff(r, r8)} |")


for setting in SETTINGS:
    st, table = load(P9, setting); st8, table8 = load(R8, setting)
    rows = surface_rows(st, table, *judged(st)); rows8 = surface_rows(st8, table8, *judged(st8))
    B[setting] = dict(r9=list(rows.values()), r8=list(rows8.values()))
    gone = [r for e, r in rows8.items() if e not in rows]             # surfaces of r8 that are not prior surfaces in r9
    shown = [r for r in rows.values() if (r["target"] and (r["sup"][0] + r["mis"][0] > 0) and (setting.startswith("M") or r["area"] >= 5))
             or r["mis"][0] >= 100 or r["sup"][0] >= 1500]
    shown.sort(key=lambda r: (r["kind"], not r["target"], -(r["sup"][0] + r["mis"][0])))
    for r in shown:
        emit(NAME[setting], label(setting, r), "지붕" if r["kind"] == 1 else "벽", r, rows8.get(r["ext"], ZERO))
    rest = [r for r in rows.values() if r not in shown]
    for kind, kn in ((1, "지붕"), (2, "벽")):
        rr = [r for r in rest if r["kind"] == kind]
        if rr:
            emit(NAME[setting], f"그 밖의 {len(rr)}개 표면 합", kn, agg(rr), agg([rows8[r["ext"]] for r in rr if r["ext"] in rows8]))
    if gone:
        tg = [r for r in gone if r["target"]]; og = [r for r in gone if not r["target"]]
        for grp, lab in ((tg, "r8의 대상 건물 바닥면 (면 " + ", ".join(str(r["ext"]) for r in tg) + ") — r9에서 뺌"), (og, f"r8의 이웃 건물 바닥면 {len(og)}개 — r9에서 뺌")):
            if grp:
                g8 = agg(grp)
                md.append(f"| {NAME[setting]} | {lab} | – | 0 / 0.0 | 0 / 0.0 | 0 / 0.0 | 0 / 0.0 | 0 / 0.0 | 0 / 0.0 | 0 / 0.0 | 0 / 0.0 | 0 / 0.0 | {diff(ZERO, g8)} |")
    tot, tot8 = agg(list(rows.values())), agg(list(rows8.values()))
    emit(f"**{NAME[setting]}**", f"**전체 {len(rows)}개 표면** (r8 {len(rows8)}개)", "–", tot, tot8)
    B[setting + "_total"] = dict(r9=tot, r8=tot8, n_surfaces=len(rows), n_surfaces_r8=len(rows8), gone=[r["ext"] for r in gone])
    # patch states of the surfaces both have: how many patches changed state (same surface, same cell centre)
    if setting.startswith("M"):
        key9 = {(int(st["surf_ext"][s]), tuple(np.round(c, 3))): i for i, (s, c) in enumerate(zip(st["loc_surface"], st["loc_center"]))}
        same = changed = missing9 = 0
        for i, (s, c) in enumerate(zip(st8["loc_surface"], st8["loc_center"])):
            k = (int(st8["surf_ext"][s]), tuple(np.round(c, 3)))
            j = key9.get(k)
            if j is None:
                missing9 += 1
            elif st["state_data"][j] == st8["state_data"][i] and st["vote_data"][j] == st8["vote_data"][i]:
                same += 1
            else:
                changed += 1
        B[setting + "_patch_match"] = dict(r8_patches=int(len(st8["loc_area"])), r9_patches=int(len(st["loc_area"])), same_state_and_vote=same,
                                           changed_state_or_vote=changed, r8_patches_not_in_r9=missing9)
res["나"] = B
md.append("")
md.append("**표 나-2. LoD2: r8과 r9의 패치 대응** (같은 표면, 같은 칸 중심)\n")
md.append("| 설정 | r8 패치 | r9 패치 | 상태·표가 같음 | 상태나 표가 바뀜 | r8에만 있음 (바닥면) |")
md.append("|---|---|---|---|---|---|")
for setting in ("M_N", "M_B"):
    b = B[setting + "_patch_match"]
    md.append(f"| {NAME[setting]} | {f0(b['r8_patches'])} | {f0(b['r9_patches'])} | {f0(b['same_state_and_vote'])} | {f0(b['changed_state_or_vote'])} | {f0(b['r8_patches_not_in_r9'])} |")
md.append("")

# ------------------------------------------------------------------ 다 pixels without a patch
md.append("### 표 다. 패치가 없는 사전 정보 픽셀 (학습 시점 13장, 원해상도)\n")
md.append("| 설정 | 사전 정보 픽셀 (r8 대비) | 패치 없음 (비율) | 그 가운데 가파른 삼각형 / 건물이 아닌 면 | 그 가운데 cₚ = 1 (비율) | cₚ = 1 가운데 일치 | cₚ = 1 가운데 충돌 | r8과 같은가 |")
md.append("|---|---|---|---|---|---|---|---|")
C_ = {}
for setting in SETTINGS:
    sm = json.loads((P9 / "stage1/products" / setting / "summary.json").read_text())
    sm8 = json.loads((R8 / "stage1/products" / setting / "summary.json").read_text())
    tot = {k: sum(sm["pixels"][v][k] for v in TRAIN) for k in sm["pixels"][TRAIN[0]]}
    tot8 = {k: sum(sm8["pixels"][v][k] for v in TRAIN) for k in sm8["pixels"][TRAIN[0]]}
    C_[setting] = dict(r9=tot, r8=tot8)
    nu = tot["no_unit_px"]; a1 = tot["no_unit_a1_px"]
    same = all(tot[k] == tot8[k] for k in tot)
    md.append(f"| {NAME[setting]} | {f0(tot['prior_px'])} ({sd(tot['prior_px'] - tot8['prior_px'])}) | {f0(nu)} ({pc(nu / tot['prior_px'])}) | {f0(tot['no_unit_steep_px'])} / {f0(tot['no_unit_nonbuilding_surface_px'])} | "
              f"{f0(a1)} ({pc(a1 / nu) if nu else '–'}) | {pc(tot['no_unit_agree_px'] / a1) if a1 else '–'} | {pc(tot['no_unit_conflict_px'] / a1) if a1 else '–'} | "
              f"{'모든 열이 같다' if same else '사전 정보 픽셀만 다르다 (바닥면을 보던 픽셀)' if all(tot[k] == tot8[k] for k in tot if k.startswith('no_unit')) else '다르다'} |")
res["다"] = C_
md.append("")
md.append("**표 다-2. 사전 정보 깊이 항이 작용하는 픽셀** (학습 해상도 1600 × 1157, 학습 시점 13장; 첫 반복 직전의 gₚ)\n")
md.append("| 설정 | 사전 정보 픽셀 (r8) | gₚ = 1 (패치 있음 · cₚ 1 / cₚ 0, 없음 · cₚ 1 / cₚ 0) | gₚ = 0 (패치 있음 · cₚ 1 / cₚ 0, 없음 · cₚ 1) | r8 gₚ = 1 | r8 gₚ = 0 |")
md.append("|---|---|---|---|---|---|")
C2 = {}
for setting in SETTINGS:
    r9 = json.loads((P9 / "runs" / f"dry_{setting}" / "model/monitor/init_report.json").read_text())["prior_weight"]["totals"]
    r8 = json.loads((R8 / "runs" / f"dry_{setting}" / "model/monitor/init_report.json").read_text())["prior_weight"]["totals"]

    def g(t):
        return (t["unit_c1_g1"] + t["unit_c0_g1"] + t["no_unit_c1_g1"] + t["no_unit_c0_g1"], t["unit_c1_g0"] + t["unit_c0_g0"] + t["no_unit_c1_g0"])
    g1, g0 = g(r9); h1, h0 = g(r8)
    pp = r9["prior_px"]
    C2[setting] = dict(r9=r9, r8=r8)
    md.append(f"| {NAME[setting]} | {f0(pp)} ({f0(r8['prior_px'])}) | {f0(g1)} ({pc(g1 / pp)}): {f0(r9['unit_c1_g1'])} / {f0(r9['unit_c0_g1'])}, {f0(r9['no_unit_c1_g1'])} / {f0(r9['no_unit_c0_g1'])} | "
              f"{f0(g0)} ({pc(g0 / pp)}): {f0(r9['unit_c1_g0'])} / {f0(r9['unit_c0_g0'])}, {f0(r9['no_unit_c1_g0'])} | {f0(h1)} ({sd(g1 - h1)}) | {f0(h0)} ({sd(g0 - h0)}) |")
res["다-2"] = C2
md.append("")

# ------------------------------------------------------------------ 라 / 마 initialisation and first protection
GROUPS = [("image", "관측 출신 (SfM 점)"), ("support", "사전 정보 · 지지 영역"), ("support_conflict", "  그 가운데 표 충돌"),
          ("missing_conflict", "사전 정보 · 결측 → 충돌"), ("missing_agree", "사전 정보 · 결측 → 일치"),
          ("missing_undetermined", "사전 정보 · 결측 → 혼재·근거 부족"), ("invisible", "사전 정보 · 비가시 영역"),
          ("bottom", "  그 가운데 바닥면 (r9에서 뺌)"), ("no_unit", "사전 정보 · 패치 없음")]


def groups_of(z, bottom_ext):
    pr = z["origin"] == 1
    loc = z["location"]; stt = z["state"]; Jt = z["judgment"]; Jl = z["unit_judgment"]
    has = pr & (loc >= 0)
    return {"image": ~pr, "support": has & (stt == rule.ST_SUPPORT), "support_conflict": has & (stt == rule.ST_SUPPORT) & (Jl == rule.J_CONFLICT),
            "missing_conflict": has & (stt == rule.ST_MISSING) & (Jt == rule.J_CONFLICT),
            "missing_agree": has & (stt == rule.ST_MISSING) & (Jt == rule.J_AGREE),
            "missing_undetermined": has & (stt == rule.ST_MISSING) & np.isin(Jt, [rule.J_MIXED, rule.J_INSUFF]),
            "invisible": has & (stt == rule.ST_INVISIBLE), "bottom": has & np.isin(z["surface"], bottom_ext), "no_unit": pr & ~has}


md_l = ["### 표 라. 초기화 — 심은 점과 심지 않은 점 (첫 반복 직전, 출처와 점이 속한 곳별)\n",
        "| 설정 | 점이 속한 곳 | 후보 점 | 심음 | 심지 않음 | r8 후보 | r8 심음 | r8 대비 (심음) |", "|---|---|---|---|---|---|---|---|"]
md_m = ["### 표 마. 처음 보호되는 가우시안 (첫 반복 직전, 식 (7): 사전 정보 출신 · 패치의 판정 충돌 아님 · c̄ᵢ < 0.5 · uᵢ = 0 ≤ 4τ)\n",
        "| 설정 | 점이 속한 곳 | r9 보호 | 그 가운데 본 시점 0 | r8 보호 | r8 대비 |", "|---|---|---|---|---|---|"]
D_, E_ = {}, {}
for setting in SETTINGS:
    z9 = np.load(P9 / "runs" / f"dry_{setting}" / "model/monitor/init_points.npz")
    z8 = np.load(R8 / "runs" / f"dry_{setting}" / "model/monitor/init_points.npz")
    t8 = {r["ext"]: r for r in json.loads((R8 / "stage1/products" / setting / f"surfaces_{main_var(setting)}.json").read_text())["surfaces"]}
    bottom_ext = [e for e, r in t8.items() if r.get("type") == "ground"]
    g9 = groups_of(z9, bottom_ext); g8 = groups_of(z8, bottom_ext)
    p9 = z9["planted"]; p8 = z8["planted"]
    pr9 = z9["origin"] == 1; pr8 = z8["origin"] == 1
    prot9, _, _, _ = rule.protected(p9 & pr9, z9["E_first"], 0.5, np.zeros(len(p9)), 1.0, z9["unit_judgment"])
    prot8 = p8 & pr8 & (z8["E_first"] < 0.5) & (z8["judgment"] != rule.J_CONFLICT)        # the r8 rule
    n0 = z9["n_seeing_first"] == 0
    rep9 = json.loads((P9 / "runs" / f"dry_{setting}" / "model/monitor/init_report.json").read_text())
    rep8 = json.loads((R8 / "runs" / f"dry_{setting}" / "model/monitor/init_report.json").read_text())
    assert int(prot9.sum()) == rep9["protection"]["n_protected"], (setting, int(prot9.sum()), rep9["protection"]["n_protected"])
    assert int(prot8.sum()) == rep8["protection"]["n_protected"], (setting, int(prot8.sum()), rep8["protection"]["n_protected"])
    D_[setting], E_[setting] = {}, {}
    for key, lab in GROUPS:
        a, b = g9[key], g8[key]
        D_[setting][key] = dict(candidates=int(a.sum()), planted=int((a & p9).sum()), unplanted=int((a & ~p9).sum()),
                                r8_candidates=int(b.sum()), r8_planted=int((b & p8).sum()))
        E_[setting][key] = dict(protected=int((a & prot9).sum()), protected_no_view=int((a & prot9 & n0).sum()), r8_protected=int((b & prot8).sum()))
        d, e = D_[setting][key], E_[setting][key]
        md_l.append(f"| {NAME[setting]} | {lab} | {f0(d['candidates'])} | {f0(d['planted'])} | {f0(d['unplanted'])} | {f0(d['r8_candidates'])} | {f0(d['r8_planted'])} | {sd(d['planted'] - d['r8_planted'])} |")
        md_m.append(f"| {NAME[setting]} | {lab} | {f0(e['protected'])} | {f0(e['protected_no_view'])} | {f0(e['r8_protected'])} | {sd(e['protected'] - e['r8_protected'])} |")
    tp9 = int(p9.sum()); tp8 = int(p8.sum())
    md_l.append(f"| **{NAME[setting]}** | **합** | {f0(len(p9))} | {f0(tp9)} | {f0(len(p9) - tp9)} | {f0(len(p8))} | {f0(tp8)} | {sd(tp9 - tp8)} |")
    md_m.append(f"| **{NAME[setting]}** | **합** | {f0(prot9.sum())} | {f0((prot9 & n0).sum())} | {f0(prot8.sum())} | {sd(int(prot9.sum()) - int(prot8.sum()))} |")
    D_[setting]["orientation"] = rep9["init"].get("orientation")
md += md_l + [""] + md_m + [""]
res["라"] = D_; res["마"] = E_

(OUT / "tables.md").write_text("\n".join(md) + "\n")
(OUT / "tables.json").write_text(json.dumps(res, indent=1, default=float))
print("\n".join(md))
