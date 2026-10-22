"""PHD-MAIN-AXES71-v2 일 1 덧붙임 (jointbuildgs:dev, CPU, read only): (1) the fixtest fix-B rewrite (own_depth_changed) of patches in the
evaluation range by region code; (2) the overlaps of the filtered image error (obs_masked) with the code-2 and premise-violation patches,
which order 5.1 puts in other cells, with their thinned GT rows, next to the distance task's '영상이 틀린 곳' (dm_common.py:180).
Output AX/work/d1/extra.json. scientific_verdict: null."""
import json
from pathlib import Path

import numpy as np

S1 = Path("/out")
FT = Path("/ph/main_fixtest_v1/PHD-MAIN-FIXTEST-v1")
FL = Path("/ph/main_fill_v1/PHD-MAIN-FILL-v1")
AX = Path("/ph/main_axes71_v2/PHD-MAIN-AXES71-v2")
out = {}
for site in ("B0_b10", "B173nb_b10", "R1rep_b10"):
    for prior in ("LoD2", "ALS"):
        R = np.load(S1 / "regions_v3" / f"regions_ext_v3_{site}_{prior}.npz")
        z = np.load(FT / "runs" / site / f"fixB_{prior}_s0" / "model/monitor/locations.npz")
        ch = z["own_depth_changed"].astype(bool)
        ie = R["in_eval"].astype(bool)
        c = R["code_ext_v3"].astype(np.int64)
        area = R["area"].astype(np.float64)
        Z = np.load(FL / "work/obs_masked" / f"region_{site}_{prior}.npz")
        obs = Z["obs"].astype(bool)
        viol = R["premise_violation"].astype(bool)
        within = R["obs_within_threshold"].astype(bool)
        r = np.load(S1 / "defs" / site / f"rows_{prior}.npz")
        pa, th = r["patch"].astype(np.int64), r["thin"].astype(bool)
        nth = np.bincount(pa[th], minlength=len(c))
        img71 = (obs & ~(ie & viol)) | (ie & within)          # dm_common.py:180
        sets = {"img_dist71": img71, "obs_or_within": ie & (obs | within), "obs_and_violation": ie & obs & viol,
                "obs_and_code2": ie & obs & (c == 2), "obs_and_code4": ie & obs & (c == 4), "within_not_obs": ie & within & ~obs,
                "violation_not_obs": ie & viol & ~obs}
        out[f"{site}/{prior}"] = dict(
            fixB_changed_in_eval_by_code={str(k): int((ch & ie & (c == k)).sum()) for k in np.unique(c[ch & ie])},
            fixB_changed_outside_eval=int((ch & ~ie).sum()),
            sets={k: dict(patches=int(m.sum()), area_m2=float(area[m].sum()), thinned_rows=int(nth[m].sum())) for k, m in sets.items()})
(AX / "work/d1/extra.json").write_text(json.dumps(out, indent=1))
print(json.dumps({k: {s: (v["patches"], round(v["area_m2"], 2), v["thinned_rows"]) for s, v in e["sets"].items()} for k, e in out.items()}))
