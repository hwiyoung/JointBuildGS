"""PHD-STAGE2-R7-PROPAGATION-v1 step 6 (jointbuildgs:dev, CPU): the pre-measurement again with the new definitions.

  python premeasure_v2.py          # after stage1_products.py (all settings) and, for table E, the dry runs
  mounts: /artifacts (ro), /repo (ro), /p7 (rw), /pm1 (pre-measurement v1 payload, ro)

Fixed values (configs/phd/stage2_r7_propagation_v1/r7.json): majority 2/3, minimum 5 locations, maximum distance 1 m,
cells 0.25 m, tolerance per surface kind with the agency spec lower bound. Propagation = src/phd/prior_propagation_v1.
Tables (Korean, Markdown blocks in /p7/premeasure_v2/tables.md; numbers in tables.json and CSVs):
  A tolerance per prior and surface kind           B locations per surface (TIN before / after the outline boundaries)
  C judgments of the missing locations (fixed values, roof / wall)      D sensitivity, one value at a time
  E initialisation candidates (dry runs of the fork, same form as table 8 of v1)   F injected faces (check only)
  G wall conflict share, v1 against now            H outline overlap (LoD2 GroundSurface against own classification)"""
import csv
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, "/repo")
from src.phd.prior_propagation_v1 import locations as locs  # noqa: E402
from src.phd.prior_propagation_v1 import outlines as outl  # noqa: E402
from src.phd.prior_propagation_v1 import rule  # noqa: E402

P7 = Path("/p7"); OUT = P7 / "premeasure_v2"; OUT.mkdir(parents=True, exist_ok=True)
PM1 = Path("/pm1")
CFG = json.loads(Path("/repo/configs/phd/stage2_r7_propagation_v1/r7.json").read_text())
S1 = Path("/artifacts/JointBuildGS/phase-payloads/phd/stage1_conf_tol_conflict_v1/PHD-STAGE1-CONF-TOL-CONFLICT-v1")
PJ = json.loads((S1 / "inputs/lod2_polygons.json").read_text())
RECT = np.array(PJ["als_crop_local_xy"], float)
V = CFG["values"]
Q, K, R, CELL = V["majority"], V["min_evidence_locations"], V["max_distance_m"], V["cell_m"]
SETTINGS = ["M_N", "M_B", "M_C", "L_N", "L_B"]
NAME = {"M_N": "LoD2 정상", "M_B": "LoD2 주지붕 +1 m", "M_C": "LoD2 그늘진 지붕 끝 +1 m", "L_N": "항공 LiDAR 정상", "L_B": "항공 LiDAR 주지붕 +1 m"}
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


def main_var(s):
    return "poly" if s.startswith("M") else "lod2"


def load(setting, var=None, cell=CELL):
    var = var or main_var(setting)
    st = locs.load_store(P7 / "stage1/products" / setting / f"store_{var}_c{cell}.npz")
    table = {r["ext"]: r for r in json.loads((P7 / "stage1/products" / setting / f"surfaces_{var}.json").read_text())["surfaces"]}
    return st, table


def judged(st, tag="spec", q=Q, k=K, r=R, G=None):
    state, vote = st[f"state_{tag}"], st[f"vote_{tag}"]
    J, _ = locs.propagate(st, state, vote, q, k, r, G=G)
    return state, vote, J


def kind_of_loc(st):
    return st["loc_kind"]          # 1 roof-like, 2 wall-like


GRAPH = {}


def graph_of(key, st):
    if key not in GRAPH:
        GRAPH[key] = locs.graph(st)
    return GRAPH[key]


