"""PHD-STAGE2-PROPAGATION-PREMEASURE-v1 report tables (jointbuildgs:dev, CPU): reads /out/{surfaces,ids,measure,candidates}
and writes /out/tables/tables.md (Markdown blocks pasted into the report), tables.json and stable_ranges.csv.
  python tables.py       # mounts as measure.py"""
import csv
import json
from collections import defaultdict
from pathlib import Path

import numpy as np
import shapely
from shapely.geometry import Polygon
from shapely.ops import unary_union

import measure as ms

OUT = Path("/out/tables"); OUT.mkdir(parents=True, exist_ok=True)
M = Path("/out/measure")
SETTINGS = ["M_N", "M_B", "L_N", "L_B"]
NAME = {"M_N": "LoD2 정상", "M_B": "LoD2 주지붕 +1 m", "L_N": "항공 LiDAR 정상", "L_B": "항공 LiDAR 주지붕 +1 m"}
KIND = {"roof": "지붕", "wall": "벽", "ground": "바닥면", "step": "단차면", "building": "지붕"}
LOD2_NOTE = {3396: "주지붕", 3394: "그늘진 지붕 끝", 3403: "정면 벽", 3404: "끝 경사면", 3393: "뒷지붕", 3387: "날개 지붕", 3389: "날개 지붕",
             3401: "대상 건물 바닥면", 3391: "옆 벽"}
Q_LABEL = {0.55: "0.55", 0.6: "0.6", 0.6667: "2/3", 0.75: "0.75", 0.8: "0.8"}
J = ["conflict", "agree", "mixed", "insufficient"]
PJ = ms.PJ
TARGET_FOOT = unary_union([Polygon(p["ring_local_xy"]) for p in PJ["polygons"] if p["is_target"] and p["citygml_type"] == "RoofSurface"])
MAIN_RING = Polygon(next(p for p in PJ["polygons"] if p["poly_index"] == 3396)["ring_local_xy"])
md = []
res = {}


def f0(x):
    return f"{x:,.0f}"


def f1(x):
    return f"{x:,.1f}"


def pc(x):
    return "–" if x != x else f"{100 * x:.1f} %"


def load(setting):
    z = dict(np.load(M / setting / "locations.npz"))
    summ = json.loads((M / setting / "summary.json").read_text())
    srows = list(csv.DictReader(open(M / setting / "surfaces.csv")))
    grid = list(csv.DictReader(open(M / setting / "grid.csv")))
    sj = {r["id"]: r for r in json.loads((Path("/out/surfaces") / setting / "surfaces.json").read_text())["surfaces"]}
    return z, summ, srows, grid, sj


D = {s: load(s) for s in SETTINGS}

# ------------------------------------------------------------------ table 1: surface numbers
md.append("### 표 1. 표면 번호 (15시점 렌더링, 픽셀 수는 15시점 합)\n")
md.append("| 설정 | 표면 수(건물 / 건물 아님) | 크롭 안 위치가 있는 건물 표면 | 사전 정보 픽셀 | 건물 표면 번호 있음 | 건물 아닌 표면(지면) | 번호 없음(가파른 삼각형) | 참고: 메시는 맞았으나 크롭 밖 |")
md.append("|---|---|---|---|---|---|---|---|")
t1 = {}
for s in SETTINGS:
    z, summ, srows, grid, sj = D[s]
    p = json.loads((M / s / "pixels.json").read_text())["all_views"]
    tot = {k: sum(v.get(k, 0) for v in p.values()) for k in ("prior_px", "building_px", "nonbuilding_surface_px", "steep_px", "hit_outside_prior_px", "no_hit_px")}
    nb = sum(1 for r in sj.values() if r["kind"] in (("roof", "wall", "ground", "step") if s.startswith("M") else ("building",)))
    nn = len(sj) - nb
    n_in = len(np.unique(z["surface"]))
    t1[s] = dict(n_surfaces=len(sj), n_building=nb, n_nonbuilding=nn, n_with_locations=n_in, **tot)
    md.append(f"| {NAME[s]} | {f0(nb)} / {f0(nn)} | {f0(n_in)} | {f0(tot['prior_px'])} | {f0(tot['building_px'])} ({pc(tot['building_px'] / tot['prior_px'])}) | "
              f"{f0(tot['nonbuilding_surface_px'])} ({pc(tot['nonbuilding_surface_px'] / tot['prior_px'])}) | {f0(tot['steep_px'])} ({pc(tot['steep_px'] / tot['prior_px'])}) | {f0(tot['hit_outside_prior_px'])} |")
