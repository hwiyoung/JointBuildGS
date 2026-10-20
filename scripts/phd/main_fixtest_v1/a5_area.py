"""PHD-MAIN-FIXTEST-v1 10 (판단을 돕는 읽기, 판 A의 A5 손해의 넓이; jointbuildgs:dev, CPU; run_step_ft.sh): for the narrowed 항공 LiDAR case
(B0 항공 LiDAR, reading T), the code-11 patches whose GT rows fall in the misfit bins of the recall curve (|gt_med| / tau: 1~1.5, 1.5~2 and
the merged group 1~4): rows, patches and their area (the regions file 'area'). Rows = the dist71 rows of place c11 (dist npz r_place, r_ratio,
r_patch) of the method's seed 0, as curve_ft.py.
  python a5_area.py
Writes FT/tables/a5_area.json and prints it. scientific_verdict: null."""
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, "/repo/scripts/phd/main_dist71_v1")
sys.path.insert(0, "/repo/scripts/phd/main_stage1_v1")
import dm_common as DC  # noqa: E402

FTP = DC.PH / "main_fixtest_v1/PHD-MAIN-FIXTEST-v1"
BIT_C11 = 1 << DC.PLACES[1:].index("c11")
out = {}
for site, prior in (("B0_b10", "ALS"),):
    z = np.load(DC.PH / "main_dist71_v1/PHD-MAIN-DIST71-v1/dist" / f"{site}_{prior}__prop_{prior}_s0.npz")
    R = np.load(DC.S1 / "regions_v3" / f"regions_ext_v3_{site}_{prior}.npz")
    m = (z["r_place"] & BIT_C11) > 0
    ratio, pa = z["r_ratio"][m].astype(np.float64), z["r_patch"][m].astype(np.int64)
    e = {}
    for lo, hi in ((1.0, 1.5), (1.5, 2.0), (1.0, 4.0)):
        s = (ratio >= lo) & (ratio < hi)
        u = np.unique(pa[s])
        e[f"{lo:g}~{hi:g}"] = dict(rows=int(s.sum()), patches=int(len(u)), area_m2=float(R["area"][u].sum()))
    e["code2_all"] = dict(rows=int(((z["r_place"] & (1 << DC.PLACES[1:].index("c2"))) > 0).sum()))
    out[f"{site}/{prior}"] = e
(FTP / "tables/a5_area.json").write_text(json.dumps(dict(task="PHD-MAIN-FIXTEST-v1", data=out, scientific_verdict=None), indent=1))
print(json.dumps(out, indent=1))