# ------------------------------------------------------------------ A tolerance
TOL = json.loads((P7 / "stage1/tolerance.json").read_text())
md.append("### 표 가. 지붕과 벽의 허용 오차 (정상 장면, 15시점, 관측 신뢰도 1, 대상 건물의 표면; 잔차는 지붕형 = 연직, 벽형 = 면에 수직)\n")
md.append("| 사전 정보 | 면 종류 | 표본 수 | 정합 뒤 중앙값 (거르기 전 → 뒤) | NMAD (거르기 전 → 뒤) | 걸러낸 비율 | 2.5 × NMAD | 기관 사양 | 허용 오차 (채택된 쪽) | 실측 폭만 쓴 값 |")
md.append("|---|---|---|---|---|---|---|---|---|---|")
for p, pname in (("M", "LoD2"), ("L", "항공 LiDAR")):
    for kind, kname in (("roof", "지붕형"), ("wall", "벽형")):
        o = TOL["priors"][p]["spec"][kind]; st_ = o["stats"]; od = TOL["priors"][p]["data"][kind]
        side = {"spec": "기관 사양", "data": "실측 폭", "data (no spec)": "실측 폭(사양 없음)"}.get(o["side"], "지붕 값(벽이 표면이 아님)" if o["side"].startswith("roof value") else o["side"])
        spec_s = "없음" if o["spec"] is None else f"{o['spec']:.2f} m"
        if st_["n"]:
            md.append(f"| {pname} | {kname} | {f0(st_['n'])} | {st_['median_before']:+.4f} → {st_['median_after']:+.4f} m | {st_['nmad_before']:.4f} → {st_['nmad_after']:.4f} m | "
                      f"{pc(st_['clipped_share'])} | {st_['width']:.4f} m | {spec_s} | **{o['tau']:.4f} m** ({side}) | {od['tau']:.4f} m |")
        else:
            md.append(f"| {pname} | {kname} | 0 | – | – | – | – | {spec_s} | **{o['tau']:.4f} m** ({side}) | {od['tau']:.4f} m |")
res["A"] = TOL
md.append("")

# ------------------------------------------------------------------ B per-surface locations
md.append("### 표 나. 표면별 위치 (한 칸 0.25 m; 일치·충돌 = 지지 위치의 표; 판정 = 고정 값 2/3·5곳·1 m의 전파)\n")
md.append("| 설정 | 표면 | 종류 | 넓이 m² | 지지 위치 | 일치 | 충돌 | 결측 위치 | 결측의 판정 (충돌 · 일치 · 혼재 · 근거 부족) | 비가시 위치 |")
md.append("|---|---|---|---|---|---|---|---|---|---|")
B = {}


def surface_rows(setting, var, st, table, state, vote, J, top=None):
    rows = []
    for s in range(len(st["surf_ext"])):
        m = st["loc_surface"] == s
        if not m.any():
            continue
        ext = int(st["surf_ext"][s]); t = table.get(ext, {})
        sup = m & (state == rule.ST_SUPPORT); mis = m & (state == rule.ST_MISSING)
        rows.append(dict(ext=ext, kind=int(st["surf_kind"][s]), target=bool(t.get("target")), type=t.get("type"), region=t.get("region"),
                         raised=t.get("raised_share", 0.0), area=float(st["loc_area"][m].sum()), n_sup=int(sup.sum()),
                         agree=float((vote[sup] == rule.V_AGREE).mean()) if sup.any() else float("nan"),
                         conflict=float((vote[sup] == rule.V_CONFLICT).mean()) if sup.any() else float("nan"),
                         n_mis=int(mis.sum()), J=[int((mis & (J == j)).sum()) for j in JN], n_inv=int((m & (state == rule.ST_INVISIBLE)).sum())))
    return rows


def label(setting, var, r):
    if setting.startswith("M"):
        e = r["ext"]
        if e >= 100000:
            return f"단차면 {e - 100000} (올린 면 둘레)"
        return f"면 {e} ({LOD2_NOTE.get(e, '대상 건물' if r['target'] else '이웃 건물')})"
    reg = r["region"]
    where = "윤곽 없음" if var == "none" else ("대상 건물 윤곽 안" if r["target"] else ("윤곽 밖" if reg is None or reg < 0 else "이웃 건물 윤곽 안"))
    extra = ", 올린 점" if r["raised"] >= 0.5 else ""
    return f"표면 {r['ext']} ({where}{extra})"