res["table1"] = t1
md.append("")

# ------------------------------------------------------------------ table 2: marks (pixel level, 13 training views)
md.append("### 표 2. 일치·충돌 표시 (학습 13시점의 건물 표면 픽셀)\n")
md.append("| 설정 | 면 종류 | 건물 표면 픽셀 | 지지 픽셀(관측 신뢰도 1) | 일치 | 충돌 | 결측 픽셀(관측 신뢰도 0) |")
md.append("|---|---|---|---|---|---|---|")
t2 = {}
for s in SETTINGS:
    z, summ, srows, grid, sj = D[s]
    kind_loc = np.array([sj[int(x)]["kind"] for x in z["surface"]])
    grp = [("지붕", np.isin(kind_loc, ["roof", "building"])), ("벽", np.isin(kind_loc, ["wall", "step"])), ("바닥면", kind_loc == "ground")]
    for g, m in grp:
        n = z["pix_sum"][m].sum()
        if n == 0:
            continue
        a1 = z["a1_sum"][m].sum(); ag = z["agree_sum"][m].sum(); cf = z["conflict_sum"][m].sum()
        t2[f"{s}_{g}"] = dict(pixels=int(n), support=int(a1), agree=int(ag), conflict=int(cf))
        md.append(f"| {NAME[s]} | {g} | {f0(n)} | {f0(a1)} ({pc(a1 / n)}) | {pc(ag / a1)} | {pc(cf / a1)} | {f0(n - a1)} ({pc((n - a1) / n)}) |")
res["table2"] = t2
md.append("")

# ------------------------------------------------------------------ table 3: per surface
md.append("### 표 3. 표면별 위치 (한 칸 0.25 m; 일치·충돌은 지지 위치의 표)\n")


def surf_line(s, r, sj, extra=""):
    sid = int(r["surface"])
    if s.startswith("M"):
        name = f"면 {sid}" if sid < 100000 else f"단차면 {sid - 100000}"
        note = LOD2_NOTE.get(sid, "대상 건물" if r["target"] == "True" else "이웃 건물")
    else:
        name = f"표면 {sid}"; info = sj[sid]
        note = "올린 주지붕" if info.get("raised_share", 0) >= 0.5 else ("대상 건물 지붕 포함" if info["target"] else "이웃 건물")
    nsup = int(r["n_support"])
    return (f"| {NAME[s]} | {KIND[r['kind']]} | {name} ({note}{extra}) | {f1(float(r['area_m2']))} | {f0(nsup)} | "
            f"{pc(float(r['agree_share'])) if nsup else '–'} | {pc(float(r['conflict_share'])) if nsup else '–'} | {f0(int(r['n_missing']))} | "
            f"{' · '.join(f0(int(r['ref_' + j])) for j in J)} | {f0(int(r['n_invisible']))} |")


