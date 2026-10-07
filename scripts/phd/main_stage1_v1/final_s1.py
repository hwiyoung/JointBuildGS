"""PHD-MAIN-STAGE1-v1 report tables pooled over the sites (jointbuildgs:dev, CPU; order 5: completeness and inheritance of the missing /
invisible regions pooled over the sites, the correction-rate curve and boundary pooled over the sites with the per-site values, the
ALS 1x / 2x comparison, time and memory). Every method of a prior is pooled over the same sites: those where the proposed method has
both seeds (common_sites); a method without a result at one of them is pooled over the rest, and the sites of each pool are written.

  python final_s1.py      -> /out/tables/final_extra.json, .md

pooled completeness   rows of code 4 (missing agreement) / 5 (invisible agreement), thinned: shares of the result-mesh distance <= 0.2 /
                      0.5 m over the pooled rows (the metric's own distances, rows npz 'dist')
pooled curve          rows of code 11, thinned, |W - GT| >= 0.2 m: per size bin (|W - GT| / tau: 1, 1.5, 2, 3, 4, 8, inf) the pooled
                      counts, bins merged by the 10,000-point rule (bins.merge_small), the GT-side share per group, the boundary
                      (bins.boundary) - the definition of the metric (metrics_s1.spread) applied to the pooled rows
inheritance           the unseen-wall inheritance (B173 sites): patches pooled
scientific_verdict: null."""
import json

import numpy as np

from s1_common import OUT, S0, SITES, jdump, log
from src.phd.metrics_v3 import bins, lines

def common_sites(prior):
    """the sites where the proposed method (both seeds) has results: every method of the prior is pooled over these sites only."""
    return [s for s in SITES if all((OUT / "metrics" / s / f"prop_{prior}_s{k}__{prior}.json").exists() for k in (0, 1))]


METH = {"LoD2": [("prop_LoD2_s0", "본 방법 0"), ("prop_LoD2_s1", "본 방법 1"), ("imgonly_s0", "영상만 0"), ("imgonly_s1", "영상만 1"),
                 ("trust_LoD2", "늘 믿음(GeoGS)"), ("samepath_LoD2", "그대로(같은 길)")],
        "ALS": [("prop_ALS_s0", "본 방법 0"), ("prop_ALS_s1", "본 방법 1"), ("prop_ALS1x_s0", "1배 0"), ("imgonly_s0", "영상만 0"),
                ("imgonly_s1", "영상만 1"), ("trust_ALS", "늘 믿음"), ("samepath_ALS", "그대로(같은 길)")]}
EDGES = [1.0, 1.5, 2.0, 3.0, 4.0, 8.0, None]


def rows_of(site, prior, res):
    f = OUT / "metrics" / site / f"{res}__{prior}_rows.npz"
    if not f.exists():
        return None, None
    return np.load(OUT / "defs" / site / f"rows_{prior}.npz"), np.load(f)


def metric(site, prior, res):
    f = OUT / "metrics" / site / f"{res}__{prior}.json"
    return json.loads(f.read_text()) if f.exists() else None


def pooled_completeness():
    out = {}
    for prior, ms in METH.items():
        for res, lab in ms:
            for nm, code in (("missing_agreement", 4), ("invisible_agreement", 5)):
                d_all, sites = [], []
                for site in common_sites(prior):
                    r, m = rows_of(site, prior, res)
                    if r is None or "dist" not in m.files:
                        continue
                    sel = (r["code"] == code) & r["thin"]
                    if sel.any():
                        d_all.append(m["dist"][sel].astype(np.float64))
                        sites.append(site)
                d = np.concatenate(d_all) if d_all else np.zeros(0)
                d = d[~np.isnan(d)]
                out[f"{prior}/{res}/{nm}"] = dict(sites=sites, n=int(len(d)), le_0_2=round(float((d <= 0.2).mean()), 4) if len(d) else None,
                                                  le_0_5=round(float((d <= 0.5).mean()), 4) if len(d) else None)
    return out


