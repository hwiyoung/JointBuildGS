#!/usr/bin/env python3
"""gen-8way Step2 — aggregate per-arm eval jsons x mechanism buckets into the 8-way generation table +
write W_generation_8way.md. NO retrain. Observe only; verdict=김휘영.
Reads d12_buckets.csv + results/.../mob/eval_gen8_*.json (per arm, written by run_overnight.sh).
A building "GENERATES a model" for an arm iff roofer_ok AND roof_surfaces>0 (tag orig). val3dity tracked.
"""
import csv, glob, json
from collections import defaultdict
from pathlib import Path
REPO = Path("/workspace/JointBuildGS")
MOB = REPO / "results/tum_transfer/mob"
LEV = MOB / "overseg_lever"
ARMS = ["gs_seed_sparse", "gs_seed_dense", "gs_seed_acmp", "raw_sparse", "raw_dense", "raw_acmp", "raw_lidar"]
BUCK = {"1_textureless": "① textureless", "2_assembly": "② assembly(missing_lod22)",
        "3_coverage": "③ coverage(near-nadir gap)", "4_impossible": "④ impossible/other"}


def main():
    buckets = {r["bid"]: r for r in csv.DictReader(open(LEV / "d12_buckets.csv"))}
    # gen[arm][bid] = (model_bool, val3dity_bool)
    gen = defaultdict(dict)
    for fp in glob.glob(str(MOB / "eval_gen8_*.json")):
        for r in json.load(open(fp)):
            if r.get("tag") != "orig":
                continue
            cfg = r.get("config"); bid = str(r["bid"]).replace("DEBY_LOD2_", "")
            model = bool(r.get("roofer_ok") and (r.get("roof_surfaces") or 0) > 0)
            val = bool(r.get("val3dity_valid")) if r.get("val3dity_valid") is not None else False
            gen[cfg][bid] = (model, val)

    # count table per bucket x arm
    lines = ["# W_generation_8way — 생성 8-way (실패 모집단, 버킷별; 재학습 없음·기존 arm 평가, 판정 금지)",
             "",
             "> **실험 2 / Phase B.** 브랜치 `feat/p2-structure-learn`. EPSG:25832. Docker. **재학습/재구성 없음** — 기존 gs_seed_{sparse,dense,acmp} ckpt + raw_{sparse,dense,acmp,lidar} npz를 P0 실패 모집단(64)에 평가 확대. 동일 Roofer 전역설정. 관찰만, 판정 = 김휘영. 무인 런(작업 B).",
             "> 모델 생성 = roofer_ok AND roof_surfaces>0(orig). 재현 `run_overnight.sh`(Task B)·`d12_buckets.py`·`gen_8way_aggregate.py`. CSV `overseg_lever/gen_8way.csv`.",
             "",
             "## §1 버킷별 8-way 생성 카운트 (모델 y / val3dity 유효 y / 버킷 n)", ""]
    bybuck = defaultdict(list)
    for bid, b in buckets.items():
        bybuck[b["bucket"]].append(bid)
    # header
    hdr = "| bucket (n) | " + " | ".join(a.replace("gs_seed_", "GS-").replace("raw_", "raw-") for a in ARMS) + " |"
    sep = "|" + "---|" * (len(ARMS) + 1)
    lines += [hdr, sep]
    rowcsv = []
    for bk in ("1_textureless", "2_assembly", "3_coverage", "4_impossible"):
        bids = bybuck.get(bk, [])
        cells = []
        for a in ARMS:
            mdl = sum(1 for bid in bids if gen.get(a, {}).get(bid, (False, False))[0])
            val = sum(1 for bid in bids if gen.get(a, {}).get(bid, (False, False))[1])
            cells.append(f"{mdl}/{val}")
        lines.append(f"| {BUCK[bk]} ({len(bids)}) | " + " | ".join(cells) + " |")
        for bid in bids:
            rowcsv.append({"bid": bid, "bucket": bk, **{a: int(gen.get(a, {}).get(bid, (False, False))[0]) for a in ARMS},
                           **{a + "_val": int(gen.get(a, {}).get(bid, (False, False))[1]) for a in ARMS}})
    # totals
    tot = []
    for a in ARMS:
        mdl = sum(1 for bid in buckets if gen.get(a, {}).get(bid, (False, False))[0])
        tot.append(str(mdl))
    lines += [f"| **TOTAL model-y ({len(buckets)})** | " + " | ".join(tot) + " |", ""]
    with open(LEV / "gen_8way.csv", "w", newline="") as f:
        if rowcsv:
            w = csv.DictWriter(f, fieldnames=list(rowcsv[0].keys())); w.writeheader(); w.writerows(rowcsv)

    # narrative
    def total(a): return sum(1 for bid in buckets if gen.get(a, {}).get(bid, (False, False))[0])
    asm = bybuck.get("2_assembly", []); tex = bybuck.get("1_textureless", [])
    def cnt(a, bids): return sum(1 for bid in bids if gen.get(a, {}).get(bid, (False, False))[0])
    lines += ["## §2 버킷별 서사 (판정 금지)", "",
        f"- **② 조립({len(asm)})** [방법-관련, dense 점 有]: GS-dense {cnt('gs_seed_dense',asm)}/{len(asm)}·GS-acmp {cnt('gs_seed_acmp',asm)}·GS-sparse {cnt('gs_seed_sparse',asm)} vs raw-dense {cnt('raw_dense',asm)}·raw-acmp {cnt('raw_acmp',asm)}·LiDAR {cnt('raw_lidar',asm)}. → GS가 raw-MVS 0면 실패를 {'회복' if cnt('gs_seed_dense',asm)>cnt('raw_dense',asm) else '미회복'}(공동최적화 조립).",
        f"- **① 무텍스처({len(tex)})** [방법-관련, dense=0]: GS-sparse {cnt('gs_seed_sparse',tex)}/{len(tex)}·GS-acmp {cnt('gs_seed_acmp',tex)} vs raw {cnt('raw_sparse',tex)}·LiDAR {cnt('raw_lidar',tex)}. → 씨앗 점 부재로 GS {'일부 생성' if cnt('gs_seed_sparse',tex)+cnt('gs_seed_acmp',tex)>0 else '미생성'}(생성됨≠충실, D6 슬랩).",
        f"- **③ 커버리지({len(bybuck.get('3_coverage',[]))})** [취득 한계, 방법 기여 아님]: baseline+LiDAR만. LiDAR {cnt('raw_lidar',bybuck.get('3_coverage',[]))}/{len(bybuck.get('3_coverage',[]))} = near-nadir 취득 결손은 영상계열 공통(재촬영 필요).",
        f"- **④ 불가/기타({len(bybuck.get('4_impossible',[]))})**: 신호 부재.",
        "",
        f"**상한/대비**: LiDAR(raw_lidar) {total('raw_lidar')}/{len(buckets)} = 점군-가용 상한; raw-ACMP {total('raw_acmp')}·raw-dense {total('raw_dense')} = MVS baseline; GS-dense {total('gs_seed_dense')}·GS-acmp {total('gs_seed_acmp')}·GS-sparse {total('gs_seed_sparse')} = 공동최적화. (val3dity 유효는 표 우측값.)",
        "",
        "## §3 종합 (판정 금지)",
        "관측: 방법-관련 버킷(①②)서 GS 공동최적화의 생성 회복을 baseline 대비 카운트. ③ 커버리지는 취득 한계(방법 무관), ④ 불가. **생성됨 ≠ 충실**(무텍스처=저편향 슬랩[D6], 조립=위상 회복이나 표면 미달[assembly-fidelity]). 버킷별 대표 정성은 `docs/figs/`(가용 시). 커밋 `gen-8way-fail`.",
        "",
        "> 재현: `run_overnight.sh` Task B(버킷 라벨→arm별 chunked extract+eval→집계). 데이터 재사용·재학습 없음."]
    (REPO / "docs/W_generation_8way.md").write_text("\n".join(lines))
    print("[gen-8way] arms with data:", [a for a in ARMS if a in gen])
    print("[gen-8way] totals model-y:", {a: total(a) for a in ARMS})
    print(f"[done] -> docs/W_generation_8way.md + {LEV}/gen_8way.csv")


if __name__ == "__main__":
    main()
