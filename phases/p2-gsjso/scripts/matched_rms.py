#!/usr/bin/env python3
"""P2 — matched-n RMS analysis (PART A): is smrf's low RMS a selection effect (only easy buildings)?
READ-ONLY: reads ref_rms_*.csv only (no disk geometry change, no recompute). Observation only (no verdict).
Classifiers per GS arm: gssem (method) vs smrf (control) vs raw (image MVS baseline) vs LiDAR (upper bound).
Views: (1) on smrf-success set, (2) gssem-extra (smrf-fail) buildings, (3) headline gssem∩raw set.
Writes the PART-A section of docs/experiments/evaluation/w_matched_rms/reports/W_matched_rms.md (PART B appended by matched_rms_partB).
"""
import csv, statistics as st
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
A = REPO / "results/tum_transfer/mob_analysis"
M = REPO / "results/tum_transfer/mob"

# (label, GS cfg, gssem csv, smrf csv, raw baseline cfg). LiDAR = raw_lidar for all.
ARMS = [
    ("D4 dense", "gs_d4_dense", "ref_rms_d4_gssem.csv", "ref_rms_d4_smrf.csv", "raw_dense"),
    ("D4 acmp",  "gs_d4_acmp",  "ref_rms_d4_gssem.csv", "ref_rms_d4_smrf.csv", "raw_acmp"),
    ("D dense",  "gs_prior_full_dense", "ref_rms_D_gssem.csv", "ref_rms_D_smrf.csv", "raw_dense"),
    ("D acmp",   "gs_prior_full_acmp",  "ref_rms_D_gssem.csv", "ref_rms_D_smrf.csv", "raw_acmp"),
]


def load(fn):
    d = {}
    p = A / fn
    if not p.exists():
        return d
    for r in csv.DictReader(open(p)):
        if r.get("tag", "orig") != "orig":
            continue
        try:
            v = float(r.get("rms_to_ref_m", ""))
        except (TypeError, ValueError):
            v = None
        d[(r["config"], r["bid"].split("_")[-1])] = v
    return d


RAW = load("ref_rms_raw.csv")


def succ(d, cfg):
    return {b for (c, b), v in d.items() if c == cfg and v is not None}


def msrow(name, d, cfg, bids):
    vals = [d[(cfg, b)] for b in bids if d.get((cfg, b)) is not None]
    if not vals:
        return f"| {name} | 0 | - | - |"
    return f"| {name} | {len(vals)} | {st.mean(vals):.2f} | {st.median(vals):.2f} |"


def val(d, cfg, b):
    v = d.get((cfg, b))
    return f"{v:.2f}" if v is not None else "-"


L = []
def w(s=""):
    L.append(s)

w("# W_matched_rms — matched-n RMS·정확도 비교 (관찰만·판정/해석 금지)")
w("")
w("> READ-ONLY: PART A 는 `ref_rms_*.csv` 만 사용(디스크 기하 무변경·재계산 없음). EPSG:25832. 관찰만(판정/해석 없음).")
w("> 분류: **gssem**(GS-의미·방법) · **smrf**(대조) · **raw**(영상 MVS→Roofer baseline; dense↔raw_dense, acmp↔raw_acmp) · **LiDAR**(raw_lidar·상한).")
w("> '성공' = 그 동에서 지붕점→RMS→ref 산출됨(rms_to_ref_m 비어있지 않음, tag=orig).")
w("> 출처: gssem=`ref_rms_{D,d4}_gssem.csv` · smrf=`ref_rms_{D,d4}_smrf.csv`(requal 백업 사본) · raw/LiDAR=`ref_rms_raw.csv`.")
w("")
w("## PART A — matched-n RMS")

for label, cfg, gfn, sfn, rawcfg in ARMS:
    G = load(gfn); S = load(sfn)
    gset, sset = succ(G, cfg), succ(S, cfg)
    rset, lset = succ(RAW, rawcfg), succ(RAW, "raw_lidar")
    extra = sorted(gset - sset)
    inter = sorted(gset & rset)
    w(f"\n### {label}  (raw baseline = {rawcfg})")
    w(f"- 성공: gssem n={len(gset)} {sorted(gset)}")
    w(f"- 성공: smrf  n={len(sset)} {sorted(sset)}  · smrf⊆gssem? **{sset <= gset}**")
    w(f"- raw n={len(rset)} · LiDAR n={len(lset)} · gssem-extra(=gssem∖smrf): {extra}")
    w("")
    w(f"**View-1 — smrf 성공집합({len(sset)}동) 고정, 같은 동에서 분류별 RMS**")
    w("| 분류 | n | mean | median |")
    w("|---|---:|---:|---:|")
    w(msrow("gssem", G, cfg, sset)); w(msrow("smrf", S, cfg, sset))
    w(msrow("raw", RAW, rawcfg, sset)); w(msrow("LiDAR", RAW, "raw_lidar", sset))
    w("")
    w(f"**View-2 — gssem 추가성공(smrf 실패) {len(extra)}동: 건물별 RMS**")
    if extra:
        w("| bid | gssem | raw | LiDAR |")
        w("|---|---:|---:|---:|")
        for b in extra:
            w(f"| {b} | {val(G,cfg,b)} | {val(RAW,rawcfg,b)} | {val(RAW,'raw_lidar',b)} |")
    else:
        w("(gssem 추가성공 동 없음)")
    w("")
    w(f"**View-3 (헤드라인) — gssem ∩ raw 성공({len(inter)}동): GS-gssem vs raw + LiDAR**")
    w(f"교집합 동: {inter}")
    w("| 분류 | n | mean | median |")
    w("|---|---:|---:|---:|")
    w(msrow("GS-gssem", G, cfg, inter)); w(msrow("raw", RAW, rawcfg, inter)); w(msrow("LiDAR", RAW, "raw_lidar", inter))
    w("")
    # per-building matrix (union of gssem∪smrf∪raw success)
    allb = sorted(gset | sset | rset)
    w(f"**건물별 매트릭스 (gssem | smrf | raw | LiDAR), {len(allb)}동**")
    w("| bid | gssem | smrf | raw | LiDAR |")
    w("|---|---:|---:|---:|---:|")
    for b in allb:
        w(f"| {b} | {val(G,cfg,b)} | {val(S,cfg,b)} | {val(RAW,rawcfg,b)} | {val(RAW,'raw_lidar',b)} |")

(M / "_matched_rms_partA.md").write_text("\n".join(L) + "\n")
print("\n".join(L))
