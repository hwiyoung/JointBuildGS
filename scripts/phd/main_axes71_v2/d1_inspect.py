"""PHD-MAIN-AXES71-v2 일 1 (정의 확인): list the keys, dtypes and shapes of the files the definition check reads (jointbuildgs:dev, CPU,
read only; run through run_cpu_ax.sh). Output: AX/work/d1/inspect.json. scientific_verdict: null."""
import json
from pathlib import Path

import numpy as np

PH = Path("/ph")
S1 = Path("/out")
S0 = Path("/s0")
FL = PH / "main_fill_v1/PHD-MAIN-FILL-v1"
S3 = PH / "main_stage3_v1/PHD-MAIN-STAGE3-v1"
AX = PH / "main_axes71_v2/PHD-MAIN-AXES71-v2"


def keys(p):
    p = Path(p)
    if not p.exists():
        return "없음"
    z = np.load(p, allow_pickle=False)
    return {k: [str(z[k].dtype), list(z[k].shape)] for k in z.files}


out = {}
for site in ("B0_b10", "B173nb_b10", "R1rep_b10"):
    for prior in ("LoD2", "ALS"):
        out[f"{site}/{prior}/region"] = keys(S1 / "regions_v3" / f"regions_ext_v3_{site}_{prior}.npz")
        out[f"{site}/{prior}/rows"] = keys(S1 / "defs" / site / f"rows_{prior}.npz")
        out[f"{site}/{prior}/obs"] = keys(FL / "work/obs_masked" / f"region_{site}_{prior}.npz")
        out[f"{site}/{prior}/borrow"] = keys(FL / "work/undecidable" / f"borrow_{site}_{prior}.npz")
        out[f"{site}/{prior}/und_regions"] = keys(FL / "work/undecidable" / f"regions_{site}_{prior}.npz")
        out[f"{site}/{prior}/dry_locations"] = keys(S3 / "checks/dry" / f"r14_{site}_{prior}" / "model/monitor/locations.npz")
        out[f"{site}/{prior}/labels"] = keys(S1 / "v3/box_gt" / site / f"labels_{prior}.npz")
        out[f"{site}/{prior}/owner"] = keys(S1 / "v3/box_gt" / site / f"gt_owner_{prior}.npz")
        if site.startswith("B0"):
            out[f"{site}/{prior}/labels_uls"] = keys(S1 / "v3/box_gt" / site / f"labels_uls_{prior}.npz")
            out[f"{site}/{prior}/owner_uls"] = keys(S1 / "v3/box_gt" / site / f"gt_owner_uls_{prior}.npz")
    out[f"{site}/gt_classes"] = keys(S1 / "defs" / site / "gt_classes.npz")
    out[f"{site}/bsurf"] = keys(S1 / "defs" / site / "bsurf.npz")
    out[f"{site}/exclusion_cells"] = keys(S1 / "v3/box_gt" / site / "exclusion_cells.npz")
    out[f"{site}/units_LoD2"] = keys(S0 / "s61/box" / site / "LoD2" / "units.npz")
(AX / "work/d1").mkdir(parents=True, exist_ok=True)
(AX / "work/d1/inspect.json").write_text(json.dumps(out, indent=1, ensure_ascii=False))
print("ok", len(out))
