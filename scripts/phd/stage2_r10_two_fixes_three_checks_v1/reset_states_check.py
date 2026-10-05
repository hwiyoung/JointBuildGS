"""PHD-STAGE2-R10-TWO-FIXES-THREE-CHECKS-v1 (conf-guided image, CPU): exact check of the two reset states a training saved
(fix 'ga'), straight from the files -- the probe's own re-read raises the opacity of the Gaussians it newly protects
(floor_now), so its opacity record is not the reset's.

  python reset_states_check.py <run> [...]      # mounts: /p10 (rw)

Per run and reset iteration: the two states hold the same Gaussians in the same order; position, rotation, scale and
colour are bit-identical; the exempt mask the reset read equals the protection (frozen_mask) of the state; exempt rows keep
their opacity bit for bit; every other row has opacity min(before, 0.01) (the base reset); counts of rows by origin.
Writes /p10/cases/reset_states_check.json."""
import json
import sys
from pathlib import Path

import torch

P10 = Path("/p10")
out = {}
for run in sys.argv[1:]:
    d = P10 / "runs" / run / "model/dump/reset_states"
    for pre_f in sorted(d.glob("reset_*_pre_reset.pt")):
        it = int(pre_f.name.split("_")[1])
        a = torch.load(pre_f, map_location="cpu"); b = torch.load(d / f"reset_{it}_post_reset.pt", map_location="cpu")
        same = {k: bool(torch.equal(a[k], b[k])) for k in ("xyz", "features_dc", "features_rest", "scaling", "rotation", "origin", "init_id", "frozen_mask")}
        ex = a["exempt_mask"]
        oa = torch.sigmoid(a["opacity"].squeeze(-1).double()); ob = torch.sigmoid(b["opacity"].squeeze(-1).double())
        want = torch.minimum(oa, torch.full_like(oa, 0.01))
        rec = dict(iteration=it, n=int(a["xyz"].shape[0]), same=same, exempt_equals_protection=bool(torch.equal(ex, a["frozen_mask"])),
                   n_exempt=int(ex.sum()), n_reset=int((~ex).sum()), n_prior=int((a["origin"] == 1).sum()),
                   n_exempt_prior=int((ex & (a["origin"] == 1)).sum()),
                   exempt_opacity_bit_identical=bool(torch.equal(a["opacity"][ex], b["opacity"][ex])),
                   reset_rows_max_abs_diff_to_min_op_001=float((ob[~ex] - want[~ex]).abs().max()),
                   reset_rows_max_opacity_after=float(ob[~ex].max()), exempt_min_opacity=float(oa[ex].min()) if bool(ex.any()) else None,
                   reset_rows_opacity_before_p50=float(oa[~ex].median()), reset_rows_above_001_before=int((oa[~ex] > 0.01).sum()))
        rec["passed"] = bool(all(same.values()) and rec["exempt_equals_protection"] and rec["exempt_opacity_bit_identical"]
                             and rec["reset_rows_max_abs_diff_to_min_op_001"] < 1e-6)
        out[f"{run}_{it}"] = rec
        print(run, it, json.dumps(rec), flush=True)
(P10 / "cases").mkdir(exist_ok=True)
(P10 / "cases/reset_states_check.json").write_text(json.dumps(out, indent=1))
