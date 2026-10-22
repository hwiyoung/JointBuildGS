"""PHD-MAIN-AXES71-v2 일 9: the new metrics of the earlier trainings (jointbuildgs:dev, CPU; reads AX/dist9, FT/dist, the ledger, a3_*.json).

  python a9_metrics.py   -> AX/tables/a9_metrics.json, /docs/tables/{stage2,stage3,fixtest,variants}/*.md|json, /docs/앞단계_새지표_숫자표_v1*.md

Cells: the training's own region file (ledger unit_inputs.region_file). A training on the stage-1 region file of a site takes the cells of
일 2 (AX/work/cells_<site>_<prior>.npz). A training on a stage-3 image condition (S2/S3 regions_v3/regions_ext_v3_<cond>_LoD2.npz) takes the
locked rule on its own codes; that condition has no obs_masked file, so the cells that need it (보존 · 거름, 보존 · 문턱 안, 다듬기, 상속 · 결측
and the sums 보존 합, 상속 합) are '정의 없음' (order 12: no other condition's or stage 1's file in its place), and so are axis 2 and the 0~1
bin of axis 1. Values: as 일 3 (a3_metrics.blocks_of) and 일 4 (the axis-1 τ bins and the axis-2 '놓음' bins where defined).
'Differs' (order 1.3 / 12): a training against the same case's proposed method (two seeds, mean): criterion = max(the pooled spread of 일 3
for that key and metric, the case's spread of the method seeds, 300 / n %p for shares), 2x for 확인 (both train). Stage 3: per condition the
method against 영상만 and the fixed GeoGS; spread = the larger of the case spreads of the fewest-image author condition's two seeds (B0a3) and of
the full-image two seeds (B0_b10 LoD2 of stage 1), used for every condition; across conditions only 전체 is compared directly, and the
difference of differences uses criterion x sqrt 2. [이 발주에서 냄] scientific_verdict: null."""
import math
from pathlib import Path

import numpy as np

from ax_common import AX, CFG, CID, DOCS, FT, KEY_KO, KEYS, PRIORS, S1, SITES, TAB, WORK, case_ko, jdump, jl, log, now
from ax_arrays import arrays, cells
from a3_metrics import blocks_of

DIST9 = AX / "dist9"
UNDEF_COND = {"c_keep_mask", "c_keep_in", "c_refine", "c_inh_miss", "s_keep", "s_inh"}
BUNDLE_DIR = {"2단계": "stage2", "3단계": "stage3", "1단계 보강": "stage3", "같은 구현의 변형": "variants", "고친 판 시험": "fixtest"}
METRICS = (("R_tau", "gt", True, "R(τ)"), ("mean", "gt", False, "참값 기준 평균 거리"), ("P_tau", "res", True, "P(τ) 셈 마"), ("mean", "res", False, "결과 기준 평균 거리 셈 마"))
ROOT = {"S1": "/out", "S2": "/ph/main_stage2_v1/PHD-MAIN-STAGE2-v1", "S3": "/ph/main_stage3_v1/PHD-MAIN-STAGE3-v1"}


def P(rel):
    a, b = rel.split("/", 1)
    return Path(ROOT[a]) / b


def cond_cells(region, geom, prior):
    """the locked rule on a condition's own codes; the obs-dependent cells undefined (-3)."""
    R = np.load(region)
    code = R["code_ext_v3"].astype(np.int64)
    ev = R["in_eval"].astype(bool)
    pv, wt = R["premise_violation"].astype(bool), R["obs_within_threshold"].astype(bool)
    C0 = cells(geom, prior)
    has = C0["has_gt"].astype(bool)
    ratio = np.abs(R["gt_med"].astype(np.float64)) / R["tau"].astype(np.float64)
    cell = np.full(len(code), -1, np.int64)
    free = ev.copy()

    def put(v, m):
        m = m & free
        cell[m] = v
        free[m] = False
    put(CID["c_nogt"], (code == 0) | ~has)
    put(CID["c_limit"], (code == 3) & pv)
    put(-3, np.isin(code, (2, 4)) | ((code == 3) & wt))
    put(CID["c_corr4p"], (code == 11) & (ratio >= 4))
    put(CID["c_corr14"], code == 11)
    put(CID["c_double"], code == 12)
    put(CID["c_miss_wrong"], code == 13)
    put(CID["c_inh_invis"], code == 5)
    put(CID["c_invis_wrong"], code == 14)
    d = {k: C0[k] for k in C0.files}
    d["cell"] = cell.astype(np.int8)
    d["ratio1"] = ratio.astype(np.float32)
    return d, dict(unassigned=int(free.sum()), undefined_patches=int((cell == -3).sum()))