for setting in SETTINGS:
    vars_ = [main_var(setting)] if setting.startswith("M") else ["none", "lod2"]
    for var in vars_:
        st, table = load(setting, var)
        state, vote, J = judged(st, G=graph_of((setting, var, CELL), st))
        rows = surface_rows(setting, var, st, table, state, vote, J)
        B[f"{setting}_{var}"] = rows
        shown = [r for r in rows if (r["target"] and (r["n_sup"] + r["n_mis"] > 0) and (setting.startswith("M") or r["area"] >= 5))
                 or r["n_mis"] >= 100 or r["n_sup"] >= 1500]
        shown.sort(key=lambda r: (r["kind"], not r["target"], -(r["n_sup"] + r["n_mis"])))
        tag = NAME[setting] + ("" if setting.startswith("M") else (" · 윤곽 경계 전" if var == "none" else " · 윤곽 경계 후"))
        for r in shown:
            md.append(f"| {tag} | {label(setting, var, r)} | {'지붕형' if r['kind'] == 1 else '벽형'} | {f1(r['area'])} | {f0(r['n_sup'])} | {pc(r['agree'])} | {pc(r['conflict'])} | "
                      f"{f0(r['n_mis'])} | {' · '.join(f0(x) for x in r['J'])} | {f0(r['n_inv'])} |")
        rest = [r for r in rows if r not in shown]
        for kind, kn in ((1, "지붕형"), (2, "벽형")):
            rr = [r for r in rest if r["kind"] == kind]
            if not rr:
                continue
            ns = sum(r["n_sup"] for r in rr); cf = sum(r["conflict"] * r["n_sup"] for r in rr if r["n_sup"])
            md.append(f"| {tag} | 그 밖의 {len(rr)}개 표면 합 | {kn} | {f1(sum(r['area'] for r in rr))} | {f0(ns)} | {pc(1 - cf / ns) if ns else '–'} | "
                      f"{pc(cf / ns) if ns else '–'} | {f0(sum(r['n_mis'] for r in rr))} | {' · '.join(f0(sum(r['J'][i] for r in rr)) for i in range(4))} | "
                      f"{f0(sum(r['n_inv'] for r in rr))} |")
res["B"] = B
md.append("")
# TIN surfaces before / after: summary counts
md.append("| 항공 LiDAR 설정 | 윤곽 | 건물 표면 수 | 위치 | 지지 | 결측 | 비가시 | 가장 큰 표면 넓이 m² | 대상 건물 윤곽 안 건물 표면 수 |")
md.append("|---|---|---|---|---|---|---|---|---|")
for setting in ("L_N", "L_B"):
    for var, vn in (("none", "없음 (지난 측정)"), ("lod2", "LoD2 바닥면"), ("cls", "자체 분류 덩어리")):
        st, table = load(setting, var)
        state = st["state_spec"]
        areas = np.bincount(st["loc_surface"], weights=st["loc_area"], minlength=len(st["surf_ext"]))
        n_t = sum(1 for r in table.values() if r["is_building_face"] and r.get("target"))
        md.append(f"| {NAME[setting]} | {vn} | {f0(len(st['surf_ext']))} | {f0(len(state))} | {f0((state == rule.ST_SUPPORT).sum())} | "
                  f"{f0((state == rule.ST_MISSING).sum())} | {f0((state == rule.ST_INVISIBLE).sum())} | {f1(areas.max())} | {f0(n_t)} |")
md.append("")

# ------------------------------------------------------------------ C judgments at the fixed values, roof / wall
md.append(f"### 표 다. 고정한 값(다수의 기준 2/3, 최소량 {K}곳, 최대 거리 {R:g} m)에서 결측 위치의 판정 (위치 수 / 넓이 m²)\n")
md.append("| 설정 | 면 종류 | 결측 위치 | 충돌 | 일치 | 혼재 | 근거 부족 | 판정이 닿은 몫 (근거 부족 아님) | 같은 표면에 지지 위치 없음 |")
md.append("|---|---|---|---|---|---|---|---|---|")
C = {}
for setting in SETTINGS:
    st, table = load(setting)
    G = graph_of((setting, main_var(setting), CELL), st)
    state, vote, J = judged(st, G=G)
    kind = kind_of_loc(st)
    has_sup = np.zeros(len(st["surf_ext"]), bool); has_sup[st["loc_surface"][state == rule.ST_SUPPORT]] = True
    for kv, kn in ((1, "지붕형"), (2, "벽형"), (0, "전체")):
        m = (state == rule.ST_MISSING) & ((kind == kv) if kv else True)
        if not m.any():
            continue
        a = st["loc_area"]
        cells = [f"{f0((m & (J == j)).sum())} / {f1(a[m & (J == j)].sum())}" for j in JN]
        reach = (m & (J != rule.J_INSUFF)).sum() / m.sum()
        nos = int((m & ~has_sup[st["loc_surface"]]).sum())
        C[f"{setting}_{kn}"] = dict(n=int(m.sum()), **{rule.J_NAMES[j]: int((m & (J == j)).sum()) for j in JN},
                                    **{f"area_{rule.J_NAMES[j]}": float(a[m & (J == j)].sum()) for j in JN}, reach=float(reach), no_support=nos)
        md.append(f"| {NAME[setting]} | {kn} | {f0(m.sum())} ({f1(a[m].sum())} m²) | " + " | ".join(cells) + f" | {pc(reach)} | {f0(nos)} |")