def pooled_curves():
    out = {}
    for prior, ms in METH.items():
        for res, lab in ms:
            ratio_all, cls_all, sites = [], [], []
            for site in common_sites(prior):
                r, m = rows_of(site, prior, res)
                if r is None or "cls" not in m.files:
                    continue
                sel = (r["code"] == 11) & r["thin"] & (np.abs(r["sW"].astype(np.float64)) >= 0.2)
                ratio_all.append(np.abs(r["sW"][sel].astype(np.float64)) / r["tau"][sel].astype(np.float64))
                cls_all.append(m["cls"][sel])
                sites.append(site)
            if not sites:
                continue
            ratio, cls = np.concatenate(ratio_all), np.concatenate(cls_all)
            counts = [int(((ratio >= EDGES[i]) & ((ratio < EDGES[i + 1]) if EDGES[i + 1] is not None else True)).sum()) for i in range(6)]
            groups = bins.merge_small(counts, 10_000)
            curve = []
            for gr in groups:
                lo, hi = EDGES[gr[0]], EDGES[gr[-1] + 1]
                mb = (ratio >= lo) & ((ratio < hi) if hi is not None else True)
                sh = lines.shares(cls[mb])
                curve.append(dict(bin=[lo, hi], points=int(mb.sum()), correction_rate=sh["gt_side"]))
            bnd = bins.boundary([c["correction_rate"] for c in curve], [c["bin"][0] for c in curve])
            per_site = {}
            for site in sites:
                j = metric(site, prior, res) or {}
                sc = j.get("spread", {}).get("size_curve", {})
                per_site[site] = dict(boundary_tau=sc.get("boundary_tau"), boundary_roof_m=sc.get("boundary_roof_m"))
            out[f"{prior}/{res}"] = dict(sites=sites, raw_counts=counts, groups=groups, curve=curve, boundary_tau=bnd, per_site=per_site)
    return out


def inheritance():
    out = {}
    for prior, ms in METH.items():
        for res, lab in ms:
            num = den = num_e = den_e = 0
            sites = []
            for site in common_sites(prior):
                j = metric(site, prior, res) or {}
                bg = j.get("unseen", {}).get("by_group")
                if not bg:
                    continue
                a, e = bg["invisible_agreement_inferred"], bg["invisible_error_inferred"]
                if a.get("share") is None:
                    continue
                num += a["share"] * a["patches"]
                den += a["patches"]
                num_e += (e["share"] or 0) * e["patches"]
                den_e += e["patches"]
                sites.append(site)
            if den:
                out[f"{prior}/{res}"] = dict(sites=sites, inheritance=round(num / den, 4), past_shape_unseen=round(num_e / den_e, 4) if den_e else None,
                                             patches_agreement=den, patches_error=den_e)
    return out


def als_1x_2x():
    keys = [("유입률 · 사전 정보 오류 (%)", ("spread", "prior_error", "main", "spread"), 100), ("유입률 · 관측 오류 문턱 이내 (%)", ("spread", "observation_error_within_threshold", "main", "spread"), 100),
            ("유입률 · 이중 오류 (%)", ("spread", "double_error_record", "main", "spread"), 100), ("완만한 지붕 편향 (cm)", ("accuracy", "thinned", "gentle", "bias"), 100),
            ("완만한 지붕 NMAD (cm)", ("accuracy", "thinned", "gentle", "nmad"), 100), ("가파른 지붕 편향 (cm)", ("accuracy", "thinned", "steep", "bias"), 100),
            ("결측 일치 0.2 m (%)", ("completeness", "missing_agreement", "all", "le_0.2"), 100), ("둘레 0.2 m (%)", ("completeness", "premise_band", "all", "le_0.2"), 100),
            ("부유 3~20 m (개)", ("floating", "near_3_20m"), 1), ("Chamfer (m)", ("summary", "chamfer_mean"), 1), ("F1 @0.2 m (%)", ("summary", "f1_0.2"), 100)]
    out = {}
    for site in ("R1rep_b10", "B0_b10"):
        for res in ("prop_ALS_s0", "prop_ALS_s1", "prop_ALS1x_s0"):
            j = metric(site, "ALS", res)
            if j is None:
                continue
            row = {}
            for lab, path, k in keys:
                v = j
                for p in path:
                    v = v.get(p) if isinstance(v, dict) else None
                row[lab] = None if v is None else round(v * k, 2)
            out[f"{site}/{res}"] = row
    return out, [k[0] for k in keys]


def times():
    out = {}
    for r in sorted((OUT / "stage1").glob("*/*/receipt.json")):
        j = json.loads(r.read_text())
        R = r.parent
        post = json.loads((R / "post/post.json").read_text()) if (R / "post/post.json").exists() else {}
        out[f"{j.get('site')}/{j.get('result')}"] = dict(status=j.get("status"), minutes=round(j.get("wall_seconds", 0) / 60, 1), gpu=j.get("gpu"),
                                                        gpu_peak_gb=round(j.get("gpu_memory_used_mib", {}).get("peak_minus_idle", 0) / 1024, 1),
                                                        gaussians=post.get("gaussians", {}).get("n"), post_host_peak_gb=post.get("peak_host_gb"),
                                                        post_seconds=post.get("seconds", {}).get("tsdf"))
    for run in ("b1_LoD2", "b2_LoD2", "b1_ALS", "b2_ALS"):
        j = json.loads((S0 / "stage0" / run / "receipt.json").read_text())
        out[f"B173nb_b10/stage0_{run}"] = dict(status=j.get("status"), minutes=round(j.get("wall_seconds", 0) / 60, 1),
                                               gpu_peak_gb=round(j.get("gpu_memory_used_mib", {}).get("peak_minus_idle", 0) / 1024, 1))
    return out