md.append("| 설정 | 종류 | 표면 | 넓이 m² | 지지 위치 | 일치 | 충돌 | 결측 위치 | 결측의 기준 조합 판정 (충돌 · 일치 · 혼재 · 근거 부족) | 비가시 위치 |")
md.append("|---|---|---|---|---|---|---|---|---|---|")
t3 = defaultdict(list)
for s in SETTINGS:
    z, summ, srows, grid, sj = D[s]
    order = {"roof": 0, "building": 0, "wall": 1, "step": 2, "ground": 3}
    shown = [r for r in srows if (r["target"] == "True" and (int(r["n_support"]) + int(r["n_missing"]) > 0) and (s.startswith("M") or float(r["area_m2"]) >= 5))
             or int(r["n_missing"]) >= 100 or int(r["n_support"]) >= 1500]
    shown.sort(key=lambda r: (order[r["kind"]], r["target"] != "True", -int(r["n_support"]) - int(r["n_missing"])))
    for r in shown:
        md.append(surf_line(s, r, sj))
        t3[s].append({k: r[k] for k in ("surface", "kind", "target", "area_m2", "n_support", "agree_share", "conflict_share", "n_missing", "n_invisible")})
    rest = [r for r in srows if r not in shown]
    for kind_g, kinds in (("지붕", ("roof", "building")), ("벽", ("wall", "step")), ("바닥면", ("ground",))):
        rr = [r for r in rest if r["kind"] in kinds]
        if not rr:
            continue
        nsup = sum(int(r["n_support"]) for r in rr)
        cf = sum(float(r["conflict_share"]) * int(r["n_support"]) for r in rr if int(r["n_support"]))
        md.append(f"| {NAME[s]} | {kind_g} | 그 밖의 {len(rr)}개 표면 합 | {f1(sum(float(r['area_m2']) for r in rr))} | {f0(nsup)} | "
                  f"{pc(1 - cf / nsup) if nsup else '–'} | {pc(cf / nsup) if nsup else '–'} | {f0(sum(int(r['n_missing']) for r in rr))} | "
                  f"{' · '.join(f0(sum(int(r['ref_' + j]) for r in rr)) for j in J)} | {f0(sum(int(r['n_invisible']) for r in rr))} |")
    if s.startswith("L"):     # split of the largest target surface by the target roof footprint (reporting only)
        big = [r for r in srows if r["target"] == "True"]
        big.sort(key=lambda r: -float(r["area_m2"]))
        for r in big[:1]:
            sid = int(r["surface"]); m = z["surface"] == sid
            inside = shapely.contains_xy(TARGET_FOOT, z["center"][:, 0], z["center"][:, 1])
            for lab, mm in (("대상 건물 지붕 발자국 안", m & inside), ("발자국 밖(이웃 건물 지붕)", m & ~inside)):
                sup = mm & (z["state"] == ms.ST_SUPPORT)
                n_s = int(sup.sum())
                cfs = float((z["vote"][sup] == ms.V_CONFLICT).mean()) if n_s else float("nan")
                mm_mis = mm & (z["state"] == ms.ST_MISSING)
                md.append(f"| {NAME[s]} | 지붕 | └ 표면 {sid} 중 {lab} | {f1(z['area'][mm].sum())} | {f0(n_s)} | {pc(1 - cfs)} | {pc(cfs)} | "
                          f"{f0(int(mm_mis.sum()))} | {' · '.join(f0(int((mm_mis & (z['jref'] == i)).sum())) for i in range(4))} | "
                          f"{f0(int((mm & (z['state'] == ms.ST_INVISIBLE)).sum()))} |")
res["table3"] = t3
md.append("")

# ------------------------------------------------------------------ table 4: distances
md.append("### 표 4. 결측 위치에서 같은 표면의 가장 가까운 지지 위치까지 표면 위 거리\n")
md.append("| 설정 | 면 종류 | 결측 위치 | 같은 표면에 지지 위치 없음 | 25 % | 50 % | 75 % | 90 % | 99 % | 최대 |")
md.append("|---|---|---|---|---|---|---|---|---|---|")
t4 = {}
for s in SETTINGS:
    for r in csv.DictReader(open(M / s / "distance.csv")):
        if int(r["n_missing"]) == 0:
            continue
        g = {"all": "전체", "roof": "지붕", "wall": "벽", "ground": "바닥면"}[r["group"]]
        t4[f"{s}_{r['group']}"] = r
        md.append(f"| {NAME[s]} | {g} | {f0(int(r['n_missing']))} | {f0(int(r['n_without_support']))} ({f1(float(r['area_without_support_m2']))} m²) | "
                  + " | ".join(f"{float(r[k]):.2f} m" for k in ("p25_m", "p50_m", "p75_m", "p90_m", "p99_m", "max_m")) + " |")
res["table4"] = t4
md.append("")

# ------------------------------------------------------------------ table 5 and 6: grid (grouped where the majority threshold gives identical counts)


def groups_for_k(grid, k):
    """majority values whose judgment counts are identical for every max distance of this k (in every setting)."""
    qs = [0.55, 0.6, 0.6667, 0.75, 0.8]
    sig = {}
    for q in qs:
        key = []
        for s in SETTINGS:
            for r in D[s][3]:
                if r["min_evidence"] == str(k) and float(r["majority"]) == q:
                    key.append(tuple(r[f"n_{j}"] for j in J))
        sig[q] = tuple(key)
    out = []
    for q in qs:
        for g in out:
            if sig[g[0]] == sig[q]:
                g.append(q); break
        else:
            out.append([q])
    return out