res["C"] = C
md.append("")

# ------------------------------------------------------------------ D sensitivity
md.append("### 표 라. 값 민감도 — 한 번에 하나씩 바꾼 결측 위치의 판정 (충돌 · 일치 · 혼재 · 근거 부족, 위치 수; 괄호 = 충돌 넓이 m²)\n")
cases = [("기준 (2/3, 5곳, 1 m, 0.25 m, 사양 하한)", dict()), ("최소량 3곳", dict(k=3)), ("최소량 10곳", dict(k=10)),
         ("최대 거리 0.5 m", dict(r=0.5)), ("최대 거리 2 m", dict(r=2.0)), ("칸 0.5 m", dict(cell=0.5)), ("허용 오차 실측 폭만", dict(tag="data"))]
md.append("| 바꾼 값 | " + " | ".join(NAME[s] for s in SETTINGS) + " |")
md.append("|---|" + "---|" * len(SETTINGS))
D = {}
for cname, kw in cases:
    cells = []
    for setting in SETTINGS:
        cell = kw.get("cell", CELL)
        st, table = load(setting, cell=cell)
        G = graph_of((setting, main_var(setting), cell), st)
        state, vote, J = judged(st, tag=kw.get("tag", "spec"), q=Q, k=kw.get("k", K), r=kw.get("r", R), G=G)
        m = state == rule.ST_MISSING
        cnt = [int((m & (J == j)).sum()) for j in JN]
        ca = float(st["loc_area"][m & (J == rule.J_CONFLICT)].sum())
        D[f"{cname}|{setting}"] = dict(counts=cnt, conflict_area=ca, n_missing=int(m.sum()))
        cells.append(" · ".join(f0(x) for x in cnt) + f" ({f1(ca)})")
    md.append(f"| {cname} | " + " | ".join(cells) + " |")
res["D"] = D
md.append("")

# ------------------------------------------------------------------ E initialisation candidates (from the dry runs)
md.append("### 표 마. 초기화 후보 사전 정보 점 (fork r7 첫 반복 직전; 가우시안 신뢰도 = 위치가 있으면 그 위치의 값, 없으면 중심 픽셀의 값)\n")
md.append("| 설정 | 후보 점 | 가우시안 신뢰도 | 점 수 | 위치 없음 | 비가시 | 지지·일치 | 지지·충돌 | 결측→충돌 | 결측→일치 | 결측→혼재 | 결측→근거 부족 | 심음 |")
md.append("|---|---|---|---|---|---|---|---|---|---|---|---|---|")
E = {}
for setting in ("M_N", "M_B", "L_N", "L_B"):
    f = P7 / "runs" / f"{setting}_spec" / "model/monitor/init_points.npz"
    if not f.exists():
        continue
    z = np.load(f)
    pr = z["origin"] == 1
    loc = z["location"][pr]; stt = z["state"][pr]; Jt = z["judgment"][pr]; Ef = z["E_first"][pr]; cnt = z["n_seeing_centre"][pr]; planted = z["planted"][pr]
    st, _ = load(setting)
    vote = np.where(loc >= 0, st["vote_spec"][np.maximum(loc, 0)], -1)
    has = loc >= 0
    seeing = np.where(has, st["n_seeing_spec"][np.maximum(loc, 0)], cnt)
    cls = np.where(seeing == 0, 0, np.where(Ef < 0.5, 1, 2))
    cols = {"no_location": ~has, "invisible": has & (stt == rule.ST_INVISIBLE),
            "support_agree": has & (stt == rule.ST_SUPPORT) & (vote == rule.V_AGREE), "support_conflict": has & (stt == rule.ST_SUPPORT) & (vote == rule.V_CONFLICT),
            "missing_conflict": has & (stt == rule.ST_MISSING) & (Jt == rule.J_CONFLICT), "missing_agree": has & (stt == rule.ST_MISSING) & (Jt == rule.J_AGREE),
            "missing_mixed": has & (stt == rule.ST_MISSING) & (Jt == rule.J_MIXED), "missing_insufficient": has & (stt == rule.ST_MISSING) & (Jt == rule.J_INSUFF)}
    E[setting] = {}
    for c, lab in ((0, "보는 시점 0"), (1, "0.5 미만"), (2, "0.5 이상")):
        mm = cls == c
        row = {k: int((v & mm).sum()) for k, v in cols.items()}; row["planted"] = int((planted & mm).sum())
        E[setting][lab] = row
        md.append(f"| {NAME[setting]} | {f0(pr.sum())} | {lab} | {f0(mm.sum())} | " + " | ".join(f0(row[k]) for k in cols) + f" | {f0(row['planted'])} |")