def jobs():
    L = jl(AX / "work/ledger9/ledger9.json")["rows"]
    out = []
    for r in L:
        cond = r["site"] if r["site"] not in SITES else None
        geom = "B0_b10" if cond else r["site"]
        run = f"{cond}__{r['result']}" if cond else r["result"]
        reg = r["unit_inputs"]["region_file"]["path"]
        e = dict(bundle=r["bundle"], result=r["result"], site=r["site"], geom=geom, cond=cond, prior=r["case_prior"], run=run, what=r.get("what"),
                 status=r["status"], region=reg, region_exists=bool(r["unit_inputs"]["region_file"].get("exists")), seed=r.get("seed"))
        out.append(e)
    return out


def paths_of(j):
    xf = DIST9 / f"{j['geom']}_{j['prior']}__{j['run']}__x.npz"
    df = FT / "dist" / f"{j['geom']}_{j['prior']}__{j['result']}.npz" if not j["cond"] else None
    if df is None or not df.exists():
        df = DIST9 / f"{j['geom']}_{j['prior']}__{j['run']}.npz"
    fb = None
    if j["geom"] == "B0_b10":
        for c in (FT / "dist" / f"{j['geom']}_{j['prior']}__{j['result']}__b0gt.npz", DIST9 / f"{j['geom']}_{j['prior']}__{j['run']}__b0gt.npz"):
            if not j["cond"] or "dist9" in str(c):
                if c.exists():
                    fb = c
                    break
    return df, xf, fb


def values_of(j, C):
    if j["status"] in ("결과 없음", "관문"):
        return {k: dict(status=j["status"]) for k in ["all"] + KEYS}
    if not j["region_exists"]:
        return {k: dict(status="정의 없음") for k in ["all"] + KEYS}
    df, xf, fb = paths_of(j)
    if not df.exists() or not xf.exists():
        return {k: dict(status="결과 없음 (거리 파일 없음)") for k in ["all"] + KEYS}
    A = arrays(j["geom"], j["prior"], j["run"], C, paths=(df, xf, fb))
    out = {}
    for k in ["all"] + KEYS:
        if j["cond"] and k in UNDEF_COND:
            out[k] = dict(status="정의 없음")
            continue
        out[k] = blocks_of([A], k)
    return out


def get(b, side, key, share):
    if not str(b.get("status", "")).startswith("있음"):
        return None, 0
    if side == "gt":
        v, n = b["gt"].get(key), b["gt"].get("n_gt", 0)
    else:
        v, n = b["res"]["E"].get(key), b["res"]["E"].get("n", 0)
    return (None if v is None else (100 * v if share else v)), n


def reading(diff, crit, n, trains=True, mult=1.0):
    if n < 100 or diff is None or crit is None:
        return None
    c = crit * mult
    g = ("확인" if abs(diff) > 2 * c else ("가능·근거 불완전" if abs(diff) > c else None)) if trains else ("확인" if abs(diff) > c else None)
    if g == "확인" and n < 10000:
        g = "가능·근거 불완전"
    return g


def main():
    J = jobs()
    D3 = jl(TAB / "a3_metrics.json")["data"]
    CR = jl(TAB / "a3_criterion.json")["data"]
    vals, info = {}, {}
    Ccache = {}
    for j in J:
        key = (j["geom"], j["prior"], j["region"])
        if key not in Ccache:
            if j["cond"]:
                Ccache[key] = cond_cells(P(j["region"]), j["geom"], j["prior"]) if j["region_exists"] else (None, None)
            else:
                Ccache[key] = (cells(j["geom"], j["prior"]), None)
        C, ci = Ccache[key]
        if ci:
            info[j["cond"] + "/" + j["prior"]] = ci
        vals[f"{j['site']}/{j['prior']}/{j['result']}"] = values_of(j, C) if C is not None or not j["region_exists"] else {}
        log(j["bundle"], j["site"], j["prior"], j["result"])
    # the prior before training on each stage-3 condition's region file (the B0 samepath mesh)
    for cond in sorted({j["cond"] for j in J if j["cond"]}):
        jj = next(j for j in J if j["cond"] == cond and j["prior"] == "LoD2")
        C, _ = Ccache[(jj["geom"], "LoD2", jj["region"])]
        A = arrays("B0_b10", "LoD2", "samepath_LoD2", C)
        vals[f"{cond}/LoD2/samepath_LoD2"] = {k: (dict(status="정의 없음") if k in UNDEF_COND else blocks_of([A], k)) for k in ["all"] + KEYS}
    # readings
    rd = {}
    for j in J:
        u = f"{j['site']}/{j['prior']}/{j['result']}"
        if j["cond"] or j["result"].startswith("prop_"):
            continue
        case = f"{j['geom']}/{j['prior']}"
        if case not in D3:
            continue
        e = D3[case]["method"]
        rd[u] = {}
        for k in ["all"] + KEYS:
            for mk, side, share, ko in METRICS:
                a, na = get(e["values"][e["results"][0]][k], side, mk, share)
                b, nb = get(e["values"][e["results"][1]][k], side, mk, share)
                v, nv = get(vals[u].get(k, {}), side, mk, share)
                if a is None or b is None or v is None:
                    continue
                mean = 0.5 * (a + b)
                pooled = CR[k][f"{side}:{mk}"]["pooled"]
                n = min(na, nb, nv)
                crit = max(x for x in (pooled, 2.8 * abs(a - b) / math.sqrt(2), 300.0 / n if share and n else None) if x is not None)
                g = reading(v - mean, crit, n)
                rd[u].setdefault(k, {})[f"{side}:{mk}"] = dict(value=v, method=mean, diff=v - mean, criterion=crit, n=n, grade=g,
                                                               side=None if g is None else ("이 학습이 나음" if (v - mean) * (1 if share else -1) > 0 else "이 학습이 못함"))
    # stage 3
    s3 = stage3(J, vals, D3)
    jdump(TAB / "a9_metrics.json", dict(task="PHD-MAIN-AXES71-v2", work="일 9", made=now(), rule=__doc__.split("\n\n")[1:3], jobs=J, values=vals, readings=rd, stage3=s3,
                                        cells_info=info, scientific_verdict=None))
    tables(J, vals, rd, s3, D3)
    log("a9 done")


