"""PHD-MAIN-B0REF-v1 일 5 2번: the B0 ground-truth points the evaluation used, by source (GeoGS cloud = primary, ULS supplement), per
place of the new distance metric (PHD-MAIN-DIST71-v1) and per kind (roof-like / wall-like). Read-only use of that task's definitions
(scripts/phd/main_dist71_v1/dm_common.py Unit: thinned region rows r_src 0 = ULS, 1 = primary; places of 2.2). (jointbuildgs:dev, CPU)

  python s5_gtsrc.py   (run with run_cpu_dm_ro.sh: the DIST71 mounts, all read-only, plus /b0 and /docs)
  -> /docs/tables/t5_gt_sources.md|json
Also the precision reference of the B0 places (DM/dist/done_b0gt.json: ULS building-surface points + primary points in the cells) and
the scene F1 reference (ULS only). [이 요청에서 냄; 행 수는 DIST71 정의를 그대로 셈] scientific_verdict: null."""
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, "/repo/scripts/phd/main_dist71_v1")
sys.path.insert(0, "/repo/scripts/phd/main_stage1_v1")
sys.path.insert(0, "/repo/scripts/phd/main_stage0_v1")
sys.path.insert(0, "/repo")
import dm_common as DC  # noqa: E402

OUT = Path("/docs/tables")


def main():
    gt = DC.SiteGT("B0_b10")
    res = {}
    for prior in ("LoD2", "ALS"):
        U = DC.Unit("B0_b10", prior, gt)
        rows = {}
        for key in DC.PLACES:
            m = U.rows_place(key)
            r = {}
            for kname, kv in (("roof", 1), ("wall", 2)):
                mk = m & (U.r_kind == kv)
                r[kname] = dict(primary=int((mk & (U.r_src == 1)).sum()), uls=int((mk & (U.r_src == 0)).sum()))
            r["patches_in_place"] = int(U.place_patch[key].sum()) if key != "all" else int(U.n_patch)
            rows[key] = r
        res[prior] = rows
    done = json.loads((DC.DM / "dist/done_b0gt.json").read_text())
    rec = dict(rows=res, place_names=DC.PLACE_KO, precision_reference_b0_places=done["gt_points"],
               scene_f1_reference="ULS building-surface points only (uls_scene)", rows_rule="thinned region rows (dm_common.Unit rows_idx = rows_<prior>.npz thin)",
               scientific_verdict=None)
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "t5_gt_sources.json").write_text(json.dumps(rec, indent=1, ensure_ascii=False))
    L = ["# 표 5. 평가에 쓴 B0 참값 점의 출처: 거리 지표 작업(DIST71)의 곳마다 [DIST71 정의로 셈, 이 요청에서 냄]", "",
         "- 행 = DIST71이 곳의 재현율에 쓴 솎은 참값 행(`S1/defs/B0_b10/rows_<사전 정보>.npz`의 thin). 출처: 주 참값 = GeoGS 점군, 드론 LiDAR = 주 참값에 라벨이 없는 패치를 채운 연직 비행 드론 LiDAR 점.",
         "- '전체'는 장면 F1이 아니라 영역 행 전체다. 장면 F1(DIST71의 '전체')의 참값은 드론 LiDAR 점(건물 표면 칸)만이다.", "",
         "| 사전 정보 | 곳 | 지붕류: 주 참값 | 지붕류: 드론 LiDAR | 벽류: 주 참값 | 벽류: 드론 LiDAR | 주 참값의 몫 |", "|---|---|---:|---:|---:|---:|---:|"]
    for prior, rows in res.items():
        for key, r in rows.items():
            tot = r["roof"]["primary"] + r["roof"]["uls"] + r["wall"]["primary"] + r["wall"]["uls"]
            sh = (r["roof"]["primary"] + r["wall"]["primary"]) / tot if tot else float("nan")
            L.append(f"| {DC.PRIOR_KO[prior]} | {DC.PLACE_KO[key]} | {r['roof']['primary']:,} | {r['roof']['uls']:,} | {r['wall']['primary']:,} | {r['wall']['uls']:,} | {sh*100:.1f} % |")
    g = done["gt_points"]
    L += ["", f"- B0 곳의 정밀도 참값(DIST71 `d2b_b0gt.py`, `DM/dist/done_b0gt.json`): 드론 LiDAR 건물 표면 칸의 점 {g['uls_scene']:,} + 칸 안의 주 참값 점 {g['primary_in_cells']:,}. 점마다 출처가 있다(두 배열을 쌓음).",
          f"- 장면 F1의 참값: 드론 LiDAR 건물 표면 칸의 점 {g['uls_scene']:,}(주 참값 없음)."]
    (OUT / "t5_gt_sources.md").write_text("\n".join(L) + "\n")
    print("\n".join(L))


if __name__ == "__main__":
    main()