res["E"] = E
md.append("")

# ------------------------------------------------------------------ F injected faces
md.append("### 표 바. 주입한 면의 확인 (값을 고르는 데 쓰지 않는다; 주입 면의 사전 정보는 1 m 틀렸으므로 결측 위치의 옳은 판정은 충돌이다)\n")
md.append("| 면 | 지지 위치 (충돌 비율) | 결측 위치 | 고정 값 판정 (충돌 · 일치 · 혼재 · 근거 부족) | 허용 오차 실측 폭만 | 최대 거리 2 m |")
md.append("|---|---|---|---|---|---|")
F = {}


def inj_rows():
    out = []
    st, table = load("M_B"); out.append(("M_B", "LoD2 주지붕 +1 m · 면 3396 (주입)", st["loc_surface"] == locs.compact_index(st, [3396])[0]))
    st, table = load("M_N"); out.append(("M_N", "비교: LoD2 정상 · 면 3396", st["loc_surface"] == locs.compact_index(st, [3396])[0]))
    st, table = load("M_C"); out.append(("M_C", "LoD2 그늘진 지붕 끝 +1 m · 면 3394 (주입)", st["loc_surface"] == locs.compact_index(st, [3394])[0]))
    st, table = load("M_N"); out.append(("M_N", "비교: LoD2 정상 · 면 3394", st["loc_surface"] == locs.compact_index(st, [3394])[0]))
    st, table = load("L_B")
    raised = [e for e, r in table.items() if r["is_building_face"] and r["raised_share"] >= 0.5]
    out.append(("L_B", f"항공 LiDAR 주지붕 +1 m · 올린 점 표면 {len(raised)}개", np.isin(st["loc_surface"], locs.compact_index(st, raised))))
    return out


for setting, lab, sel in inj_rows():
    st, _ = load(setting)
    G = graph_of((setting, main_var(setting), CELL), st)
    res_c = []
    for kw in (dict(), dict(tag="data"), dict(r=2.0)):
        state, vote, J = judged(st, tag=kw.get("tag", "spec"), r=kw.get("r", R), G=G)
        m = sel & (state == rule.ST_MISSING)
        res_c.append([int((m & (J == j)).sum()) for j in JN])
        if not kw:
            sup = sel & (state == rule.ST_SUPPORT)
            cf = float((vote[sup] == rule.V_CONFLICT).mean()) if sup.any() else float("nan")
            n_sup, n_mis = int(sup.sum()), int(m.sum())
    F[lab] = dict(n_support=n_sup, support_conflict=cf, n_missing=n_mis, fixed=res_c[0], data=res_c[1], r2=res_c[2])
    md.append(f"| {lab} | {f0(n_sup)} ({pc(cf)}) | {f0(n_mis)} | " + " | ".join(" · ".join(f0(x) for x in c) for c in res_c) + " |")
res["F"] = F
md.append("")