def main():
    comp, curves, inh, t = pooled_completeness(), pooled_curves(), inheritance(), times()
    a12, a12_keys = als_1x_2x()
    jdump(OUT / "tables/final_extra.json", dict(rule=__doc__, completeness=comp, curves=curves, inheritance=inh, als_1x_2x=a12, times=t, scientific_verdict=None))
    md = []
    for prior, ms in METH.items():
        md.append(f"\n**결측·비가시 일치 영역의 완전성, 지역을 합침 — {prior}** (0.2 / 0.5 m 안 %, 점 수, 들어간 지역)\n")
        md.append("| 방법 | 결측 일치 | 비가시 일치 | 지역 |")
        md.append("|---|---|---|---|")
        for res, lab in ms:
            a, b = comp.get(f"{prior}/{res}/missing_agreement"), comp.get(f"{prior}/{res}/invisible_agreement")
            if not a or not a["n"]:
                continue
            f = lambda e: "—" if not e or not e["n"] else f"{100 * e['le_0_2']:.1f} / {100 * e['le_0_5']:.1f} ({e['n']:,})"
            md.append(f"| {lab} | {f(a)} | {f(b)} | {len(a['sites'])} |")
    for prior, ms in METH.items():
        md.append(f"\n**보정률 곡선과 보정 경계, 지역을 합침 — {prior}** (묶인 구간의 참값 쪽 %, 점 수; 경계 = 그 구간부터 모두 50 % 이상인 첫 아래 끝)\n")
        md.append("| 방법 | 묶인 구간: 보정률 (점) | 합친 경계 (τ) | 지역별 경계 (τ) |")
        md.append("|---|---|---|---|")
        for res, lab in ms:
            c = curves.get(f"{prior}/{res}")
            if not c:
                continue
            cs = "; ".join(f"{c_['bin'][0]:g}~{'' if c_['bin'][1] is None else format(c_['bin'][1], 'g')}τ: {100 * c_['correction_rate']:.0f} ({c_['points']:,})" for c_ in c["curve"])
            ps = ", ".join(f"{s.split('_')[0]} {v['boundary_tau'] if v['boundary_tau'] is not None else '—'}" for s, v in c["per_site"].items())
            md.append(f"| {lab} | {cs} | {c['boundary_tau'] if c['boundary_tau'] is not None else '—'} | {ps} |")
    if inh:
        md.append("\n**못 본 곳 상속률, 지역을 합침** (B173 지역; 맞음으로 미룬 패치의 상속률 / 틀림으로 미룬 패치의 과거 형상)\n")
        md.append("| 단위 · 방법 | 상속률 (%) | 못 본 곳 과거 형상 (%) | 패치 | 지역 |")
        md.append("|---|---|---|---|---|")
        for k, v in inh.items():
            past = "—" if v["past_shape_unseen"] is None else "%.1f" % (100 * v["past_shape_unseen"])
            md.append("| %s | %.1f | %s | %s / %s | %s |" % (k, 100 * v["inheritance"], past, format(v["patches_agreement"], ","), format(v["patches_error"], ","), ", ".join(v["sites"])))
    md.append("\n**항공 LiDAR 1배(1τ)와 2배(2τ) 버리는 규칙** (R1 부채꼴, B0)\n")
    cols = [k for k in a12]
    md.append("| 지표 | " + " | ".join(cols) + " |")
    md.append("|---|" + "---|" * len(cols))
    for lab in a12_keys:
        md.append(f"| {lab} | " + " | ".join("—" if a12[c][lab] is None else f"{a12[c][lab]:g}" for c in cols) + " |")
    md.append("\n**학습마다 시간과 메모리**\n")
    md.append("| 학습 | 상태 | 분 | GPU 최대 (GB) | 가우시안 (만) | 후처리 호스트 최대 (GB) |")
    md.append("|---|---|---|---|---|---|")
    for k, v in t.items():
        md.append(f"| {k} | {v['status']} | {v['minutes']} | {v.get('gpu_peak_gb', '—')} | {'—' if not v.get('gaussians') else round(v['gaussians'] / 1e4)} | {v.get('post_host_peak_gb') or '—'} |")
    (OUT / "tables/final_extra.md").write_text("\n".join(md) + "\n")
    print("\n".join(md))
    log("final extra", len(comp), len(curves), len(inh), len(t))


if __name__ == "__main__":
    main()