def stage3(J, vals, D3):
    """per condition: the method vs 영상만 and the fixed GeoGS; the spread of the rule (B0a3 pair, full-image pair)."""
    conds = sorted({j["cond"] for j in J if j["cond"] and j["bundle"] == "3단계"})
    out = dict(conditions=conds, spread={}, compare={}, flows={})
    full = D3["B0_b10/LoD2"]["method"]
    for k in ["all"] + KEYS:
        for mk, side, share, ko in METRICS:
            a3 = [get(vals.get(f"B0a3/LoD2/prop_LoD2_s{s}", {}).get(k, {}), side, mk, share)[0] for s in (0, 1)]
            fl = [get(full["values"][r][k], side, mk, share)[0] for r in full["results"]]
            sp = [2.8 * abs(x[0] - x[1]) / math.sqrt(2) for x in (a3, fl) if None not in x]
            out["spread"].setdefault(k, {})[f"{side}:{mk}"] = max(sp) if sp else None
    for c in conds:
        for k in ["all"] + KEYS:
            for mk, side, share, ko in METRICS:
                m, nm = get(vals.get(f"{c}/LoD2/prop_LoD2_s0", {}).get(k, {}), side, mk, share)
                if c == "B0a3":
                    m2, _ = get(vals.get(f"{c}/LoD2/prop_LoD2_s1", {}).get(k, {}), side, mk, share)
                    m = None if m is None or m2 is None else 0.5 * (m + m2)
                sp = out["spread"][k][f"{side}:{mk}"]
                for comp in ("imgonly_s0", "trust_LoD2_fix1", "samepath_LoD2"):
                    v, nv = get(vals.get(f"{c}/LoD2/{comp}", {}).get(k, {}), side, mk, share)
                    if m is None or v is None or sp is None:
                        continue
                    n = min(nm, nv)
                    crit = max(sp, 300.0 / n if share and n else 0)
                    g = reading(m - v, crit, n, trains=comp != "samepath_LoD2")
                    out["compare"].setdefault(c, {}).setdefault(k, {}).setdefault(comp, {})[f"{side}:{mk}"] = dict(method=m, value=v, diff=m - v, criterion=crit, n=n, grade=g)
    # flows of 전체 from the full images (stage 1 B0) and the difference of differences (x sqrt 2)
    for mk, side, share, ko in METRICS:
        base_m = np.mean([get(full["values"][r]["all"], side, mk, share)[0] for r in full["results"]])
        io = D3["B0_b10/LoD2"].get("twodgs")
        sp = out["spread"]["all"][f"{side}:{mk}"]
        fl = {"B0_b10 (영상 전체)": dict(method=float(base_m))}
        for c in conds:
            m = out["compare"].get(c, {}).get("all", {}).get("imgonly_s0", {}).get(f"{side}:{mk}")
            if m is None:
                continue
            fl[c] = dict(method=m["method"], imgonly=m["value"], diff=m["diff"], method_change=m["method"] - float(base_m),
                         criterion_dd=None if sp is None else sp * math.sqrt(2))
        out["flows"][f"{side}:{mk}"] = fl
    return out


def fmt(b):
    st = b.get("status", "")
    if not str(st).startswith("있음"):
        return st or "—"
    g = b["gt"]
    n = g.get("n_gt", 0)
    if n < 100:
        return "표본 부족"
    return f"{100 * g['R_tau']:.1f} · {g['mean']:.1f}" + ("*" if n < 10000 else "")