# ------------------------------------------------------------------ G wall conflict share, v1 against now
md.append("### 표 사. 벽의 충돌 비율 — 지난 측정(벽에 지붕 허용 오차 0.0568 m)과 지금(벽 허용 오차)\n")
md.append("| 면 | 지지 위치 (지난 / 지금) | 충돌 비율 지난 | 충돌 비율 지금 | 픽셀 충돌 비율 지난 | 픽셀 충돌 비율 지금 |")
md.append("|---|---|---|---|---|---|")
G_ = {}
old = {int(r["surface"]): r for r in csv.DictReader(open(PM1 / "measure/M_N/surfaces.csv"))}
oz = np.load(PM1 / "measure/M_N/locations.npz")
st, table = load("M_N")
state, vote = st["state_spec"], st["vote_spec"]
walls = [3403, 3391, 3392, 3388, 3398, 3390, 3400, 3397, 3402]
tot_old = [0, 0, 0, 0]; tot_new = [0, 0, 0, 0]
for w in walls + ["target", "all"]:
    if w == "target":
        e_set = [e for e, r in table.items() if r["target"] and r["kind"] == 2]
    elif w == "all":
        e_set = [e for e, r in table.items() if r["kind"] == 2]
    else:
        e_set = [w]
    cidx = locs.compact_index(st, e_set); cidx = cidx[cidx >= 0]
    m = np.isin(st["loc_surface"], cidx)
    sup = m & (state == rule.ST_SUPPORT)
    new_share = float((vote[sup] == rule.V_CONFLICT).mean()) if sup.any() else float("nan")
    om = np.isin(oz["surface"], e_set); osup = om & (oz["state"] == 1)
    old_share = float((oz["vote"][osup] == 1).mean()) if osup.any() else float("nan")
    px_old = float(oz["conflict_sum"][om].sum() / max(oz["a1_sum"][om].sum(), 1))
    px_new = float(st["conflict_sum_spec"][m].sum() / max(st["a1_sum"][m].sum(), 1))
    name = {"target": "대상 건물 벽 전체", "all": "크롭 안 LoD2 벽 전체"}.get(w, f"면 {w} ({LOD2_NOTE.get(w, '대상 건물')})")
    G_[str(w)] = dict(n_support_old=int(osup.sum()), n_support_new=int(sup.sum()), share_old=old_share, share_new=new_share, px_old=px_old, px_new=px_new)
    if int(osup.sum()) + int(sup.sum()) == 0:
        continue
    md.append(f"| {name} | {f0(osup.sum())} / {f0(sup.sum())} | {pc(old_share)} | {pc(new_share)} | {pc(px_old)} | {pc(px_new)} |")
res["G"] = G_
md.append("")

# ------------------------------------------------------------------ H outline overlap
md.append("### 표 아. 항공 LiDAR 건물 윤곽 — LoD2 바닥면(첫째 출처)과 자체 건물 분류 덩어리(둘째 출처)의 겹침 비율 (교집합 ÷ 합집합, 0.5 m 격자)\n")
md.append("| 건물 (LoD2 바닥면) | 바닥면 넓이 m² (크롭 안) | 가장 많이 겹친 덩어리 넓이 m² | 겹침 비율 | 같은 덩어리에 묶인 이웃 건물 |")
md.append("|---|---|---|---|---|")
m_tin = dict(np.load(P7 / "stage1/meshes/L_N.npz"))
co = CFG["surfaces"]["classification_outline"]
lab, rec = outl.classification_clusters(m_tin["V"][:, :2], m_tin["cls"], RECT, cell=co["cell_m"], building_class=co["building_class"],
                                        min_share=co["min_share"], close_iter=co["close_iter"], min_cells=co["min_cells"])
rings = [(p["building_id"], p["ring_local_xy"]) for p in PJ["polygons"] if p["citygml_type"] == "GroundSurface"]
rl = outl.rings_raster([r for _, r in rings], RECT, co["cell_m"])
rows = outl.overlap_table(rl, lab, [b for b, _ in rings], co["cell_m"])
for r in rows:
    md.append(f"| {r['outline']}{' (대상)' if r['outline'] == PJ['target_building'] else ''} | {f1(r['area_m2'])} | {f1(r.get('cluster_area_m2', 0.0))} | "
              f"{r['iou']:.2f} | {', '.join(r['merged_with']) if r['merged_with'] else '–'} |")
res["H"] = dict(rows=rows, record=rec)
md.append("")

(OUT / "tables.md").write_text("\n".join(md) + "\n")
(OUT / "tables.json").write_text(json.dumps(res, indent=1, default=float))
print("\n".join(md))
