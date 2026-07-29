#!/usr/bin/env python3
"""P2-D5 PART 2 — §5 cp 판정표 (D5a/b/c vs D4, 전부 gssem; smrf 병기). 관찰만·판정 금지.
Reads gssem+smrf number snapshots (gssem_requal_numbers.py output):
  D5: gssem_requal_backup/numbers_d5_{gssem,smrf}.json   (PART 2)
  D4: gssem_requal_backup/numbers_{gssem,smrf}.json       (PART 1, key gs_d4_*)
Measurements (사전등록 §5): 복합 42364663·42364659 과분할 면수 · 곡면 4906969(목표 LiDAR 5) 면수+RMS(과-평탄 watch)
  · RMS→ref(mean) · valid-solid/8 · 생성 assembled/8.  Cells = gssem (smrf 괄호).
LiDAR/ref reference from baselines.json + ref_rms_raw.csv + raw_lidar roofer cityjson.
Writes the §5 result section into docs/experiments/w_d5/reports/W_D5.md (replaces the '§2~ 대기' placeholder; keeps §0/§1).
"""
import csv, glob, json
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
M = REPO / "results/tum_transfer/mob"
A = REPO / "results/tum_transfer/mob_analysis"
EVALROOT = REPO / "phases/p0-audit/runs/mob_eval"
BK = M / "gssem_requal_backup"
COMPOSITE = ["42364663", "42364659"]
CURVED = "4906969"

# cp ladder: (label, gssem-numbers-file, smrf-numbers-file, dense cfg, acmp cfg)
LAD = [
    ("D5a (cp OFF)",   "numbers_d5_gssem.json", "numbers_d5_smrf.json", "gs_d5a_dense", "gs_d5a_acmp"),
    ("D4  (cp FAIR)",  "numbers_gssem.json",    "numbers_smrf.json",    "gs_d4_dense",  "gs_d4_acmp"),
    ("D5c (cp EARLY)", "numbers_d5_gssem.json", "numbers_d5_smrf.json", "gs_d5c_dense", "gs_d5c_acmp"),
    ("D5b (cp HARD)",  "numbers_d5_gssem.json", "numbers_d5_smrf.json", "gs_d5b_dense", "gs_d5b_acmp"),
]


def load(fn):
    p = BK / fn
    return json.loads(p.read_text())["arms"] if p.exists() else {}


def lidar_facet(bid):
    full = f"DEBY_LOD2_{bid}"
    g = glob.glob(str(EVALROOT / "raw_lidar" / f"roofer_{full}_orig" / "*.city.jsonl"))
    if not g:
        return None
    n = 0
    for ln in open(g[0]):
        if not ln.strip():
            continue
        for cid, o in json.loads(ln).get("CityObjects", {}).items():
            if cid == full or cid.startswith(full + "-"):
                for ge in o.get("geometry", []):
                    for s in ge.get("semantics", {}).get("surfaces", []):
                        if s.get("type") == "RoofSurface":
                            n += 1
    return n


def lidar_rms():
    out = {}
    p = A / "ref_rms_raw.csv"
    if p.exists():
        for r in csv.DictReader(open(p)):
            if r["config"] == "raw_lidar" and r.get("tag", "orig") == "orig":
                try:
                    out[r["bid"].split("_")[-1]] = float(r["rms_to_ref_m"])
                except (TypeError, ValueError):
                    pass
    return out


def cell(g, s, key, sub=None, fmt="{}"):
    def get(d):
        if not d:
            return None
        v = d.get(key) if sub is None else (d.get(key, {}) or {}).get(sub)
        return v
    gv, sv = get(g), get(s)
    def f(v):
        return fmt.format(v) if isinstance(v, (int, float)) else ("-" if v is None else str(v))
    return f"{f(gv)} ({f(sv)})"


