"""PHD-MAIN-JUDGEABL-v1 5절 검산: 세 실험 지역 상자에서 이 구현으로 다시 낸 최종 변화 칸과 구분이
  (가) BASELINES-v1 저장 칸(detect/cells.npz final)과 칸으로 같은지, (나) JUDGEAPPLY 저장 구분(decisions region[4])과 넓이로 같은지.
JA 구분은 지역 파일 패치(regions_v3, source_index)의 중심 칸으로 냈으므로 같은 중심으로, 그리고 JA decisions 의 centre 로도 다시 낸다.
  python fa_check.py  -> /res/check/check.json. 참값 읽지 않음. scientific_verdict: null."""
import json
from pathlib import Path

import numpy as np

import fa_common as FC
from fa_common import M

rows = []
for site, s in FC.SITES.items():
    if s["kind"] != "box_check":
        continue
    for prior in ("LoD2", "ALS"):
        mine = np.load(FC.RES / "sites" / site / prior / "cells.npz")
        ref = np.load(s["compare_cells"].format(prior=prior))
        same_grid = bool(np.allclose(mine["lo"], ref["lo"]) and int(mine["nx"]) == int(ref["nx"]) and int(mine["ny"]) == int(ref["ny"]))
        f, g = mine["final_25"], ref["final"]
        r = dict(site=site, prior=prior, same_grid=same_grid, cells_mine=int(f.sum()), cells_stored=int(g.sum()),
                 cells_equal_share=float((f == g).mean()), cells_disagree=int((f != g).sum()),
                 vote_disagree=int((mine["vote"] != ref["vote"]).sum()), removal_disagree=int((mine["removal"] != ref["removal"]).sum()),
                 grown_disagree=int((mine["grown"] != ref["grown"]).sum()), nsee_equal_share=float((mine["nsee"] == ref["nsee"]).mean()),
                 dz_med_max_abs_m=float(np.nanmax(np.abs(mine["dz_med"] - ref["dz_med"]))) if np.isfinite(mine["dz_med"]).any() else None)
        dec = np.load(s["compare_decisions"].format(prior=prior), allow_pickle=True)
        Rg = np.load(s["compare_regions"].format(prior=prior), allow_pickle=True)
        grid = M.Grid(site)
        ii = dec["source_index"]; area = dec["area"].astype(float); ja = dec["region"][4]
        for name, xy in (("regions_v3_centre", Rg["centre"][ii]), ("decisions_centre", dec["centre"])):
            c = grid.cell(xy); inch = np.zeros(len(c), bool); inch[c >= 0] = f.ravel()[c[c >= 0]]
            reg = np.where(inch, 2, 1)
            r[f"region4_equal_area_share_{name}"] = float(area[reg == ja].sum() / area.sum())
            r[f"region4_equal_count_{name}"] = f"{int((reg == ja).sum())}/{len(ja)}"
        r["ja_image_area_m2"] = float(area[ja == 2].sum()); r["ja_prior_area_m2"] = float(area[ja == 1].sum())
        rows.append(r)
        print(json.dumps(r, ensure_ascii=False), flush=True)
ok = all(r["region4_equal_area_share_regions_v3_centre"] > 0.99 for r in rows)
FC.jdump(FC.RES / "check/check.json", dict(at=FC.now(), rows=rows, rule=FC.C["check_rule"], passed_99=ok, GT_read=False, scientific_verdict=None))
print("CHECK", "PASS" if ok else "NOT_PASS")