QG = {k: groups_for_k(None, k) for k in ms.K_LIST}
res["majority_groups"] = {str(k): [[Q_LABEL[q] for q in g] for g in v] for k, v in QG.items()}


def grid_row(grid, q, k, p):
    return [r for r in grid if float(r["majority"]) == q and r["min_evidence"] == str(k) and r["max_distance_percentile"] == str(p)][0]


t5 = {}
for s in SETTINGS:
    z, summ, srows, grid, sj = D[s]
    nm = int(grid[0]["n_missing"])
    pct = summ["percentiles_m"]
    md.append(f"### 표 5-{SETTINGS.index(s) + 1}. {NAME[s]} — 결측 위치 {f0(nm)}곳({f1(summ['area_missing_m2'])} m²)의 판정 (위치 수 / 넓이 m²)\n")
    md.append(f"최대 거리 후보 = 표 4의 백분위수: 25 % {pct['25']:.2f} m, 50 % {pct['50']:.2f} m, 75 % {pct['75']:.2f} m, 90 % {pct['90']:.2f} m.\n")
    md.append("| 최소량 | 최대 거리 | 다수의 기준 | 충돌 | 일치 | 혼재 | 근거 부족 |")
    md.append("|---|---|---|---|---|---|---|")
    for k in ms.K_LIST:
        for p in ms.PCT_LIST:
            for g in QG[k]:
                r = grid_row(grid, g[0], k, p)
                ql = "·".join(Q_LABEL[q] for q in g)
                cells = [f"{f0(int(r[f'n_{j}']))} / {f1(float(r[f'area_{j}_m2']))}" for j in J]
                md.append(f"| {k} | {p} % ({float(r['max_distance_m']):.2f} m) | {ql} | " + " | ".join(cells) + " |")
    md.append("")
    t5[s] = grid
# stable ranges
st_rows = []
for s in SETTINGS:
    grid = D[s][3]; nm = int(grid[0]["n_missing"])
    def cnt(q, k, p):
        r = grid_row(grid, q, k, p); return np.array([int(r[f"n_{j}"]) for j in J])
    qs = [0.55, 0.6, 0.6667, 0.75, 0.8]
    for k in ms.K_LIST:
        for p in ms.PCT_LIST:
            for a, b in zip(qs[:-1], qs[1:]):
                st_rows.append(dict(setting=s, parameter="majority", fixed=f"min {k}, dist {p}", step=f"{Q_LABEL[a]}->{Q_LABEL[b]}", max_change_share=float(np.abs(cnt(b, k, p) - cnt(a, k, p)).max() / nm)))
    for q in qs:
        for p in ms.PCT_LIST:
            for a, b in zip(ms.K_LIST[:-1], ms.K_LIST[1:]):
                st_rows.append(dict(setting=s, parameter="min_evidence", fixed=f"maj {Q_LABEL[q]}, dist {p}", step=f"{a}->{b}", max_change_share=float(np.abs(cnt(q, b, p) - cnt(q, a, p)).max() / nm)))
        for k in ms.K_LIST:
            for a, b in zip(ms.PCT_LIST[:-1], ms.PCT_LIST[1:]):
                st_rows.append(dict(setting=s, parameter="max_distance", fixed=f"maj {Q_LABEL[q]}, min {k}", step=f"{a}->{b}", max_change_share=float(np.abs(cnt(q, k, b) - cnt(q, k, a)).max() / nm)))
with open(OUT / "stable_ranges.csv", "w", newline="") as fh:
    w = csv.DictWriter(fh, fieldnames=list(st_rows[0].keys())); w.writeheader(); [w.writerow(r) for r in st_rows]
thr = ms.CFG["stable_range_rule"]
stable = {}
for s in SETTINGS:
    rr = [r for r in st_rows if r["setting"] == s]
    out = {}
    for par in ("majority", "min_evidence", "max_distance"):
        steps = sorted({r["step"] for r in rr if r["parameter"] == par}, key=lambda x: [r["step"] for r in rr if r["parameter"] == par].index(x))
        out[par] = {st: dict(max=max(r["max_change_share"] for r in rr if r["parameter"] == par and r["step"] == st),
                             n_fixed_below_2pct=sum(r["max_change_share"] < 0.02 for r in rr if r["parameter"] == par and r["step"] == st),
                             n_fixed=sum(1 for r in rr if r["parameter"] == par and r["step"] == st)) for st in steps}
    stable[s] = out
