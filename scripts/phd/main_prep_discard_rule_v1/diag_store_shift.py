"""PHD-MAIN-PREP-DISCARD-RULE-v1 diagnostic (jointbuildgs:dev, CPU; observation only, nothing changed): the stage-1 code locates
the registered ray hits (prior moved by the registration shift) in the patch store built on the unregistered prior. When the
shift is not zero, a hit is looked up in cells that sit shift away from where the registered surface puts them.
For the runs below this counts, on their saved figure views, the prior pixels whose patch would differ if the hit were moved
back by the shift before the lookup (what a store moved with the prior would give).
  python diag_store_shift.py [run_dir ...]      (default: the eq1 ALS runs with a non-zero shift)
Writes diag/store_shift.json. scientific_verdict: null."""
import json
import sys
from pathlib import Path

import numpy as np

from common import OUT, Views, jdump, log
from src.phd.prior_propagation_v5 import locations as locs
import s03_stage1 as s3


def main():
    runs = [Path(p) for p in sys.argv[1:]] or [OUT / "eq1/s03" / r / "ALS" for r in ("B0", "R3", "R3E", "R4", "R5")]
    V = Views()
    out = {}
    for run in runs:
        summ = json.loads((run / "summary.json").read_text())
        sh = np.asarray(summ["registration"]["shift_applied"], float)
        if not np.any(sh):
            out[str(run)] = dict(shift=sh.tolist(), note="no shift"); continue
        U = locs.load_store(run / "units.npz")
        rid = summ["range"]
        mesh_dir = Path(summ["mesh_dir"]) if "mesh_dir" in summ else OUT / "s02" / rid
        pr = s3.Prior(mesh_dir, "ALS"); pr.shift = sh
        n_tot = n_diff = n_lost = 0
        for f in sorted((run / "figviews").glob("*.npz")):
            z = np.load(f); n = f.stem
            loc = z["loc"].reshape(-1); t = z["prior_depth"].reshape(-1)
            ok = loc >= 0
            Dr = V.rays(n).reshape(-1, 3).astype(np.float64); C = V.C(n)
            X = C[None, :] + t[ok, None] * Dr[ok]
            ci = U["loc_surface"][loc[ok]]
            back = locs.locate(U, ci, X - sh)
            n_tot += int(ok.sum()); n_diff += int((back != loc[ok]).sum()); n_lost += int((back < 0).sum())
        out[str(run)] = dict(range=rid, shift=sh.tolist(), prior_pixels=n_tot, other_patch=n_diff, share=round(n_diff / max(n_tot, 1), 4),
                             no_patch_after_moving_back=n_lost)
        log(rid, sh, n_tot, n_diff)
    jdump(OUT / "diag/store_shift.json", dict(rule=__doc__.split("\n\n")[0], runs=out, scientific_verdict=None))


if __name__ == "__main__":
    main()
