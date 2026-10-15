"""PHD-CH6-FACTS64-v1 task 8: wall ground truth of the B0 target building (DEBY_LOD2_4959323), counted from EXISTING records
only (no new GT, no new labels): the stage-1 box GT of B0 (v3, common height alignment) holds per GT point the patch that owns
it (gt_owner_LoD2.npz = gt_clean, the GeoGS example cloud r1_b1_sub002; gt_owner_uls_LoD2.npz = the ULS supplement, single-return
points on vertical surfaces) and the labels of both sources (labels_LoD2.npz, labels_uls_LoD2.npz), written by
scripts/phd/main_stage1_v1/s04_gt_v7.py (lines 332-348; wall rule vertical_points line 107). The evaluation reads the gt_clean
label where it exists, else the ULS label; the exclusion flag follows the label used (labels_of: scripts/phd/main_stage0_v1/
regions_v1.py lines 45-55, scripts/phd/main_stage1_v1/sens_count.py line 25; owners: s1_common.py lines 76-100). (jointbuildgs:dev, CPU)

  python t8_b0_walls.py

Counts for the LoD2 wall patches (loc_kind 2) of the building, in the box range and in the evaluation range: patches, patches
with a gt_clean label, with a ULS label, with either (the label the evaluation used), and the owned GT points of each source.
Writes /out/t8/b0_walls.json and .md. scientific_verdict: null."""
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, "/repo/scripts/phd/ch6_support_v1")
from ch6_common import BOXDEF, DR, OUT, S0, S1, in_eval_rect, jdump, xy_to_uv  # noqa: E402

BOX, BLD = "B0_b10", "DEBY_LOD2_4959323"
O = OUT / "t8"; O.mkdir(parents=True, exist_ok=True)


def main():
    G = S1 / "v3/box_gt" / BOX
    U = np.load(S0 / "s61/box" / BOX / "LoD2" / "units.npz")
    tab = json.loads((DR / "s02_box" / BOX / "lod2_surfaces.json").read_text())["surfaces"]
    bld_of_ext = {r["ext"]: r["building"] for r in tab}
    ext = U["surf_ext"][U["loc_surface"]]
    in_b = np.array([bld_of_ext.get(int(e), "") == BLD for e in ext])
    wall = (U["loc_kind"] == 2) & in_b
    inr = U["loc_in_range"].astype(bool)
    ev = in_eval_rect(xy_to_uv(U["loc_center"][:, :2]), "B0")
    Lg = np.load(G / "labels_LoD2.npz"); Lu = np.load(G / "labels_uls_LoD2.npz")
    lab_g, lab_u = Lg["label"], Lu["label"]
    use_u = (lab_g < 0) & (lab_u >= 0)                                       # labels_of: the ULS label only where gt_clean has none
    ex = Lg["excluded"].astype(bool) | (use_u & Lu["excluded"].astype(bool))
    Og = np.load(G / "gt_owner_LoD2.npz"); Ou = np.load(G / "gt_owner_uls_LoD2.npz")
    n = len(U["loc_kind"])                                                  # index checks: same patch store, no unowned rows
    assert len(lab_g) == n and len(lab_u) == n, "labels and units differ in length"
    assert Og["patch"].min() >= 0 and Ou["patch"].max() < n and Og["patch"].max() < n and Ou["patch"].min() >= 0
    S = json.loads((G / "gt_summary.json").read_text())
    out = dict(building=BLD, box=BOX, source_dir=str(G), gt_primary=S["gt_primary"], vertical_surface_points=S["vertical_surface_points"])
    for name, m in (("box_range", wall & inr), ("evaluation_range", wall & inr & ev)):
        idx = np.nonzero(m)[0]
        sel = np.zeros(len(U["loc_kind"]), bool); sel[idx] = True
        pg = sel[Og["patch"]]; pu = sel[Ou["patch"]]
        used = np.where(lab_g >= 0, 0, np.where(lab_u >= 0, 1, -1))          # the evaluation's choice per patch
        out[name] = dict(
            wall_patches=int(m.sum()), wall_area_m2=round(float(U["loc_area"][m].sum()), 1),
            with_gt_clean_label=int((m & (lab_g >= 0)).sum()), with_uls_label=int((m & (lab_u >= 0)).sum()),
            with_either_label=int((m & ((lab_g >= 0) | (lab_u >= 0))).sum()), with_both_labels=int((m & (lab_g >= 0) & (lab_u >= 0)).sum()),
            label_used_gt_clean=int((m & (used == 0)).sum()), label_used_uls=int((m & (used == 1)).sum()), excluded=int((m & ex).sum()),
            scored_gt_clean=int((m & (used == 0) & ~ex).sum()), scored_uls=int((m & (used == 1) & ~ex).sum()),
            gt_clean_points_on_these_walls=int(pg.sum()), uls_single_return_points_on_these_walls=int(pu.sum()),
            gt_clean_points_on_walls_whose_label_was_used=int((pg & (used[Og["patch"]] == 0)).sum()),
            uls_points_on_walls_whose_label_was_used=int((pu & (used[Ou["patch"]] == 1)).sum()))
    jdump(O / "b0_walls.json", dict(**out, rule=__doc__.split("\n\n")[0], scientific_verdict=None))
    L = ["# B0 대상 건물의 벽 참값 (기존 소유 기록에서 셈)", "", "| 범위 | 벽 패치 | 정리본 라벨 | 드론 LiDAR 라벨 | 평가가 쓴 라벨: 정리본 / 드론 LiDAR | 정리본 점 | 드론 LiDAR 단일 반사 점 |", "|---|---|---|---|---|---|---|"]
    for name, ko in (("box_range", "상자 범위"), ("evaluation_range", "평가 범위")):
        d = out[name]
        L.append(f"| {ko} | {d['wall_patches']:,} ({d['wall_area_m2']:,} m²) | {d['with_gt_clean_label']:,} | {d['with_uls_label']:,} | {d['label_used_gt_clean']:,} / {d['label_used_uls']:,} | {d['gt_clean_points_on_these_walls']:,} | {d['uls_single_return_points_on_these_walls']:,} |")
    (O / "b0_walls.md").write_text("\n".join(L) + "\n")
    print("\n".join(L))


if __name__ == "__main__":
    main()