res["stable"] = stable
md.append("### 값 변화에 따른 판정 개수 변화 (칸마다 네 판정 가운데 가장 크게 변한 개수 ÷ 결측 위치 수의 최댓값; 괄호 = 나머지 두 값 조합 중 2 % 미만인 수 / 조합 수)\n")
md.append("| 설정 | 다수의 기준 0.55→0.6 | 0.6→2/3 | 2/3→0.75 | 0.75→0.8 | 최소량 1→3 | 3→5 | 5→10 | 최대 거리 25→50 % | 50→75 % | 75→90 % |")
md.append("|---|---|---|---|---|---|---|---|---|---|---|")
for s in SETTINGS:
    o = stable[s]
    cells = []
    for par, steps in (("majority", ["0.55->0.6", "0.6->2/3", "2/3->0.75", "0.75->0.8"]), ("min_evidence", ["1->3", "3->5", "5->10"]), ("max_distance", ["25->50", "50->75", "75->90"])):
        for st in steps:
            v = o[par][st]
            cells.append(f"{100 * v['max']:.1f} % ({v['n_fixed_below_2pct']}/{v['n_fixed']})")
    md.append(f"| {NAME[s]} | " + " | ".join(cells) + " |")
md.append("")

# table 6: conflict area
md.append("### 표 6. 충돌로 전파되는 결측 넓이 (m²; 괄호 = 충돌을 받은 표면들의 넓이 대비 / 크롭 안 건물 표면 전체 넓이 대비)\n")
md.append("| 최소량 | 최대 거리 | 다수의 기준 | " + " | ".join(NAME[s] for s in SETTINGS) + " |")
md.append("|---|---|---|" + "---|" * len(SETTINGS))
t6 = []
for k in ms.K_LIST:
    for p in ms.PCT_LIST:
        for g in QG[k]:
            cells = []
            for s in SETTINGS:
                r = grid_row(D[s][3], g[0], k, p)
                cells.append(f"{f1(float(r['area_conflict_m2']))} ({pc(float(r['conflict_share_of_those_surfaces']))} / {pc(float(r['conflict_share_of_all_building_surfaces']))})")
                t6.append(dict(setting=s, min_evidence=k, pct=p, majority=[Q_LABEL[q] for q in g], area=float(r["area_conflict_m2"])))
            md.append(f"| {k} | {p} % | {'·'.join(Q_LABEL[q] for q in g)} | " + " | ".join(cells) + " |")
md.append("")
md.append("| 설정 | 크롭 안 건물 표면 넓이 | 지지 넓이 | 결측 넓이 | 비가시 넓이 | 지지 위치 가운데 충돌 |")
md.append("|---|---|---|---|---|---|")
for s in SETTINGS:
    summ = D[s][1]
    md.append(f"| {NAME[s]} | {f1(summ['area_total_m2'])} m² | {f1(summ['area_support_m2'])} m² | {f1(summ['area_missing_m2'])} m² | {f1(summ['area_invisible_m2'])} m² | {pc(summ['support_conflict_share'])} |")
md.append("")
res["table6"] = t6

# ------------------------------------------------------------------ table 7: injected faces (truth used only here)


def judge_subset(z, sel_mis, q, k, r):
    kd = z["k_dist"][sel_mis]; kv = z["k_vote"][sel_mis]
    return ms.judge(kd, kv, None, q, k, r)