def main():
    base = json.loads((M / "baselines.json").read_text())
    LR = lidar_rms()
    rows = []
    L = []
    def w(s=""):
        L.append(s)

    w("## §2~ 본런 결과 — cp ablation (gssem 정본 read-out; smrf 괄호 병기). 관찰만·판정 금지.")
    w("")
    w("> 측정 = **target-only 면수**(gssem 재평가 후 디스크) · RMS→ref(gssem .las) · valid-solid/assembled(eval_d5_gssem.json) · smrf 병기(괄호).")
    w("> 사전등록 §5 측정항: 복합{42364663,42364659} 과분할 · 곡면 4906969(목표 LiDAR 5, 과-평탄 watch) · RMS→ref · valid-solid · 생성 7/8.")
    w("> 출처: D5=`numbers_d5_{gssem,smrf}.json` · D4=`numbers_{gssem,smrf}.json` (gssem_requal_numbers.py) · LiDAR/ref=baselines+ref_rms_raw+raw_lidar cityjson.")
    w("")
    w("### §5 cp 판정표 — cp 끔/공정/일찍/세게 × dense·acmp  (값 = gssem (smrf))")
    w("| arm | dens | 생성/8 | valid-solid/8 | RMS→ref mean | 곡면4906969 면수 | 곡면4906969 RMS | 복합42364663 | 복합42364659 |")
    w("|---|---|---:|---:|---:|---:|---:|---:|---:|")
    for label, gfn, sfn, cd, ca in LAD:
        G = load(gfn); S = load(sfn)
        for dens, cfg in [("dense", cd), ("acmp", ca)]:
            g = G.get(cfg); s = S.get(cfg)
            asm = cell(g, s, "assembled_REC", fmt="{}")
            vs = cell(g, s, "valid_solid_REC", fmt="{}")
            rm = cell(g, s, "rms_mean", fmt="{:.2f}")
            cf = cell(g and g.get("facets_target_only"), s and s.get("facets_target_only"), CURVED, fmt="{}")
            cr = cell(g and g.get("rms_focus"), s and s.get("rms_focus"), CURVED, fmt="{:.2f}")
            f1 = cell(g and g.get("facets_target_only"), s and s.get("facets_target_only"), "42364663", fmt="{}")
            f2 = cell(g and g.get("facets_target_only"), s and s.get("facets_target_only"), "42364659", fmt="{}")
            w(f"| {label} | {dens} | {asm} | {vs} | {rm} | {cf} | {cr} | {f1} | {f2} |")
    # reference / ceiling row
    refc = base[f"DEBY_LOD2_{CURVED}"]["ref_roof_surfaces"]
    ref1 = base["DEBY_LOD2_42364663"]["ref_roof_surfaces"]; ref2 = base["DEBY_LOD2_42364659"]["ref_roof_surfaces"]
    w(f"| ref (GT) | - | - | - | - | {refc} | - | {ref1} | {ref2} |")
    w(f"| LiDAR (상한) | - | 7 | 7 | {LR.get('mean','-')} | {lidar_facet(CURVED)} | {LR.get(CURVED,'-'):.2f} | {lidar_facet('42364663')} | {lidar_facet('42364659')} |"
      if CURVED in LR else
      f"| LiDAR (상한) | - | 7 | 7 | - | {lidar_facet(CURVED)} | - | {lidar_facet('42364663')} | {lidar_facet('42364659')} |")
    w("")
    w("측정 기준: 면수=target-only(이웃 제외) · RMS→ref=GS 지붕점→ref 평면(1-DOF dz 정렬) · valid-solid/assembled=REC 8동.")
    w("곡면 4906969 과-평탄 watch = 면수 급감(→1) 또는 RMS 급증 시 과병합 신호(관찰만, 판정=사람).")
    w("복합 42364663·42364659 = 다지붕 과분할(cp가 정리하는지 관찰).")
    w("")
    w("### 건물별 target-only 면수 (gssem; 11동, cp 사다리)")
    bids = ["42364663", "42364659", "4906969", "4906972", "4907182", "4908023", "4907510", "42364609", "4908050", "4908166", "4908176"]
    w("| bid | ref | " + " | ".join(f"{lab.split()[0]}.{d[0]}" for lab, _, _, _, _ in LAD for d in ["dense", "acmp"]) + " | LiD |")
    w("|---|---:|" + "---:|" * (len(LAD) * 2 + 1))
    for b in bids:
        ref = base[f"DEBY_LOD2_{b}"]["ref_roof_surfaces"]
        cells = []
        for label, gfn, _, cd, ca in LAD:
            G = load(gfn)
            for cfg in [cd, ca]:
                v = (G.get(cfg, {}).get("facets_target_only", {}) or {}).get(b)
                cells.append("-" if v is None else str(v))
        cells.append(str(lidar_facet(b)))
        w(f"| {b} | {ref} | " + " | ".join(cells) + " |")
    w("")
    w("(생성 assembled/8 ≥7 유지 여부 = §5 'B 생성', valid-solid = 위상, RMS·과-평탄 = 품질. 판정=김휘영.)")

    # merge into W_D5.md (keep everything before '## §2~', append results)
    doc = M.parent.parent / "docs/experiments/w_d5/reports/W_D5.md"   # results/tum_transfer/.. -> repo? fix below
    doc = REPO / "docs/experiments/w_d5/reports/W_D5.md"
    body = "\n".join(L) + "\n"
    if doc.exists():
        txt = doc.read_text()
        idx = txt.find("## §2~")
        head = txt[:idx] if idx != -1 else txt + "\n"
        doc.write_text(head.rstrip() + "\n\n" + body)
    else:
        doc.write_text(body)
    (M / "_d5_cp_table.md").write_text(body)
    print(body)
    print(f"[done] -> {doc}")


if __name__ == "__main__":
    main()