def tables(J, vals, rd, s3, D3):
    lines_all = {}
    for bundle, sub in BUNDLE_DIR.items():
        js = [j for j in J if j["bundle"] == bundle]
        if not js:
            continue
        (DOCS / "tables" / sub).mkdir(parents=True, exist_ok=True)
        L = [f"## {bundle}", ""] + (["- 비교 상대: 지역 경우(B0, B173 주변, R1)는 1단계 본 방법 두 씨앗의 평균, 3단계 조건(B0a…, B0n…)은 그 조건의 본 방법 씨앗 0.", ""]
                                    if any(j["cond"] for j in js) else [])
        for k in ["all"] + KEYS:
            refh = "같은 경우·조건의 본 방법" if any(j["cond"] for j in js) else "같은 경우 본 방법 (두 씨앗 평균)"
            L += [f"**{KEY_KO[k]}** — 참값 기준 재현율 R(τ) (%) · 참값 기준 평균 거리 (cm)", "", f"| 학습 | 경우 | 이 학습 | {refh} |", "|---|---|---|---|"]
            for j in js:
                u = f"{j['site']}/{j['prior']}/{j['result']}"
                b = vals.get(u, {}).get(k, {"status": "—"})
                case = f"{j['geom']}/{j['prior']}"
                if j["cond"]:
                    ref = vals.get(f"{j['cond']}/{j['prior']}/prop_LoD2_s0", {}).get(k, {"status": "—"}) if j["prior"] == "LoD2" else {"status": "정의 없음"}
                    cko = f"{j['cond']} · {'LoD2' if j['prior'] == 'LoD2' else '항공 LiDAR'}"
                else:
                    ref = D3.get(case, {}).get("method", {}).get("mean", {}).get(k, {"status": "—"})
                    cko = case_ko(j["geom"], j["prior"])
                L.append(f"| {j['result']} | {cko} | {fmt(b)} | {fmt(ref)} |")
            L.append("")
        md = [f"# 일 9 {bundle} — 새 지표 (PHD-MAIN-AXES71-v2) [이 발주에서 냄]", "", f"- 만든 때 {now()}. 학습 대장 `AX/work/ledger9/ledger9.json`(표 일9_학습대장.md). 칸은 그 학습이 쓴 영역 파일로 정함. "
              "3단계 조건은 조건마다 obs_masked 파일이 없어 보존 · 거름, 보존 · 문턱 안, 다듬기, 상속 · 결측(과 그 합)은 정의 없음. 결과 기준 값, 부록 값, 축 구간, 읽기는 같은 이름의 json.", ""] + L
        (DOCS / "tables" / sub / f"일9_{sub}_{bundle.replace(' ', '')}.md").write_text("\n".join(md) + "\n")
        jdump(DOCS / "tables" / sub / f"일9_{sub}_{bundle.replace(' ', '')}.json", dict(task="PHD-MAIN-AXES71-v2", work="일 9", bundle=bundle, made=now(),
              values={f"{j['site']}/{j['prior']}/{j['result']}": vals.get(f"{j['site']}/{j['prior']}/{j['result']}") for j in js},
              readings={u: v for u, v in rd.items() if any(u == f"{j['site']}/{j['prior']}/{j['result']}" for j in js)},
              stage3=s3 if bundle == "3단계" else None, scientific_verdict=None))
        lines_all[bundle] = L
    # the numbers file(s), split at 20,000 characters
    head = ["# 앞 단계 학습들의 새 지표 — 숫자표 (PHD-MAIN-AXES71-v2 일 9) [이 발주에서 냄]", "", f"- 만든 때 {now()}. 한 칸 = 참값 기준 재현율 R(τ) (%) · 참값 기준 평균 거리 (cm). "
            "`*` 표본 1만 점 미만, '표본 부족' 100점 미만. 나머지 값은 tables/stage2·stage3·fixtest·variants의 md·json.", ""]
    chunks, cur = [], list(head)
    for bundle, L in lines_all.items():
        blocks, b = [], []
        for x in L:
            b.append(x)
            if x == "":
                blocks.append(b)
                b = []
        for bl in blocks:
            if len("\n".join(cur + bl)) > 19500:
                chunks.append(cur)
                cur = list(head[:1]) + [f"- (이어서) {bundle}", ""]
            cur += bl
    chunks.append(cur)
    for i, ch in enumerate(chunks):
        nm = "앞단계_새지표_숫자표_v1.md" if i == 0 else f"앞단계_새지표_숫자표_v1_{i + 1}.md"
        (DOCS / nm).write_text("\n".join(ch) + "\n")


if __name__ == "__main__":
    main()