md.append("### 표 7. 주입한 면의 판정 (확인용; 값을 고르는 데 쓰지 않는다. 주입 면의 사전 정보는 1 m 틀렸으므로 결측 위치의 옳은 판정은 충돌이다)\n")
md.append("칸 = 충돌 / 일치 / 혼재 / 근거 부족 (위치 수), 다수의 기준 2/3. 마지막 열 = 다른 다수의 기준(0.55·0.6·0.75·0.8)에서 네 판정 가운데 가장 크게 달라진 위치 수.\n")
md.append("| 면 | 지지 위치(충돌 비율) | 결측 위치 | 최소량 | 최대 거리 25 % | 50 % | 75 % | 90 % | 다른 다수의 기준과의 차 |")
md.append("|---|---|---|---|---|---|---|---|---|")
t7 = []
inj_sets = []
zMB = D["M_B"][0]; inj_sets.append(("M_B", "LoD2 주지붕 +1 m · 면 3396 (주입)", zMB["surface"] == 3396))
zMN = D["M_N"][0]; inj_sets.append(("M_N", "비교: LoD2 정상 · 면 3396 (주입 없음)", zMN["surface"] == 3396))
zLB = D["L_B"][0]; sjLB = D["L_B"][4]
raised_ids = [sid for sid, r in sjLB.items() if r["kind"] == "building" and r["raised_share"] >= 0.5]
selLB = np.isin(zLB["surface"], raised_ids)
big_raised = max(raised_ids, key=lambda i: sjLB[i]["area_mesh_m2"])
inj_sets.append(("L_B", f"항공 LiDAR 주지붕 +1 m · 표면 {big_raised}과 작은 표면 {len(raised_ids) - 1}개 (꼭짓점의 절반 넘게 올린 표면)", selLB))
zLN = D["L_N"][0]
key = lambda c: np.round(c[:, :2] / ms.SP - 0.5).astype(np.int64)
kb = {tuple(x) for x in key(zLB["center"][selLB])}
selLN = np.array([tuple(x) in kb for x in key(zLN["center"])])
inj_sets.append(("L_N", "비교: 항공 LiDAR 정상 · 같은 칸 (주입 없음)", selLN))
QS = [0.55, 0.6, 2 / 3, 0.75, 0.8]
for s, lab, sel in inj_sets:
    z = D[s][0]; pct = D[s][1]["percentiles_m"]
    sup = sel & (z["state"] == ms.ST_SUPPORT); mis_mask = sel[z["mis"]]
    cfs = float((z["vote"][sup] == ms.V_CONFLICT).mean()) if sup.any() else float("nan")
    for i, k in enumerate(ms.K_LIST):
        cells, dq = [], 0
        for p in ms.PCT_LIST:
            cnts = {q: [int((judge_subset(z, mis_mask, q, k, pct[str(p)]) == c).sum()) for c in range(4)] for q in QS}
            ref_c = cnts[2 / 3]
            dq = max(dq, max(max(abs(x - y) for x, y in zip(cnts[q], ref_c)) for q in QS))
            cells.append(" / ".join(f0(x) for x in ref_c))
            t7.append(dict(setting=s, label=lab, min_evidence=k, pct=p, counts_by_majority={Q_LABEL[round(q, 4)]: cnts[q] for q in QS},
                           n_support=int(sup.sum()), support_conflict=cfs, n_missing=int(mis_mask.sum())))
        head = f"| {lab} | {f0(int(sup.sum()))} ({pc(cfs)}) | {f0(int(mis_mask.sum()))} " if i == 0 else "| | | "
        md.append(head + f"| {k} | " + " | ".join(cells) + f" | {dq} |")
res["table7"] = t7
md.append("")

# ------------------------------------------------------------------ candidates (check c)
cj = Path("/out/candidates/candidates.json")
if cj.exists():
    C = json.loads(cj.read_text())["summary"]
    md.append("### 확인 (다)의 표. 초기화 후보 사전 정보 점마다 첫 가우시안 신뢰도(사전 정보 깊이로 가림)와 그 점이 앉은 위치의 상태·전파 판정(기준 조합)\n")
    md.append("| 설정 | 후보 점 | 가우시안 신뢰도 | 점 수 | 위치 없음 | 비가시 | 지지·일치 | 지지·충돌 | 결측→충돌 | 결측→일치 | 결측→혼재 | 결측→근거 부족 |")
    md.append("|---|---|---|---|---|---|---|---|---|---|---|---|")
    for s in SETTINGS:
        c = C[s]
        for ec, lab in (("unseen", "보는 시점 0 (r6가 초기화에서 뺌)"), ("E<0.5", "0.5 미만 (1회에 보호)"), ("E>=0.5", "0.5 이상")):
            t = c["table"][ec]; n = sum(t.values())
            md.append(f"| {NAME[s]} | {f0(c['n_candidates'])} | {lab} | {f0(n)} | " + " | ".join(f0(t[x]) for x in ("no_location", "invisible", "support_agree", "support_conflict", "missing_conflict", "missing_agree", "missing_mixed", "missing_insufficient")) + " |")
    res["candidates"] = C
    md.append("")

(OUT / "tables.md").write_text("\n".join(md) + "\n")
(OUT / "tables.json").write_text(json.dumps(res, indent=1, default=str))
print("\n".join(md))
